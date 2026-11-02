# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""B4 真值表：对照表重建的只读预检、输入绑定、显式应用与回滚。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from auto_epublizer import align_rebuild
from auto_epublizer import orchestrator as orch


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter I\n\nFirst sentence here.\n\nSecond sentence here.\n", encoding="utf-8"
    )
    return orch.init(str(src), workspace_dir=tmp_path / "ws")


def _write_products(store, tgt_md: str, rows: list[dict]) -> None:
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body/ch01.md").write_text(tgt_md, encoding="utf-8")
    align = store.unit_align_path("ch01")
    align.parent.mkdir(parents=True, exist_ok=True)
    align.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


def _plan(store, rows: list[dict], *, approved: bool = True) -> dict:
    pub = store.load_publication()
    unit = pub.units[0]
    target = store.translation_dir / "body/ch01.md"
    align = store.unit_align_path(unit.id)
    return {
        "schema_version": "1",
        "rule_version": "align-rebuild-1",
        "source_sha256": pub.meta.source_sha256,
        "units": [
            {
                "unit": unit.id,
                "translation_sha256": _sha(target.read_bytes()),
                "align_sha256": _sha(align.read_bytes()),
                "rows": rows,
                "approved": approved,
            }
        ],
    }


def _rows() -> list[dict]:
    return [
        {"seq": 1, "src": "First sentence here.", "tgt": "第一句。", "note": None},
        {"seq": 2, "src": "Second sentence here.", "tgt": "第二句。", "note": None},
    ]


def _prepare(tmp_path: Path):
    store = _workspace(tmp_path)
    _write_products(store, "# 第一章\n\n第一句。\n", _rows()[:1])
    orch.import_translations(store)
    # agent 修订译文：补上第二句（尚未 import）
    _write_products(store, "# 第一章\n\n第一句。第二句。\n", _rows()[:1])
    return store


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    store = _prepare(tmp_path)
    plan = _plan(store, _rows())
    align = store.unit_align_path("ch01")
    before = align.read_bytes()
    result = align_rebuild.apply_align_rebuild(store, plan)
    assert result["status"] == "dry_run"
    assert align.read_bytes() == before


def test_apply_writes_rows_and_registers_baseline(tmp_path: Path) -> None:
    store = _prepare(tmp_path)
    plan = _plan(store, _rows())
    result = align_rebuild.apply_align_rebuild(store, plan, apply=True)
    assert result["status"] == "applied"
    saved = [json.loads(line) for line in store.unit_align_path("ch01").read_text().splitlines()]
    assert [row["seq"] for row in saved] == [1, 2]
    unit = store.load_publication().units[0]
    from auto_translator.review import align_block_spans, structure_digest
    from auto_translator.translation.align import read_align

    spans, issues = align_block_spans(
        (store.translation_dir / "body/ch01.md").read_text(),
        read_align(store.unit_align_path("ch01")),
    )
    assert issues == []
    assert unit.meta["align_structure"] == structure_digest(spans)


def test_changed_align_after_plan_is_rejected(tmp_path: Path) -> None:
    store = _prepare(tmp_path)
    plan = _plan(store, _rows())
    align = store.unit_align_path("ch01")
    align.write_text(align.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="对照表基线已变更"):
        align_rebuild.apply_align_rebuild(store, plan, apply=True)


def test_rows_must_match_translation_md(tmp_path: Path) -> None:
    store = _prepare(tmp_path)
    plan = _plan(store, _rows()[:1])
    with pytest.raises(ValueError, match="译文与对照表不一致"):
        align_rebuild.apply_align_rebuild(store, plan)


def test_reviewed_state_is_invalidated_by_apply(tmp_path: Path) -> None:
    store = _prepare(tmp_path)
    plan = _plan(store, _rows())
    align_rebuild.apply_align_rebuild(store, plan, apply=True)
    store.set_unit_status("ch01", "reviewed")
    rows = _rows()
    rows[1]["note"] = "rebuilt"
    plan = _plan(store, rows)
    align_rebuild.apply_align_rebuild(store, plan, apply=True)
    assert store.load_publication().units[0].status == "aligned"


def test_write_failure_rolls_back_all_units(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter I\n\nFirst sentence here.\n\n# Chapter II\n\nThird sentence here.\n",
        encoding="utf-8",
    )
    store = orch.init(str(src), workspace_dir=tmp_path / "ws")
    products = (
        ("ch01", "body/ch01.md", "# 第1章\n\n第一句。", "First sentence here.", "第一句。"),
        ("ch02", "body/ch02.md", "# 第2章\n\n第三句。", "Third sentence here.", "第三句。"),
    )
    for unit_id, rel, md, source, target in products:
        path = store.translation_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md + "\n", encoding="utf-8")
        align = store.unit_align_path(unit_id)
        align.parent.mkdir(parents=True, exist_ok=True)
        align.write_text(
            json.dumps({"seq": 1, "src": source, "tgt": target, "note": None}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
    orch.import_translations(store)
    pub = store.load_publication()
    units = []
    for unit_id, rel, _md, source, target in products:
        align = store.unit_align_path(unit_id)
        units.append(
            {
                "unit": unit_id,
                "translation_sha256": _sha((store.translation_dir / rel).read_bytes()),
                "align_sha256": _sha(align.read_bytes()),
                "rows": [
                    {"seq": 1, "src": source, "tgt": target, "note": "rebuilt"},
                ],
                "approved": True,
            }
        )
    plan = {
        "schema_version": "1",
        "rule_version": "align-rebuild-1",
        "source_sha256": pub.meta.source_sha256,
        "units": units,
    }
    before = {unit.id: store.unit_align_path(unit.id).read_bytes() for unit in pub.units}
    calls = {"n": 0}
    real_replace = align_rebuild._replace

    def flaky(path, data):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real_replace(path, data)

    monkeypatch.setattr(align_rebuild, "_replace", flaky)
    with pytest.raises(ValueError, match="已回滚"):
        align_rebuild.apply_align_rebuild(store, plan, apply=True)
    for unit in pub.units:
        assert store.unit_align_path(unit.id).read_bytes() == before[unit.id]


def test_failure_during_registration_restores_state_and_digests(
    tmp_path: Path, monkeypatch
) -> None:
    """写文件成功后登记失败，也必须恢复 unit 状态/meta（审查 P1）。"""
    store = _prepare(tmp_path)
    plan = _plan(store, _rows())
    store.set_unit_status("ch01", "reviewed")
    before_unit = store.load_publication().units[0]
    before_meta = json.loads(json.dumps(before_unit.meta))
    assert before_unit.status == "reviewed"

    def boom(*args, **kwargs):
        raise OSError("state io")

    monkeypatch.setattr(store, "record_unit_content", boom)
    with pytest.raises(ValueError, match="已回滚"):
        align_rebuild.apply_align_rebuild(store, plan, apply=True)
    after = store.load_publication().units[0]
    assert after.status == before_unit.status
    assert after.meta == before_meta


def test_missing_structured_source_blocks_registration(tmp_path: Path) -> None:
    store = _prepare(tmp_path)
    plan = _plan(store, _rows())
    pub = store.load_publication()
    rel = pub.units[0].meta["rel_path"]
    (store.structured_dir / rel).unlink()
    with pytest.raises(ValueError, match="结构化源文"):
        align_rebuild.apply_align_rebuild(store, plan, apply=True)


def _pending_journal(store, plan, rows):
    """构造「文件与状态已改、日志仍 pending」的中断现场。"""
    pub = store.load_publication()
    unit = pub.units[0]
    align = store.unit_align_path(unit.id)
    before = align.read_bytes()
    from auto_epublizer.align_rebuild import _rows_payload

    after = _rows_payload(rows)
    align.write_bytes(after)
    store.set_unit_status(unit.id, "aligned")
    journal = {
        "rule_version": "align-rebuild-1",
        "plan_sha256": "x",
        "status": "pending",
        "files": [
            {
                "path": align.relative_to(store.dir).as_posix(),
                "unit": unit.id,
                "status_before": "reviewed",
                "meta_before": {"rel_path": unit.meta.get("rel_path")},
                "before": before.hex(),
                "old_sha256": _sha(before),
                "new_sha256": _sha(after),
                "align_structure": "digest",
            }
        ],
    }
    path = align_rebuild._journal_dir(store) / "crashed.json"
    align_rebuild._persist(path, journal)
    return path, align, before, unit.id


def test_interrupted_transaction_is_recovered_from_journal(tmp_path: Path) -> None:
    store = _prepare(tmp_path)
    path, align, before, unit_id = _pending_journal(store, None, _rows())
    assert align.read_bytes() != before
    result = orch.repair_recover(store)
    assert result["align"]["status"] == "recovered"
    assert align.read_bytes() == before
    assert store.load_publication().unit(unit_id).status == "reviewed"
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "rolled_back"


def test_pending_transaction_blocks_new_apply(tmp_path: Path) -> None:
    store = _prepare(tmp_path)
    _pending_journal(store, None, _rows())
    plan = _plan(store, _rows())
    with pytest.raises(ValueError, match="未决重对齐事务"):
        align_rebuild.apply_align_rebuild(store, plan, apply=True)


def test_failed_state_restore_is_not_reported_as_rolled_back(tmp_path: Path, monkeypatch) -> None:
    store = _prepare(tmp_path)
    plan = _plan(store, _rows())
    store.set_unit_status("ch01", "reviewed")

    def boom(*args, **kwargs):
        raise OSError("state io")

    monkeypatch.setattr(store, "record_unit_content", boom)
    monkeypatch.setattr(store, "restore_unit_registration", boom)
    with pytest.raises(ValueError, match="回滚未完成"):
        align_rebuild.apply_align_rebuild(store, plan, apply=True)
    journal = next(align_rebuild._journal_dir(store).glob("*.json"))
    assert json.loads(journal.read_text(encoding="utf-8"))["status"] == "rollback_incomplete"
    # 修复故障后显式恢复
    monkeypatch.undo()
    result = orch.repair_recover(store)
    assert result["align"]["status"] == "recovered"
    assert store.load_publication().units[0].status == "reviewed"
    assert json.loads(journal.read_text(encoding="utf-8"))["status"] == "rolled_back"


def test_retry_after_success_is_idempotent(tmp_path: Path) -> None:
    store = _prepare(tmp_path)
    plan = _plan(store, _rows())
    align_rebuild.apply_align_rebuild(store, plan, apply=True)
    again = align_rebuild.apply_align_rebuild(store, plan, apply=True)
    assert again["status"] in {"already_applied", "applied"}
