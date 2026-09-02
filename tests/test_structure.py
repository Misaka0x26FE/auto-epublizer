"""structure 测试：四层归类、清洗、落盘。"""

from __future__ import annotations

from pathlib import Path

from auto_common.workspace import Publication, PublicationMeta, RunStore, init_workspace
from auto_epublizer.ingest.models import SourceDocument, SourceSegment, SourceUnit
from auto_epublizer.structure import (
    classify_units,
    clean_header_footer,
    rebuild_structure,
    strip_page_numbers,
    write_structured,
)


def _unit(title: str, segments: list[SourceSegment], kind: str = "chapter") -> SourceUnit:
    return SourceUnit(id="x", kind=kind, title=title, segments=segments)


def _seg(text: str, page: int | None = None, kind: str = "text") -> SourceSegment:
    meta = {}
    if page is not None:
        meta["source_page"] = page
    return SourceSegment(index=0, source=text, kind=kind, meta=meta)


def test_classify_units_front_body_back() -> None:
    doc = SourceDocument(
        title="B",
        units=[
            _unit("前言", [_seg("前言内容")], "preface"),
            _unit("第一章", [_seg("正文")], "chapter"),
            _unit("第二章", [_seg("更多正文")], "chapter"),
            _unit("索引", [_seg("索引内容")], "index"),
        ],
    )
    entries = classify_units(doc)
    assert entries[0].region == "frontmatter"
    assert entries[0].unit_id == "front-preface"
    assert entries[1].region == "body"
    assert entries[1].unit_id == "ch01"
    assert entries[2].unit_id == "ch02"
    assert entries[3].region == "backmatter"
    assert entries[3].unit_id == "back-index"


def test_classify_cover() -> None:
    doc = SourceDocument(title="B", units=[_unit("封面", [_seg("书名")], "cover")])
    entries = classify_units(doc)
    assert entries[0].unit_id == "cover"


def test_classify_toc() -> None:
    doc = SourceDocument(title="B", units=[_unit("目录", [_seg("...")], "toc")])
    entries = classify_units(doc)
    assert entries[0].rel_path == "frontmatter/toc.md"


def test_strip_page_numbers() -> None:
    segs = [_seg("正文1"), _seg("  12  "), _seg("正文2"), _seg("- 8 -")]
    out = strip_page_numbers(segs)
    assert [s.source for s in out] == ["正文1", "正文2"]
    assert [s.index for s in out] == [0, 1]


def test_clean_header_footer_removes_repeat() -> None:
    segs = []
    # 3 页，每页首行都是同一页眉"书名"
    for pg in (1, 2, 3):
        segs.append(_seg("书名", pg))
        segs.append(_seg(f"第{pg}页正文", pg))
    out = clean_header_footer(segs, min_pages=3)
    assert all(s.source != "书名" for s in out)
    assert len(out) == 3


def test_clean_header_footer_keeps_distinct() -> None:
    segs = [_seg("A", 1), _seg("B", 2), _seg("C", 3)]
    out = clean_header_footer(segs, min_pages=3)
    assert len(out) == 3


def test_rebuild_structure_entries() -> None:
    doc = SourceDocument(
        title="B",
        units=[_unit("第一章", [_seg("正文")], "chapter")],
    )
    pub = Publication(slug="b", meta=PublicationMeta(title="B"))
    entries = rebuild_structure(doc, pub)
    assert entries[0]["id"] == "ch01"
    assert entries[0]["region"] == "body"


def test_write_structured(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n\n# 第二章\n\n更多。\n", encoding="utf-8")
    store = init_workspace(src, workspace_dir=tmp_path / "ws")
    from auto_epublizer.ingest import load_document

    doc = load_document(src, store=store)
    entries = rebuild_structure(doc, store.load_publication())
    write_structured(store, doc, entries)
    assert (store.structured_dir / "body/ch01.md").is_file()
    assert (store.structured_dir / "body/ch02.md").is_file()


def test_write_structured_writes_front_and_back(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "ws")
    store.ensure_skeleton()
    doc = SourceDocument(
        title="B",
        units=[
            _unit("前言", [_seg("前言")], "preface"),
            _unit("第一章", [_seg("正文")], "chapter"),
            _unit("后记", [_seg("后记")], "afterword"),
        ],
    )
    entries = rebuild_structure(
        doc, store.load_publication() if store.exists() else Publication(slug="b")
    )
    write_structured(store, doc, entries)
    assert (store.structured_dir / "frontmatter/preface.md").is_file()
    assert (store.structured_dir / "body/ch01.md").is_file()
    assert (store.structured_dir / "backmatter/afterword.md").is_file()
