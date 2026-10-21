# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""EPUB 解包逐项审计：结构性检查（零 token、离线）。"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from auto_common.markdown import inline_code_chunks, markdown_chunks

from ..fingerprint import strip_fingerprint_comments
from ..media_paths import epub_member_path

_XHTML = "application/xhtml+xml"
_HTTPS = re.compile(r"^(https?|javascript|data):", re.IGNORECASE)

# 体积阈值（postprocessing-spec P2 体积审计；可按需调整）
_MAX_EPUB_BYTES = 50 * 1024 * 1024
_MAX_IMG_BYTES = 2 * 1024 * 1024
_MEDIA_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".avif")

# markdown 残留标记（供 W_RESIDUE）。`**` 只在**恰好两个**星号时算残留：以星号作行内
# 脚注标记的书籍（现场报告 #8：源文 `…«行为矫正»****`）必须原样保留这些符号——
# `marker` 守恒是硬门，而渲染层也不会把 `****` 解释为强调，它在成品里就是显示文本。
_MD_RESIDUE: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("![", re.compile(r"!\[")),
    ("**", re.compile(r"(?<!\*)\*\*(?!\*)")),
    (":::", re.compile(r":::")),
    ("{.", re.compile(r"\{\.")),
    ("[^", re.compile(r"\[\^")),
    # 反斜杠转义残留（`\(1\)`、`p\. cm.`、`\[编辑插入\]`）：渲染层未脱转义时
    # 读者会看到裸反斜杠。此形态在四本越南书上累计 1000+ 处、7 本书 md 共 2198 处
    # 却长期无告警——因为本表此前不含该项（2026-10-04 补）。
    ("\\", re.compile(r"\\[!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~]")),
    # 转义后的原始 HTML：渲染层缺 pandoc raw-HTML 直通时 `<div>`/`<svg>` 会以
    # ``&lt;div&gt;`` 原样印给读者（2026-10-06 Thiriart 封面整段 SVG 漏成乱码）。
    ("&lt;/", re.compile(r"&lt;/?[a-zA-Z][\w:.-]*(?:\s[^<>]*)?&gt;")),
    ("{=html}", re.compile(r"\{\s*=\s*html\s*\}")),
    # 未渲染的 ATX 标题：源抽取/MinerU OCR 丢失标题前空行时，标题会成为懒续行落进
    # `<p>`（parliamentary-socialism 33 处、sample-rtl-a-1 3 处、
    # sample-document-d-1 1 处，epubcheck 与 G0 标题计数都不报）。
    # 判据限定在**段首**，以免误报 Pentagon Papers 正文里合法的文件编号 `# 1`。
    ("段首ATX标题", re.compile(r"<p[^>]*>\s*#{1,6}\s+\S")),
    # 剥离 id 后残留的空 pandoc span（`[]{#d1}` 只剥了 `{#d1}`），
    # 以及抽取丢失井号的锚点 `[]{GBS.0014.05}`。id 字符集不含空格，
    # 故 `[]{#word illegible}` 之类校勘标记不会被本条误判。
    ("空span", re.compile(r"\[\]")),
)


class _NonCodeMarkup(HTMLParser):
    """保留原始标记供残留审计，但不把真实 code/pre 的显示内容当 Markdown。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.code_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.code_depth:
            self.code_depth += 1
        elif tag in {"pre", "code"}:
            self.code_depth = 1
        else:
            self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        if self.code_depth:
            self.code_depth -= 1
        else:
            self.parts.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.code_depth and tag not in {"pre", "code"}:
            self.parts.append(self.get_starttag_text())

    def handle_data(self, data: str) -> None:
        if not self.code_depth:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.handle_data(f"&#{name};")


# ── 版面型候选（issue #38）───────────────────────────────────────────────
# 上面 32 个检查码全是「结构/资源/元数据」类：XML 层面完全合法、内容却被版面
# 重排切碎的缺陷天然看不见。三类典型形态：汉字间虚假空格（词被劈开）、段落未以
# 句末标点收束（页边界切断）、注码被夹进词组。全部为 **warning 候选**（W_*），
# 供 agent 核证——诗歌、标题、合法空格与统计数字不得因此自动阻断或改写。
_CJK_CLASS = r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]"
_CJK_ONE_RE = re.compile(_CJK_CLASS)
_CJK_SPACE_CJK_RE = re.compile(rf"{_CJK_CLASS}[ \u3000]{_CJK_CLASS}")
_PARA_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.DOTALL | re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
# 汉字 + 空白 + 1~3 位数字 + 空白 + 汉字；末字为量词时视为统计数字（见 _MEASURE_AFTER）
_NOTE_IN_PHRASE_RE = re.compile(rf"{_CJK_CLASS}\s(\d{{1,3}})\s({_CJK_CLASS})")
_MEASURE_AFTER = (
    "人年月日个名条吨米位页章节周天号项次辆架台艘款种岁分秒时元角"
    "枚张封把支颗只头匹双套组批届栋间处座"  # 常见量词（减少候选噪声；非穷举）
)
# 合法的段落收束（含引号/括号收尾与省略号）
_PARA_END_OK = "。！？…!?;；”’\"'」』）)】〕》>"

# Collected-notes candidates (#46), deliberately conservative and never identity evidence.
_NOTE_NUMBER = re.compile(r"(?<![\w.])[0-9]{1,3}\.\s")
_NOTES_MIN_CANDIDATES = 8
_NOTES_PARAGRAPH_RATIO = 4
_NOTES_LONG_PARAGRAPH = 1000
_EPUB_TYPE = "{http://www.idpf.org/2007/ops}type"
_NOTES_COLLECTION = {"endnotes", "footnotes", "rearnotes"}
_NOTE_NODE = {"footnote", "endnote", "rearnote"}


def _prose_text(element: ET.Element) -> str:
    """Visible non-code text, keeping tails after excluded code/pre nodes."""
    if element.tag.rsplit("}", 1)[-1] in {"code", "pre", "script", "style"}:
        return ""
    return (element.text or "") + "".join(
        _prose_text(child) + (child.tail or "") for child in element
    )


def _markdown_note_candidates(markdown: str) -> int:
    parts: list[str] = []
    for kind, chunk in markdown_chunks(markdown):
        if kind == "code":
            continue
        for is_code, text in inline_code_chunks(chunk):
            if not is_code:
                parts.append(text)
    # Raw HTML code uses the same exclusion policy as the existing residue audit.
    parser = _NonCodeMarkup()
    parser.feed("\n".join(parts))
    text = _HTML_TAG_RE.sub("", "".join(parser.parts)).replace("\\.", ".")
    return len(_NOTE_NUMBER.findall(text))


def _collected_notes_candidates(
    result: AuditResult,
    name: str,
    root: ET.Element,
    context: Mapping[str, str] | None,
) -> None:
    """只检查权威注释单元或显式集合，不以文件名猜身份。"""
    parents = {child: parent for parent in root.iter() for child in parent}

    def ancestors(element: ET.Element) -> list[ET.Element]:
        chain = [element]
        while chain[-1] in parents:
            chain.append(parents[chain[-1]])
        return chain

    def semantic(element: ET.Element, types: set[str], roles: set[str]) -> bool:
        return bool(
            types.intersection(element.get(_EPUB_TYPE, "").split())
            or roles.intersection(element.get("role", "").split())
        )

    authoritative = context is not None and context.get("kind") == "notes"
    regions = (
        [root]
        if authoritative
        else [
            element
            for element in root.iter()
            if semantic(element, _NOTES_COLLECTION, {"doc-endnotes", "doc-footnotes"})
        ]
    )
    # 只取最外层集合，避免嵌套区域重复告警。
    regions = [region for region in regions if not any(a in regions for a in ancestors(region)[1:])]
    indices_by_tag = {
        tag: {
            element: index
            for index, element in enumerate(
                (e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == tag), 1
            )
        }
        for tag in ("p", "li")
    }
    for region in regions:
        blocks: list[tuple[str, int, str, int]] = []
        for element in region.iter():
            local = element.tag.rsplit("}", 1)[-1]
            if local not in indices_by_tag:
                continue
            chain = ancestors(element)
            if any(a.tag.rsplit("}", 1)[-1] in {"pre", "code"} for a in chain):
                continue
            # 规范单注的合法多段/列表由独立 N 门核对，不猜成 legacy 边界。
            if any(semantic(a, _NOTE_NODE, {"doc-footnote", "doc-endnote"}) for a in chain):
                continue
            # 含 p 或嵌套 li 的列表项是容器，不再把同一份文字计数两次。
            if local == "li" and any(
                e is not element and e.tag.rsplit("}", 1)[-1] in {"p", "li"} for e in element.iter()
            ):
                continue
            text = _prose_text(element).strip()
            if text:
                blocks.append(
                    (local, indices_by_tag[local][element], text, len(_NOTE_NUMBER.findall(text)))
                )
        if not blocks:
            continue
        rendered_count = sum(count for _, _, _, count in blocks)
        input_count = (
            _markdown_note_candidates(context["markdown"])
            if authoritative and context is not None and "markdown" in context
            else None
        )
        imbalanced = (
            input_count is not None
            and input_count >= _NOTES_MIN_CANDIDATES
            and input_count >= _NOTES_PARAGRAPH_RATIO * len(blocks)
            and any(count >= 2 for _, _, _, count in blocks)
        )
        suspect = [
            (tag, index, text, count)
            for tag, index, text, count in blocks
            if count >= 2 and (len(text) >= _NOTES_LONG_PARAGRAPH or imbalanced)
        ]
        if not suspect:
            continue
        data: dict[str, object] = {
            "file": name,
            "unit": context.get("unit", "") if context else "",
            "input_path": context.get("input_path", "") if context else "",
            "scope": "unit" if authoritative else "semantic_collection",
            "region_id": region.get("id", ""),
            "paragraph_count": sum(tag == "p" for tag, _, _, _ in blocks),
            "list_item_count": sum(tag == "li" for tag, _, _, _ in blocks),
            "input_candidate_count": input_count,
            "rendered_candidate_count": rendered_count,
            "longest_paragraph_chars": max(
                (len(text) for tag, _, text, _ in blocks if tag == "p"), default=0
            ),
            "longest_list_item_chars": max(
                (len(text) for tag, _, text, _ in blocks if tag == "li"), default=0
            ),
            "longest_block_chars": max(len(text) for _, _, text, _ in blocks),
            "paragraph_indices": [index for tag, index, _, _ in suspect if tag == "p"],
            "list_item_indices": [index for tag, index, _, _ in suspect if tag == "li"],
            "paragraphs": [
                {"index": index, "chars": len(text), "candidate_count": count}
                for tag, index, text, count in suspect
                if tag == "p"
            ],
            "list_items": [
                {"index": index, "chars": len(text), "candidate_count": count}
                for tag, index, text, count in suspect
                if tag == "li"
            ],
            "raw_evidence": "structured/raw/",
        }
        data["reasons"] = (["candidate_paragraph_imbalance"] if imbalanced else []) + (
            ["long_paragraph_multiple_candidates"]
            if any(len(text) >= _NOTES_LONG_PARAGRAPH for _, _, text, _ in suspect)
            else []
        )
        result.add(
            "warning",
            "W_COLLECTED_NOTES_UNSEGMENTED",
            f"疑似书末注释未分段（候选非结论）：{name}；"
            f"段索引={data['paragraph_indices']}，列表项索引={data['list_item_indices']}；"
            f"段数={data['paragraph_count']}，独立列表项数={data['list_item_count']}，"
            f"MD注号候选={input_count}，成品块内候选={rendered_count}，"
            f"最长文本块={data['longest_block_chars']} 字符；"
            "请对照 structured/raw/ 和原页逐注核证，不自动切段、不据此阻断；独立 N 门不变",
            data=data,
        )


def _layout_candidates(result: AuditResult, name: str, content: str) -> None:
    """版面型候选（issue #38）：每文档每类至多一条 W 级提示，供 agent 逐条核证。

    只报「可定位的形态」：① 同段落 ≥2 处汉字间空格；② ≥20 字段落末字为汉字或
    悬挂的逗号/顿号/分号；③ 汉字-空格-数字-空格-汉字且数字后不是量词。简洁与诗行
    可能命中 ①②，但它们只是候选（非阻断、不自动改写），由 agent 结合源件判断。
    """
    for m in _PARA_RE.finditer(content):
        body = _HTML_TAG_RE.sub("", m.group(1)).strip()
        n_spaced = len(_CJK_SPACE_CJK_RE.findall(body))
        if n_spaced >= 2:
            result.add(
                "warning",
                "W_CJK_SPACED",
                f"汉字间疑似虚假空格（{n_spaced} 处，疑词被劈开）：{name}",
            )
            break
    for m in _PARA_RE.finditer(content):
        body = _HTML_TAG_RE.sub("", m.group(1)).strip()
        if len(body) < 20 or body[-1] in _PARA_END_OK:
            continue
        if _CJK_ONE_RE.match(body[-1]) or body[-1] in "，、；,":
            result.add(
                "warning",
                "W_PARA_UNCLOSED",
                f"段落未以句末标点收束（末字「{body[-1]}」，疑页边界切断）：{name}",
            )
            break
    text = _HTML_TAG_RE.sub("", content)
    for m in _NOTE_IN_PHRASE_RE.finditer(text):
        if m.group(2) in _MEASURE_AFTER:
            continue  # 量词前数字是统计数字（`共 3 人`），不是注码
        snippet = text[max(0, m.start() - 6) : m.end() + 6].replace("\n", " ")
        result.add(
            "warning",
            "W_NOTE_IN_PHRASE",
            f"疑似注码夹进词组（…{snippet}…）：{name}",
        )
        break


@dataclass
class AuditFinding:
    level: str  # error | warning
    code: str
    message: str
    data: dict[str, object] | None = None


@dataclass
class AuditResult:
    ok: bool
    findings: list[AuditFinding] = field(default_factory=list)

    def add(
        self, level: str, code: str, message: str, *, data: dict[str, object] | None = None
    ) -> None:
        self.findings.append(AuditFinding(level=level, code=code, message=message, data=data))
        if level == "error":
            self.ok = False


def _image_size(data: bytes, ext: str) -> tuple[int, int] | None:
    """解析 png/jpg/gif/bmp 的像素尺寸（其余格式或解析失败返回 None）。"""
    try:
        if ext == ".png" and len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        if ext == ".gif" and len(data) >= 10 and data[:3] == b"GIF":
            return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
        if ext == ".bmp" and len(data) >= 26 and data[:2] == b"BM":
            return (
                abs(int.from_bytes(data[18:22], "little")),
                abs(int.from_bytes(data[22:26], "little")),
            )
        if ext in (".jpg", ".jpeg") and data[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3):  # SOF：含宽高
                    h = int.from_bytes(data[i + 5 : i + 7], "big")
                    w = int.from_bytes(data[i + 7 : i + 9], "big")
                    return w, h
                if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:  # 无长度段
                    i += 2
                    continue
                seg_len = int.from_bytes(data[i + 2 : i + 4], "big")
                if seg_len < 2:
                    return None
                i += 2 + seg_len
        return None
    except IndexError:
        return None


# ── 图注判据（T12-4）────────────────────────────────────────────────────
# 文件名式图注：带图片扩展名，或「含数字、无空格」的机器名（p001-img01 / image_1）。
# **slug 只认 ASCII**：Python 的 ``\w`` 在 Unicode 下包含 CJK，早期写法
# ``^[\w.\-]*\d[\w.\-]*$`` 会把「1955年两名年轻女子在花丛中微笑的合影」这种
# 正常中文图注判成文件名（批次 11 复查实测两本书被误挡）。文件名是 ASCII 串，
# 中文说明文字不该被这条判据拦下。
_CAPTION_FILENAME_EXT = re.compile(r"\.(png|jpe?g|gif|svg|tiff?|bmp|webp)$", re.IGNORECASE)
_CAPTION_FILENAME_SLUG = re.compile(r"^[A-Za-z0-9._\-]*\d[A-Za-z0-9._\-]*$")
# 占位词图注
_CAPTION_PLACEHOLDER = re.compile(
    r"^(image|img|figure|fig|picture|photo|graphic|icon|illustration|"
    r"插图|图片|圖片|图像|圖像|图|未命名|待补|待定|todo|tbd|n/?a|xxx+)\.?$",
    re.IGNORECASE,
)


def _caption_is_filename(label: str) -> bool:
    """图注看起来是**文件名**（而非说明文字）。"""
    text = (label or "").strip()
    if not text or " " in text:
        return False
    if _CAPTION_FILENAME_EXT.search(text):
        return True
    return bool(_CAPTION_FILENAME_SLUG.match(text))


def _caption_is_placeholder(label: str) -> bool:
    """图注是**占位词**（image / 插图 / TODO …）。"""
    return bool(_CAPTION_PLACEHOLDER.match((label or "").strip()))


def audit_epub(
    path: str | Path,
    *,
    nav_exempt: set[str] | None = None,
    notes_registered: bool = False,
    notes_context: Mapping[str, Mapping[str, str]] | None = None,
) -> AuditResult:
    """解包 EPUB 并逐项审计结构。

    ``nav_exempt``：目录深度投影（``output.nav_depth``）剔除而不进 nav 的 spine
    文档 basename 集合（orchestrator 由 provenance 的同一投影算得）——这些文档仍在
    spine 阅读顺序中，豁免 E_TOC_COVERAGE；集合中出现非 spine 文档名则报错。
    ``notes_registered``：调用方已验证有效登记并执行独立注释门时，移交必需回链判定。
    ``notes_context``：实际构建输入按精确 EPUB 成员路径映射，含 kind/unit/markdown/input_path；
    仅 kind=notes 授权整单元候选检查。不提供时仍检查显式注释集合语义区。
    """
    result = AuditResult(ok=True)
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        result.add("error", "E_NOT_EPUB", f"不是有效的 zip：{e}")
        return result

    with zf:
        names = zf.namelist()

        # 1. mimetype 首位未压缩、内容正确
        if not names or names[0] != "mimetype":
            result.add("error", "E_MIMETYPE_FIRST", "mimetype 必须是 zip 首个条目")
        else:
            info = zf.getinfo("mimetype")
            if info.compress_type != zipfile.ZIP_STORED:
                result.add("error", "E_MIMETYPE_STORED", "mimetype 不得压缩")
            if zf.read("mimetype").decode("utf-8") != "application/epub+zip":
                result.add("error", "E_MIMETYPE_CONTENT", "mimetype 内容错误")

        # 1b. zip 条目名不得重复（zip 规范允许同名条目后者遮蔽前者，内容即不可信）
        for dupe, count in Counter(names).items():
            if count > 1:
                result.add("error", "E_ZIP_DUPLICATE", f"zip 条目名重复：{dupe}")

        # 2. container.xml 指向 OPF
        if "META-INF/container.xml" not in names:
            result.add("error", "E_NO_CONTAINER", "缺少 META-INF/container.xml")
            return result
        container = zf.read("META-INF/container.xml").decode("utf-8")
        m = re.search(r'full-path="([^"]+)"', container)
        if not m:
            result.add("error", "E_CONTAINER_OPF", "container.xml 未声明 OPF")
            return result
        opf_path = m.group(1)

        # 3. OPF 解析 manifest/spine
        if opf_path not in names:
            result.add("error", "E_OPF_MISSING", f"OPF 缺失：{opf_path}")
            return result
        opf = zf.read(opf_path).decode("utf-8")
        manifest_hrefs = set(re.findall(r'<item[^>]+href="([^"]+)"', opf))
        spine_idrefs = set(re.findall(r'<itemref[^>]+idref="([^"]+)"', opf))
        manifest_ids = set(re.findall(r'<item[^>]+id="([^"]+)"', opf))

        for idref in spine_idrefs:
            if idref not in manifest_ids:
                result.add("error", "E_SPINE_REF", f"spine idref 未在 manifest：{idref}")

        opf_dir = Path(opf_path).parent
        for href in manifest_hrefs:
            full = epub_member_path(opf_path, href)
            if full not in names:
                result.add("error", "E_MANIFEST_HREF", f"manifest href 无法解析：{href}")

        # 4. nav / NCX / landmarks 链接可解析（引用不存在的文件即悬空）
        nav_entries = [n for n in names if n.endswith("nav.xhtml")]
        for nav in nav_entries:
            content = zf.read(nav).decode("utf-8")
            for href in re.findall(r'href="([^"]+\.xhtml)"', content):
                full = (Path(nav).parent / href).as_posix()
                if full not in names:
                    result.add("error", "E_NAV_HREF", f"nav 链接无法解析：{href}")

        for ncx in (n for n in names if n.endswith(".ncx")):
            content = zf.read(ncx).decode("utf-8")
            for src in re.findall(r'<content src="([^"]+)"', content):
                # NCX src 可带 #fragment；解析 zip 成员时须剥离片段
                full = (Path(ncx).parent / src.split("#", 1)[0]).as_posix()
                if full not in names:
                    result.add("error", "E_NCX_HREF", f"NCX content src 无法解析：{src}")

        # 4a. spine ↔ nav 双向覆盖（S1.3）：每个 spine 内容文档进目录、
        #     每个 nav 条目指向 spine 文档；nav/landmarks 自身与封面（linear="no"）豁免
        id2href: dict[str, str] = {}
        for item in re.findall(r"<item\b[^>]*>", opf):
            mid = re.search(r'\bid="([^"]+)"', item)
            mhref = re.search(r'\bhref="([^"]+)"', item)
            if mid and mhref:
                id2href[mid.group(1)] = mhref.group(1)
        spine_docs = {(opf_dir / id2href[ref]).as_posix() for ref in spine_idrefs if ref in id2href}
        cover_docs: set[str] = set()
        for ref in re.findall(r'<itemref[^>]+idref="([^"]+)"[^>]*linear="no"', opf):
            if ref in id2href:
                cover_docs.add((opf_dir / id2href[ref]).as_posix())
        nav_doc_hrefs: set[str] = set()
        for nav in nav_entries:
            content = zf.read(nav).decode("utf-8")
            m = re.search(r'<nav[^>]*epub:type="toc"[^>]*>(.*?)</nav>', content, re.DOTALL)
            if not m:
                m = re.search(r"<nav\b[^>]*>(.*?)</nav>", content, re.DOTALL)
            if not m:
                continue
            for href in re.findall(r'href="([^"]+\.xhtml)[^"]*"', m.group(1)):
                nav_doc_hrefs.add((Path(nav).parent / href.split("#")[0]).as_posix())
        exempt = {n for n in names if n.endswith(("nav.xhtml", "landmarks.xhtml"))} | cover_docs
        projected = nav_exempt or set()
        spine_names = {Path(doc).name for doc in spine_docs}
        for name in sorted(projected - spine_names):
            result.add("error", "E_TOC_COVERAGE", f"目录投影豁免集含非 spine 文档：{name}")
        for doc in spine_docs - exempt:
            if doc not in nav_doc_hrefs and Path(doc).name not in projected:
                result.add("error", "E_TOC_COVERAGE", f"spine 文档未进目录：{doc}")
        for doc in nav_doc_hrefs - spine_docs:
            result.add("error", "E_TOC_COVERAGE", f"nav 条目不在 spine：{doc}")

        for lm in (n for n in names if n.endswith("landmarks.xhtml")):
            content = zf.read(lm).decode("utf-8")
            for href in re.findall(r'href="([^"]+\.xhtml)"', content):
                full = (Path(lm).parent / href).as_posix()
                if full not in names:
                    result.add("error", "E_LANDMARKS_HREF", f"landmarks 链接无法解析：{href}")

        # 4b. XHTML img 与 SVG image 的本地媒体引用必须存在，URL 共用一次解码规则。
        for name in names:
            if not name.endswith(".xhtml"):
                continue
            try:
                root = ET.fromstring(zf.read(name))
            except ET.ParseError as exc:
                result.add("error", "E_XHTML_XML", f"内容文档 XML 无效：{name}：{exc}")
                continue
            _collected_notes_candidates(result, name, root, (notes_context or {}).get(name))
            sources = [
                image.attrib["src"]
                for image in root.iter("{http://www.w3.org/1999/xhtml}img")
                if "src" in image.attrib
            ]
            for image in root.iter("{http://www.w3.org/2000/svg}image"):
                sources.extend(
                    image.attrib[attr]
                    for attr in ("href", "{http://www.w3.org/1999/xlink}href")
                    if attr in image.attrib
                )
            for src in sources:
                if _HTTPS.match(src):
                    result.add(
                        "error",
                        "E_IMG_REMOTE",
                        f"图片引用为外部链接（媒体必须打包进 EPUB）：{name} -> {src}",
                    )
                    continue
                full = epub_member_path(name, src)
                if full not in names:
                    result.add("error", "E_IMG_SRC", f"图片引用无法解析：{name} -> {src}")

        # 5. URL 安全：无 javascript:/data: 注入
        for name in names:
            if not name.endswith(".xhtml") and not name.endswith(".opf"):
                continue
            content = zf.read(name).decode("utf-8")
            if re.search(r'href="\s*(javascript|data):', content, re.IGNORECASE):
                result.add("error", "E_UNSAFE_URL", f"发现危险 URL 注入：{name}")

        # 5b. 主题层校验（epub-template-spec §5）：禁具体字体名/颜色/字号，
        # serif/sans-serif 等泛化族名允许（阅读器映射到自己的字体）。
        if "OEBPS/style.css" in names:
            css = re.sub(
                r"/\*.*?\*/", "", zf.read("OEBPS/style.css").decode("utf-8"), flags=re.DOTALL
            )
            if re.search(r"font-family\s*:[^;}]*[\"']", css):
                result.add(
                    "error",
                    "E_THEME_FONT",
                    "style.css 含具体字体名（只允许 serif/sans-serif 泛化族名）",
                )
            if re.search(r"\bfont-size\s*:", css):
                result.add("error", "E_THEME_FONT", "style.css 设置了字号（应由阅读器决定）")
            if re.search(r"(?<![-\w])color\s*:", css):
                result.add("error", "E_THEME_COLOR", "style.css 设置了颜色（应由阅读器处理）")

        # 5c. 媒体审计（postprocessing-spec P1）：alt 空值/缺失、格式兼容、超大/超宽超高
        for name in names:
            if not name.endswith(".xhtml"):
                continue
            content = zf.read(name).decode("utf-8")
            for tag in re.findall(r"<img\b[^>]*?/?>", content):
                malt = re.search(r'\balt="([^"]*)"', tag)
                if malt is None or not malt.group(1).strip():
                    result.add("warning", "W_IMG_NO_ALT", f"img alt 为空或缺失：{name}")
                msrc = re.search(r'src="([^"]+)"', tag)
                if not msrc:
                    continue
                src = msrc.group(1)
                if _HTTPS.match(src):
                    continue
                full = epub_member_path(name, src)
                if full not in names:
                    continue  # 悬空已由 E_IMG_SRC 覆盖
                ext = Path(full).suffix.lower()
                if ext in (".avif", ".webp"):
                    result.add("warning", "W_IMG_FORMAT", f"图片格式阅读器兼容性差（{ext}）：{src}")
                size = _image_size(zf.read(full), ext)
                if size:
                    w, h = size
                    if w > 4000:
                        result.add("warning", "W_IMG_LARGE", f"图片宽度过大（{w}px）：{src}")
                    ratio = max(w, h) / max(min(w, h), 1)
                    if ratio > 5:
                        result.add("warning", "W_IMG_RATIO", f"超宽/超高图（{w}x{h}）：{src}")

        # 6. 内容文档 lang 正确、恰好一个 h1
        for name in names:
            if not name.endswith(".xhtml") or name.endswith(("nav.xhtml", "landmarks.xhtml")):
                continue
            content = zf.read(name).decode("utf-8")
            if "xml:lang=" not in content and "lang=" not in content:
                result.add("warning", "W_NO_LANG", f"内容文档缺少 lang：{name}")
            h1s = re.findall(r"<h1\b", content, re.IGNORECASE)
            if len(h1s) != 1:
                result.add("warning", "W_H1_COUNT", f"内容文档 h1 数量不为 1：{name}")

        # 7. 封面 meta 一致性（epub-template-spec §3）：properties 与 <meta name="cover"> 互证
        has_cover_prop = 'properties="cover-image"' in opf
        cover_meta = re.search(r'<meta name="cover" content="([^"]+)"', opf)
        if has_cover_prop and not cover_meta:
            result.add(
                "error", "E_COVER_META", 'manifest 声明 cover-image 但缺 <meta name="cover">'
            )
        elif cover_meta and not has_cover_prop:
            result.add(
                "error",
                "E_COVER_META",
                '<meta name="cover"> 指向的条目未声明 properties="cover-image"',
            )
        elif cover_meta and cover_meta.group(1) not in manifest_ids:
            result.add("error", "E_COVER_META", f"cover meta 指向未知条目：{cover_meta.group(1)}")

        # 8. 标题跳级（postprocessing-spec P2）：h1→h3 等跳级
        for name in names:
            if not name.endswith(".xhtml") or name.endswith(("nav.xhtml", "landmarks.xhtml")):
                continue
            content = zf.read(name).decode("utf-8")
            levels = [int(m) for m in re.findall(r"<h([1-6])\b", content, re.IGNORECASE)]
            for prev, cur in zip(levels, levels[1:], strict=False):
                if cur > prev + 1:
                    result.add("error", "E_HEADING_SKIP", f"标题跳级 h{prev}→h{cur}：{name}")
                    break

        # 9. 残留检查（postprocessing-spec P2）：HTML 注释=error；markdown/pandoc 标记=warning
        for name in names:
            if not name.endswith(".xhtml") or name.endswith(("nav.xhtml", "landmarks.xhtml")):
                continue
            content = strip_fingerprint_comments(zf.read(name).decode("utf-8"))
            if "<!--" in content:
                result.add("error", "E_RESIDUE", f"HTML 注释残留：{name}")
            prose = _NonCodeMarkup()
            prose.feed(content)
            content = "".join(prose.parts)
            for label, pattern in _MD_RESIDUE:
                if pattern.search(content):
                    result.add("warning", "W_RESIDUE", f"markdown 标记残留（{label}）：{name}")
                    break

        # 9b. 版面型候选（issue #38）：warning 级、供 agent 核证；不阻断、不自动改写
        for name in names:
            if not name.endswith(".xhtml") or name.endswith(("nav.xhtml", "landmarks.xhtml")):
                continue
            _layout_candidates(result, name, zf.read(name).decode("utf-8"))

        # 9c. 图注判据（T12-4）：alt / figcaption 不得是**文件名**或**占位词**
        img_refs: dict[str, list[str]] = {}
        for name in names:
            if not name.endswith(".xhtml") or name.endswith(("nav.xhtml", "landmarks.xhtml")):
                continue
            content = zf.read(name).decode("utf-8")
            for tag, attrs in re.findall(r"<(img|figure)\b([^>]*)>", content, re.IGNORECASE):
                src = re.search(r'src="([^"]+)"', attrs)
                alt = re.search(r'alt="([^"]*)"', attrs)
                caption = ""
                if tag.lower() == "figure":
                    cap = re.search(
                        r"<figcaption[^>]*>(.*?)</figcaption>", content, re.DOTALL | re.IGNORECASE
                    )
                    caption = re.sub(r"<[^>]+>", "", cap.group(1)).strip() if cap else ""
                label = (alt.group(1).strip() if alt else "") or caption
                if not label:
                    continue
                if _caption_is_filename(label):
                    result.add(
                        "error",
                        "E_CAPTION_FILENAME",
                        f"图注是文件名而非说明文字：{label!r}（{name}）",
                    )
                elif _caption_is_placeholder(label):
                    result.add(
                        "error",
                        "E_CAPTION_PLACEHOLDER",
                        f"图注是占位词：{label!r}（{name}）",
                    )
                if src:
                    img_refs.setdefault(src.group(1), []).append(name)
        # 9d. 重复图（T12-4）：同一图片文件被多处引用 → warning（是否缺陷由流程裁决）
        for src, where in sorted(img_refs.items()):
            if len(where) > 1:
                result.add(
                    "warning",
                    "W_IMAGE_DUPLICATE",
                    f"同一图片被引用 {len(where)} 次（{len(set(where))} 个文档）：{src}",
                )

        # 10. 元数据完备（postprocessing-spec P2）：次级 DC 项缺失**或空白**提示（供 agent 补全）
        missing_meta = [
            tag
            for tag in ("dc:creator", "dc:date", "dc:publisher", "dc:rights")
            if not re.search(rf"<{tag}(?:\s[^>]*)?>\s*\S[^<]*</{tag}>", opf)
        ]
        if missing_meta:
            result.add("warning", "W_META_INCOMPLETE", "DC 元数据缺失：" + "、".join(missing_meta))

        # 11. 内部锚点与脚注回链（postprocessing-spec P2；N 阶段支持跨文件回链）
        docs: dict[str, str] = {}
        ids_by_doc: dict[str, set[str]] = {}
        for name in names:
            if not name.endswith(".xhtml"):
                continue
            docs[name] = zf.read(name).decode("utf-8")
            ids_by_doc[name] = set(re.findall(r'\bid="([^"]+)"', docs[name]))
        for name, content in docs.items():
            ids = ids_by_doc[name]
            for href in re.findall(r'href="#([^"]+)"', content):
                if href not in ids:
                    result.add("error", "E_ANCHOR", f"内部锚点无法解析（#{href}）：{name}")
            for m in re.finditer(
                r'<aside[^>]*epub:type="footnote"[^>]*id="([^"]+)"[^>]*>(.*?)</aside>',
                content,
                re.DOTALL,
            ):
                fn_id, body = m.group(1), m.group(2)
                backs = re.findall(r'<a\b[^>]*epub:type="backlink"[^>]*href="([^"]+)"', body)
                if not backs and not notes_registered:
                    result.add("error", "E_FN_BACKLINK", f"脚注 {fn_id} 缺回链：{name}")
                    continue
                for href in backs:
                    file_part, _, frag = href.partition("#")
                    key = (
                        file_part
                        if not file_part or file_part.startswith("OEBPS/")
                        else f"OEBPS/{file_part}"
                    )
                    target_ids = ids_by_doc.get(key, set()) if key else ids
                    if not frag or frag not in target_ids:
                        result.add(
                            "error",
                            "E_FN_BACKLINK",
                            f"脚注 {fn_id} 回链不可解析：{name}（{href}）",
                        )
                        break

        # 13. 体积审计（postprocessing-spec P2）：告警不阻断
        total = sum(i.file_size for i in zf.infolist())
        if total > _MAX_EPUB_BYTES:
            result.add("warning", "W_EPUB_SIZE", f"EPUB 体积过大：{total // (1024 * 1024)}MB")
        for item in zf.infolist():
            if (
                Path(item.filename).suffix.lower() in _MEDIA_EXTS
                and item.file_size > _MAX_IMG_BYTES
            ):
                result.add(
                    "warning",
                    "W_IMG_UNCOMPRESSED",
                    f"图片过大（{item.file_size // 1024}KB，建议压缩）：{item.filename}",
                )

    return result
