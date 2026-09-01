"""build 测试：XHTML 渲染、确定性 EPUB 写入、ZIP 结构验证。"""

from __future__ import annotations

import zipfile
from pathlib import Path

from auto_epublizer.build import build_epub
from auto_epublizer.build.html import markdown_to_xhtml, render_document, slug_file
from auto_epublizer.workspace import Publication, PublicationMeta, Unit


def test_markdown_to_xhtml() -> None:
    out = markdown_to_xhtml("# 标题\n\n第一段。\n\n第二段。\n")
    assert "<h1>标题</h1>" in out
    assert "<p>第一段。</p>" in out
    assert "<p>第二段。</p>" in out


def test_markdown_to_xhtml_escapes() -> None:
    out = markdown_to_xhtml("<script>alert(1)</script>\n")
    assert "&lt;script&gt;" in out


def test_render_document() -> None:
    html = render_document("T", "para", lang="zh-CN")
    assert 'xml:lang="zh-CN"' in html
    assert "<title>T</title>" in html


def test_slug_file() -> None:
    assert slug_file("ch01") == "ch01"
    assert slug_file("front-titlepage") == "front-titlepage"


def _pub() -> Publication:
    return Publication(
        slug="book",
        meta=PublicationMeta(title="测试书", creator="作者", target_language="zh-CN"),
        units=[Unit(id="ch01", kind="chapter", title="第一章")],
    )


def test_build_epub_structure(tmp_path: Path) -> None:
    pub = _pub()
    entries = [
        {"id": "ch01", "region": "body", "title": "第一章"},
    ]
    content_files = [
        ("ch01.xhtml", render_document("第一章", "# 第一章\n\n正文。\n", lang="zh-CN"))
    ]
    out = build_epub(
        pub,
        entries,
        content_files,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "book.epub",
    )
    assert out.is_file()
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert names[0] == "mimetype"
        assert zf.read("mimetype") == b"application/epub+zip"
        assert zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        for expected in (
            "META-INF/container.xml",
            "OEBPS/content.opf",
            "OEBPS/nav.xhtml",
            "OEBPS/toc.ncx",
            "OEBPS/landmarks.xhtml",
            "OEBPS/ch01.xhtml",
        ):
            assert expected in names, expected
        container = zf.read("META-INF/container.xml").decode("utf-8")
        assert "OEBPS/content.opf" in container
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "dc:title" in opf
        assert "dcterms:modified" in opf
        assert 'media-type="application/xhtml+xml"' in opf
        nav = zf.read("OEBPS/nav.xhtml").decode("utf-8")
        assert "ch01.xhtml" in nav


def test_build_epub_deterministic(tmp_path: Path) -> None:
    pub = _pub()
    entries = [
        {"id": "ch01", "region": "body", "title": "第一章"},
        {"id": "ch02", "region": "body", "title": "第二章"},
    ]
    content_files = [
        ("ch01.xhtml", render_document("第一章", "para1", lang="zh-CN")),
        ("ch02.xhtml", render_document("第二章", "para2", lang="zh-CN")),
    ]
    args = dict(lang="zh-CN", modified="2026-01-01T00:00:00Z")
    out1 = build_epub(pub, entries, content_files, out_path=tmp_path / "a.epub", **args)
    out2 = build_epub(pub, entries, content_files, out_path=tmp_path / "b.epub", **args)
    assert out1.read_bytes() == out2.read_bytes()


def test_build_epub_frontmatter_landmarks(tmp_path: Path) -> None:
    pub = _pub()
    entries = [
        {"id": "front-preface", "region": "frontmatter", "title": "前言"},
        {"id": "ch01", "region": "body", "title": "第一章"},
        {"id": "back-index", "region": "backmatter", "title": "索引"},
    ]
    content_files = []
    out = build_epub(
        pub,
        entries,
        content_files,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "b.epub",
    )
    with zipfile.ZipFile(out) as zf:
        lm = zf.read("OEBPS/landmarks.xhtml").decode("utf-8")
        assert 'epub:type="frontmatter"' in lm
        assert 'epub:type="bodymatter"' in lm
        assert 'epub:type="backmatter"' in lm


def test_build_epub_ncx(tmp_path: Path) -> None:
    pub = _pub()
    entries = [
        {"id": "ch01", "region": "body", "title": "第一章"},
        {"id": "ch02", "region": "body", "title": "第二章"},
    ]
    out = build_epub(
        pub,
        entries,
        [],
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "c.epub",
    )
    with zipfile.ZipFile(out) as zf:
        ncx = zf.read("OEBPS/toc.ncx").decode("utf-8")
        assert "navPoint" in ncx
        assert "playOrder" in ncx
        assert 'src="ch01.xhtml"' in ncx
