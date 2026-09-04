"""插入内容描述文件测试：id 命名、落盘/读取回路（schema 见 docs/pdf-content-spec.md §2）。"""

from __future__ import annotations

from auto_epublizer.ingest.inserts import (
    InsertRecord,
    InsertSource,
    next_insert_id,
    read_inserts,
    write_inserts,
)


def _rec(rid: str, type_: str, *, file: str | None = None) -> InsertRecord:
    return InsertRecord(
        id=rid,
        type=type_,
        source=InsertSource(page=12, bbox=[0, 0, 100, 100], xref=7, method="embedded"),
        file=file,
    )


def test_next_insert_id_page_sequencing() -> None:
    recs: list[InsertRecord] = []
    first = next_insert_id(recs, 12, "image")
    recs.append(_rec(first, "image"))
    second = next_insert_id(recs, 12, "image")
    assert (first, second) == ("p012-img01", "p012-img02")
    # 同页不同类型各自计数
    assert next_insert_id(recs, 12, "table") == "p012-tbl01"
    assert next_insert_id(recs, 12, "formula") == "p012-fml01"
    # 跨页重新计数
    assert next_insert_id(recs, 13, "image") == "p013-img01"


def test_write_and_read_roundtrip_sorted_by_id(tmp_path) -> None:
    recs = [
        _rec("p012-tbl01", "table"),
        _rec("p012-img02", "image", file="media/p012-img02.png"),
        _rec("p012-fml01", "formula"),
        _rec("p012-img01", "image", file="media/p012-img01.png"),
    ]
    write_inserts(tmp_path, recs)
    # 单文件 + index.jsonl 均落盘
    for r in recs:
        assert (tmp_path / "inserts" / f"{r.id}.json").is_file()
    loaded = read_inserts(tmp_path)
    assert [r.id for r in loaded] == [
        "p012-fml01",
        "p012-img01",
        "p012-img02",
        "p012-tbl01",
    ]
    assert loaded[1].source.xref == 7
    assert loaded[2].latex is None and loaded[2].content_desc == ""


def test_write_empty_is_noop_and_read_missing_is_empty(tmp_path) -> None:
    write_inserts(tmp_path, [])
    assert not (tmp_path / "inserts").exists()
    assert read_inserts(tmp_path) == []
