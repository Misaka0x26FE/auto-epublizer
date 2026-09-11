"""EPUB 读取器测试：锚点清洗 / spine 切分 / 非线性项内联 / 元数据。

离线确定性；需要 pandoc 的集成用例用 skipif 门控。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from auto_epublizer.ingest.epub_reader import (
    clean_pandoc_residue,
    read_epub,
    read_epub_package,
    split_by_spine_anchors,
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


def test_clean_pandoc_residue_removes_anchors_and_attrs() -> None:
    raw = "[]{#f.xhtml#a}Hello []{#g}[Sub]{.small} *keep* <br/>world"
    out = clean_pandoc_residue(raw)
    assert out == "Hello Sub *keep*  world"
    assert "[]{#" not in out
    assert "{.small}" not in out
    assert "<br" not in out
    # 裸类属性（非 [text]{.class} 形式，如 `*Name* {.author}`）也要清除
    assert clean_pandoc_residue("*Jordan Goodman* {.author}") == "*Jordan Goodman*"


def test_clean_pandoc_residue_preserves_grid_table_indent() -> None:
    md = "  --- ---\n  a   b\n  --- ---"
    assert clean_pandoc_residue(md) == md


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
