# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""issue #60 / PR67 的 D1–D3 验收：容器与资源、书签与元数据、CLI 与产物安全。"""

from __future__ import annotations

import base64
import json
import zipfile
from pathlib import Path

import pymupdf
import pytest
from typer.testing import CliRunner

from auto_epublizer import orchestrator as orch
from auto_epublizer import pdfexport
from auto_epublizer.cli import app

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" xmlns:opf="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">urn:test:pdf</dc:identifier>
    <dc:title>测试书</dc:title>
    <dc:creator id="creator-aut" opf:role="aut">作者甲</dc:creator>
    <dc:creator id="creator-trl">译者乙</dc:creator>
    <meta refines="#creator-trl" property="role">trl</meta>
    <dc:language>zh-CN</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="css" href="style.css" media-type="text/css"/>
    <item id="cover-img" href="media/cover.png" media-type="image/png" properties="cover-image"/>
    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch1" href="text/ch01.xhtml" media-type="application/xhtml+xml"/>
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
<body>
<nav epub:type="landmarks"><ol><li><a href="ch01.xhtml">不是目录</a></li></ol></nav>
<nav epub:type="toc"><ol>
  <li><a href="text/ch01.xhtml">第一章 开端</a>
    <ol><li><a href="text/ch01.xhtml#s1">第一节 细节</a></li></ol>
  </li>
  <li><a href="ch02.xhtml">第二章 收束</a></li>
</ol></nav></body></html>
"""

_CH1 = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>第一章 开端</title></head>
<body><section class="chapter">
<h1>第一章 开端</h1>
<p>正文第一段，带一个注码<a epub:type="noteref" href="#n1">[1]</a>。</p>
<h2 id="s1">第一节 细节</h2>
<p>第二节的正文。</p>
<img src="../media/pic.png" alt="插图"/>
<img src="https://example.com/remote.png" alt="远程"/>
<script>alert(1)</script>
<p onclick="evil()">带事件属性的段落。</p>
<aside epub:type="footnote" id="n1">
  <p>[1]</p>
  <p>注文正文。</p>
  <p><a epub:type="backlink" href="ch01.xhtml#ref1">↩</a></p>
</aside>
</section></body></html>
"""


def _mini_epub(tmp: Path, *, opf_name: str = "content.opf", decoy: bool = False) -> Path:
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
        "text/ch01.xhtml": _CH1,
    }
    opf = _OPF if opf_name == "content.opf" else _OPF.replace("text/ch01.xhtml", "ch01.xhtml")
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0" encoding="utf-8"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            f'<rootfiles><rootfile full-path="OEBPS/{opf_name}" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        zf.writestr(f"OEBPS/{opf_name}", opf)
        zf.writestr("OEBPS/nav.xhtml", _NAV)
        zf.writestr("OEBPS/style.css", "body { font-family: serif; line-height: 1.7; }\n")
        zf.writestr("OEBPS/media/cover.png", _PNG)
        zf.writestr("OEBPS/media/pic.png", _PNG)
        for name, body in docs.items():
            zf.writestr(f"OEBPS/{name}", body)
        if decoy:
            zf.writestr("OEBPS/decoy.opf", "<package><spine/></package>")
    return epub


def _unpack(tmp: Path, epub: Path) -> Path:
    with zipfile.ZipFile(epub) as zf:
        zf.extractall(tmp / "unpacked")
    return tmp / "unpacked"


# ── D1 容器与资源 ───────────────────────────────────────────────────────


def test_print_style_defaults_and_validation() -> None:
    css = pdfexport.PrintStyle().css()
    assert "@page { size: 148mm 210mm; margin: 18mm 16mm 20mm 16mm; }" in css
    assert "font-size: 10.5pt" in css and "font-size: 8.5pt" in css
    assert pdfexport.PrintStyle(size="16k").page_size_mm() == (185, 260)
    assert pdfexport.PrintStyle(size="nonsense").page_size_mm() == (148, 210)

    for bad in (
        pdfexport.PrintStyle(body_pt=0),
        pdfexport.PrintStyle(body_pt=99),
        pdfexport.PrintStyle(note_pt=float("nan")),
        pdfexport.PrintStyle(line_height=0.5),
        pdfexport.PrintStyle(line_height=9),
    ):
        with pytest.raises(ValueError):
            bad.validate()


def test_opf_located_via_container_not_by_guess(tmp_path: Path) -> None:
    work = _unpack(tmp_path, _mini_epub(tmp_path, opf_name="pkg.opf", decoy=True))
    opf = pdfexport._opf_path(work)
    assert opf.name == "pkg.opf"  # 不是字母序靠前的 decoy.opf


def test_safe_extract_rejects_escape_and_absolute(tmp_path: Path) -> None:
    for name, payload in (
        ("../escape.txt", "x"),
        ("/abs.txt", "x"),
    ):
        archive = tmp_path / "bad.epub"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr(name, payload)
        with zipfile.ZipFile(archive) as zf, pytest.raises(ValueError):
            pdfexport._safe_extract(zf, tmp_path / "out")


def test_chapter_resources_are_relocated_per_directory(tmp_path: Path) -> None:
    """子目录章节的 `../media/pic.png` 要按章节目录重定位；远程引用丢弃并留痕。"""
    work = _unpack(tmp_path, _mini_epub(tmp_path))
    package = pdfexport._parse_opf(work / "OEBPS" / "content.opf")
    target, sections = pdfexport.build_print_html(package, pdfexport.PrintStyle())
    html = target.read_text(encoding="utf-8")
    assert 'src="media/pic.png"' in html  # 已按 text/ 目录重定位
    assert "example.com" not in html
    assert "<script" not in html and "onclick" not in html
    assert sections == 3
    notes = target.with_suffix(".notes.txt").read_text(encoding="utf-8")
    assert "example.com" in notes


def test_missing_spine_document_is_an_error(tmp_path: Path) -> None:
    work = _unpack(tmp_path, _mini_epub(tmp_path))
    (work / "OEBPS" / "ch02.xhtml").unlink()
    package = pdfexport._parse_opf(work / "OEBPS" / "content.opf")
    with pytest.raises(ValueError, match="spine 文档缺失"):
        pdfexport.build_print_html(package, pdfexport.PrintStyle())


# ── D2 书签与元数据 ─────────────────────────────────────────────────────


def test_nav_entries_only_toc_and_levels(tmp_path: Path) -> None:
    work = _unpack(tmp_path, _mini_epub(tmp_path))
    entries = pdfexport.nav_entries(work / "OEBPS" / "nav.xhtml")
    assert [(level, title) for level, title, _ in entries] == [
        (1, "第一章 开端"),
        (2, "第一节 细节"),
        (1, "第二章 收束"),
    ]


def test_metadata_excludes_refined_translator(tmp_path: Path) -> None:
    work = _unpack(tmp_path, _mini_epub(tmp_path))
    package = pdfexport._parse_opf(work / "OEBPS" / "content.opf")
    assert package.title == "测试书"
    assert package.author == "作者甲"  # meta refines role=trl 的译者不算作者


def test_outline_maps_fragment_inside_section_and_records_unlocated(tmp_path: Path) -> None:
    doc = pymupdf.open()
    for text in ("封面", "第一章 开端", "第一节 细节\n正文", "第二章 收束"):
        page = doc.new_page()
        page.insert_text((40, 60), text, fontsize=10, fontname="china-s")
    notes: list[str] = []
    toc = pdfexport.attach_outline(
        doc,
        [
            (1, "第一章 开端", "text/ch01.xhtml"),
            (2, "第一节 细节", "text/ch01.xhtml#s1"),
            (1, "第二章 收束", "ch02.xhtml"),
            (1, "不存在的章", "ghost.xhtml"),
        ],
        spine=[
            ("cover", "cover.xhtml"),
            ("ch1", "text/ch01.xhtml"),
            ("ch2", "ch02.xhtml"),
        ],
        section_pages={1: 1, 2: 2, 3: 4},
        notes=notes,
        cover=True,
    )
    assert toc[0] == [1, "封面", 1]
    assert [entry[2] for entry in toc[1:]] == [2, 3, 4]
    assert any("ghost.xhtml" in note for note in notes)
    doc.close()


def test_unlocated_fragment_uses_section_start_and_says_so(tmp_path: Path) -> None:
    doc = pymupdf.open()
    for _ in range(3):
        page = doc.new_page()
        page.insert_text((40, 60), "普通正文", fontsize=10, fontname="china-s")
    notes: list[str] = []
    toc = pdfexport.attach_outline(
        doc,
        [(2, "找不到的标题", "ch01.xhtml#x")],
        spine=[("ch1", "ch01.xhtml")],
        section_pages={1: 2},
        notes=notes,
        cover=False,
    )
    assert toc == [[2, "找不到的标题", 2]]
    assert any("未定位" in note for note in notes)
    doc.close()


# ── D3 CLI 与产物安全 ───────────────────────────────────────────────────


def test_render_rejects_same_path_and_missing_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    epub = _mini_epub(tmp_path)
    with pytest.raises(ValueError, match="相同"):
        pdfexport.render(epub, epub)
    monkeypatch.setattr(pdfexport, "find_chromium", lambda: None)
    with pytest.raises(RuntimeError, match="Chromium"):
        pdfexport.render(epub, tmp_path / "out.pdf")


def test_failed_render_leaves_no_partial_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    epub = _mini_epub(tmp_path)
    fake = tmp_path / "fake-chromium"
    fake.write_text("#!/bin/sh\necho boom >&2\nexit 3\n", encoding="utf-8")
    fake.chmod(0o755)
    out = tmp_path / "out.pdf"
    out.write_bytes(b"%PDF-old")  # 既有旧成品不得被破坏
    with pytest.raises(RuntimeError, match="退出码 3"):
        pdfexport.render(epub, out, chromium=str(fake))
    assert out.read_bytes() == b"%PDF-old"


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_render_end_to_end_clears_markers_and_writes_outline(tmp_path: Path) -> None:
    epub = _mini_epub(tmp_path)
    out = tmp_path / "out.pdf"
    result = pdfexport.render(epub, out, pdfexport.PrintStyle(body_pt=12, note_pt=9))
    assert out.is_file() and result.pages >= 3
    assert result.bookmarks >= 3
    doc = pymupdf.open(out)
    assert doc[0].rect.width == pytest.approx(420, abs=1)  # 148 mm
    text = "".join(doc[i].get_text() for i in range(doc.page_count))
    assert "第一章 开端" in text
    assert "AEPMARK" not in text  # 定位标记已清除
    assert "1" not in doc[0].get_text()  # 封面不编号
    doc.close()


def test_cli_pdf_json_error_channel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nBody.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    orch.build(store)
    monkeypatch.setattr(pdfexport, "find_chromium", lambda: None)
    result = CliRunner().invoke(app, ["pdf", "--workspace", str(store.dir), "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert "Chromium" in payload["error"]


def test_cli_pdf_rejects_unknown_size(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nBody.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    orch.build(store)
    result = CliRunner().invoke(app, ["pdf", "--workspace", str(store.dir), "--size", "folio"])
    assert result.exit_code == 1
    assert "未知开本" in result.output
