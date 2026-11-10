# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""issue #60 / PR67 的 D1–D3 验收：容器与资源、书签与元数据、CLI 与产物安全。"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import zipfile
from pathlib import Path

import pymupdf
import pytest
from typer.testing import CliRunner

from auto_epublizer import orchestrator as orch
from auto_epublizer import pdfexport
from auto_epublizer.cli import app
from auto_epublizer.qa import artifacts_digest

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


def _variant(epub: Path, replacements: dict[str, str | bytes]) -> Path:
    with zipfile.ZipFile(epub) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files.update(
        {
            name: value.encode() if isinstance(value, str) else value
            for name, value in replacements.items()
        }
    )
    target = epub.with_name("variant.epub")
    with zipfile.ZipFile(target, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return target


def _raster_png(width: int = 32, height: int = 48) -> bytes:
    samples = bytes(
        v for y in range(height) for x in range(width) for v in (x % 256, y % 256, (x + y) % 256)
    )
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, width, height, samples, False)
    return pixmap.tobytes("png")


def test_nonlinear_cover_identity_does_not_depend_on_filename(tmp_path: Path) -> None:
    epub = _mini_epub(tmp_path)
    with zipfile.ZipFile(epub) as archive:
        cover = archive.read("OEBPS/cover.xhtml").decode()
    opf = _OPF.replace('href="cover.xhtml"', 'href="jacket.xhtml"').replace(
        '<itemref idref="cover"/>', '<itemref idref="cover" linear="no"/>'
    )
    work = _unpack(
        tmp_path, _variant(epub, {"OEBPS/content.opf": opf, "OEBPS/jacket.xhtml": cover})
    )
    package = pdfexport._parse_opf(work / "OEBPS/content.opf")

    assert package.spine[0] == ("cover", "jacket.xhtml")
    assert package.cover_href == "jacket.xhtml"
    target, sections = pdfexport.build_print_html(package, pdfexport.PrintStyle())
    assert sections == 3
    assert 'src="media/cover.png"' in target.read_text()


def test_cover_substring_does_not_hide_regular_chapter(tmp_path: Path) -> None:
    epub = _mini_epub(tmp_path)
    opf = _OPF.replace('href="ch02.xhtml"', 'href="discoveries.xhtml"')
    work = _unpack(
        tmp_path,
        _variant(
            epub,
            {
                "OEBPS/content.opf": opf,
                "OEBPS/discoveries.xhtml": '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Discoveries</title></head><body><h1>Discoveries</h1><p>Keep this entire chapter.</p></body></html>',
            },
        ),
    )
    package = pdfexport._parse_opf(work / "OEBPS/content.opf")
    target, _ = pdfexport.build_print_html(package, pdfexport.PrintStyle())
    assert "Keep this entire chapter." in target.read_text()


def test_registered_cover_image_without_document_is_printed_once(tmp_path: Path) -> None:
    epub = _mini_epub(tmp_path)
    opf = _OPF.replace('<itemref idref="cover"/>', "")
    work = _unpack(tmp_path, _variant(epub, {"OEBPS/content.opf": opf}))
    package = pdfexport._parse_opf(work / "OEBPS/content.opf")
    target, sections = pdfexport.build_print_html(package, pdfexport.PrintStyle())
    assert sections == 3
    assert target.read_text().count('src="media/cover.png"') == 1


def test_semantic_svg_cover_keeps_graphics_and_excludes_other_nonlinear_pages(
    tmp_path: Path,
) -> None:
    epub = _mini_epub(tmp_path)
    opf = (
        _OPF.replace('href="cover.xhtml"', 'href="jacket.xhtml"')
        .replace('properties="cover-image"', "")
        .replace(
            '<itemref idref="cover"/>',
            '<itemref idref="cover" linear="no"/><itemref idref="software" linear="no"/>',
        )
        .replace(
            "</manifest>",
            '<item id="software" href="software.xhtml" media-type="application/xhtml+xml"/></manifest>',
        )
    )
    nav = _NAV.replace(
        '<nav epub:type="landmarks"><ol>',
        '<nav epub:type="landmarks"><ol><li><a epub:type="cover" href="jacket.xhtml">封面</a></li>',
    )
    svg = '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Jacket</title></head><body><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 48"><image href="media/cover.png" width="32" height="48"/></svg></body></html>'
    work = _unpack(
        tmp_path,
        _variant(
            epub,
            {
                "OEBPS/content.opf": opf,
                "OEBPS/nav.xhtml": nav,
                "OEBPS/jacket.xhtml": svg,
                "OEBPS/software.xhtml": "<html><body>Do not print this software appendix.</body></html>",
            },
        ),
    )
    package = pdfexport._parse_opf(work / "OEBPS/content.opf")
    target, sections = pdfexport.build_print_html(package, pdfexport.PrintStyle())
    assert sections == 3
    assert package.cover_href == "jacket.xhtml"
    assert "<svg " in target.read_text()
    assert 'href="media/cover.png"' in target.read_text()
    assert "Do not print this software appendix." not in target.read_text()


def test_cover_resource_url_is_decoded_once_and_reencoded_for_html(tmp_path: Path) -> None:
    epub = _mini_epub(tmp_path)
    with zipfile.ZipFile(epub) as archive:
        cover = archive.read("OEBPS/cover.xhtml").decode()
    opf = _OPF.replace("media/cover.png", "media/jacket%23scan.png")
    work = _unpack(
        tmp_path,
        _variant(
            epub,
            {
                "OEBPS/content.opf": opf,
                "OEBPS/cover.xhtml": cover.replace("media/cover.png", "media/jacket%23scan.png"),
                "OEBPS/media/jacket#scan.png": _raster_png(),
            },
        ),
    )
    package = pdfexport._parse_opf(work / "OEBPS/content.opf")
    target, _ = pdfexport.build_print_html(package, pdfexport.PrintStyle())
    assert 'src="media/jacket%23scan.png"' in target.read_text()
    assert not target.with_suffix(".notes.txt").read_text().count("jacket")


def test_nested_opf_can_reference_sibling_resources_inside_archive(tmp_path: Path) -> None:
    epub = _mini_epub(tmp_path)
    opf = _OPF.replace('href="', 'href="../')
    container = '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/package/content.opf"/></rootfiles></container>'
    epub = _variant(epub, {"META-INF/container.xml": container, "OEBPS/package/content.opf": opf})
    work = _unpack(tmp_path, epub)

    package = pdfexport._parse_opf(pdfexport._opf_path(work), archive_root=work)

    assert package.cover_href == "OEBPS/cover.xhtml"
    target, sections = pdfexport.build_print_html(package, pdfexport.PrintStyle())
    assert sections == 3
    assert 'src="OEBPS/media/cover.png"' in target.read_text()
    entries = pdfexport.nav_entries(work / package.nav_href, owner_href=package.nav_href)
    assert entries[0][2] == "OEBPS/text/ch01.xhtml"


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
@pytest.mark.parametrize("has_cover", [True, False])
def test_printed_cover_and_page_one_footer_follow_declared_identity(
    tmp_path: Path, has_cover: bool
) -> None:
    epub = _mini_epub(tmp_path)
    opf = _OPF.replace('<itemref idref="cover"/>', '<itemref idref="cover" linear="no"/>')
    if not has_cover:
        opf = opf.replace('<itemref idref="cover" linear="no"/>', "").replace(
            'properties="cover-image"', ""
        )
    epub = _variant(epub, {"OEBPS/content.opf": opf, "OEBPS/media/cover.png": _raster_png()})
    result = pdfexport.render(epub, tmp_path / "print.pdf")
    with pymupdf.open(result.out) as doc:
        footer = (
            doc[0]
            .get_text(
                clip=pymupdf.Rect(0, doc[0].rect.height - 35, doc[0].rect.width, doc[0].rect.height)
            )
            .strip()
        )
        if has_cover:
            assert doc[0].get_image_info()
            assert all(
                pymupdf.Rect(info["bbox"]).y1 <= doc[0].rect.height + 0.1
                for info in doc[0].get_image_info()
            )
            assert doc.get_toc()[0] == [1, "封面", 1]
            assert footer == ""
        else:
            assert footer == "1"
            assert doc.get_toc()[0][1] != "封面"


def test_clearing_markers_does_not_edit_underlying_cover_pixels() -> None:
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_image(page.rect, stream=_raster_png())
        page.insert_text((100, 100), "AEPMARK0001", fontsize=12)
        before = page.get_image_info(hashes=True)[0]["digest"]

        pdfexport._clear_markers(doc, 1)

        page = doc.reload_page(page)
        assert "AEPMARK" not in page.get_text()
        assert page.get_image_info(hashes=True)[0]["digest"] == before


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
@pytest.mark.parametrize("size", ["a5", "16k"])
@pytest.mark.parametrize("references", [1, 2])
@pytest.mark.parametrize("dimensions", [(804, 1293), (1293, 804)])
def test_tall_plates_are_drawn_once_per_reference_with_captions(
    tmp_path: Path, size: str, references: int, dimensions: tuple[int, int]
) -> None:
    epub = _mini_epub(tmp_path)
    figures = "".join(
        f'<figure class="imgfig"><img src="../media/plate.png"/><figcaption>Plate {index} CAPTION_END</figcaption></figure>'
        for index in range(references)
    )
    epub = _variant(
        epub,
        {
            "OEBPS/text/ch01.xhtml": f'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Plates</title></head><body><h1>Plates</h1>{figures}</body></html>',
            "OEBPS/media/plate.png": _raster_png(*dimensions),
        },
    )
    result = pdfexport.render(epub, tmp_path / "plates.pdf", pdfexport.PrintStyle(size=size))
    with pymupdf.open(result.out) as doc:
        draws = [
            (page.number, info["bbox"])
            for page in doc
            for info in page.get_image_info()
            if (info["width"], info["height"]) == dimensions
        ]
        assert len(draws) == references
        for page_index, bbox in draws:
            assert pymupdf.Rect(bbox).y0 >= 18 * 72 / 25.4 - 1
            assert pymupdf.Rect(bbox).y1 <= doc[page_index].rect.height - 20 * 72 / 25.4 + 1
            assert "CAPTION_END" in doc[page_index].get_text()


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_uncaptioned_standalone_plate_is_not_split_across_pages(tmp_path: Path) -> None:
    epub = _variant(
        _mini_epub(tmp_path),
        {
            "OEBPS/text/ch01.xhtml": '<html><body><h1>Plate</h1><p class="imgp"><img src="../media/plate.png"/></p></body></html>',
            "OEBPS/media/plate.png": _raster_png(804, 1293),
        },
    )
    result = pdfexport.render(epub, tmp_path / "uncaptioned.pdf")
    with pymupdf.open(result.out) as doc:
        draws = [
            (page, info) for page in doc for info in page.get_image_info() if info["width"] == 804
        ]
        assert len(draws) == 1
        page, info = draws[0]
        assert pymupdf.Rect(info["bbox"]).y1 <= page.rect.height - 20 * 72 / 25.4 + 1


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_plate_with_overlong_caption_keeps_image_once_and_all_caption_text(tmp_path: Path) -> None:
    epub = _mini_epub(tmp_path)
    caption = "Caption continuation. " * 180 + "CAPTION_END"
    epub = _variant(
        epub,
        {
            "OEBPS/text/ch01.xhtml": f'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Plate</title></head><body><h1>Plate</h1><figure class="imgfig"><img src="../media/plate.png"/><figcaption>{caption}</figcaption></figure></body></html>',
            "OEBPS/media/plate.png": _raster_png(804, 1293),
        },
    )
    result = pdfexport.render(epub, tmp_path / "long-caption.pdf")
    with pymupdf.open(result.out) as doc:
        assert sum(info["width"] == 804 for page in doc for info in page.get_image_info()) == 1
        text = "".join(
            page.get_text(clip=pymupdf.Rect(0, 0, page.rect.width, page.rect.height - 35))
            for page in doc
        )
        assert re.sub(r"\s+", "", text).count("Captioncontinuation.") == 180
        assert "CAPTION_END" in text


def _wide_table_epub(tmp_path: Path) -> Path:
    cells = "".join("<td>123456789012345</td>" for _ in range(13))
    body = "<p>BODY_SAMPLE This paragraph supplies ordinary narrative text for independent font measurement before the wide table.</p>"
    html = f'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Wide table</title></head><body><h1 id="s1">Wide table</h1>{body}<table class="data"><tr>{cells}</tr></table>{body}</body></html>'
    return _variant(_mini_epub(tmp_path), {"OEBPS/text/ch01.xhtml": html})


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_thirteen_column_table_does_not_shrink_the_entire_a5_document(tmp_path: Path) -> None:
    result = pdfexport.render(_wide_table_epub(tmp_path), tmp_path / "wide.pdf", strict=True)
    with pymupdf.open(result.out) as doc:
        sizes = [
            span["size"]
            for page in doc
            for block in page.get_text("dict")["blocks"]
            if "lines" in block
            for line in block["lines"]
            for span in line["spans"]
            if "BODY_SAMPLE" in span["text"]
        ]
        assert sizes and all(abs(size - 10.5) <= 0.2 for size in sizes)
    assert result.diagnostics["fonts"]["body"]["observed_pt"] == pytest.approx(10.5, abs=0.2)
    assert not any(f["code"] == "E_PDF_FONT_SCALE" for f in result.diagnostics["findings"])


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_strict_pdf_diagnostics_fail_before_overwriting_existing_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    epub = _wide_table_epub(tmp_path)
    output = tmp_path / "existing.pdf"
    output.write_bytes(b"old product must remain unchanged")
    css = pdfexport.PrintStyle.css
    monkeypatch.setattr(
        pdfexport.PrintStyle,
        "css",
        lambda self, **kwargs: css(self, **kwargs) + "\np {font-size:6pt !important}",
    )
    with pytest.raises(ValueError, match="E_PDF_FONT_SCALE"):
        pdfexport.render(epub, output, strict=True)
    assert output.read_bytes() == b"old product must remain unchanged"


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_cli_pdf_strict_json_includes_source_bound_font_diagnostics(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# One\n\nBody.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    result = CliRunner().invoke(
        app,
        [
            "pdf",
            "--workspace",
            str(store.dir),
            "--epub",
            str(_wide_table_epub(tmp_path)),
            "--strict",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["diagnostics"]["status"] == "pass"
    assert payload["diagnostics"]["fonts"]["body"]["observed_pt"] == pytest.approx(10.5, abs=0.2)
    assert Path(payload["pdf"]).is_file()


def _toc_epub(tmp_path: Path, *, list_style: bool = False, stray: bool = False) -> Path:
    opf = _OPF.replace(
        "</manifest>",
        '<item id="toc-body" href="front/contents.xhtml" media-type="application/xhtml+xml"/><item id="preface" href="front/preface.xhtml" media-type="application/xhtml+xml"/><item id="index" href="back/index.xhtml" media-type="application/xhtml+xml"/></manifest>',
    )
    opf = opf.replace(
        '<itemref idref="cover"/>',
        '<itemref idref="cover"/><itemref idref="toc-body"/><itemref idref="preface"/>',
    ).replace('<itemref idref="ch2"/>', '<itemref idref="ch2"/><itemref idref="index"/>')
    labels = [
        ("序", "front/preface.xhtml#intro"),
        ("Alpha", "text/ch01.xhtml#real"),
        ("Beta", "ch02.xhtml"),
        ("Index", "back/index.xhtml"),
    ]
    nav = (
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Navigation</title></head><body><nav epub:type="toc"><ol>'
        + "".join(f'<li><a href="{href}">{title}</a></li>' for title, href in labels)
        + "</ol></nav></body></html>"
    )
    rows = "".join(
        f"<li><strong>{title}</strong> — vii <em>Author C</em></li>"
        if list_style
        else f"<p>{title} 999</p>"
        for title, _ in labels
    )
    if stray:
        rows += "<p>Unknown entry 999</p>"
    return _variant(
        _mini_epub(tmp_path),
        {
            "OEBPS/content.opf": opf,
            "OEBPS/nav.xhtml": nav,
            "OEBPS/front/contents.xhtml": f"<html><head><title>Contents</title></head><body><h1>Contents</h1>{rows}</body></html>",
            "OEBPS/front/preface.xhtml": '<html><head><title>序</title></head><body><h1 id="intro">序</h1><p>PREFACE_TARGET Body paragraph for the preface.</p></body></html>',
            "OEBPS/text/ch01.xhtml": '<html><head><title>Alpha</title></head><body><h1>Alpha</h1><p>Alpha is echoed here, not the requested target.</p><div style="page-break-before:always"><h2 id="real">REAL_TARGET_ALPHA</h2><p>The actual fragment starts here.</p></div></body></html>',
            "OEBPS/ch02.xhtml": "<html><head><title>Beta</title></head><body><h1>Beta</h1><p>BETA_TARGET Some body text.</p></body></html>",
            "OEBPS/back/index.xhtml": "<html><head><title>Index</title></head><body><h1>Index</h1><p>Original index Alpha 123, Beta 456.</p></body></html>",
        },
    )


def _long_toc_epub(tmp_path: Path) -> Path:
    label = "A Very Long Title With Subtitle And Author Name"
    opf = _OPF.replace(
        "</manifest>",
        '<item id="toc-body" href="front/contents.xhtml" media-type="application/xhtml+xml"/></manifest>',
    ).replace('<itemref idref="cover"/>', '<itemref idref="cover"/><itemref idref="toc-body"/>')
    nav = (
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
        '<head><title>Navigation</title></head><body><nav epub:type="toc"><ol>'
        f'<li><a href="text/ch01.xhtml#real">{label}</a></li>'
        "</ol></nav></body></html>"
    )
    contents = (
        "<html><head><title>Contents</title></head><body><h1>Contents</h1>"
        "<p>Contents</p><p>§</p>"
        "<p>A Very Long Title With</p><p>Subtitle And Author Name 9</p>"
        "</body></html>"
    )
    chapter = (
        "<html><head><title>Long</title></head><body><h1>Long</h1>"
        '<div style="page-break-before:always"><h2 id="real">LONG_TARGET</h2>'
        "<p>The long-title target page.</p></div></body></html>"
    )
    return _variant(
        _mini_epub(tmp_path),
        {
            "OEBPS/content.opf": opf,
            "OEBPS/nav.xhtml": nav,
            "OEBPS/front/contents.xhtml": contents,
            "OEBPS/text/ch01.xhtml": chapter,
        },
    )


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_index_two_columns_cip_no_indent_and_cjk_emphasis(tmp_path: Path) -> None:
    """E5：索引分栏、CIP 不缩进、中文强调正体加粗而拉丁强调保留斜体。"""
    entries = "".join(
        f"<p>Entry {index:03d} — 索引条目 {index}，页码 {index + 1}。</p>" for index in range(80)
    )
    index = (
        "<html><head><title>Index</title></head><body><section class='chapter'>"
        f"<h1>Index</h1>{entries}"
        "<p>BODY_TEXT 中文<em>强调语</em>与拉丁<em>Latin emphasis</em>。</p>"
        "</section></body></html>"
    )
    cip = (
        "<html><head><title>Copyright</title></head><body><section class='chapter'>"
        "<h1>Copyright</h1><p>CIP_TEXT 图书在版编目数据。</p></section></body></html>"
    )
    epub = _variant(
        _mini_epub(tmp_path),
        {
            "OEBPS/text/ch01.xhtml": index,
            "OEBPS/ch02.xhtml": cip,
        },
    )
    result = pdfexport.render(epub, tmp_path / "index.pdf")
    with pymupdf.open(result.out) as doc:
        index_page = next(page for page in doc if "Entry 000" in page.get_text())
        entry_words = [word for word in index_page.get_text("words") if word[4] == "Entry"]
        assert min(word[0] for word in entry_words) < 150
        assert max(word[0] for word in entry_words) > 200
        cip_page = next(page for page in doc if "CIP_TEXT" in page.get_text())
        body_page = next(page for page in doc if "BODY_TEXT" in page.get_text())
        cip_word = next(word for word in cip_page.get_text("words") if word[4] == "CIP_TEXT")
        body_word = next(word for word in body_page.get_text("words") if word[4] == "BODY_TEXT")
        assert cip_word[0] < body_word[0] - 10
        assert "强调语" in "".join(page.get_text() for page in doc)
    transformed = pdfexport._mark_cjk_emphasis(
        "<p>中文<em>强调语</em>与拉丁<em>Latin emphasis</em>。</p>"
    )
    assert '<span class="cjk-em">强调语</span>' in transformed
    assert "<em>Latin emphasis</em>" in transformed
    assert "span.cjk-em { font-style: normal; font-weight: 600; }" in pdfexport.CSS_TEMPLATE


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_running_heads_follow_section_roles_and_truncate(tmp_path: Path) -> None:
    """E4：封面无页眉页脚；章节首页不重复页眉；正文页眉对章名并截断；页码保持绝对页序。"""
    long_title = "A Very Long Chapter Title That Must Be Truncated In The Running Header " * 2
    paragraphs = "".join(f"<p>Paragraph {index} of the chapter body.</p>" for index in range(48))
    ch1 = (
        f"<html><head><title>{long_title}</title></head><body><section class='chapter'>"
        f"<h1>{long_title}</h1>{paragraphs}<p>CH1_LAST</p></section></body></html>"
    )
    ch2 = (
        "<html><head><title>Second Chapter</title></head><body><section class='chapter'>"
        f"<h1>Second Chapter</h1>{paragraphs}<p>CH2_LAST</p></section></body></html>"
    )
    epub = _variant(
        _mini_epub(tmp_path),
        {"OEBPS/text/ch01.xhtml": ch1, "OEBPS/ch02.xhtml": ch2},
    )
    result = pdfexport.render(epub, tmp_path / "heads.pdf")
    with pymupdf.open(result.out) as doc:

        def head_text(page: pymupdf.Page) -> str:
            return " ".join(word[4] for word in page.get_text("words") if word[1] < 35)

        def folio_text(page: pymupdf.Page) -> str:
            return " ".join(word[4] for word in page.get_text("words") if word[1] > 560)

        assert not head_text(doc[0]) and not folio_text(doc[0])
        first_ch1 = next(
            p for p in doc if "Paragraph 0 " in p.get_text() and "CH1_LAST" not in p.get_text()
        )
        assert not head_text(first_ch1)
        assert folio_text(first_ch1) == str(first_ch1.number + 1)
        second_ch1 = doc[first_ch1.number + 1]
        assert head_text(second_ch1).endswith("...")
        assert head_text(second_ch1).startswith("A Very Long Chapter")
        assert folio_text(second_ch1) == str(second_ch1.number + 1)
        first_ch2 = next(
            p for p in doc if "Paragraph 0 " in p.get_text() and p.number > first_ch1.number
        )
        assert "Second Chapter" not in head_text(first_ch2)
        second_ch2 = doc[first_ch2.number + 1]
        assert head_text(second_ch2) == "Second Chapter"
        assert folio_text(second_ch2) == str(second_ch2.number + 1)


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
@pytest.mark.parametrize("size", ["a5", "32k"])
def test_plate_fits_both_trims_without_duplication(tmp_path: Path, size: str) -> None:
    """E3：两种开本下图版只绘一次、不越出纸面；标题与后续正文不被拆成孤页规则仍生效。"""
    epub = _variant(
        _mini_epub(tmp_path),
        {
            "OEBPS/text/ch01.xhtml": '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Plate</title></head><body><h1>Plate</h1><figure class="imgfig"><img src="../media/plate.png"/><figcaption>PLATE_CAPTION</figcaption></figure><p>AFTER_PLATE text.</p></body></html>',
            "OEBPS/media/plate.png": _raster_png(804, 1293),
        },
    )
    result = pdfexport.render(epub, tmp_path / f"plate-{size}.pdf", pdfexport.PrintStyle(size=size))
    with pymupdf.open(result.out) as doc:
        images = [info for page in doc for info in page.get_image_info() if info["width"] == 804]
        assert len(images) == 1
        page = next(page for page in doc if "PLATE_CAPTION" in page.get_text())
        x0, y0, x1, y1 = images[0]["bbox"]
        assert x0 >= 0 and y0 >= 0 and x1 <= page.rect.width + 1
        assert y1 <= page.rect.height + 1
        assert "AFTER_PLATE" in "".join(p.get_text() for p in doc)
    assert "page-break-after: avoid" in pdfexport.CSS_TEMPLATE


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_generated_toc_rows_right_align_page_numbers(tmp_path: Path) -> None:
    """E3：目录行题名在左、页码贴右，长题名也不把页码挤到下一行。"""
    rows = (
        '<div class="toc-row"><a href="text/ch01.xhtml#real">Alpha</a>'
        '<span class="toc-dots"></span><span class="toc-page">3</span></div>'
        '<div class="toc-row"><a href="ch02.xhtml">A very long chapter title that wraps '
        "across the line in a narrow text area</a>"
        '<span class="toc-dots"></span><span class="toc-page">12</span></div>'
    )
    contents = (
        f"<html><head><title>Contents</title></head><body><h1>Contents</h1>{rows}</body></html>"
    )
    epub = _variant(_toc_epub(tmp_path), {"OEBPS/front/contents.xhtml": contents})
    result = pdfexport.render(epub, tmp_path / "toc-rows.pdf")
    with pymupdf.open(result.out) as doc:
        page = next(page for page in doc if "Alpha" in page.get_text())
        words = page.get_text("words")
        label = next(word for word in words if word[4] == "Alpha")
        number = next(word for word in words if word[4] == "3")
        assert number[0] > label[2]
        assert abs(number[1] - label[1]) < 4
        assert number[2] > page.rect.width * 0.7
        long_number = next(word for word in words if word[4] == "12")
        last_word = next(word for word in words if word[4] == "area")
        assert long_number[0] > last_word[2]
        assert abs(long_number[1] - last_word[1]) < 4
        assert long_number[2] > page.rect.width * 0.7
    assert ".toc-dots" in pdfexport.CSS_TEMPLATE
    assert "border-bottom: 1px dotted" in pdfexport.CSS_TEMPLATE


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_mixed_script_uses_latin_first_with_cjk_fallback(tmp_path: Path) -> None:
    """E1：拉丁字形优先、CJK 回落；’ 与中文标点读回，且无脚本/字体错配告警。"""
    paragraph = (
        "l’État and Marx’s legacy survive in print: "
        "中文标点与拉丁文混排必须各自成体，并保持足够长度用于正文样本核验。"
    )
    chapter = (
        "<html><head><title>Mixed</title></head><body><section class='chapter'>"
        f"<h1>Mixed</h1><p>{paragraph}</p></section></body></html>"
    )
    result = pdfexport.render(
        _variant(_mini_epub(tmp_path), {"OEBPS/text/ch01.xhtml": chapter}),
        tmp_path / "mixed.pdf",
    )
    script_fonts = result.diagnostics["script_fonts"]
    latin = [name for name in script_fonts["latin"] if script_fonts["latin"][name]]
    cjk = [name for name in script_fonts["cjk"] if script_fonts["cjk"][name]]
    assert latin and all(
        any(hint in name.casefold() for hint in ("nimbus", "liberation", "dejavu"))
        for name in latin
    ), latin
    assert cjk and all(
        any(hint in name.casefold() for hint in ("cjk", "songti", "simsun")) for name in cjk
    ), cjk
    codes = {finding["code"] for finding in result.diagnostics["findings"]}
    assert not {"W_PDF_FONT_LATIN_USES_CJK", "W_PDF_FONT_CJK_USES_LATIN"} & codes
    with pymupdf.open(result.out) as doc:
        text = "".join(page.get_text() for page in doc)
    assert "l’État" in text and "Marx’s" in text and "中文标点" in text


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_long_toc_title_with_hint_lines_gets_final_page(tmp_path: Path) -> None:
    label = "A Very Long Title With Subtitle And Author Name"
    result = pdfexport.render(_long_toc_epub(tmp_path), tmp_path / "long-toc.pdf")
    with pymupdf.open(result.out) as doc:
        page = next(page.number + 1 for page in doc if "LONG_TARGET" in page.get_text())
        toc_text = next(page.get_text() for page in doc if "Contents" in page.get_text())
        assert re.search(rf"Author Name\s*(?:—\s*)?{page}(?!\d)", toc_text), (page, toc_text)
        assert any(title == label and target == page for _, title, target in doc.get_toc())
        assert "Contents" in toc_text and "§" in toc_text
    assert result.toc["converged"] is True


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
@pytest.mark.parametrize("list_style", [False, True])
def test_print_toc_and_bookmarks_use_final_fragment_pages_not_title_echoes(
    tmp_path: Path, list_style: bool
) -> None:
    epub = _toc_epub(tmp_path, list_style=list_style)
    original = epub.read_bytes()
    result = pdfexport.render(epub, tmp_path / "toc.pdf")
    with pymupdf.open(result.out) as doc:
        actual = {
            name: next(page.number + 1 for page in doc if needle in page.get_text())
            for name, needle in [
                ("序", "PREFACE_TARGET"),
                ("Alpha", "REAL_TARGET_ALPHA"),
                ("Beta", "BETA_TARGET"),
                ("Index", "Original index"),
            ]
        }
        toc_text = next(page.get_text() for page in doc if "Contents" in page.get_text())
        for label, page in actual.items():
            assert re.search(rf"{label}\s*(?:—\s*)?{page}(?!\d)", toc_text), (label, page, toc_text)
            assert any(title == label and target == page for _, title, target in doc.get_toc())
        assert re.sub(r"\s+", "", "Original index Alpha 123, Beta 456.") in re.sub(
            r"\s+", "", "".join(page.get_text() for page in doc)
        )
        assert "AEPANCHOR" not in "".join(page.get_text() for page in doc)
    assert result.toc["converged"] is True and result.toc["rounds"] >= 2
    assert epub.read_bytes() == original


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_postprocessing_failure_preserves_existing_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    epub = _mini_epub(tmp_path)
    target = tmp_path / "old.pdf"
    target.write_bytes(b"previous approved product")

    def fail(*args, **kwargs):
        raise RuntimeError("postprocess fault injection")

    monkeypatch.setattr(pdfexport, "stamp_folios", fail)
    with pytest.raises(RuntimeError, match="postprocess fault"):
        pdfexport.render(epub, target)
    assert target.read_bytes() == b"previous approved product"


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_strict_toc_unlocated_finding_preserves_existing_pdf(tmp_path: Path) -> None:
    epub = _toc_epub(tmp_path, stray=True)
    target = tmp_path / "old.pdf"
    target.write_bytes(b"previous approved product")
    with pytest.raises(ValueError, match="E_PDF_TOC_UNLOCATED"):
        pdfexport.render(epub, target, strict=True)
    assert target.read_bytes() == b"previous approved product"


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_unstable_toc_pages_fail_without_replacing_existing_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    epub = _toc_epub(tmp_path)
    target = tmp_path / "old.pdf"
    target.write_bytes(b"previous approved product")
    calls = {"count": 0}

    def drifting(doc, sections, *, prefix="AEPMARK"):
        calls["count"] += 1
        return {number: number + calls["count"] * 10 for number in range(1, sections + 1)}

    monkeypatch.setattr(pdfexport, "_section_pages", drifting)
    with pytest.raises(ValueError, match="E_PDF_TOC_UNSTABLE"):
        pdfexport.render(epub, target)
    assert target.read_bytes() == b"previous approved product"
    assert calls["count"] == 3


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_marker_like_source_text_survives_positioning_and_cleanup(tmp_path: Path) -> None:
    epub = _variant(
        _mini_epub(tmp_path),
        {
            "OEBPS/text/ch01.xhtml": '<html><body><h1>Code examples</h1><p>Literal AEPMARK0001 and AEPANCHOR000001 must survive.</p><h2 id="s1">Details</h2></body></html>'
        },
    )
    result = pdfexport.render(epub, tmp_path / "literal.pdf")
    with pymupdf.open(result.out) as doc:
        text = "".join(page.get_text() for page in doc)
        assert "AEPMARK0001" in text
        assert "AEPANCHOR000001" in text
        assert "AEPPOS" not in text


def _metadata_epub(tmp_path: Path) -> tuple[Path, str]:
    rights = "版权所有 © 2026 示例出版社。" + "保留所有权利。" * 40
    metadata = f"""<metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="uid">urn:isbn:978-7-0000-0000-0</dc:identifier>
    <dc:title>Ünïcode 书名：测试</dc:title>
    <dc:creator id="a1">作者甲</dc:creator>
    <dc:creator id="a2">Author B</dc:creator>
    <dc:creator id="t1">译者乙</dc:creator>
    <meta refines="#t1" property="role">trl</meta>
    <dc:publisher>示例出版社</dc:publisher>
    <dc:date>2026-10-31</dc:date>
    <dc:rights>{rights}</dc:rights>
    <dc:language>zh-CN</dc:language>
    <dc:subject>印刷</dc:subject>
    <dc:subject>排版</dc:subject>
    <dc:description>说明文字</dc:description>
  </metadata>"""
    opf = re.sub(r"<metadata.*?</metadata>", metadata, _OPF, flags=re.S)
    return _variant(_mini_epub(tmp_path), {"OEBPS/content.opf": opf}), rights


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_publication_metadata_maps_unicode_authors_translator_and_full_rights(
    tmp_path: Path,
) -> None:
    epub, rights = _metadata_epub(tmp_path)
    result = pdfexport.render(epub, tmp_path / "meta.pdf")
    with pymupdf.open(result.out) as doc:
        info = doc.metadata
        xmp = doc.get_xml_metadata()
        assert info["title"] == "Ünïcode 书名：测试"
        assert info["author"] == "作者甲; Author B"
        assert info["keywords"] == "印刷; 排版"
        assert info["subject"] == "说明文字"
        assert "20261031" not in info["creationDate"]
        assert "2026-10-31" in xmp
        assert "20261031" not in xmp
        assert "示例出版社" in xmp
        assert "译者乙" in xmp
        assert rights in xmp  # 完整权利声明不能被截断
        assert "Ünïcode" in xmp
    assert result.metadata["info_readback"]["author"] == "作者甲; Author B"
    assert result.metadata["xmp_readback"]["rights"] == rights
    assert result.metadata["xmp_readback"]["translators"] == ["译者乙"]
    assert result.metadata["xmp_readback"]["publishers"] == ["示例出版社"]


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_empty_publication_fields_do_not_invent_metadata(tmp_path: Path) -> None:
    result = pdfexport.render(_mini_epub(tmp_path), tmp_path / "empty.pdf")
    assert result.metadata["source"]["publisher"] == ""
    assert result.metadata["source"]["rights"] == ""
    assert result.metadata["xmp_readback"]["publishers"] == []
    assert result.metadata["xmp_readback"]["rights"] == ""
    assert result.metadata["info_readback"]["title"] == "测试书"
    assert result.metadata["generated_at"].endswith("Z")


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_pdf_artifact_manifest_binds_hashes_and_detects_tampering(tmp_path: Path) -> None:
    epub = _mini_epub(tmp_path)
    result = pdfexport.render(epub, tmp_path / "bound.pdf")
    manifest_path = result.out.with_name(result.out.name + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "auto-epublizer/pdf-artifact/v1"
    assert manifest["epub"]["sha256"] == hashlib.sha256(epub.read_bytes()).hexdigest()
    assert manifest["pdf"]["sha256"] == hashlib.sha256(result.out.read_bytes()).hexdigest()
    assert manifest["pdf"]["pages"] == result.pages
    assert manifest["parameters"]["body_pt"] == 10.5
    assert manifest["metadata"]["xmp_readback"]["title"] == "测试书"
    assert pdfexport.verify_pdf_artifact(result.out)["ok"] is True

    result.out.write_bytes(result.out.read_bytes() + b"\n%tampered")
    verdict = pdfexport.verify_pdf_artifact(result.out)
    assert verdict["ok"] is False
    assert any(check["name"] == "pdf_sha256" and not check["ok"] for check in verdict["checks"])


def test_missing_or_corrupt_manifest_is_reported_not_crashing(tmp_path: Path) -> None:
    pdf = tmp_path / "missing.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    verdict = pdfexport.verify_pdf_artifact(pdf)
    assert verdict["ok"] is False
    assert verdict["error"]


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_pdf_and_manifest_stay_outside_epub_report_digest(tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    source.write_text("# One\n\nBody.\n", encoding="utf-8")
    store = orch.init(str(source), workspace_dir=str(tmp_path / "ws"))
    before = artifacts_digest(store)
    result = pdfexport.render(_mini_epub(tmp_path), store.output_dir / "book.pdf")
    assert artifacts_digest(store) == before
    assert pdfexport.manifest_path(result.out).is_file()


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_cli_pdf_verify_reports_tampered_artifact_with_nonzero_exit(tmp_path: Path) -> None:
    source = tmp_path / "book.md"
    source.write_text("# One\n\nBody.\n", encoding="utf-8")
    store = orch.init(str(source), workspace_dir=str(tmp_path / "ws"))
    rendered = pdfexport.render(_mini_epub(tmp_path), store.output_dir / "book.pdf")
    ok = CliRunner().invoke(app, ["pdf-verify", "--pdf", str(rendered.out), "--json"])
    assert ok.exit_code == 0, ok.output
    assert json.loads(ok.stdout)["ok"] is True
    rendered.out.write_bytes(rendered.out.read_bytes() + b"\n%tampered")
    bad = CliRunner().invoke(app, ["pdf-verify", "--pdf", str(rendered.out), "--json"])
    assert bad.exit_code == 1
    assert json.loads(bad.stdout)["ok"] is False


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


def test_container_cannot_read_an_opf_outside_the_extracted_package(tmp_path: Path) -> None:
    root = tmp_path / "package"
    (root / "META-INF").mkdir(parents=True)
    (tmp_path / "outside.opf").write_text(_OPF, encoding="utf-8")
    (root / "META-INF/container.xml").write_text(
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="../outside.opf"/></rootfiles></container>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="包文档路径"):
        pdfexport._opf_path(root)


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
        target_pages={"text/ch01.xhtml#s1": 3},
    )
    assert toc[0] == [1, "封面", 1]
    assert [entry[2] for entry in toc[1:]] == [2, 3, 4]
    assert any("ghost.xhtml" in note for note in notes)
    doc.close()


def test_unlocated_fragment_is_not_guessed_from_section_start(tmp_path: Path) -> None:
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
    assert toc == []
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


def test_cjk_running_head_is_not_dots() -> None:
    """中文页眉必须用可承载汉字的字体（审查 P2：helv 只出圆点）。"""
    doc = pymupdf.open()
    doc.new_page(width=420, height=595)
    doc.new_page(width=420, height=595)
    pdfexport.stamp_folios(
        doc, cover=False, section_titles={1: "第一章 奴隶劳动"}, section_pages={1: 1}
    )
    page = doc[1]
    spans = [
        span
        for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span["bbox"][3] < 40
    ]
    assert spans, "第二页应有页眉"
    assert "第一章" in "".join(span["text"] for span in spans)
    assert all("Helvetica" not in span["font"] for span in spans)


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_full_page_cover_and_dot_leaders_do_not_shrink_body_text(tmp_path: Path) -> None:
    """T5：整页封面 + 长引导点不得让 Chromium 整书缩小（8.24pt 回归）。"""
    cover_paras = "".join(
        f"<p>封面说明第 {i} 行，用于制造超出整页高度的内容。</p>" for i in range(30)
    )
    cover = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>封面</title></head>'
        '<body><section class="cover"><h1>封面</h1>'
        '<figure class="imgfig"><img src="../media/cover.png"/><figcaption>封面图</figcaption></figure>'
        f"{cover_paras}</section></body></html>"
    )
    dots = "目录条目" + "…" * 400 + "1"
    toc = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>目录</title></head>'
        f"<body><section class='chapter'><h1>目录</h1><p>{dots}</p>"
        "<p>正文段落应当保持十点五磅。</p></section></body></html>"
    )
    epub = _variant(
        _mini_epub(tmp_path),
        {"OEBPS/cover.xhtml": cover, "OEBPS/text/ch01.xhtml": toc},
    )
    result = pdfexport.render(epub, tmp_path / "shrink.pdf")
    with pymupdf.open(result.out) as doc:
        lines = [
            (
                "".join(span["text"] for span in line["spans"]),
                max(round(span["size"], 2) for span in line["spans"]),
            )
            for page in doc
            for block in page.get_text("dict")["blocks"]
            for line in block.get("lines", [])
            if line.get("spans")
        ]
    body = [size for text, size in lines if "正文段落应当保持" in text]
    assert body and all(abs(size - 10.5) < 0.05 for size in body), lines
    assert not any(abs(size - 8.24) < 0.05 for _, size in lines), lines


def test_mixed_script_emphasis_keeps_latin_italic_and_merges_class() -> None:
    """T4c：混排 em 只把汉字段转正体，拉丁仍斜体；class 不重复。"""
    out = pdfexport._mark_cjk_emphasis('<em class="lead">中文 Latin</em>')
    assert out == '<em class="lead"><span class="cjk-em">中文</span> Latin</em>'
    pure = pdfexport._mark_cjk_emphasis('<i class="x">汉字</i>')
    assert pure == '<span class="cjk-em x">汉字</span>'
    code = pdfexport._mark_cjk_emphasis("<em><code>汉字</code> 中文</em>")
    assert "<em><code>汉字</code> " in code


@pytest.mark.skipif(pdfexport.find_chromium() is None, reason="需要 Chromium/Chrome")
def test_titlepage_role_suppresses_header_and_folio(tmp_path: Path) -> None:
    """T4b：书名页/部分页按角色隐藏页眉页脚，绝对页序不变。"""
    ch2 = (
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>书名页</title></head>'
        '<body data-aep-role="titlepage"><section class="chapter"><h1>书名页</h1>'
        "<p>ROLE_MARKER 正文。</p></section></body></html>"
    )
    epub = _variant(_mini_epub(tmp_path), {"OEBPS/ch02.xhtml": ch2})
    result = pdfexport.render(epub, tmp_path / "role.pdf")
    with pymupdf.open(result.out) as doc:
        page = next(p for p in doc if "ROLE_MARKER" in p.get_text())
        head = [w[4] for w in page.get_text("words") if w[1] < 35]
        folio = [w[4] for w in page.get_text("words") if w[1] > 560]
    assert head == [] and folio == []


def test_font_stack_env_override_is_used(monkeypatch) -> None:
    """E4：AEP_PDF_FONT 可覆盖印刷字体栈；默认仍保留拉丁优先与 CJK 回退。"""
    css = pdfexport.PrintStyle().css()
    assert '"Nimbus Roman"' in css and '"Noto Serif CJK SC TTF"' in css
    monkeypatch.setenv("AEP_PDF_FONT", '"Custom Serif", serif')
    assert '"Custom Serif", serif' in pdfexport.PrintStyle().css()


def test_clear_markers_removes_marker_span_without_touching_neighbours() -> None:
    """E4：按 span bbox redaction，只删标记 span，保留相邻正文。"""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "SURROUNDING", fontsize=10)
    page.insert_text((150, 72), "AEPMARK0001", fontsize=1)
    page.insert_text((72, 100), "MORE WORDS", fontsize=10)
    pdfexport._clear_markers(doc, 1)
    text = page.get_text()
    assert "AEPMARK0001" not in text
    assert "SURROUNDING" in text and "MORE WORDS" in text


def test_cover_headings_are_not_printed_and_optional_colophon_is_added(
    tmp_path, monkeypatch
) -> None:
    """E4：封面只出图（h1/figcaption 不印）；AEP_PDF_COLOPHON 追加制作信息页。"""
    epub = _mini_epub(tmp_path)
    cover = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>封面</title></head>'
        '<body><section class="cover"><h1>封面标题</h1>'
        '<figure><img src="media/cover.png" alt="封面"/><figcaption>封面图注</figcaption></figure>'
        "</section></body></html>"
    )
    build_info = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>制作信息</title></head>'
        "<body><p>制作信息正文。</p></body></html>"
    )
    opf = _OPF.replace(
        '<item id="ch2" href="ch02.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="ch2" href="ch02.xhtml" media-type="application/xhtml+xml"/>\n'
        '    <item id="info" href="auto-epublizer-build-info.xhtml" '
        'media-type="application/xhtml+xml"/>',
    ).replace(
        '<itemref idref="ch2"/>',
        '<itemref idref="ch2"/>\n    <itemref idref="info"/>',
    )
    variant = _variant(
        epub,
        {
            "OEBPS/content.opf": opf,
            "OEBPS/cover.xhtml": cover,
            "OEBPS/auto-epublizer-build-info.xhtml": build_info,
        },
    )
    monkeypatch.setenv("AEP_PDF_COLOPHON", "1")
    result = pdfexport.render(variant, tmp_path / "colophon.pdf")
    with pymupdf.open(result.out) as doc:
        first = doc[0].get_text()
        last = doc[-1].get_text()
    assert "封面标题" not in first and "封面图注" not in first
    assert "制作信息与版权" in last and "制作信息正文" in last
