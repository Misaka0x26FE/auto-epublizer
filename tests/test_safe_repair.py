# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""批准的精确替换必须预检整组，失败回滚，中断后拒绝静默续跑。"""

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fixture(tmp_path: Path):
    source = tmp_path / "book.md"
    source.write_text("# Chapter\n\nA synthetic source sentence.\n")
    store = orch.init(str(source), workspace_dir=str(tmp_path / "ws"))
    pub = store.load_publication()
    unit = pub.units[0]
    rel = unit.meta["rel_path"]
    md = store.translation_dir / rel
    md.parent.mkdir(exist_ok=True, parents=True)
    md.write_text("# 章节\n\n旧译名的合成句子。\n")
    align = store.unit_align_path(unit.id)
    align.parent.mkdir(exist_ok=True, parents=True)
    align.write_text(
        json.dumps(
            {
                "seq": 1,
                "src": "A synthetic source sentence.",
                "tgt": "旧译名的合成句子。",
                "note": None,
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    evidence = pub.meta.source
    plan = {
        "schema_version": "1",
        "rule_version": "safe-repair-1",
        "source_sha256": pub.meta.source_sha256,
        "edits": [],
    }
    for path in (md, align):
        plan["edits"].append(
            {
                "unit": unit.id,
                "path": path.relative_to(store.dir).as_posix(),
                "sha256": _hash(path.read_bytes()),
                "old": "旧译名",
                "new": "新译名",
                "approved": True,
                "evidence": {
                    "path": evidence,
                    "sha256": _hash((store.dir / evidence).read_bytes()),
                    "page": 1,
                },
            }
        )
    return store, plan, md, align


def _snapshot(store):
    return {
        p.relative_to(store.dir).as_posix(): p.read_bytes()
        for p in store.dir.rglob("*")
        if p.is_file()
    }


def test_dry_run_is_byte_read_only_and_apply_is_idempotent(tmp_path: Path) -> None:
    from auto_epublizer.safe_repair import apply_plan

    store, plan, md, _ = _fixture(tmp_path)
    before = _snapshot(store)
    assert apply_plan(store, plan)["status"] == "dry_run"
    assert _snapshot(store) == before
    assert apply_plan(store, plan, apply=True)["status"] == "applied"
    assert "新译名" in md.read_text()
    after = _snapshot(store)
    assert apply_plan(store, plan, apply=True)["status"] == "already_applied"
    assert _snapshot(store) == after
    assert (store.publication_path).read_bytes() == before["publication.json"]


@pytest.mark.parametrize(
    "defect", ["unapproved", "baseline", "unknown", "ambiguous", "drift", "escape", "evidence"]
)
def test_preflight_rejects_entire_group_without_writes(tmp_path: Path, defect: str) -> None:
    from auto_epublizer.safe_repair import apply_plan

    store, plan, md, _ = _fixture(tmp_path)
    if defect == "unapproved":
        plan["edits"][1]["approved"] = False
    elif defect == "baseline":
        plan["edits"][1]["sha256"] = "0" * 64
    elif defect == "unknown":
        plan["edits"][1]["regex"] = True
    elif defect == "ambiguous":
        md.write_text(md.read_text() + "\n旧译名\n")
        plan["edits"][0]["sha256"] = _hash(md.read_bytes())
    elif defect == "drift":
        plan["edits"].pop()
    elif defect == "escape":
        plan["edits"][1]["path"] = "../outside.md"
    else:
        plan["edits"][1]["evidence"]["sha256"] = "0" * 64
    before = _snapshot(store)
    with pytest.raises(ValueError):
        apply_plan(store, plan, apply=True)
    assert _snapshot(store) == before


def test_io_failure_rolls_back_complete_group(tmp_path: Path, monkeypatch) -> None:
    from auto_epublizer import safe_repair as repair

    store, plan, md, align = _fixture(tmp_path)
    before = [md.read_bytes(), align.read_bytes()]
    real = repair._replace_bytes
    calls = 0

    def failing(path, data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic disk failure")
        return real(path, data)

    monkeypatch.setattr(repair, "_replace_bytes", failing)
    with pytest.raises(ValueError, match="回滚"):
        repair.apply_plan(store, plan, apply=True)
    assert [md.read_bytes(), align.read_bytes()] == before
    repair.assert_no_pending(store)


def test_interruption_blocks_cli_and_recovery_refuses_other_work(
    tmp_path: Path, monkeypatch
) -> None:
    from auto_epublizer import safe_repair as repair

    store, plan, md, align = _fixture(tmp_path)
    before = [md.read_bytes(), align.read_bytes()]
    real = repair._replace_bytes
    calls = 0

    def interrupted(path, data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt()
        return real(path, data)

    monkeypatch.setattr(repair, "_replace_bytes", interrupted)
    with pytest.raises(KeyboardInterrupt):
        repair.apply_plan(store, plan, apply=True)
    with pytest.raises(ValueError, match="未决"):
        repair.assert_no_pending(store)
    result = CliRunner().invoke(app, ["build", "--workspace", str(store.dir)])
    assert result.exit_code != 0 and "未决" in result.output
    md.write_text("Other person's new work.\n")
    with pytest.raises(ValueError):
        repair.recover(store)
    assert md.read_text() == "Other person's new work.\n"
    md.write_bytes(before[0])
    monkeypatch.setattr(repair, "_replace_bytes", real)
    assert repair.recover(store)["status"] == "rolled_back"
    assert [md.read_bytes(), align.read_bytes()] == before


@pytest.mark.parametrize(
    "protected", ["[^ref-1]", "[link](target.xhtml)", "1945", "OriginalName", "{{img:x}}"]
)
def test_paired_edits_cannot_drop_protected_source_tokens(tmp_path: Path, protected: str) -> None:
    from auto_epublizer.safe_repair import apply_plan

    store, plan, md, align = _fixture(tmp_path)
    for path, edit in zip((md, align), plan["edits"], strict=True):
        path.write_text(path.read_text().replace("旧译名", "旧译名" + protected))
        edit["sha256"] = _hash(path.read_bytes())
        edit["old"] = "旧译名" + protected
    before = _snapshot(store)
    with pytest.raises(ValueError):
        apply_plan(store, plan, apply=True)
    assert _snapshot(store) == before


def test_idempotent_record_does_not_override_changed_source_identity(tmp_path: Path) -> None:
    from auto_epublizer.safe_repair import apply_plan

    store, plan, _, _ = _fixture(tmp_path)
    apply_plan(store, plan, apply=True)
    (store.dir / store.load_publication().meta.source).write_text("A different source.")
    with pytest.raises(ValueError):
        apply_plan(store, plan, apply=True)


def test_cli_dry_run_and_apply_are_explicit(tmp_path: Path) -> None:
    store, plan, md, _ = _fixture(tmp_path)
    file = tmp_path / "repair.json"
    file.write_text(json.dumps(plan, ensure_ascii=False))
    before = _snapshot(store)
    result = CliRunner().invoke(app, ["repair", "apply", str(file), "--workspace", str(store.dir)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "dry_run"
    assert _snapshot(store) == before
    result = CliRunner().invoke(
        app, ["repair", "apply", str(file), "--workspace", str(store.dir), "--apply"]
    )
    assert result.exit_code == 0, result.output
    assert "新译名" in md.read_text()


def test_inline_code_cannot_be_rewritten_as_a_name(tmp_path: Path) -> None:
    from auto_epublizer.safe_repair import apply_plan

    store, plan, md, _ = _fixture(tmp_path)
    md.write_text(md.read_text().replace("旧译名", "`旧译名`"))
    plan["edits"][0]["sha256"] = _hash(md.read_bytes())
    with pytest.raises(ValueError):
        apply_plan(store, plan)
