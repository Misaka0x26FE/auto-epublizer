# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 auto-epublizer contributors
"""印刷版 PDF 导出（pdf 命令）：版式参数、注文印刷化、书签映射、端到端渲染。"""

from __future__ import annotations

import base64
import zipfile
from pathlib import Path

import pymupdf
import pytest

from auto_epublizer import pdfexport

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">urn:test:pdf</dc:identifier>
    <dc:title>测试书</dc:title>
    <dc:creator id="creator-aut" opf:role="aut">作者甲</dc:creator>
    <dc:creator id="creator-trl" opf:role="trl">译者乙</dc:creator>
    <dc:language>zh-CN</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="css" href="style.css" media-type="text/css"/>
    <item id="cover-img" href="media/cover.png" media-type="image/png" properties="cover-image"/>
    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch1" href="ch01.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="ch02.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="cover"/>
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
  </spine>
</package>
"""

_NAV = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>目录</title></head>
<body><nav epub:type="toc"><ol>
  <li><a href="ch01.xhtml">第一章 开端</a>
    <ol><li><a href="ch01.xhtml#s1">第一节 细节</a></li></ol>
  </li>
  <li><a href="ch02.xhtml">第二章 收束</a></li>
</ol></nav></body></html>
"""

_ASIDE_DOC = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>第一章 开端</title></head>
<body><section class="chapter">
<h1>第一章 开端</h1>
<p>正文第一段，带一个注码<a epub:type="noteref" href="#n1">[1]</a>。</p>
<h2 id="s1">第一节 细节</h2>
<p>第二节的正文。</p>
<aside epub:type="footnote" id="n1">
  <p>[1]</p>
  <p>注文正文。</p>
  <p><a epub:type="backlink" href="ch01.xhtml#ref1">↩</a></p>
</aside>
</section></body></html>
"""


def _mini_epub(tmp: Path) -> Path:
    epub = tmp / "mini.epub"
    docs = {
        "cover.xhtml": (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>封面</title></head>'
            '<body><section class="cover"><img src="media/cover.png" alt="封面"/></section>'
            "</body></html>"
        ),
        "ch02.xhtml": (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>第二章 收束</title></head>'
            "<body><section class='chapter'><h1>第二章 收束</h1><p>结尾一段。</p></section>"
            "</body></html>"
        ),
    }
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0" encoding="utf-8"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        zf.writestr("OEBPS/content.opf", _OPF)
        zf.writestr("OEBPS/nav.xhtml", _NAV)
        zf.writestr("OEBPS/style.css", "body { font-family: serif; line-height: 1.7; }\n")
        zf.writestr("OEBPS/ch01.xhtml", _ASIDE_DOC)
        zf.writestr("OEBPS/media/cover.png", _PNG)
        for name, body in docs.items():
            zf.writestr(f"OEBPS/{name}", body)
    return epub


def test_print_style_defaults_and_presets() -> None:
    """缺省按中文学术书：大 32 开 A5、五号正文、小五注文。"""
    css = pdfexport.PrintStyle().css()
    assert "@page { size: 148mm 210mm; margin: 18mm 16mm 20mm 16mm; }" in css
    assert "font-size: 10.5pt" in css
    assert "font-size: 8.5pt" in css
    assert "text-indent: 2em" in css
    assert "};" not in css  # CSS 花括号不是模板占位符

    wide = pdfexport.PrintStyle(size="16k").css()
    assert "@page { size: 185mm 260mm;" in wide
    assert pdfexport.PrintStyle(size="nonsense").page_size_mm() == (148, 210)


def test_prepare_asides_prints_like_a_book() -> None:
    """注文印刷化：回链箭头去掉，注号与注文同行（不再独占一行）。"""
    html = pdfexport.prepare_asides(_ASIDE_DOC)
    assert "backlink" not in html
    assert "↩" not in html
    assert '<p class="fn"><span class="fnnum">[1]</span> 注文正文。' in html


def test_nav_entries_levels(tmp_path: Path) -> None:
    """nav.xhtml 的 <ol> 嵌套深度即书签层级。"""
    epub = _mini_epub(tmp_path)
    with zipfile.ZipFile(epub) as zf:
        zf.extractall(tmp_path / "unpacked")
    entries = pdfexport.nav_entries(tmp_path / "unpacked" / "OEBPS")
    assert [(level, title) for level, title, _ in entries] == [
        (1, "第一章 开端"),
        (2, "第一节 细节"),
        (1, "第二章 收束"),
    ]


def test_attach_outline_maps_titles_to_pages(tmp_path: Path) -> None:
    """书签落页按渲染后正文逐条检索，页码单调递增。"""
    doc = pymupdf.open()
    for text in ("封面", "第一章 开端\n第一节 细节", "第二章 收束"):
        page = doc.new_page()
        page.insert_text((40, 60), text, fontsize=10, fontname="china-s")
    written = pdfexport.attach_outline(doc, [(1, "第一章 开端", ""), (1, "第二章 收束", "")])
    assert written == 3
    toc = doc.get_toc()
    assert toc[0] == [1, "封面", 1]
    assert [entry[2] for entry in toc] == [1, 2, 3]


def test_metadata_excludes_translator(tmp_path: Path) -> None:
    """dc:creator role=trl 是译者，不得写进 PDF 的 author。"""
    epub = _mini_epub(tmp_path)
    with zipfile.ZipFile(epub) as zf:
        zf.extractall(tmp_path / "unpacked")
    meta = pdfexport._metadata(tmp_path / "unpacked" / "OEBPS")
    assert meta == {"title": "测试书", "author": "作者甲"}


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_render_minimal_epub(tmp_path: Path) -> None:
    """端到端：EPUB → A5 PDF，含页码（封面除外）与书签。"""
    epub = _mini_epub(tmp_path)
    out = tmp_path / "out.pdf"
    result = pdfexport.render(epub, out, pdfexport.PrintStyle(body_pt=12, note_pt=9))
    assert out.is_file()
    assert result.pages >= 3
    assert result.bookmarks >= 3
    doc = pymupdf.open(out)
    assert doc[0].rect.width == pytest.approx(420, abs=1)  # 148 mm
    assert doc[0].rect.height == pytest.approx(595, abs=1)  # 210 mm
    assert "第一章 开端" in "".join(doc[i].get_text() for i in range(doc.page_count))
    # 封面不编号，正文页脚有页码
    assert "1" not in doc[0].get_text()
    assert any(str(n) in doc[n].get_text() for n in range(1, doc.page_count))
