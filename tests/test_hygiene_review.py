"""#93：hygiene 候选的逐条处置、文本失效与坏文件诊断。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_epublizer import orchestrator as orch
from auto_epublizer.hygiene_review import collect, review_path, summarize


def _store(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n这是一个没有结束的句子\n", encoding="utf-8"
    )
    return store


def _write(store, rows: list[dict]) -> None:
    path = review_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_candidates_need_disposition_and_records_are_bound_to_text(tmp_path: Path) -> None:
    store = _store(tmp_path)
    data = collect(store)
    entry = next(e for e in data["entries"] if e["code"] == "half_sentence")
    assert entry["disposition"] is None
    summary = summarize(store)
    assert summary["status"] == "open" and summary["open"] >= 1

    _write(
        store,
        [
            {
                "schema_version": 1,
                "unit": entry["unit"],
                "block": entry["block"],
                "code": entry["code"],
                "text_sha256": entry["text_sha256"],
                "disposition": "false_positive",
                "reason": "原文诗行，句末无标点属体例",
            }
        ],
    )
    closed = summarize(store)
    assert closed["status"] == "ok" and closed["open"] == 0

    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n这是一个改过但仍未结束的句子\n", encoding="utf-8"
    )
    reopened = summarize(store)
    assert reopened["open"] >= 1 and reopened["stale"] >= 1


def test_bad_review_file_is_invalid_not_pass(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _write(store, [{"schema_version": 1, "unit": "ch01", "code": "half_sentence"}])
    summary = summarize(store)
    assert summary["status"] == "invalid"
    assert "text_sha256" in summary["reason"]

    _write(
        store,
        [
            {
                "schema_version": 1,
                "unit": "ch01",
                "block": 2,
                "code": "half_sentence",
                "text_sha256": "0" * 64,
                "disposition": "maybe",
                "reason": "x",
            }
        ],
    )
    with pytest.raises(ValueError, match="disposition"):
        collect(store)


def test_tail_change_after_context_prefix_reopens(tmp_path: Path) -> None:
    """#93：只改 60 字之后的尾部也必须让旧处置 stale。"""
    store = _store(tmp_path)
    prefix = "这是一个没有结束的句子" + "很长的正文" * 20
    target = store.translation_dir / "body" / "ch01.md"
    target.write_text(f"# 第一章\n\n{prefix}甲\n", encoding="utf-8")
    first = next(e for e in collect(store)["entries"] if e["code"] == "half_sentence")
    _write(
        store,
        [
            {
                "schema_version": 1,
                "unit": first["unit"],
                "block": first["block"],
                "code": first["code"],
                "text_sha256": first["text_sha256"],
                "disposition": "false_positive",
                "reason": "测试",
            }
        ],
    )
    target.write_text(f"# 第一章\n\n{prefix}乙\n", encoding="utf-8")
    assert summarize(store)["stale"] >= 1


def test_unit_scoped_collect_does_not_mark_other_units_gone(tmp_path: Path) -> None:
    """#93：按单元汇总时，其他单元的既有处置不能算 gone。"""
    src = tmp_path / "two.md"
    src.write_text("# 第一章\n\n正文。\n\n# 第二章\n\n正文。\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws-two"))
    for name, heading in (("ch01", "第一章"), ("ch02", "第二章")):
        (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
        (store.translation_dir / "body" / f"{name}.md").write_text(
            f"# {heading}\n\n这是一个没有结束的句子\n", encoding="utf-8"
        )
    entries = collect(store)["entries"]
    half = [e for e in entries if e["code"] == "half_sentence"]
    assert len(half) >= 2
    _write(
        store,
        [
            {
                "schema_version": 1,
                "unit": e["unit"],
                "block": e["block"],
                "code": e["code"],
                "text_sha256": e["text_sha256"],
                "disposition": "false_positive",
                "reason": "测试",
            }
            for e in half
        ],
    )
    scoped = summarize(store, unit_id="ch01")
    assert scoped["status"] == "ok"
    assert scoped["gone"] == 0
