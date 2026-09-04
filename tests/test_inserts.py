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


def test_read_inserts_scans_files_not_index(tmp_path) -> None:
    """读取以 <id>.json 为权威：排除 index.jsonl；手工补语义即时生效。"""
    import json

    recs = [_rec("p012-img01", "image", file="media/p012-img01.png")]
    write_inserts(tmp_path, recs)
    # agent 只编辑单文件补 content_desc（index.jsonl 快照不动）
    p = tmp_path / "inserts" / "p012-img01.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["content_desc"] = "第一章示意图"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    # agent 手工新增一条记录
    rec2 = _rec("p013-fml01", "formula").model_copy(update={"latex": "E=mc^2"})
    (tmp_path / "inserts" / "p013-fml01.json").write_text(rec2.model_dump_json(), encoding="utf-8")

    loaded = read_inserts(tmp_path)
    assert [r.id for r in loaded] == ["p012-img01", "p013-fml01"]
    assert loaded[0].content_desc == "第一章示意图"
    assert loaded[1].latex == "E=mc^2"


def test_read_inserts_skips_corrupt_files(tmp_path) -> None:
    """坏 json 跳过；index.jsonl 不作为读取源。"""
    (tmp_path / "inserts").mkdir()
    (tmp_path / "inserts" / "p001-img01.json").write_text("{broken", encoding="utf-8")
    (tmp_path / "inserts" / "p002-img01.json").write_text(
        _rec("p002-img01", "image").model_dump_json(), encoding="utf-8"
    )
    (tmp_path / "inserts" / "index.jsonl").write_text("garbage\n", encoding="utf-8")
    assert [r.id for r in read_inserts(tmp_path)] == ["p002-img01"]
