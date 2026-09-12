"""内部链接重写测试：pandoc 前导 # 清理 + 源文件→成品单元的 spine 映射。"""

from __future__ import annotations

from auto_epublizer.ingest.models import SourceDocument, SourceSegment, SourceUnit
from auto_epublizer.structure.classify import ClassifiedUnit, classify_units
from auto_epublizer.structure.links import (
    build_src_to_unit,
    rewrite_internal_links,
    rewrite_links_in_text,
)


def _cls(unit_id: str, spine_href: str, segments: list[SourceSegment]) -> ClassifiedUnit:
    unit = SourceUnit(
        id="x",
        kind="chapter",
        title="t",
        segments=segments,
        meta={"spine_href": spine_href},
    )
    return ClassifiedUnit(
        unit=unit, region="body", kind="chapter", unit_id=unit_id, rel_path=f"body/{unit_id}.md"
    )


def test_strip_pandoc_leading_hash_and_remap() -> None:
    src_map = {"ch17": "ch19"}
    # pandoc -f epub 产生的非法链接：#ch17.html#page_311（两个 #）
    out = rewrite_links_in_text("[311](#ch17.html#page_311)", "back-index", src_map)
    assert out == "[311](ch19.xhtml#page_311)"


def test_plain_internal_link_also_remapped() -> None:
    src_map = {"ch17": "ch19"}
    assert (
        rewrite_links_in_text("[x](ch17.html#page_1)", "back-index", src_map)
        == "[x](ch19.xhtml#page_1)"
    )
    # 尖括号包裹
    assert (
        rewrite_links_in_text("[x](<ch17.html#page_1>)", "back-index", src_map)
        == "[x](ch19.xhtml#page_1)"
    )
    # 带相对路径
    assert (
        rewrite_links_in_text("[x](../Text/ch17.html#page_1)", "back-index", src_map)
        == "[x](ch19.xhtml#page_1)"
    )
    # 无 fragment
    assert rewrite_links_in_text("[x](ch17.html)", "back-index", src_map) == "[x](ch19.xhtml)"


def test_same_unit_link_becomes_pure_fragment() -> None:
    src_map = {"ch17": "ch19"}
    # 目标就是当前单元：只保留锚点
    assert rewrite_links_in_text("[15](#ch17.html#page_15)", "ch19", src_map) == "[15](#page_15)"


def test_external_and_unmapped_links_untouched() -> None:
    src_map = {"ch17": "ch19"}
    assert (
        rewrite_links_in_text("[web](https://example.com/a#b)", "ch19", src_map)
        == "[web](https://example.com/a#b)"
    )
    assert (
        rewrite_links_in_text("[mail](mailto:a@b.com)", "ch19", src_map) == "[mail](mailto:a@b.com)"
    )
    # 源文件不在 spine 映射中：保留原样（不猜测）
    assert rewrite_links_in_text("[x](unknown.html#y)", "ch19", src_map) == "[x](unknown.html#y)"


def test_build_src_to_unit_from_classified() -> None:
    c1 = _cls("ch03", "Text/ch01.html", [])
    c2 = _cls("back-index", "Text/index.html", [])
    mapping = build_src_to_unit([c1, c2])
    assert mapping == {"ch01": "ch03", "index": "back-index"}


def test_rewrite_internal_links_mutates_doc() -> None:
    seg = SourceSegment(index=0, source="see [311](#ch17.html#page_311) now", kind="text")
    target = _cls("ch19", "Text/ch17.html", [SourceSegment(index=0, source="body", kind="text")])
    cur = _cls("back-index", "Text/index.html", [seg])
    doc = SourceDocument(title="b", units=[target.unit, cur.unit])
    n = rewrite_internal_links(doc, [target, cur])
    assert n == 1
    assert cur.unit.segments[0].source == "see [311](ch19.xhtml#page_311) now"


def test_classify_then_rewrite_end_to_end() -> None:
    # classify_units 分配 ch01 给第一个正文章节；其 meta.spine_href 提供源文件名
    unit = SourceUnit(
        id="x",
        kind="chapter",
        title="Chapter One",
        segments=[SourceSegment(index=0, source="ref [15](#ch01.html#page_15)", kind="text")],
        meta={"spine_href": "Text/ch01.html"},
    )
    doc = SourceDocument(title="b", units=[unit])
    classified = classify_units(doc)
    rewrite_internal_links(doc, classified)
    # 第一章 → ch01；链接指向自身 → 纯锚点
    assert classified[0].unit_id == "ch01"
    assert doc.units[0].segments[0].source == "ref [15](#page_15)"


def test_anchor_span_strips_source_prefix_and_class() -> None:
    src_map = {"ch02": "ch04"}
    # pandoc 空锚点：[]{#源文件#锚点}，可能带 class；落点在当前单元 → 纯锚点
    out = rewrite_links_in_text("[]{#ch02.html#page_21}Europeans were", "ch04", src_map)
    assert out == "[]{#page_21}Europeans were"
    out2 = rewrite_links_in_text("x []{#ch02.html#page_20 .calibre5} y", "ch04", src_map)
    assert out2 == "x []{#page_20} y"
    # 已是纯锚点则保持不变
    assert rewrite_links_in_text("a []{#page_3} b", "ch04", src_map) == "a []{#page_3} b"


def test_heading_id_attr_strips_source_prefix_and_class() -> None:
    src_map = {"ch02": "ch04"}
    # pandoc 标题属性 {#源文件#id .h1} → {#id}
    out = rewrite_links_in_text("**2 Title** {#ch02.html#ch02 .h1}", "ch04", src_map)
    assert out == "**2 Title** {#ch02}"
    # 纯 {#id} 保持
    assert rewrite_links_in_text("Title {#ch02}", "ch04", src_map) == "Title {#ch02}"
