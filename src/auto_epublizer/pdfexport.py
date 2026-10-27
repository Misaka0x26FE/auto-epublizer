# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 auto-epublizer contributors
"""Built EPUB → print PDF (headless Chromium), for paper-like reading.

Why Chromium and not LaTeX/pandoc: the book already exists as per-unit XHTML plus one
stylesheet, and the browser renders exactly that — including tables, images and CJK
line breaking. This module unpacks the EPUB, concatenates the spine into one HTML with
print `@page` rules, prints it with ``--print-to-pdf``, then stamps the page folios and
the outline with PyMuPDF (Chromium emits neither).

The typography follows Chinese scholarly practice for a translated monograph rather
than browser defaults: 大 32 开 page, 五号 body (10.5 pt) with 1.55 line height,
小五 notes (8.5 pt) with the note number inline, 2-em first-line indent, no paragraph
gaps. Screen-only affordances (link colours, back-link arrows) are dropped.

Boundary: this produces a *derived* artifact. The EPUB remains the delivery format;
the PDF is regenerated from it, never edited, and it is not part of the QA digest.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
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


def _package(work: Path) -> tuple[Path, dict[str, str], list[tuple[str, str]], set[str]]:
    """Return (oebps dir, manifest id→href, spine [(id, href)], nav item ids)."""
    opf_path = next(work.rglob("*.opf"))
    opf = opf_path.read_text(encoding="utf-8")
    manifest: dict[str, str] = {}
    for m in re.finditer(r"<item\b[^>]*>", opf):
        tag = m.group(0)
        id_ = re.search(r'\bid="([^"]+)"', tag)
        href = re.search(r'\bhref="([^"]+)"', tag)
        if id_ and href:
            manifest[id_.group(1)] = href.group(1)
    nav_ids: set[str] = set()
    for m in re.finditer(r"<item\b[^>]*>", opf):
        tag = m.group(0)
        props = re.search(r'\bproperties="([^"]*)"', tag)
        mid = re.search(r'\bid="([^"]+)"', tag)
        if props and mid and "nav" in props.group(1).split():
            nav_ids.add(mid.group(1))
    spine_block = re.search(r"<spine[^>]*>(.*?)</spine>", opf, re.S)
    spine: list[tuple[str, str]] = []
    for m in re.finditer(
        r'<itemref\b[^>]*idref="([^"]+)"', spine_block.group(1) if spine_block else ""
    ):
        ref = m.group(1)
        if ref in nav_ids:
            continue
        href = manifest.get(ref)
        if href:
            spine.append((ref, href))
    return opf_path.parent, manifest, spine, nav_ids


def _metadata(opf_dir: Path) -> dict[str, str]:
    """dc:title / dc:creator straight from the package document."""
    opf_path = next(opf_dir.glob("*.opf"))
    out: dict[str, str] = {}
    try:
        root = ET.fromstring(opf_path.read_bytes())
    except ET.ParseError:
        # 包文档不是合法 XML（缺命名空间声明等）时退回正则：宁可少字段，不可丢标题
        raw = opf_path.read_text(encoding="utf-8", errors="replace")
        title = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", raw, re.S)
        if title and title.group(1).strip():
            out["title"] = re.sub(r"<[^>]+>", "", title.group(1)).strip()
        authors = [
            re.sub(r"<[^>]+>", "", m.group(2)).strip()
            for m in re.finditer(r"<dc:creator\b([^>]*)>(.*?)</dc:creator>", raw, re.S)
            if 'role="trl"' not in m.group(1)
        ]
        if authors:
            out["author"] = "; ".join(a for a in authors if a)
        return out
    ns = {"dc": "http://purl.org/dc/elements/1.1/", "opf": "http://www.idpf.org/2007/opf"}
    title = root.find(".//dc:title", ns)
    authors: list[str] = []
    for element in root.findall(".//dc:creator", ns):
        name = (element.text or "").strip()
        role = (element.get(f"{{{ns['opf']}}}role") or "").strip()
        if name and role != "trl":  # 译者单列，不冒充作者
            authors.append(name)
    if title is not None and (title.text or "").strip():
        out["title"] = title.text.strip()
    if authors:
        out["author"] = "; ".join(authors)
    return out


def prepare_asides(html: str) -> str:
    """Print notes the way books print them: no back-link arrow, number inline."""

    def one(match: re.Match[str]) -> str:
        block = BACKLINK_RE.sub("", match.group(0))
        return FNLABEL_RE.sub(
            lambda m: f'<p class="fn"><span class="fnnum">[{m.group(1)}]</span> ', block
        )

    return ASIDE_RE.sub(one, html)


def build_print_html(oebps: Path, style: PrintStyle) -> tuple[Path, int]:
    """Concatenate the spine into one print HTML; returns (file, section count)."""
    _opf_dir, _manifest, spine, _nav = _package(oebps)
    parts: list[str] = []
    for index, (ref, href) in enumerate(spine):
        doc_path = oebps / href
        if not doc_path.is_file():
            continue
        html = doc_path.read_text(encoding="utf-8")
        body = BODY_RE.search(html)
        if not body:
            continue
        inner = prepare_asides(body.group(1))
        if ref == "cover" or (index == 0 and "cover" in href.lower()):
            image = IMG_RE.search(inner)
            if image:
                prefix = href.rsplit("/", 1)[0] + "/" if "/" in href else ""
                parts.append(
                    f'<section class="cover"><img src="{prefix}{image.group(1)}"/></section>'
                )
                continue
        parts.append(f'<section class="chapter">{inner}</section>')
    first = spine[0][1] if spine else ""
    prefix = first.rsplit("/", 1)[0] + "/" if "/" in first else ""
    sheet = oebps / f"{prefix}style.css"
    link = (
        f'<link rel="stylesheet" type="text/css" href="{prefix}style.css"/>'
        if sheet.is_file()
        else ""
    )
    title = TITLE_RE.search((oebps / first).read_text(encoding="utf-8")) if first else None
    html = (
        '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8"/>\n'
        f"<title>{title.group(1) if title else ''}</title>\n"
        f"{link}\n<style>{style.css()}</style>\n</head><body>\n"
        + "\n".join(parts)
        + "\n</body></html>"
    )
    target = oebps / "print.html"
    target.write_text(html, encoding="utf-8")
    return target, len(parts)


def nav_entries(oebps: Path) -> list[tuple[int, str, str]]:
    """``nav.xhtml`` → (level, title, href); ``<ol>`` nesting depth is the level."""
    nav = next((p for p in oebps.glob("nav.xhtml")), None) or next(
        (p for p in oebps.glob("*.xhtml") if "nav" in p.name.lower()), None
    )
    if nav is None:
        return []
    body = BODY_RE.search(nav.read_text(encoding="utf-8"))
    if not body:
        return []
    entries: list[tuple[int, str, str]] = []
    level = 0
    for token in re.finditer(
        r"<ol\b|</ol>|(?P<a><a\b[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>)", body.group(1), re.S | re.I
    ):
        chunk = token.group(0)
        if token.group("a") is None:
            level = level + 1 if chunk.startswith("<ol") else max(1, level - 1)
            continue
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", token.group(3))).strip()
        if title:
            entries.append((max(1, level), title, token.group(2)))
    return entries


def attach_outline(doc: pymupdf.Document, entries: list[tuple[int, str, str]]) -> int:
    """Map nav titles onto rendered pages (monotonic scan) and write the outline."""
    pages = [re.sub(r"\s+", "", doc[i].get_text()) for i in range(doc.page_count)]
    toc: list[list[object]] = [[1, "封面", 1]]
    cursor = 0
    for level, title, _href in entries:
        key = re.sub(r"\s+", "", title)
        page = None
        for needle in (key, key[:10]):
            if not needle:
                continue
            for candidate in range(cursor, len(pages)):
                if needle in pages[candidate]:
                    page = candidate + 1
                    cursor = candidate
                    break
            if page is not None:
                break
        if page is not None:
            toc.append([level, title, page])
    doc.set_toc(toc)
    return len(toc)


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
) -> PdfResult:
    """Render ``epub`` to ``out``; raises RuntimeError when Chromium is unavailable."""
    style = style or PrintStyle()
    browser = chromium or find_chromium()
    if not browser:
        raise RuntimeError(
            "未找到 Chromium/Chrome（可用 AUTO_EPUBLIZER_CHROME 指定路径）；"
            "印刷版 PDF 需要浏览器排版"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aep-pdf-") as tmp:
        work = Path(tmp)
        with zipfile.ZipFile(epub) as archive:
            archive.extractall(work)
        oebps = next(p for p in work.rglob("*.opf")).parent
        target, sections = build_print_html(oebps, style)
        raw = work / "raw.pdf"
        subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--no-pdf-header-footer",
                "--virtual-time-budget=30000",
                f"--print-to-pdf={raw}",
                target.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
        shutil.copyfile(raw, out)
        meta = _metadata(oebps)
        outline = nav_entries(oebps)

    doc = pymupdf.open(out)
    stamp_folios(doc)
    written = attach_outline(doc, outline) if bookmarks else 0
    merged = {k: v for k, v in (doc.metadata or {}).items() if k in {"title", "author"}}
    merged.update(meta)
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
    )
