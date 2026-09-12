"""EPUB 读取器测试：锚点清洗 / spine 切分 / 非线性项内联 / 元数据。

离线确定性；需要 pandoc 的集成用例用 skipif 门控。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from auto_epublizer.ingest.epub_reader import (
    _parse_heading_line,
    clean_pandoc_residue,
    read_epub,
    read_epub_package,
    split_by_spine_anchors,
    strip_self_file_prefix,
)
from auto_epublizer.ingest.pandoc_reader import pandoc_available

_CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Fixture Book</dc:title>
    <dc:creator>A. Author</dc:creator>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="tbl1" href="tbl1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="ch1"/><itemref idref="tbl1" linear="no"/></spine>
</package>
"""

_CH1 = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>CH ONE</title></head><body>
<div class="chapter"><h1><a id="ncx_1"></a>1 A TEST CHAPTER</h1>
<p>See <a href="tbl1.xhtml">Table 1.1</a> for data.</p>
<p><a href="tbl1.xhtml"><i>Table 1.1</i> Data table</a></p>
</div></body></html>
"""

_TBL1 = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>CH ONE</title></head><body>
<p><i>Table 1.1</i> Data table</p>
<table><tr><td>Item</td><td>Value</td></tr><tr><td>Foo</td><td>42</td></tr></table>
</body></html>
"""


def _make_epub(tmp_path: Path) -> Path:
    p = tmp_path / "fixture.epub"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER)
        zf.writestr("OEBPS/content.opf", _OPF)
        zf.writestr("OEBPS/ch1.xhtml", _CH1)
        zf.writestr("OEBPS/tbl1.xhtml", _TBL1)
    return p


# ── 纯函数 ────────────────────────────────────────────────────────────────


def test_clean_pandoc_residue_removes_file_anchors_and_attrs() -> None:
    # 无 fragment 的 spine 边界文件锚点删除；类属性清除；<br> 转空格
    raw = "[]{#f.xhtml}Hello [Sub]{.small} *keep* <br/>world"
    out = clean_pandoc_residue(raw)
    assert out == "Hello Sub *keep*  world"
    assert ".xhtml" not in out
    assert "{.small}" not in out
    assert "<br" not in out
    # 裸类属性（非 [text]{.class} 形式，如 `*Name* {.author}`）也要清除
    assert clean_pandoc_residue("*Jordan Goodman* {.author}") == "*Jordan Goodman*"


def test_clean_pandoc_residue_keeps_inline_nav_anchors() -> None:
    # 正文导航锚点 []{#page_15} / 带 fragment 的文件锚点 []{#f.xhtml#a}（源 <a id>）
    # 必须保留：它们是索引/目录跳转目标，删除会让成品内部链接全部失效。
    assert "[]{#page_15}" in clean_pandoc_residue("a []{#page_15}b")
    assert "[]{#f.xhtml#a}" in clean_pandoc_residue("pre []{#f.xhtml#a} post")
    # 标题 id 属性 {#ch01} 同样保留（供 build 渲染 <h id>）
    assert "{#ch01}" in clean_pandoc_residue("Heading {#ch01}")
    # 无 fragment 的纯文件锚点仍应清除
    assert "[]{#a.xhtml}" not in clean_pandoc_residue("pre []{#a.xhtml} post")


def test_clean_pandoc_residue_preserves_grid_table_indent() -> None:
    md = "  --- ---\n  a   b\n  --- ---"
    assert clean_pandoc_residue(md) == md


def test_strip_self_file_prefix() -> None:
    # 当前 spine 文件自身的文件名前缀去除（锚点/链接/标题属性）
    assert strip_self_file_prefix("[]{#ch1.xhtml#ncx_1}Title", "ch1.xhtml") == "[]{#ncx_1}Title"
    assert strip_self_file_prefix("see [x](#ch1.xhtml#p2)", "ch1.xhtml") == "see [x](#p2)"
    assert strip_self_file_prefix("T {#ch1.xhtml#h1 .h1}", "ch1.xhtml") == "T {#h1}"
    # 无 fragment 的纯文件锚点删除
    assert strip_self_file_prefix("a []{#ch1.xhtml} b", "ch1.xhtml") == "a  b"
    # 指向其他文件的引用保留（交给 links 全局重映射）
    assert strip_self_file_prefix("[y](ch2.xhtml#q)", "ch1.xhtml") == "[y](ch2.xhtml#q)"


def test_parse_heading_line_extracts_id_and_leading_anchors() -> None:
    title, hid, leading = _parse_heading_line(
        "[]{#page_20 .calibre5}**2 Confrontation** {#ch02 .h1}"
    )
    assert title == "2 Confrontation"
    assert hid == "ch02"
    assert leading == "[]{#page_20}"
    # 无属性的普通标题
    t2, h2, l2 = _parse_heading_line("[]{#ncx_1}1 A TEST CHAPTER")
    assert t2 == "1 A TEST CHAPTER"
    assert h2 is None
    assert l2 == "[]{#ncx_1}"


def test_split_by_spine_anchors_in_order() -> None:
    md = "pre\n\n[]{#a.xhtml}\n\nbody a\n\n[]{#b.xhtml}\n\nbody b\n"
    blocks = split_by_spine_anchors(md, ["a.xhtml", "b.xhtml"])
    assert blocks is not None
    assert "pre" in blocks[0][0]  # 首锚点前内容归入首块
    assert "body a" in "\n".join(blocks[0])
    assert "body b" in "\n".join(blocks[1])


def test_split_by_spine_anchors_missing_or_out_of_order_returns_none() -> None:
    md = "[]{#a.xhtml}\n\n[]{#b.xhtml}\n"
    assert split_by_spine_anchors(md, ["a.xhtml", "c.xhtml"]) is None
    assert split_by_spine_anchors(md, ["b.xhtml", "a.xhtml"]) is None


def test_derive_heading_levels_part_chapter_nesting() -> None:
    """部（PART x）为 1 级，部内编号章为 2 级；部结束（结论等）后回到 1 级。"""
    from auto_epublizer.ingest.epub_reader import _derive_heading_levels

    titles = [
        "1. WHAT IS TOBACCO?",
        "PART I",
        "2. FOOD OF THE SPIRITS",
        "3. WHY TOBACCO?",
        "PART II",
        "4. RITUALS",
        "CONCLUSION",
        "10. TO DIE BY SMOKE",
        "GLOSSARY",
    ]
    assert _derive_heading_levels(titles) == [1, 1, 2, 2, 1, 2, 1, 1, 1]


def test_derive_heading_levels_no_parts_stays_flat() -> None:
    from auto_epublizer.ingest.epub_reader import _derive_heading_levels

    assert _derive_heading_levels(["Intro", "1. A", "2. B"]) == [1, 1, 1]


# ── EPUB 包解析 ───────────────────────────────────────────────────────────


def test_read_epub_package_spine_and_metadata(tmp_path: Path) -> None:
    pkg = read_epub_package(_make_epub(tmp_path))
    assert pkg.metadata["title"] == "Fixture Book"
    assert pkg.metadata["creator"] == "A. Author"
    assert len(pkg.linear) == 1
    assert len(pkg.nonlinear) == 1
    assert pkg.linear[0].href == "ch1.xhtml"
    assert pkg.nonlinear[0].href == "tbl1.xhtml"


# ── 集成（需 pandoc）──────────────────────────────────────────────────────


@pytest.mark.skipif(not pandoc_available(), reason="需要 pandoc")
def test_read_epub_spine_units_and_table_inlined(tmp_path: Path) -> None:
    doc = read_epub(_make_epub(tmp_path), media_dir=tmp_path / "media")
    assert doc.fmt == "epub"
    assert len(doc.units) == 1
    unit = doc.units[0]
    assert unit.title == "1 A TEST CHAPTER"
    assert "[]{#" not in unit.title
    body = "\n".join(s.source for s in unit.segments)
    # 非线性表格项的表体被内联（caption 链接段 → caption + 表格 + 表源）
    assert "Foo" in body and "42" in body
    assert "See [Table 1.1](tbl1.xhtml) for data." in body


@pytest.mark.skipif(not pandoc_available(), reason="需要 pandoc")
def test_inlined_nonlinear_content_is_cleaned(tmp_path: Path) -> None:
    """非线性项内联内容与线性路径同样清洗：pandoc 类属性不得进成品。"""
    p = tmp_path / "residue.epub"
    tbl = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<p><i>Table 1.1</i> Data table</p>"
        '<table><tr><td><span class="small">Item</span></td>'
        "<td>Value</td></tr></table></body></html>"
    )
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER)
        zf.writestr("OEBPS/content.opf", _OPF)
        zf.writestr("OEBPS/ch1.xhtml", _CH1)
        zf.writestr("OEBPS/tbl1.xhtml", tbl)
    doc = read_epub(p, media_dir=tmp_path / "media")
    body = "\n".join(s.source for u in doc.units for s in u.segments)
    assert "{." not in body  # pandoc 类属性残留已清洗
    assert "Item" in body  # 文本本身保留
