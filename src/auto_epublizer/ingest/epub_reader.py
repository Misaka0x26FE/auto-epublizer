"""EPUB 读取器：按 OPF spine 切分单元，内联非线性 spine 项，清洗 pandoc 残留。

背景（真书 dogfooding 发现，见 lessons/2026-09-11-epub-nonlinear-spine-tables.md）：

- pandoc 只读线性 spine 项，``linear="no"`` 的表格/图表文件被跳过，正文只剩链接；
- pandoc 会把 ``<a id>`` 转成 ``[]{#id}`` 锚点、把 ``<small>`` 转成 ``[...]{.small}``，
  污染标题，直接进 EPUB 章节标题与目录；
- 按 ATX 标题切分时，无 ``<h1>`` 的 spine 项（版权页等）正文被并入前一个标题单元。

本模块改为 **按 OPF spine 切分**：pandoc 对每个线性 spine 项恰好输出一行独立锚点
``[]{#<href basename>.xhtml}``（实测稳定），以它为边界即得「一项一单元」；非线性
spine 项单独转 Markdown 后在正文引用处内联。语义判断仍全由 agent 完成（唯一 LLM 原则）。
"""

from __future__ import annotations

import posixpath
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from .models import KIND_HEADING, KIND_TEXT, SourceDocument, SourceSegment, SourceUnit
from .pandoc_reader import PandocError, pandoc_available, parse_markdown_units, run_pandoc

_DC = "http://purl.org/dc/elements/1.1/"
_XHTML_TYPES = {"application/xhtml+xml", "text/html"}
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_ANCHOR_LINE_RE = re.compile(r"^\[\]\{(#[^}]*)\}$")
# spine 边界文件锚点：独立成行的 ``[]{#xx.xhtml}``（id 整体是文件名、无 #fragment）
# 已由 _strip_anchor_lines 删除，这里兜底行内残留。带 fragment 的正文锚点
# ``[]{#ch02.html#page_21}`` 必须保留（id 内含第二个 #），用 [^}#] 排除 fragment，
# 其文件前缀在 structure/links.py 按 spine 映射重写为纯锚点。
_SPINE_FILE_ANCHOR_RE = re.compile(r"\[\]\{#[^}#]*\.(?:x?html)[^}#]*\}")
_ATTR_ONLY_RE = re.compile(r"\{\.[^}]*\}")  # 裸类属性 {.class}（{#id} 锚点保留）
_SPAN_CLASS_RE = re.compile(r"\[([^\[\]]*)\]\{\.[^}]*\}")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)

# 顶层 div class → 可读标题（无 nav/标题时的兜底，如 dedication）
_CLASS_TITLES = {
    "cover": "Cover",
    "titlepage": "Title Page",
    "copyright": "Copyright",
    "dedication": "Dedication",
    "foreword": "Foreword",
    "preface": "Preface",
    "toc": "Contents",
    "chapter": "Chapter",
    "glossary": "Glossary",
    "bibliography": "Bibliography",
    "index": "Index",
}


class EpubError(RuntimeError):
    """EPUB 结构无法解析（交由调用方回退到 pandoc 通用路径）。"""


@dataclass
class SpineItem:
    """一个 spine 项（线性 = 正文阅读顺序；非线性 = 表格/图表等附属内容）。"""

    id: str
    href: str  # 相对 OPF 目录、已规范化的 POSIX 路径
    zip_path: str  # zip 内完整路径
    media_type: str
    linear: bool


@dataclass
class EpubPackage:
    opf_dir: str
    spine: list[SpineItem] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    href_labels: dict[str, str] = field(default_factory=dict)  # href → nav/NCX 标题

    @property
    def linear(self) -> list[SpineItem]:
        return [i for i in self.spine if i.linear]

    @property
    def nonlinear(self) -> list[SpineItem]:
        return [i for i in self.spine if not i.linear]


def clean_pandoc_residue(text: str) -> str:
    """清理 pandoc 转出的行内残留（确定性纯函数）。

    - 删除指向文件的 spine 边界锚点 ``[]{#xx.xhtml}``（独立成行的已由
      ``_strip_anchor_lines`` 删除，这里兜底行内残留）；
    - **保留正文导航锚点** ``[]{#page_15}`` / ``[]{#ch01}``（源 XHTML 的
      ``<a id>``，是索引/目录跳转目标，删除会让成品内部链接全部失效）；
    - 删除 ``[text]{.class}`` 的类属性（保留文本）与裸类属性 ``{.class}``
      （``{#id}`` 标题锚点保留）；``<br>`` 变体转空格。
    - **不改动行首空白**（避免破坏网格表格缩进），仅去行尾空白。
    """
    if not text:
        return text
    text = _SPINE_FILE_ANCHOR_RE.sub("", text)
    text = _SPAN_CLASS_RE.sub(r"\1", text)
    text = _ATTR_ONLY_RE.sub("", text)
    text = _BR_RE.sub(" ", text)
    return text.rstrip()


def _clean_heading(text: str) -> str:
    """标题清洗：在行内清洗基础上折叠空白为单行。"""
    return re.sub(r"\s+", " ", clean_pandoc_residue(text)).strip()


def _resolve_href(opf_dir: str, href: str) -> str:
    """把 OPF href 规范化为相对 OPF 目录的 POSIX 路径（去 fragment/URL 解码）。"""
    href = unquote(href.split("#", 1)[0]).strip()
    if not href or "://" in href:
        return ""
    joined = posixpath.join(opf_dir, href) if opf_dir else href
    return posixpath.normpath(joined)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iter_nav_titles(
    zf: zipfile.ZipFile, names: list[str], opf: ET.Element, opf_dir: str
) -> dict[str, str]:
    """从 EPUB3 nav 或 EPUB2 NCX 收集 href → 标题（首个标签优先）。

    返回 key 是相对 OPF 目录的 href（与 manifest/spine 的 href 表示一致）。
    """
    labels: dict[str, str] = {}
    nav_href = next(
        (
            it.get("href")
            for it in opf.findall(".//{*}manifest/{*}item")
            if "nav" in (it.get("properties") or "")
        ),
        None,
    )
    if nav_href:
        full = _resolve_href(opf_dir, nav_href)
        if full in names:
            try:
                root = ET.fromstring(zf.read(full))
            except ET.ParseError:
                root = None
            if root is not None:
                for nav in root.iter("{http://www.w3.org/1999/xhtml}nav"):
                    if "toc" not in (nav.get("{http://www.idpf.org/2007/ops}type") or ""):
                        continue
                    for a in nav.iter("{http://www.w3.org/1999/xhtml}a"):
                        title = "".join(a.itertext()).strip()
                        key = unquote((a.get("href") or "").split("#")[0])
                        if title and key:
                            labels.setdefault(key, title)
                    break
    if labels:
        return labels
    ncx_href = next(
        (
            it.get("href")
            for it in opf.findall(".//{*}manifest/{*}item")
            if (it.get("media-type") or "") == "application/x-dtbncx+xml"
        ),
        None,
    )
    if ncx_href:
        full = _resolve_href(opf_dir, ncx_href)
        if full in names:
            try:
                root = ET.fromstring(zf.read(full))
            except ET.ParseError:
                root = None
            if root is not None:
                for np in root.iter("{http://www.daisy.org/z3986/2005/ncx/}navPoint"):
                    label = np.find(
                        "{http://www.daisy.org/z3986/2005/ncx/}navLabel/"
                        "{http://www.daisy.org/z3986/2005/ncx/}text"
                    )
                    content = np.find("{http://www.daisy.org/z3986/2005/ncx/}content")
                    if label is None or content is None:
                        continue
                    title = (label.text or "").strip()
                    key = unquote((content.get("src") or "").split("#")[0])
                    if title and key:
                        labels.setdefault(key, title)
    return labels


def read_epub_package(path: str | Path) -> EpubPackage:
    """解析 EPUB 的 container → OPF，返回 spine / DC 元数据 / TOC 标签。"""
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise EpubError(f"EPUB 不是有效的 zip：{e}") from e
    with zf:
        names = zf.namelist()
        try:
            container = ET.fromstring(zf.read("META-INF/container.xml"))
        except (KeyError, ET.ParseError) as e:
            raise EpubError(f"缺少/损坏 container.xml：{e}") from e
        rootfile = container.find(".//{*}rootfile")
        opf_path = rootfile.get("full-path") if rootfile is not None else None
        if not opf_path or opf_path not in names:
            raise EpubError("OPF 路径无效")
        try:
            opf = ET.fromstring(zf.read(opf_path))
        except ET.ParseError as e:
            raise EpubError(f"OPF 解析失败：{e}") from e
        opf_dir = posixpath.dirname(opf_path)

        metadata: dict[str, str] = {}
        md = opf.find(".//{*}metadata")
        if md is not None:
            for tag in ("title", "creator", "language", "date", "identifier", "publisher"):
                el = md.find(f"{{{_DC}}}{tag}")
                if el is not None and (el.text or "").strip():
                    metadata[tag] = el.text.strip()

        manifest: dict[str, tuple[str, str]] = {}
        for it in opf.findall(".//{*}manifest/{*}item"):
            iid = it.get("id")
            href = it.get("href")
            if iid and href:
                manifest[iid] = (href, it.get("media-type") or "")

        labels = _iter_nav_titles(zf, names, opf, opf_dir)

        spine: list[SpineItem] = []
        for ref in opf.findall(".//{*}spine/{*}itemref"):
            iid = ref.get("idref") or ""
            if iid not in manifest:
                continue
            href, media_type = manifest[iid]
            rel = _resolve_href(opf_dir, href)
            if not rel or rel not in names:
                continue
            spine.append(
                SpineItem(
                    id=iid,
                    href=href.split("#", 1)[0],
                    zip_path=rel,
                    media_type=media_type,
                    linear=(ref.get("linear") or "yes").lower() != "no",
                )
            )

        # href 标签按规范化的 opf 相对路径（去目录）对齐
        href_labels: dict[str, str] = {}
        for key, title in labels.items():
            href_labels[unquote(key).lstrip("./")] = title
        return EpubPackage(opf_dir=opf_dir, spine=spine, metadata=metadata, href_labels=href_labels)


def split_by_spine_anchors(md: str, basenames: list[str]) -> list[list[str]] | None:
    """按线性 spine 锚点行切分 pandoc Markdown，返回每个 spine 项的行块。

    每个锚点形如 ``[]{#<basename>.xhtml}``（独立成行）。任一 basename 缺锚点、
    或顺序不符，返回 ``None``（调用方回退到按标题切分）。首块含正文首锚点之前的内容。
    """
    lines = md.splitlines()
    index_of: dict[str, int] = {}
    for i, line in enumerate(lines):
        m = _ANCHOR_LINE_RE.match(line.strip())
        if not m:
            continue
        anchor = m.group(1).lstrip("#")
        index_of.setdefault(anchor, i)

    positions: list[int] = []
    for name in basenames:
        pos = index_of.get(name)
        if pos is None:
            pos = next(
                (i for a, i in index_of.items() if a.endswith("/" + name)),
                None,
            )
        if pos is None:
            return None
        positions.append(pos)
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        return None

    blocks: list[list[str]] = []
    for k, start in enumerate(positions):
        end = positions[k + 1] if k + 1 < len(positions) else len(lines)
        chunk = lines[start:end]
        if k == 0 and start > 0:
            chunk = lines[:start] + chunk
        blocks.append(chunk)
    return blocks


def _strip_anchor_lines(lines: list[str]) -> list[str]:
    return [ln for ln in lines if not _ANCHOR_LINE_RE.match(ln.strip())]


def strip_self_file_prefix(text: str, self_basename: str) -> str:
    """去掉引用中**当前 spine 文件自身**的文件名前缀（切块时当前 href 已知）。

    pandoc -f epub 会给当前文件内的锚点/链接也带上源文件名：
    ``[]{#ch1.xhtml#ncx_1}`` → ``[]{#ncx_1}``、``[x](#ch1.xhtml#p2)`` → ``[x](#p2)``、
    ``{#ch1.xhtml#h .h1}`` → ``{#h}``。指向**其他** spine 文件的引用不在此处理，
    交给 structure/links.py 按全局 spine 映射重写。无 fragment 的纯文件锚点
    （``[]{#ch1.xhtml}``）是边界标记，直接删除。
    """
    if not self_basename:
        return text
    q = re.escape(self_basename)

    def _anchor(m: re.Match[str]) -> str:
        frag = m.group(1)
        return f"[]{{#{frag}}}" if frag else ""

    def _attr(m: re.Match[str]) -> str:
        frag = m.group(1)
        return f"{{#{frag}}}" if frag else m.group(0)

    text = re.sub(r"\[\]\{#" + q+r"(?:#([^}\s]*))?[^}]*\}", _anchor, text)
    text = re.sub(r"\{#" + q+r"(?:#([^}\s]*))?[^}]*\}", _attr, text)
    text = re.sub(
        r"(\]\(\s*<?)#?" + q+r"(?:#([^)>]*))?(>?\s*\))",
        lambda m: f"{m.group(1)}#{m.group(2)}{m.group(3)}" if m.group(2) else m.group(0),
        text,
    )
    return text


def _parse_heading_line(raw: str) -> tuple[str, str | None, str]:
    """解析首个标题行，返回 (纯标题文本, 标题 id|None, 前导空锚点文本)。

    pandoc 标题形如 ``[]{#page_20 .calibre5}**2 Title** {#ch02 .h1}``（文件名前缀
    已由 strip_self_file_prefix 去除）：前导空锚点是章节首页页码锚点（须保留为正文
    首个锚点），末尾 ``{#id}`` 是标题锚点（成品 h1 的 id，供目录跳转），其余去
    markdown 行内标记后为纯标题。
    """
    text = raw
    leading: list[str] = []

    def _take_anchor(m: re.Match[str]) -> str:
        if m.group(1):
            leading.append(f"[]{{#{m.group(1)}}}")
        return ""

    # 反复摘除行首前导空锚点（可能多个）
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"^\s*\[\]\{#([^}\s]+)(?:\s+[^}]*)?\}", _take_anchor, text)
    # 末尾标题 id 属性
    heading_id = None
    m_id = re.search(r"\{#([^}\s]+)(?:\s+[^}]*)?\}\s*$", text)
    if m_id:
        heading_id = m_id.group(1)
        text = text[: m_id.start()] + text[m_id.end():]
    # 去行内 markdown 标记 → 纯标题
    clean = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    clean = clean.replace("**", "").replace("__", "")
    clean = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", clean)
    clean = re.sub(r"`([^`]+)`", r"\1", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean, heading_id, "".join(leading)


def _first_heading_line(lines: list[str]) -> tuple[int, str] | None:
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line.rstrip())
        if m:
            return i, m.group(2)
    return None


def _blocks_to_segments(lines: list[str]) -> list[SourceSegment]:
    """把行块转成段落/标题段（按空行切段，标题单独成段）。"""
    segments: list[SourceSegment] = []
    buffer: list[str] = []

    def flush() -> None:
        block = "\n".join(buffer).strip("\n")
        buffer.clear()
        for para in re.split(r"\n\s*\n", block):
            cleaned = clean_pandoc_residue(para)
            if cleaned:
                segments.append(SourceSegment(index=0, source=cleaned, kind=KIND_TEXT))

    for line in lines:
        m = _HEADING_RE.match(line.rstrip())
        if m:
            flush()
            text = _clean_heading(m.group(2))
            if text:
                segments.append(SourceSegment(index=0, source=text, kind=KIND_HEADING))
        else:
            buffer.append(line)
    flush()
    for i, seg in enumerate(segments):
        seg.index = i
    return segments


def _xhtml_title(zf: zipfile.ZipFile, zip_path: str) -> str:
    try:
        text = zf.read(zip_path).decode("utf-8", "ignore")
    except KeyError:
        return ""
    m = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    return _clean_heading(re.sub(r"<[^>]+>", " ", m.group(1))) if m else ""


def _xhtml_div_class(zf: zipfile.ZipFile, zip_path: str) -> str:
    """取顶层 div 的 class 作为标题兜底（如 dedication）。"""
    try:
        text = zf.read(zip_path).decode("utf-8", "ignore")
    except KeyError:
        return ""
    m = re.search(r"<div[^>]*class=[\"']([^\"']+)[\"']", text, re.IGNORECASE)
    if not m:
        return ""
    for cls in m.group(1).split():
        if cls in _CLASS_TITLES:
            return _CLASS_TITLES[cls]
    return ""


def _pandoc_html_to_markdown(html_text: str) -> str:
    """用 pandoc 把单文件 XHTML 转为 Markdown（用于非线性 spine 项）。"""
    if not pandoc_available():
        raise PandocError("未找到 pandoc；无法转换非线性 spine 项")
    try:
        proc = subprocess.run(
            ["pandoc", "-f", "html", "-t", "markdown", "--wrap=none"],
            input=html_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as e:
        raise PandocError(f"pandoc 执行失败：{e}") from e
    if proc.returncode != 0:
        raise PandocError(f"pandoc 转换失败：{proc.stderr.strip()[:200]}")
    return proc.stdout


def _is_caption_for(segment_source: str, href: str) -> bool:
    """判断段落是否恰好是指向某非线性项的图题/表题链接。"""
    pattern = r"^\s*\[[^\]]*\]\(\s*<?" + re.escape(href) + r">?\s*\)\s*(?:\{#[^}]*\})?\s*$"
    return re.match(pattern, segment_source) is not None


def _inline_nonlinear(units: list[SourceUnit], package: EpubPackage, path: str | Path) -> None:
    """把非线性 spine 项（表格等）转 md，在首个引用段内联；无引用则追加到末尾单元。"""
    if not package.nonlinear:
        return
    with zipfile.ZipFile(path) as zf:
        for item in package.nonlinear:
            if item.media_type not in _XHTML_TYPES:
                continue
            html = zf.read(item.zip_path).decode("utf-8", "ignore")
            md = _pandoc_html_to_markdown(html).strip()
            if not md:
                continue
            blocks = [b for b in re.split(r"\n\s*\n", md) if b.strip()]
            placed = False
            for unit in units:
                for idx, seg in enumerate(unit.segments):
                    if _is_caption_for(seg.source, item.href):
                        new_segs = [
                            SourceSegment(index=0, source=b, kind=KIND_TEXT) for b in blocks
                        ]
                        unit.segments[idx : idx + 1] = new_segs
                        _reindex(unit)
                        placed = True
                        break
                if placed:
                    break
            if not placed and units:
                unit = units[-1]
                unit.segments.extend(
                    SourceSegment(index=0, source=b, kind=KIND_TEXT) for b in blocks
                )
                _reindex(unit)


def _reindex(unit: SourceUnit) -> None:
    for i, seg in enumerate(unit.segments):
        seg.index = i


_PART_TITLE_RE = re.compile(r"^PART\s+[IVXLCD\d]+\.?\s*$", re.IGNORECASE)
_NUMBERED_TITLE_RE = re.compile(r"^\d+\s*\.")


def _derive_heading_levels(titles: list[str]) -> list[int]:
    """从 spine 顺序的单元标题推导目录层级（纯函数）。

    规则：分部标题（PART I/II/…）为 1 级并开启「部内」状态；其后的编号章
    （``2.`` ``10.`` 等）为 2 级（部之子章）；其余标题回到 1 级并关闭该状态。
    例：``PART I, 2., 3., PART II, 4.`` → ``1,2,2,1,2``；``结论`` 与其后的
    ``10.``（部已结束）仍为 1 级。纯启发式，但与常见书籍结构一致；
    无分部结构的书全部落 1 级（扁平目录），行为与旧版一致。
    """
    levels: list[int] = []
    in_part = False
    for title in titles:
        if _PART_TITLE_RE.match(title.strip()):
            levels.append(1)
            in_part = True
            continue
        if in_part and _NUMBERED_TITLE_RE.match(title.strip()):
            levels.append(2)
            continue
        levels.append(1)
        in_part = False
    return levels


def read_epub(path: str | Path, *, media_dir: str | Path | None = None) -> SourceDocument:
    """读取 EPUB：按 spine 切分单元 + 内联非线性项 + 清洗残留。

    任一环节无法按 spine 处理时抛 :class:`EpubError`，由 ``load_document`` 回退到
    通用 pandoc 标题切分路径。
    """
    path = Path(path)
    try:
        package = read_epub_package(path)
    except (EpubError, OSError) as e:
        raise EpubError(str(e)) from e
    linear = package.linear
    if not linear:
        raise EpubError("EPUB 无可用的线性 spine 项")

    content = run_pandoc(path, media_dir=media_dir)
    basenames = [posixpath.basename(i.zip_path) for i in linear]
    blocks = split_by_spine_anchors(content, basenames)
    if blocks is None:
        return _fallback_by_heading(path, package, content)

    units: list[SourceUnit] = []
    with zipfile.ZipFile(path) as zf:
        for seq, (item, block) in enumerate(zip(linear, blocks, strict=False), start=1):
            self_base = posixpath.basename(item.zip_path)
            lines = [strip_self_file_prefix(ln, self_base) for ln in _strip_anchor_lines(block)]
            heading = _first_heading_line(lines)
            heading_id: str | None = None
            leading_anchors = ""
            heading_text = ""
            if heading is not None:
                heading_text, heading_id, leading_anchors = _parse_heading_line(heading[1])
                del lines[heading[0]]
            label = package.href_labels.get(unquote(item.href).lstrip("./"), "")
            title = (
                label
                or heading_text
                or _xhtml_title(zf, item.zip_path)
                or _xhtml_div_class(zf, item.zip_path)
                or "正文"
            )
            segments = _blocks_to_segments(lines)
            if leading_anchors:
                # 章节首页页码锚点：作为正文第一个锚点段保留（内部跳转落点）
                segments.insert(0, SourceSegment(index=0, source=leading_anchors, kind=KIND_TEXT))
                for i, seg in enumerate(segments):
                    seg.index = i
            units.append(
                SourceUnit(
                    id=f"spine{seq:03d}",
                    kind="chapter",
                    title=_clean_heading(title),
                    segments=segments,
                    meta={
                        "heading_level": 1,
                        "spine_href": item.href,
                        **({"heading_id": heading_id} if heading_id else {}),
                    },
                )
            )

    _inline_nonlinear(units, package, path)
    levels = _derive_heading_levels([u.title for u in units])
    for unit, level in zip(units, levels, strict=True):
        unit.meta["heading_level"] = level
    return SourceDocument(
        title=package.metadata.get("title") or path.stem,
        source_path=str(path.resolve()),
        fmt="epub",
        units=units,
        meta={"via": "pandoc-epub", **package.metadata},
    )


def _fallback_by_heading(path: Path, package: EpubPackage, content: str) -> SourceDocument:
    """无 spine 锚点时回退到按标题切分（并清洗残留），保证通用 EPUB 可用。"""
    units = parse_markdown_units(content)
    for unit in units:
        unit.title = _clean_heading(unit.title)
        for seg in unit.segments:
            seg.source = (
                _clean_heading(seg.source)
                if seg.kind == KIND_HEADING
                else clean_pandoc_residue(seg.source)
            )
        unit.segments = [s for s in unit.segments if s.source.strip()]
        _reindex(unit)
    _inline_nonlinear(units, package, path)
    return SourceDocument(
        title=package.metadata.get("title") or path.stem,
        source_path=str(path.resolve()),
        fmt="epub",
        units=units,
        meta={"via": "pandoc-epub-fallback", **package.metadata},
    )
