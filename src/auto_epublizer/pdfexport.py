# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""EPUB → 印刷版 PDF（headless Chromium + PyMuPDF），派生件不替代交付格式。

为什么用浏览器而不是 LaTeX/pandoc：书已经是「每单元 XHTML + 一份样式表」，浏览器
渲染的就是成品本身（表格、图片、CJK 断行），不需要第二套排版源。

要点（issue #60 / PR67 的 D1–D3 验收）：

- **容器**：包文档只经 ``META-INF/container.xml`` 定位，不在解包目录里猜 ``*.opf``；
- **解包安全**：拒绝绝对路径、``..`` 与符号链接，任何成员都不能落到临时目录外；
- **资源**：每章资源按**章节目录**重定位（子目录章节的 ``images/x.png`` 不会错配）；
  远程/包外引用丢弃并记 notes；``script``/``on*`` 一律移除；spine 文档缺失直接报错；
- **书签**：只读 OPF 声明的 ``properties="nav"`` 且只取 ``epub:type="toc"``；渲染时给
  每区段写不可见定位标记，按标记取真实页，再在区段页范围内找标题；找不到记
  ``notes`` 明确「未定位」，不靠「页码单调」冒充正确；映射后 redaction 清除标记；
- **元数据**：OPF3 ``meta refines`` 的译者不写进 author；
- **CLI 契约**：字号/行距做区间与有限性校验；缺浏览器、超时、进程失败、产物非 PDF
  都是中文错误；失败不留半成品，也不改动 EPUB 与报告状态。

产物是 *derived artifact*：EPUB 仍是交付格式，PDF 每次从 EPUB 重新生成、不手改，
也不进入 QA 摘要（``artifacts_digest`` 不遍历 ``output/``）。
"""

from __future__ import annotations

import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from string import Template
from xml.etree import ElementTree as ET

import pymupdf

BODY_RE = re.compile(r"<body[^>]*>(.*)</body>", re.S | re.I)
ASIDE_RE = re.compile(r"<aside\b[^>]*>.*?</aside>", re.S | re.I)
BACKLINK_RE = re.compile(r"<p>\s*<a\b[^>]*epub:type=\"backlink\"[^>]*>.*?</a>\s*</p>", re.S | re.I)
FNLABEL_RE = re.compile(r"<p>\s*\[([^\]]{1,8})\]\s*</p>\s*<p>", re.S | re.I)
IMG_RE = re.compile(r'<img[^>]*src="([^"]+)"', re.I)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)
ON_ATTR_RE = re.compile(r'\son\w+\s*=\s*"[^"]*"', re.I)
RES_TAG_RE = re.compile(r"<(img|image|link|source|use|iframe|object)\b[^>]*>", re.I)
RES_ATTR_RE = re.compile(r'\b(src|href|xlink:href)\s*=\s*"([^"]*)"', re.I)

_NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
}

_CHROMIUM_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
)

#: 开本预设（mm）：中文纸书常用开本。键名即 ``--size`` 的取值。
SIZES: dict[str, tuple[int, int]] = {
    "a5": (148, 210),  # 大 32 开（本工具缺省）
    "32k": (130, 184),  # 32 开
    "b5": (176, 250),
    "16k": (185, 260),  # 16 开
}

#: 版式区间（D3）：超出即拒，不静默夹到边界——纸书参数错了要看得见。
BODY_PT_RANGE = (4.0, 24.0)
NOTE_PT_RANGE = (4.0, 20.0)
LINE_HEIGHT_RANGE = (1.0, 3.0)
DEFAULT_TIMEOUT = 240

CSS_TEMPLATE = r"""/* 印刷版式：${page_note}，正文 ${body_pt} pt、注文 ${note_pt} pt，行距 ${line_height}，
   首行缩进 2 字、段间不留空——中文学术书（译著）惯例。 */
@page { size: ${size_css}; margin: ${margins}; }
@page :first { margin: 0; }
html, body { margin: 0; padding: 0; }
body { font-family: "Noto Serif CJK SC", "Songti SC", serif; font-size: ${body_pt}pt;
       line-height: ${line_height}; text-align: justify; }
p { font-size: ${body_pt}pt; line-height: ${line_height}; text-indent: 2em; margin: 0;
    text-align: justify; }
p.imgp, figure.imgfig { text-indent: 0; margin: 0.6em 0; }
figure.imgfig figcaption { font-size: ${note_pt}pt; color: #444; }
h1 { font-size: ${h1_pt}pt; line-height: 1.35; margin: 1.1em 0 0.9em; }
h2 { font-size: ${h2_pt}pt; line-height: 1.4; margin: 1em 0 0.7em; }
h3 { font-size: ${h3_pt}pt; line-height: 1.45; margin: 0.9em 0 0.5em; }
h4, h5, h6 { font-size: ${h4_pt}pt; margin: 0.8em 0 0.4em; }
blockquote { font-size: ${quote_pt}pt; line-height: 1.5; margin: 0.6em 0 0.6em 1.5em; }
aside, .footnote, section.footnotes { font-size: ${note_pt}pt; line-height: 1.4;
    text-align: justify; display: block; margin: 0.2em 0 0.5em 0; }
aside p, .footnote p, p.fn { font-size: ${note_pt}pt; line-height: 1.4; text-indent: 0;
    margin: 0 0 0.3em 0; }
span.fnnum { font-weight: 600; }
/* 印刷版不保留屏幕样式：链接同色无下划线，注码与正文同色 */
a { color: inherit; text-decoration: none; }
a[epub\:type~="noteref"], a[role="doc-noteref"] { color: inherit; }
table.data { font-size: ${table_pt}pt; }
table.data th, table.data td { padding: 0.12em 0.4em; }
section.chapter { page-break-after: always; }
section.chapter:last-of-type { page-break-after: auto; }
section.cover { page-break-after: always; width: 100%; height: 100vh; margin: 0; padding: 0; }
section.cover img { width: 100%; height: 100%; object-fit: contain; }
h1, h2, h3, h4 { page-break-after: avoid; }
figure, table, aside { page-break-inside: avoid; }
/* 定位标记：不可见但对 PDF 文本层可检索；映射完成后 redaction 清除 */
span.aepmark { font-size: 1px; color: #ffffff; }
"""


@dataclass(slots=True)
class PrintStyle:
    """版式参数。缺省为中文社科学术书：大 32 开 + 五号正文 + 小五注文。"""

    size: str = "a5"
    body_pt: float = 10.5
    note_pt: float = 8.5
    line_height: float = 1.55
    margins_mm: tuple[float, float, float, float] = (18, 16, 20, 16)

    def page_size_mm(self) -> tuple[int, int]:
        return SIZES.get(self.size.lower(), SIZES["a5"])

    def validate(self) -> None:
        """D3：有限且在区间内；越界直接拒绝，不夹取值。"""
        for name, value in (
            ("body_pt", self.body_pt),
            ("note_pt", self.note_pt),
            ("line_height", self.line_height),
        ):
            if not isfinite(float(value)):
                raise ValueError(f"{name} 必须是有限数值：{value!r}")
        low, high = BODY_PT_RANGE
        if not low <= float(self.body_pt) <= high:
            raise ValueError(f"body_pt 超出区间 {low:g}–{high:g}：{self.body_pt}")
        low, high = NOTE_PT_RANGE
        if not low <= float(self.note_pt) <= high:
            raise ValueError(f"note_pt 超出区间 {low:g}–{high:g}：{self.note_pt}")
        low, high = LINE_HEIGHT_RANGE
        if not low <= float(self.line_height) <= high:
            raise ValueError(f"line_height 超出区间 {low:g}–{high:g}：{self.line_height}")

    def css(self) -> str:
        width, height = self.page_size_mm()
        top, outer, bottom, inner = self.margins_mm
        return Template(CSS_TEMPLATE).substitute(
            page_note=f"{width}×{height} mm（{self.size}）",
            size_css=f"{width}mm {height}mm",
            margins=f"{top}mm {outer}mm {bottom}mm {inner}mm",
            body_pt=self.body_pt,
            note_pt=self.note_pt,
            line_height=self.line_height,
            h1_pt=round(self.body_pt * 1.8, 1),
            h2_pt=round(self.body_pt * 1.43, 1),
            h3_pt=round(self.body_pt * 1.19, 1),
            h4_pt=round(self.body_pt * 1.05, 1),
            quote_pt=round(self.body_pt * 0.9, 1),
            table_pt=round(self.body_pt * 0.86, 1),
        )


@dataclass(slots=True)
class PdfResult:
    out: Path
    pages: int
    sections: int
    bookmarks: int
    size_mm: tuple[int, int]
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Package:
    """OPF 的确定性视图：manifest/spine/nav/metadata 都从同一棵树读出。"""

    root: Path
    opf_dir: Path
    spine: list[tuple[str, str]]  # (manifest id, href)
    nav_href: str | None
    manifest: dict[str, dict[str, str]]
    title: str
    author: str


def find_chromium() -> str | None:
    """Locate a Chromium/Chrome binary (``AUTO_EPUBLIZER_CHROME`` wins)."""
    override = os.environ.get("AUTO_EPUBLIZER_CHROME")
    if override and Path(override).exists():
        return override
    for name in _CHROMIUM_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    return None


def _safe_extract(archive: zipfile.ZipFile, dest: Path) -> None:
    """解包到 ``dest``；拒绝绝对路径、``..`` 与符号链接（D1）。"""
    root = dest.resolve()
    for info in archive.infolist():
        name = info.filename
        if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
            raise ValueError(f"EPUB 含绝对路径成员：{name}")
        target = (dest / name).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"EPUB 成员越界：{name}")
        mode = (info.external_attr >> 16) & 0xF000
        if mode == 0xA000:
            raise ValueError(f"EPUB 含符号链接成员：{name}")
        if name.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)


def _opf_path(work: Path) -> Path:
    """只经 ``META-INF/container.xml`` 定位包文档（D1：不按首个 ``*.opf`` 猜）。"""
    container = work / "META-INF" / "container.xml"
    if not container.is_file():
        raise ValueError("EPUB 缺 META-INF/container.xml，无法定位包文档")
    try:
        root = ET.fromstring(container.read_bytes())
    except ET.ParseError as exc:
        raise ValueError(f"container.xml 不是合法 XML：{exc}") from None
    for rootfile in root.iterfind(".//container:rootfile", _NS):
        full_path = rootfile.get("full-path")
        if full_path:
            path = work / full_path
            if path.is_file():
                return path
    raise ValueError("container.xml 未指向存在的包文档")


def _parse_opf(opf_path: Path) -> Package:
    """解析 OPF（命名空间感知）；spine 文档缺失/坏 XML 都是可预期错误。"""
    try:
        root = ET.fromstring(opf_path.read_bytes())
    except ET.ParseError as exc:
        raise ValueError(f"包文档不是合法 XML：{exc}") from None
    manifest: dict[str, dict[str, str]] = {}
    nav_href: str | None = None
    for item in root.iterfind(".//opf:manifest/opf:item", _NS):
        item_id = item.get("id") or ""
        href = item.get("href") or ""
        if not item_id or not href:
            continue
        properties = (item.get("properties") or "").split()
        manifest[item_id] = {
            "href": href,
            "media-type": item.get("media-type") or "",
            "properties": " ".join(properties),
        }
        if "nav" in properties and nav_href is None:
            nav_href = href
    spine: list[tuple[str, str]] = []
    for ref in root.iterfind(".//opf:spine/opf:itemref", _NS):
        if (ref.get("linear") or "").lower() == "no":
            continue
        item_id = ref.get("idref") or ""
        href = (manifest.get(item_id) or {}).get("href") or ""
        if item_id and href:
            spine.append((item_id, href))
    if not spine:
        raise ValueError("包文档 spine 为空，无内容可排版")

    # 译者/作者：OPF3 的 role 可以在 meta refines 里
    roles: dict[str, str] = {}
    for meta in root.iterfind(".//opf:metadata/opf:meta", _NS):
        refines = meta.get("refines") or ""
        property_ = meta.get("property") or ""
        if property_ == "role" and refines.startswith("#"):
            roles[refines[1:]] = (meta.text or "").strip()
    title = ""
    title_el = root.find(".//dc:title", _NS)
    if title_el is not None and (title_el.text or "").strip():
        title = title_el.text.strip()
    authors: list[str] = []
    for creator in root.iterfind(".//dc:creator", _NS):
        name = (creator.text or "").strip()
        if not name:
            continue
        role = (creator.get(f"{{{_NS['opf']}}}role") or "").strip()
        role = role or roles.get(creator.get("id") or "", "")
        if role == "trl":  # 译者单列，不冒充作者
            continue
        authors.append(name)
    return Package(
        root=opf_path.parent,
        opf_dir=opf_path.parent,
        spine=spine,
        nav_href=nav_href,
        manifest=manifest,
        title=title,
        author="; ".join(authors),
    )


def prepare_asides(html: str) -> str:
    """Print notes the way books print them: no back-link arrow, number inline."""

    def one(match: re.Match[str]) -> str:
        block = BACKLINK_RE.sub("", match.group(0))
        return FNLABEL_RE.sub(
            lambda m: f'<p class="fn"><span class="fnnum">[{m.group(1)}]</span> ', block
        )

    return ASIDE_RE.sub(one, html)


def _strip_active(html: str) -> str:
    """移除脚本与 ``on*`` 事件属性：印刷版不执行任何包内代码。"""
    return ON_ATTR_RE.sub("", SCRIPT_RE.sub("", html))


def _rewrite_resources(inner: str, chapter_href: str, root: Path, notes: list[str]) -> str:
    """把资源引用按**章节目录**重定位；远程/越界/缺失引用丢弃并记 notes。"""
    chapter_dir = posixpath.dirname(chapter_href)

    def one_tag(tag_match: re.Match[str]) -> str:
        tag = tag_match.group(0)

        def one_attr(attr_match: re.Match[str]) -> str:
            attr, value = attr_match.group(1), attr_match.group(2)
            if not value or value.startswith(("#", "data:")):
                return attr_match.group(0)
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value) or value.startswith("//"):
                notes.append(f"丢弃远程资源引用：{chapter_href}:{value}")
                return ""
            joined = posixpath.normpath(posixpath.join(chapter_dir, value))
            target = (root / joined).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                notes.append(f"丢弃包外/缺失资源：{chapter_href}:{value}")
                return ""
            return f'{attr}="{joined}"'

        return RES_ATTR_RE.sub(one_attr, tag)

    return RES_TAG_RE.sub(one_tag, inner)


def build_print_html(package: Package, style: PrintStyle) -> tuple[Path, int]:
    """把 spine 顺序拼成一份印刷 HTML；缺失 spine 文档直接报错（不静默跳过）。"""
    root = package.root
    parts: list[str] = []
    notes: list[str] = []
    for index, (_item_id, href) in enumerate(package.spine, start=1):
        doc_path = root / href
        if not doc_path.is_file():
            raise ValueError(f"spine 文档缺失：{href}")
        html = doc_path.read_text(encoding="utf-8")
        body = BODY_RE.search(html)
        if not body:
            raise ValueError(f"spine 文档没有 body：{href}")
        inner = _rewrite_resources(prepare_asides(body.group(1)), href, root, notes)
        inner = _strip_active(inner)
        marker = f'<span class="aepmark">{_marker(index)}</span>'
        if "cover" in href.lower():
            image = IMG_RE.search(inner)
            if image:
                parts.append(f'<section class="cover">{marker}{image.group(0)}</section>')
                continue
            parts.append(f'<section class="cover">{marker}</section>')
            continue
        parts.append(f'<section class="chapter">{marker}{inner}</section>')
    # 样式表：按包内声明选第一个 text/css（多章子目录也不做首章猜测）
    stylesheet = next(
        (item["href"] for item in package.manifest.values() if item["media-type"] == "text/css"),
        None,
    )
    link = f'<link rel="stylesheet" type="text/css" href="{stylesheet}"/>' if stylesheet else ""
    html = (
        '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8"/>\n'
        f"<title>{package.title}</title>\n{link}\n<style>{style.css()}</style>\n</head><body>\n"
        + "\n".join(parts)
        + "\n</body></html>"
    )
    target = root / "print.html"
    target.write_text(html, encoding="utf-8")
    if notes:
        target.with_suffix(".notes.txt").write_text("\n".join(notes), encoding="utf-8")
    return target, len(parts)


def nav_entries(nav_path: Path | None) -> list[tuple[int, str, str]]:
    """只解析 ``epub:type="toc"`` 的 nav；``<ol>`` 嵌套深度即书签层级（D2）。"""
    if nav_path is None or not nav_path.is_file():
        return []
    try:
        root = ET.fromstring(nav_path.read_bytes())
    except ET.ParseError:
        return []
    epub_type = "{http://www.idpf.org/2007/ops}type"
    toc = None
    for nav in root.iter():
        if nav.tag.rsplit("}", 1)[-1] != "nav":
            continue
        if "toc" in (nav.get(epub_type) or "").split():
            toc = nav
            break
    if toc is None:
        return []
    entries: list[tuple[int, str, str]] = []

    def walk(element: ET.Element, level: int) -> None:
        for child in element:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "ol":
                walk(child, level + 1)
            elif tag == "li":
                for sub in child:
                    sub_tag = sub.tag.rsplit("}", 1)[-1]
                    if sub_tag == "a":
                        title = re.sub(r"\s+", " ", "".join(sub.itertext())).strip()
                        if title:
                            entries.append((max(1, level), title, sub.get("href") or ""))
                    elif sub_tag in ("ol", "ul"):
                        walk(sub, level + 1)

    walk(toc, 0)
    return entries


def _marker(index: int) -> str:
    return f"AEPMARK{index:04d}"


def _section_pages(doc: pymupdf.Document, sections: int) -> dict[int, int]:
    """按不可见标记定位每个区段的起始页（标记写入 HTML，PDF 文本层可检索）。"""
    pages: dict[int, int] = {}
    for index in range(doc.page_count):
        text = doc[index].get_text()
        for number in range(1, sections + 1):
            if number in pages:
                continue
            if _marker(number) in re.sub(r"\s+", "", text):
                pages[number] = index + 1
    return pages


def _clear_markers(doc: pymupdf.Document, sections: int) -> None:
    """映射完成后 redaction 清除定位标记（D2：标记不留进成品）。"""
    needles = [_marker(number) for number in range(1, sections + 1)]
    for index in range(doc.page_count):
        page = doc[index]
        hits: list[pymupdf.Rect] = []
        for needle in needles:
            hits.extend(page.search_for(needle))
        if not hits:
            continue
        for rect in hits:
            page.add_redact_annot(rect)
        page.apply_redactions()


def attach_outline(
    doc: pymupdf.Document,
    entries: list[tuple[int, str, str]],
    *,
    spine: list[tuple[str, str]],
    section_pages: dict[int, int],
    notes: list[str],
    cover: bool,
) -> list[list[object]]:
    """nav 条目 → PDF 书签；文档级条目用区段起始页，片段级在区段页内找标题。"""
    href_to_section = {
        posixpath.normpath(href): index for index, (_item_id, href) in enumerate(spine, start=1)
    }
    toc: list[list[object]] = [[1, "封面", 1]] if cover else []
    for level, title, href in entries:
        path, _, fragment = href.partition("#")
        target = posixpath.normpath(path or "")
        section = href_to_section.get(target)
        if section is None:
            notes.append(f"书签未定位（章节不在 spine）：{title} → {href}")
            continue
        start = section_pages.get(section)
        if start is None:
            notes.append(f"书签未定位（区段无标记）：{title} → {href}")
            continue
        page = start
        if fragment:
            next_start = section_pages.get(section + 1, doc.page_count + 1)
            needle = re.sub(r"\s+", "", title)[:20]
            found = None
            for candidate in range(start - 1, min(next_start - 1, doc.page_count)):
                if needle and needle in re.sub(r"\s+", "", doc[candidate].get_text()):
                    found = candidate + 1
                    break
            if found is None:
                notes.append(f"书签未定位（区段内无标题文本，用区段起始页）：{title} → {href}")
            else:
                page = found
        toc.append([level, title, page])
    return toc


def stamp_folios(doc: pymupdf.Document, *, font_size: float = 9) -> None:
    """Number every page but the cover, centred in the bottom margin."""
    for index in range(1, doc.page_count):
        page = doc[index]
        page.insert_text(
            (page.rect.width / 2 - 6, page.rect.height - 18),
            str(index + 1),
            fontsize=font_size,
            fontname="helv",
            color=(0.35, 0.35, 0.35),
        )


def render(
    epub: Path,
    out: Path,
    style: PrintStyle | None = None,
    *,
    bookmarks: bool = True,
    chromium: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> PdfResult:
    """Render ``epub`` to ``out``; 失败抛 ``ValueError``/``RuntimeError``（中文信息）。"""
    style = style or PrintStyle()
    style.validate()
    epub = Path(epub)
    out = Path(out)
    if out.resolve() == epub.resolve():
        raise ValueError("输出路径与输入 EPUB 相同；拒绝覆盖交付格式")
    browser = chromium or find_chromium()
    if not browser:
        raise RuntimeError(
            "未找到 Chromium/Chrome（可用 AUTO_EPUBLIZER_CHROME 指定路径）；"
            "印刷版 PDF 需要浏览器排版"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    with tempfile.TemporaryDirectory(prefix="aep-pdf-") as tmp:
        work = Path(tmp)
        try:
            with zipfile.ZipFile(epub) as archive:
                _safe_extract(archive, work)
        except zipfile.BadZipFile as exc:
            raise ValueError(f"不是有效的 EPUB/ZIP：{exc}") from None
        package = _parse_opf(_opf_path(work))
        target, sections = build_print_html(package, style)
        notes_path = target.with_suffix(".notes.txt")
        if notes_path.is_file():
            notes.extend(notes_path.read_text(encoding="utf-8").splitlines())
        raw = work / "raw.pdf"
        command = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-pdf-header-footer",
            "--virtual-time-budget=30000",
            f"--print-to-pdf={raw}",
            target.as_uri(),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"排版超时（{timeout} s）：Chromium 未在限时内产出 PDF") from None
        except OSError as exc:
            raise RuntimeError(f"无法启动浏览器排版：{exc}") from None
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace").strip().splitlines()
            tail = detail[-1] if detail else ""
            raise RuntimeError(f"Chromium 排版失败（退出码 {completed.returncode}）：{tail}")
        if not raw.is_file() or raw.stat().st_size == 0:
            raise RuntimeError("Chromium 未产出 PDF（进程成功但没有文件）")
        if raw.read_bytes()[:5] != b"%PDF-":
            raise RuntimeError("Chromium 产物不是 PDF")
        # 先写临时件再原子替换：失败不留下伪成功，也不破坏已有旧成品。
        staged = out.with_name(f".{out.name}.part")
        try:
            shutil.copyfile(raw, staged)
            os.replace(staged, out)
        finally:
            staged.unlink(missing_ok=True)
        metadata = {"title": package.title, "author": package.author}
        spine = package.spine
        outline = nav_entries(package.root / package.nav_href if package.nav_href else None)

    cover = bool(package.spine and "cover" in package.spine[0][1].lower())
    doc = pymupdf.open(out)
    section_pages = _section_pages(doc, sections)
    _clear_markers(doc, sections)
    stamp_folios(doc)
    written = 0
    if bookmarks:
        toc = attach_outline(
            doc,
            outline,
            spine=spine,
            section_pages=section_pages,
            notes=notes,
            cover=cover,
        )
        doc.set_toc(toc)
        written = len(toc)
    merged = {k: v for k, v in (doc.metadata or {}).items() if k in {"title", "author"}}
    merged.update({k: v for k, v in metadata.items() if v})
    doc.set_metadata(merged)
    doc.saveIncr()
    pages = doc.page_count
    doc.close()
    return PdfResult(
        out=out,
        pages=pages,
        sections=sections,
        bookmarks=written,
        size_mm=style.page_size_mm(),
        notes=notes,
    )
