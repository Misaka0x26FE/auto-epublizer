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

import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from html import escape, unescape
from math import isfinite
from pathlib import Path
from string import Template
from urllib.parse import quote, unquote, urlsplit
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

import pymupdf

from auto_common.workspace import source_sha256

from .pdftoc import canonical_href, inject_anchor_markers, is_toc_document, rewrite_toc
from .pdftoc import member_href as _member_href

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

_XMP_NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "aep": "https://github.com/Misaka0x26FE/auto-epublizer/ns/1.0/",
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
${first_page}
html, body { margin: 0; padding: 0; }
body { font-family: "Noto Serif CJK SC", "Songti SC", serif; font-size: ${body_pt}pt;
       line-height: ${line_height}; text-align: justify; }
p { font-size: ${body_pt}pt; line-height: ${line_height}; text-indent: 2em; margin: 0;
    text-align: justify; }
p.imgp, figure.imgfig { text-indent: 0; margin: 0.6em 0; }
figure.imgfig figcaption { font-size: ${note_pt}pt; color: #444; }
section.chapter img { max-width: 100%; max-height: ${image_height}mm; width: auto; height: auto; }
figure.imgfig img, p.imgp img { display: block; margin: 0 auto; }
h1 + figure.imgfig img, h2 + figure.imgfig img, h3 + figure.imgfig img {
    max-height: ${heading_image_height}mm; }
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
table { font-size: ${table_pt}pt; width: 100%; max-width: 100%; table-layout: fixed; }
table th, table td { overflow-wrap: anywhere; word-break: normal; }
table p { font-size: inherit; text-indent: 0; }
table.data th, table.data td { padding: 0.12em 0.4em; }
section.chapter { page-break-after: always; }
section.chapter:last-of-type { page-break-after: auto; }
section.cover { page-break-after: auto; width: 100%; height: 100%; margin: 0; padding: 0;
    display: flex; flex-direction: column; position: relative; min-height: 0; }
body > section.cover { page-break-after: always; width: ${page_width}mm; height: ${cover_height}mm; }
section.cover > section { flex: 1; min-height: 0; }
section.cover img, section.cover svg { width: 100%; height: 100%; max-width: 100%; max-height: 100%; object-fit: contain; display: block; min-height: 0; }
section.cover span.aepmark { position: absolute; top: 0; left: 0; }
h1, h2, h3, h4 { page-break-after: avoid; }
figure, table, aside { page-break-inside: avoid; }
/* 定位标记：不可见但对 PDF 文本层可检索；映射完成后 redaction 清除 */
span.aepmark { font-size: 1px; color: #ffffff; }
span.aepmark.aepanchor { font-size: 0.1px; line-height: 0; }
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

    def css(self, *, cover: bool = True) -> str:
        width, height = self.page_size_mm()
        top, outer, bottom, inner = self.margins_mm
        return Template(CSS_TEMPLATE).substitute(
            page_note=f"{width}×{height} mm（{self.size}）",
            size_css=f"{width}mm {height}mm",
            margins=f"{top}mm {outer}mm {bottom}mm {inner}mm",
            first_page="@page :first { margin: 0; }" if cover else "",
            page_width=width,
            page_height=height,
            cover_height=height - 0.5,  # Chromium 纸张取整余量，防止整页图溢出几分之一毫米
            image_height=round(
                max(1, height - top - bottom - 4 - 3 * self.note_pt * self.line_height * 25.4 / 72),
                2,
            ),
            heading_image_height=round(
                max(
                    1,
                    height
                    - top
                    - bottom
                    - 4
                    - (3 * self.note_pt * self.line_height + self.body_pt * 1.8 * 3.35) * 25.4 / 72,
                ),
                2,
            ),
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
    diagnostics: dict[str, object] = field(default_factory=dict)
    toc: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)
    artifact: dict[str, object] = field(default_factory=dict)


@dataclass
class PrintEvidence:
    toc_documents: list[dict] = field(default_factory=list)
    anchors: dict[str, str] = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)


@dataclass(slots=True)
class PublicationMetadata:
    """OPF 出版元数据的显式视图；空字段保持空，不补造。"""

    title: str = ""
    authors: list[str] = field(default_factory=list)
    translators: list[str] = field(default_factory=list)
    publisher: str = ""
    date: str = ""
    rights: str = ""
    language: str = ""
    subjects: list[str] = field(default_factory=list)
    description: str = ""
    identifier: str = ""

    def source(self) -> dict[str, object]:
        return {
            "title": self.title,
            "authors": list(self.authors),
            "translators": list(self.translators),
            "publisher": self.publisher,
            "date": self.date,
            "rights": self.rights,
            "language": self.language,
            "subjects": list(self.subjects),
            "description": self.description,
            "identifier": self.identifier,
        }


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
    cover_href: str | None = None
    toc_hrefs: set[str] = field(default_factory=set)
    metadata: PublicationMetadata = field(default_factory=PublicationMetadata)


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
            member = _member_href(full_path)
            if member is None:
                raise ValueError(f"包文档路径越界或非法：{full_path}")
            path = work / member
            if not path.resolve().is_relative_to(work.resolve()):
                raise ValueError(f"包文档路径越界或非法：{full_path}")
            if path.is_file():
                return path
    raise ValueError("container.xml 未指向存在的包文档")


def _landmark_hrefs(
    opf: ET.Element, root: Path, manifest: dict[str, dict[str, str]], *, owner: str, role: str
) -> set[str]:
    declared: set[str] = set()
    for ref in opf.iterfind(".//opf:guide/opf:reference", _NS):
        if ref.get("type") == role:
            href = _member_href(ref.get("href") or "", owner)
            if href:
                declared.add(href)
    for item in manifest.values():
        if "nav" not in item["properties"].split():
            continue
        path = root / item["href"]
        if not path.is_file():
            continue
        try:
            nav = ET.fromstring(path.read_bytes())
        except ET.ParseError:
            continue
        for link in nav.iter():
            if role in (link.get("{http://www.idpf.org/2007/ops}type") or "").split():
                href = _member_href(link.get("href") or "", item["href"])
                if href:
                    declared.add(href)
    return declared


def _cover_spine(
    opf: ET.Element,
    root: Path,
    manifest: dict[str, dict[str, str]],
    *,
    opf_owner: str = "",
) -> tuple[list[tuple[str, str]], str | None]:
    """印刷顺序：语义封面或登记封面图优先，其余仅保留线性正文。"""
    cover_ids = {
        key for key, item in manifest.items() if "cover-image" in item["properties"].split()
    }
    if not cover_ids:
        cover_ids = {
            el.get("content")
            for el in opf.iterfind(".//opf:metadata/opf:meta", _NS)
            if el.get("name") == "cover" and el.get("content") in manifest
        }
    if len(cover_ids) > 1:
        raise ValueError("包文档存在多个封面图身份，须先核证唯一封面")
    image_id = next(iter(cover_ids), None)
    image_href = manifest[image_id]["href"] if image_id else None
    epub_type = "{http://www.idpf.org/2007/ops}type"
    declared = _landmark_hrefs(opf, root, manifest, owner=opf_owner, role="cover")
    refs: list[tuple[str, str, bool]] = []
    candidates: list[tuple[str, str]] = []
    for ref in opf.iterfind(".//opf:spine/opf:itemref", _NS):
        key = ref.get("idref") or ""
        if key not in manifest:
            raise ValueError(f"spine 引用未登记的 manifest id：{key}")
        href = manifest[key]["href"]
        nonlinear = (ref.get("linear") or "").lower() == "no"
        refs.append((key, href, nonlinear))
        path = root / href
        if not path.is_file():
            if href in declared:
                candidates.append((key, href))
            continue
        try:
            document = ET.fromstring(path.read_bytes())
        except ET.ParseError:
            continue
        semantic = href in declared or any(
            "cover" in (el.get(epub_type) or "").split() for el in document.iter()
        )
        images = [
            _member_href(
                el.get("src")
                or el.get("href")
                or el.get("{http://www.w3.org/1999/xlink}href")
                or "",
                href,
            )
            for el in document.iter()
            if el.tag.rsplit("}", 1)[-1] in ("img", "image")
        ]
        has_prose = any(
            el.tag.rsplit("}", 1)[-1] == "p" and "".join(el.itertext()).strip()
            for el in document.iter()
        )
        if semantic or (
            image_href
            and image_href in images
            and (nonlinear or (len(refs) == 1 and not has_prose))
        ):
            candidates.append((key, href))
    if len(candidates) > 1:
        raise ValueError("封面内容文档身份有歧义：" + "、".join(href for _, href in candidates))
    cover = candidates[0] if candidates else ((image_id, image_href) if image_id else None)
    spine = [(key, href) for key, href, nonlinear in refs if not nonlinear and (key, href) != cover]
    if cover:
        spine.insert(0, cover)
    return spine, cover[1] if cover else None


def _parse_opf(opf_path: Path, *, archive_root: Path | None = None) -> Package:
    """解析 OPF（命名空间感知）；spine 文档缺失/坏 XML 都是可预期错误。"""
    try:
        root = ET.fromstring(opf_path.read_bytes())
    except ET.ParseError as exc:
        raise ValueError(f"包文档不是合法 XML：{exc}") from None
    archive_root = (archive_root or opf_path.parent).resolve()
    if not opf_path.resolve().is_relative_to(archive_root):
        raise ValueError("包文档路径越界")
    owner = opf_path.resolve().relative_to(archive_root).as_posix()
    manifest: dict[str, dict[str, str]] = {}
    nav_href: str | None = None
    for item in root.iterfind(".//opf:manifest/opf:item", _NS):
        item_id = item.get("id") or ""
        href = _member_href(item.get("href") or "", owner)
        if not item_id or not href:
            raise ValueError("manifest id/href 缺失或不是合法包内路径")
        properties = (item.get("properties") or "").split()
        manifest[item_id] = {
            "href": href,
            "media-type": item.get("media-type") or "",
            "properties": " ".join(properties),
        }
        if "nav" in properties and nav_href is None:
            nav_href = href
    spine, cover_href = _cover_spine(root, archive_root, manifest, opf_owner=owner)
    if not spine:
        raise ValueError("包文档 spine 为空，无内容可排版")

    # 出版元数据：空字段保持空；译者单列，不混入作者
    roles: dict[str, str] = {}
    for meta in root.iterfind(".//opf:metadata/opf:meta", _NS):
        refines = meta.get("refines") or ""
        property_ = meta.get("property") or ""
        if property_ == "role" and refines.startswith("#"):
            roles[refines[1:]] = (meta.text or "").strip()

    def dc_text(tag: str) -> str:
        for element in root.iterfind(f".//dc:{tag}", _NS):
            value = (element.text or "").strip()
            if value:
                return value
        return ""

    def dc_values(tag: str) -> list[str]:
        return [
            (element.text or "").strip()
            for element in root.iterfind(f".//dc:{tag}", _NS)
            if (element.text or "").strip()
        ]

    authors: list[str] = []
    translators: list[str] = []
    for creator in root.iterfind(".//dc:creator", _NS):
        name = (creator.text or "").strip()
        if not name:
            continue
        role = (creator.get(f"{{{_NS['opf']}}}role") or "").strip()
        role = role or roles.get(creator.get("id") or "", "")
        if role == "trl":  # 译者单列，不冒充作者
            translators.append(name)
        else:
            authors.append(name)
    publication = PublicationMetadata(
        title=dc_text("title"),
        authors=authors,
        translators=translators,
        publisher=dc_text("publisher"),
        date=dc_text("date"),
        rights=dc_text("rights"),
        language=dc_text("language"),
        subjects=dc_values("subject"),
        description=dc_text("description"),
        identifier=dc_text("identifier"),
    )
    return Package(
        root=archive_root,
        opf_dir=opf_path.parent,
        spine=spine,
        nav_href=nav_href,
        manifest=manifest,
        title=publication.title,
        author="; ".join(publication.authors),
        cover_href=cover_href,
        toc_hrefs=_landmark_hrefs(root, archive_root, manifest, owner=owner, role="toc"),
        metadata=publication,
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

    def one_tag(tag_match: re.Match[str]) -> str:
        tag = tag_match.group(0)

        def one_attr(attr_match: re.Match[str]) -> str:
            attr, value = attr_match.group(1), attr_match.group(2)
            if not value or value.startswith(("#", "data:")):
                return attr_match.group(0)
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value) or value.startswith("//"):
                notes.append(f"丢弃远程资源引用：{chapter_href}:{value}")
                return ""
            joined = _member_href(value, chapter_href)
            if joined is None:
                notes.append(f"丢弃包外/缺失资源：{chapter_href}:{value}")
                return ""
            target = (root / joined).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                notes.append(f"丢弃包外/缺失资源：{chapter_href}:{value}")
                return ""
            fragment = urlsplit(value).fragment
            uri = quote(joined, safe="/") + (f"#{fragment}" if fragment else "")
            return f'{attr}="{escape(uri, quote=True)}"'

        return RES_ATTR_RE.sub(one_attr, tag)

    return RES_TAG_RE.sub(one_tag, inner)


def build_print_html(
    package: Package,
    style: PrintStyle,
    *,
    page_map: dict[str, int] | None = None,
    evidence: PrintEvidence | None = None,
    marker_prefix: str = "AEPMARK",
) -> tuple[Path, int]:
    """把 spine 顺序拼成一份印刷 HTML；缺失 spine 文档直接报错（不静默跳过）。"""
    root = package.root
    parts: list[str] = []
    notes: list[str] = []
    evidence = evidence if evidence is not None else PrintEvidence()
    outline = nav_entries(
        package.root / package.nav_href if package.nav_href else None, owner_href=package.nav_href
    )
    for index, (item_id, href) in enumerate(package.spine, start=1):
        doc_path = root / href
        if not doc_path.is_file():
            raise ValueError(f"spine 文档缺失：{href}")
        marker = f'<span class="aepmark">{_marker(index, prefix=marker_prefix)}</span>'
        if href == package.cover_href and package.manifest[item_id]["media-type"].startswith(
            "image/"
        ):
            parts.append(
                f'<section class="cover">{marker}<img src="{escape(quote(href, safe="/"), quote=True)}" alt="封面"/></section>'
            )
            continue
        html = doc_path.read_text(encoding="utf-8")
        body = BODY_RE.search(html)
        if not body:
            raise ValueError(f"spine 文档没有 body：{href}")
        inner = _rewrite_resources(prepare_asides(body.group(1)), href, root, notes)
        inner = _strip_active(inner)
        title_match = TITLE_RE.search(html)
        title = unescape(title_match.group(1)) if title_match else ""
        if is_toc_document(inner, title=title, declared=href in package.toc_hrefs):
            record = {"document": href, "updates": [], "findings": []}
            if page_map is not None:
                rewritten = rewrite_toc(inner, outline, page_map, owner_href=href)
                inner = rewritten.html
                record.update(updates=rewritten.updates, findings=rewritten.findings)
                evidence.findings.extend(rewritten.findings)
            evidence.toc_documents.append(record)
        positioned = inject_anchor_markers(
            inner, outline, owner_href=href, prefix=marker_prefix + "A"
        )
        inner = positioned.html
        evidence.anchors.update(positioned.markers)
        evidence.findings.extend(positioned.findings)
        if href == package.cover_href:
            parts.append(f'<section class="cover">{marker}{inner}</section>')
            continue
        parts.append(f'<section class="chapter">{marker}{inner}</section>')
    # 样式表：按包内声明选第一个 text/css（多章子目录也不做首章猜测）
    stylesheet = next(
        (item["href"] for item in package.manifest.values() if item["media-type"] == "text/css"),
        None,
    )
    link = (
        f'<link rel="stylesheet" type="text/css" href="{escape(quote(stylesheet, safe="/"), quote=True)}"/>'
        if stylesheet
        else ""
    )
    html = (
        '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8"/>\n'
        f"<title>{escape(package.title)}</title>\n{link}\n<style>{style.css(cover=package.cover_href is not None)}</style>\n</head><body>\n"
        + "\n".join(parts)
        + "\n</body></html>"
    )
    target = root / "print.html"
    target.write_text(html, encoding="utf-8")
    if notes:
        target.with_suffix(".notes.txt").write_text("\n".join(notes), encoding="utf-8")
    else:
        target.with_suffix(".notes.txt").unlink(missing_ok=True)
    return target, len(parts)


def nav_entries(
    nav_path: Path | None, *, owner_href: str | None = None
) -> list[tuple[int, str, str]]:
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
                            href = sub.get("href") or ""
                            if owner_href is not None:
                                href = canonical_href(href, owner_href) or href
                            entries.append((max(1, level), title, href))
                    elif sub_tag in ("ol", "ul"):
                        walk(sub, level + 1)

    walk(toc, 0)
    return entries


def _marker(index: int, *, prefix: str = "AEPMARK") -> str:
    return f"{prefix}{index:04d}"


def _section_pages(
    doc: pymupdf.Document, sections: int, *, prefix: str = "AEPMARK"
) -> dict[int, int]:
    """按不可见标记定位每个区段的起始页（标记写入 HTML，PDF 文本层可检索）。"""
    pages: dict[int, int] = {}
    for index in range(doc.page_count):
        text = doc[index].get_text()
        for number in range(1, sections + 1):
            if number in pages:
                continue
            if _marker(number, prefix=prefix) in re.sub(r"\s+", "", text):
                pages[number] = index + 1
    return pages


def _anchor_pages(
    doc: pymupdf.Document, markers: dict[str, str]
) -> tuple[dict[str, int], list[dict]]:
    hits: dict[str, list[int]] = {identity: [] for identity in markers}
    for page in doc:
        text = re.sub(r"\s+", "", page.get_text())
        for identity, marker in markers.items():
            hits[identity].extend([page.number + 1] * text.count(marker))
    pages = {identity: found[0] for identity, found in hits.items() if len(found) == 1}
    findings = [
        {"level": "error", "code": "E_PDF_ANCHOR_UNLOCATED", "href": identity, "pages": found}
        for identity, found in hits.items()
        if len(found) != 1
    ]
    return pages, findings


def _clear_markers(
    doc: pymupdf.Document,
    sections: int,
    *,
    extra: list[str] | None = None,
    prefix: str = "AEPMARK",
) -> None:
    """映射完成后 redaction 清除本次定位标记（D2：标记不留进成品）。"""
    needles = [_marker(number, prefix=prefix) for number in range(1, sections + 1)] + (extra or [])
    for index in range(doc.page_count):
        page = doc[index]
        hits: list[pymupdf.Rect] = []
        for needle in needles:
            hits.extend(page.search_for(needle))
        if not hits:
            continue
        for rect in hits:
            page.add_redact_annot(rect, fill=False)
        page.apply_redactions(images=0, graphics=0)


def attach_outline(
    doc: pymupdf.Document,
    entries: list[tuple[int, str, str]],
    *,
    spine: list[tuple[str, str]],
    section_pages: dict[int, int],
    notes: list[str],
    cover: bool,
    target_pages: dict[str, int] | None = None,
) -> list[list[object]]:
    """nav 条目 → PDF 书签；文档级条目用区段起始页，片段级在区段页内找标题。"""
    href_to_section = {
        posixpath.normpath(href): index for index, (_item_id, href) in enumerate(spine, start=1)
    }
    toc: list[list[object]] = [[1, "封面", 1]] if cover else []
    for level, title, href in entries:
        fragment = unquote(urlsplit(href).fragment)
        target = _member_href(href)
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
            found = (target_pages or {}).get(canonical_href(href))
            if found is None:
                notes.append(
                    f"书签未定位（缺少真实 fragment 位置，不猜区段起始页）：{title} → {href}"
                )
                continue
            page = found
        toc.append([level, title, page])
    return toc


def stamp_folios(doc: pymupdf.Document, *, font_size: float = 9, cover: bool = True) -> None:
    """Number every page but the cover, centred in the bottom margin."""
    for index in range(1 if cover else 0, doc.page_count):
        page = doc[index]
        page.insert_text(
            (page.rect.width / 2 - 6, page.rect.height - 18),
            str(index + 1),
            fontsize=font_size,
            fontname="helv",
            color=(0.35, 0.35, 0.35),
        )


def _render_chromium(target: Path, raw: Path, browser: str, timeout: float) -> None:
    if timeout <= 0:
        raise RuntimeError("排版超时：多遍渲染已耗尽总时间预算")
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
        raise RuntimeError("排版超时：Chromium 未在限时内产出 PDF") from None
    except OSError as exc:
        raise RuntimeError(f"无法启动浏览器排版：{exc}") from None
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(
            f"Chromium 排版失败（退出码 {completed.returncode}）：{detail[-1] if detail else ''}"
        )
    if not raw.is_file() or raw.stat().st_size == 0:
        raise RuntimeError("Chromium 未产出 PDF（进程成功但没有文件）")
    if raw.read_bytes()[:5] != b"%PDF-":
        raise RuntimeError("Chromium 产物不是 PDF")


def _publish_pdf(staged: Path, out: Path) -> None:
    """完成全部后处理后才同目录原子替换，失败只清理本次唯一临时件。"""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=out.parent, prefix=f".{out.name}.", suffix=".part", delete=False
        ) as handle:
            temporary = Path(handle.name)
            with staged.open("rb") as source:
                shutil.copyfileobj(source, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, out)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _xmp_alt(tag: str, value: str) -> str:
    return (
        f'<dc:{tag}><rdf:Alt><rdf:li xml:lang="x-default">'
        f"{xml_escape(value)}</rdf:li></rdf:Alt></dc:{tag}>"
    )


def _xmp_seq(tag: str, values: list[str], *, prefix: str = "dc") -> str:
    if not values:
        return ""
    items = "".join(f"<rdf:li>{xml_escape(value)}</rdf:li>" for value in values)
    return f"<{prefix}:{tag}><rdf:Seq>{items}</rdf:Seq></{prefix}:{tag}>"


def _xmp_bag(tag: str, values: list[str], *, prefix: str = "dc") -> str:
    if not values:
        return ""
    items = "".join(f"<rdf:li>{xml_escape(value)}</rdf:li>" for value in values)
    return f"<{prefix}:{tag}><rdf:Bag>{items}</rdf:Bag></{prefix}:{tag}>"


def _build_xmp(meta: PublicationMetadata, generated_at: str) -> str:
    """完整出版信息进 XMP；Info 只承担标准短字段，权利声明不截断。"""
    fields = [
        _xmp_alt("title", meta.title) if meta.title else "",
        _xmp_seq("creator", meta.authors),
        _xmp_seq("contributor", meta.translators),
        _xmp_seq("translators", meta.translators, prefix="aep"),
        _xmp_bag("publisher", [meta.publisher]) if meta.publisher else "",
        _xmp_seq("date", [meta.date]) if meta.date else "",
        _xmp_alt("rights", meta.rights) if meta.rights else "",
        _xmp_bag("language", [meta.language]) if meta.language else "",
        _xmp_alt("description", meta.description) if meta.description else "",
        _xmp_bag("subject", meta.subjects),
        _xmp_bag("identifier", [meta.identifier]) if meta.identifier else "",
        f"<xmp:CreateDate>{xml_escape(generated_at)}</xmp:CreateDate>",
        f"<xmp:MetadataDate>{xml_escape(generated_at)}</xmp:MetadataDate>",
        "<xmp:CreatorTool>auto-epublizer</xmp:CreatorTool>",
        "<pdf:Producer>auto-epublizer</pdf:Producer>",
    ]
    body = "\n   ".join(field for field in fields if field)
    return (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '  <rdf:Description rdf:about="" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
        'xmlns:pdf="http://ns.adobe.com/pdf/1.3/" '
        'xmlns:aep="https://github.com/Misaka0x26FE/auto-epublizer/ns/1.0/">\n'
        f"   {body}\n"
        "  </rdf:Description>\n"
        " </rdf:RDF>\n"
        "</x:xmpmeta>\n"
        '<?xpacket end="w"?>'
    )


def _read_xmp(xml: str) -> dict[str, object]:
    """读回已写入的 XMP；解析失败不回退成“已保全”猜测。"""
    empty: dict[str, object] = {
        "title": "",
        "creators": [],
        "translators": [],
        "publishers": [],
        "dates": [],
        "rights": "",
        "languages": [],
        "subjects": [],
        "description": "",
        "identifiers": [],
        "create_date": "",
    }
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return empty

    def values(path: str) -> list[str]:
        return [
            element.text or ""
            for element in root.iterfind(path, _XMP_NS)
            if (element.text or "").strip()
        ]

    def first(path: str) -> str:
        found = values(path)
        return found[0] if found else ""

    return {
        "title": first(".//dc:title//rdf:li"),
        "creators": values(".//dc:creator//rdf:li"),
        "translators": values(".//aep:translators//rdf:li"),
        "publishers": values(".//dc:publisher//rdf:li"),
        "dates": values(".//dc:date//rdf:li"),
        "rights": first(".//dc:rights//rdf:li"),
        "languages": values(".//dc:language//rdf:li"),
        "subjects": values(".//dc:subject//rdf:li"),
        "description": first(".//dc:description//rdf:li"),
        "identifiers": values(".//dc:identifier//rdf:li"),
        "create_date": first(".//xmp:CreateDate"),
    }


def _pdf_date(moment: datetime) -> str:
    return moment.strftime("D:%Y%m%d%H%M%S+00'00'")


def _apply_publication_metadata(
    doc: pymupdf.Document, meta: PublicationMetadata, generated_at: str
) -> dict[str, object]:
    """写 Info 短字段 + 完整 XMP，并读回实际值作为证据。"""
    info: dict[str, str] = {}
    if meta.title:
        info["title"] = meta.title
    if meta.authors:
        info["author"] = "; ".join(meta.authors)
    if meta.description:
        info["subject"] = meta.description
    if meta.subjects:
        info["keywords"] = "; ".join(meta.subjects)
    moment = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    info.update(
        creator="auto-epublizer",
        producer="auto-epublizer",
        creationDate=_pdf_date(moment),
        modDate=_pdf_date(moment),
    )
    xmp = _build_xmp(meta, generated_at)
    doc.set_metadata(info)
    doc.set_xml_metadata(xmp)
    return {
        "source": meta.source(),
        "generated_at": generated_at,
        "info_written": info,
        "info_readback": {key: doc.metadata.get(key, "") for key in info},
        "xmp_sha256": sha256(xmp.encode("utf-8")).hexdigest(),
        "xmp_readback": _read_xmp(doc.get_xml_metadata()),
        "info_mapping": {
            "title": "dc:title",
            "author": "dc:creator（作者，分号连接；译者不入作者）",
            "subject": "dc:description（无描述时留空）",
            "keywords": "dc:subject（分号连接）",
            "creationDate": "生成时间（不是 dc:date 出版日期）",
            "modDate": "生成时间",
            "creator": "auto-epublizer",
            "producer": "auto-epublizer",
        },
        "xmp_mapping": {
            "title": "dc:title",
            "creators": "dc:creator",
            "translators": "aep:translators",
            "publishers": "dc:publisher",
            "dates": "dc:date",
            "rights": "dc:rights（完整原文，不截断）",
            "languages": "dc:language",
            "subjects": "dc:subject",
            "description": "dc:description",
            "identifiers": "dc:identifier",
            "create_date": "xmp:CreateDate（生成时间）",
        },
    }


MANIFEST_SCHEMA = "auto-epublizer/pdf-artifact/v1"


def manifest_path(pdf: str | Path) -> Path:
    path = Path(pdf)
    return path.with_name(path.name + ".manifest.json")


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def verify_pdf_artifact(pdf: str | Path) -> dict[str, object]:
    """按派生件清单核对 PDF/源 EPUB 字节；清单缺失或字节改动明确失败。"""
    path = Path(pdf)
    sidecar = manifest_path(path)
    try:
        manifest = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            "ok": False,
            "pdf": str(path),
            "manifest": str(sidecar),
            "error": f"派生清单不可读：{exc}",
            "checks": [],
        }
    checks: list[dict[str, object]] = []

    def check(name: str, expected: object, actual: object) -> None:
        checks.append(
            {"name": name, "ok": expected == actual, "expected": expected, "actual": actual}
        )

    check("schema", MANIFEST_SCHEMA, manifest.get("schema"))
    if not path.is_file():
        checks.append({"name": "pdf_present", "ok": False, "expected": True, "actual": False})
    else:
        data = path.read_bytes()
        check("pdf_sha256", (manifest.get("pdf") or {}).get("sha256"), sha256(data).hexdigest())
        check("pdf_bytes", (manifest.get("pdf") or {}).get("bytes"), len(data))
        try:
            with pymupdf.open(path) as doc:
                check("pdf_pages", (manifest.get("pdf") or {}).get("pages"), doc.page_count)
        except Exception as exc:  # PyMuPDF 对损坏件抛多种异常
            checks.append(
                {"name": "pdf_readable", "ok": False, "expected": True, "actual": str(exc)}
            )
    epub = Path(str((manifest.get("epub") or {}).get("path") or ""))
    if epub.is_file():
        check("epub_sha256", (manifest.get("epub") or {}).get("sha256"), source_sha256(epub))
        check("epub_bytes", (manifest.get("epub") or {}).get("bytes"), epub.stat().st_size)
    else:
        checks.append(
            {"name": "epub_present", "ok": False, "expected": str(epub), "actual": "missing"}
        )
    return {
        "ok": all(bool(item["ok"]) for item in checks),
        "pdf": str(path),
        "manifest": str(sidecar),
        "checks": checks,
    }


def render(
    epub: Path,
    out: Path,
    style: PrintStyle | None = None,
    *,
    bookmarks: bool = True,
    chromium: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    strict: bool = False,
) -> PdfResult:
    """Render ``epub`` to ``out``; 失败抛 ``ValueError``/``RuntimeError``（中文信息）。"""
    style = style or PrintStyle()
    style.validate()
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
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
    deadline = time.monotonic() + timeout
    with tempfile.TemporaryDirectory(prefix="aep-pdf-") as tmp:
        work = Path(tmp)
        try:
            with zipfile.ZipFile(epub) as archive:
                _safe_extract(archive, work)
        except zipfile.BadZipFile as exc:
            raise ValueError(f"不是有效的 EPUB/ZIP：{exc}") from None
        package = _parse_opf(_opf_path(work), archive_root=work)
        marker_prefix = "AEPPOS" + source_sha256(epub)[:16].upper()
        for item in package.manifest.values():
            path = package.root / item["href"]
            if not path.is_file() or item["media-type"] not in {
                "application/xhtml+xml",
                "text/html",
                "image/svg+xml",
                "text/css",
            }:
                continue
            if marker_prefix in unescape(path.read_text(encoding="utf-8", errors="replace")):
                marker_prefix += "X"
        previous: dict[str, int] | None = None
        seen: list[dict[str, int]] = []
        for round_no in range(1, 4):
            evidence = PrintEvidence()
            target, sections = build_print_html(
                package,
                style,
                page_map=previous,
                evidence=evidence,
                marker_prefix=marker_prefix,
            )
            raw = work / f"raw-{round_no}.pdf"
            _render_chromium(target, raw, browser, deadline - time.monotonic())
            with pymupdf.open(raw) as located:
                section_pages = _section_pages(located, sections, prefix=marker_prefix)
                target_pages = {
                    quote(href, safe="/"): section_pages[index]
                    for index, (_, href) in enumerate(package.spine, start=1)
                    if index in section_pages
                }
                anchor_pages, anchor_findings = _anchor_pages(located, evidence.anchors)
                target_pages.update(anchor_pages)
                evidence.findings.extend(anchor_findings)
            if not evidence.toc_documents or (previous is not None and previous == target_pages):
                break
            if round_no == 3 or target_pages in seen:
                raise ValueError(
                    "E_PDF_TOC_UNSTABLE：目录页码在最多三遍排版内未收敛，旧 PDF 保持不变"
                )
            seen.append(target_pages)
            previous = target_pages
        notes_path = target.with_suffix(".notes.txt")
        if notes_path.is_file():
            notes.extend(notes_path.read_text(encoding="utf-8").splitlines())
        from .pdfdiagnostics import collect_font_samples, diagnose_pdf

        with pymupdf.open(raw) as check:
            diagnostics = diagnose_pdf(
                check,
                samples=collect_font_samples(target.read_text(encoding="utf-8")),
                body_pt=style.body_pt,
                note_pt=style.note_pt,
                size_mm=style.page_size_mm(),
                margins_mm=style.margins_mm,
                cover=package.cover_href is not None,
                marker_values={
                    _marker(index, prefix=marker_prefix) for index in range(1, sections + 1)
                }
                | set(evidence.anchors.values()),
            )
        for finding in diagnostics["findings"]:
            notes.append(f"排版诊断 {finding['code']}：{finding}")
        for finding in evidence.findings:
            notes.append(f"目录/锚点诊断 {finding['code']}：{finding}")
        all_findings = diagnostics["findings"] + evidence.findings
        if strict and any(f["level"] == "error" for f in all_findings):
            codes = sorted({f["code"] for f in all_findings if f["level"] == "error"})
            raise ValueError("严格排版检查未通过：" + "、".join(codes))
        outline = nav_entries(
            package.root / package.nav_href if package.nav_href else None,
            owner_href=package.nav_href,
        )

        cover = package.cover_href is not None
        with pymupdf.open(raw) as doc:
            _clear_markers(
                doc,
                sections,
                extra=list(evidence.anchors.values()),
                prefix=marker_prefix,
            )
            stamp_folios(doc, cover=cover)
            written = 0
            if bookmarks:
                toc = attach_outline(
                    doc,
                    outline,
                    spine=package.spine,
                    section_pages=section_pages,
                    notes=notes,
                    cover=cover,
                    target_pages=target_pages,
                )
                doc.set_toc(toc)
                written = len(toc)
            metadata_report = _apply_publication_metadata(doc, package.metadata, generated_at)
            pages = doc.page_count
            staged = work / "final.pdf"
            doc.save(staged, garbage=4, deflate=True)
        _publish_pdf(staged, out)

    pdf_bytes = out.stat().st_size
    pdf_digest = source_sha256(out)
    epub_bytes = epub.stat().st_size
    epub_digest = source_sha256(epub)
    artifact = {
        "schema": MANIFEST_SCHEMA,
        "generated_at": generated_at,
        "epub": {
            "path": str(epub.resolve()),
            "name": epub.name,
            "sha256": epub_digest,
            "bytes": epub_bytes,
        },
        "pdf": {
            "path": str(out.resolve()),
            "name": out.name,
            "sha256": pdf_digest,
            "bytes": pdf_bytes,
            "pages": pages,
        },
        "parameters": {
            "size": style.size,
            "size_mm": list(style.page_size_mm()),
            "margins_mm": list(style.margins_mm),
            "body_pt": style.body_pt,
            "note_pt": style.note_pt,
            "line_height": style.line_height,
            "bookmarks": bookmarks,
            "strict": strict,
        },
        "metadata": metadata_report,
        "diagnostics": {
            "status": diagnostics.get("status"),
            "overflow_count": diagnostics.get("overflow_count"),
            "overflow_pages": diagnostics.get("overflow_pages"),
        },
        "toc": {
            "converged": True,
            "rounds": round_no,
            "documents": evidence.toc_documents,
            "findings": evidence.findings,
        },
    }
    _write_manifest(manifest_path(out), artifact)
    return PdfResult(
        out=out,
        pages=pages,
        sections=sections,
        bookmarks=written,
        size_mm=style.page_size_mm(),
        notes=notes,
        diagnostics=diagnostics,
        toc={
            "converged": True,
            "rounds": round_no,
            "documents": evidence.toc_documents,
            "findings": evidence.findings,
            "target_pages": target_pages,
        },
        metadata=metadata_report,
        artifact=artifact,
    )
