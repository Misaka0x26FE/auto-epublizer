# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""报告摘要覆盖全部放行硬门输入（增量审查 F2）：逐类状态转换/失效证据。

每类输入变化都必须让已放行报告 `stale=True`（否则 status/ledger 会把违反硬门的
工作区当成有效放行）。覆盖：术语冲突账本、词表、注释登记摘要、inserts 单文件与
其引用资源存在性；catalog 已有既有回归（test_notes.py）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_common.config import Config
from auto_common.workspace import RunStore
from auto_epublizer import orchestrator as orch
from auto_epublizer.ingest.inserts import InsertRecord, InsertSource, read_inserts, write_inserts
from auto_epublizer.qa.artifacts import artifacts_digest, report_state
from auto_epublizer.qa.epubcheck import EpubcheckResult


def _released_ws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunStore:
    """构造已放行工作区；仅外部 epubcheck 边界替身，不代表真实检查器验证。"""
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "root"))
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n第一句话。\n", encoding="utf-8"
    )
    (store.translation_dir / "align").mkdir(parents=True, exist_ok=True)
    (store.unit_align_path("ch01")).write_text(
        json.dumps(
            {"seq": 1, "src": "First sentence.", "tgt": "第一句话。", "note": None},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    orch.preprocess(store, config=Config())
    for name in ("capabilities.md", "global.md", "todo.md"):
        (store.preprocessing_dir / name).write_text("x", encoding="utf-8")
    review_dir = store.reviews_dir / "review-20261015T000000"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "result.json").write_text(
        json.dumps({"issue_count": 0, "g2_confirmed": 0, "termination": "clean_confirmed"}),
        encoding="utf-8",
    )
    orch.import_translations(store)
    for unit in store.load_publication().units:
        store.set_unit_status(unit.id, "reviewed")
    epub = orch.build(store)
    monkeypatch.setattr(
        orch, "run_epubcheck", lambda *a, **k: EpubcheckResult(True, True, 0, 0, returncode=0)
    )
    report = orch.qa(store, epub_path=str(epub))
    assert report["released"] is True, report.get("released_reason")
    assert report_state(store)["stale"] is False
    return store


def test_open_glossary_conflict_invalidates_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F2 复现：放行后新增 open 术语冲突 → 摘要必须变化（否则假有效放行）。"""
    store = _released_ws(tmp_path, monkeypatch)
    store.analysis_dir.mkdir(parents=True, exist_ok=True)
    (store.analysis_dir / "glossary_conflicts.jsonl").write_text(
        json.dumps(
            {
                "source": "Sample Standards Office",
                "existing": "示例标准署",
                "proposed": "示例规范署",
                "status": "open",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    state = report_state(store)
    assert state["stale"] is True, state


def test_glossary_edit_invalidates_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """放行后修改词表（可产生 blocking terminology）→ 报告过期。"""
    store = _released_ws(tmp_path, monkeypatch)
    store.analysis_dir.mkdir(parents=True, exist_ok=True)
    (store.analysis_dir / "glossary.csv").write_text(
        "source,target,type,status\nFirst sentence,第一句话,term,confirmed\n", encoding="utf-8"
    )
    assert report_state(store)["stale"] is True


def test_adding_terminology_exemptions_invalidates_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _released_ws(tmp_path, monkeypatch)
    (store.preprocessing_dir / "terminology_exemptions.csv").write_text(
        "unit,source,reason\nch01,First sentence,文献题名保留原文\n", encoding="utf-8"
    )
    assert report_state(store)["stale"] is True
    overview = orch.status_all(store.dir.parent)
    assert overview[0]["report_stale"] is True
    assert overview[0]["progress"] == "built_not_released"


@pytest.mark.parametrize("change", ["reason", "remove-entry", "remove-file"])
def test_changing_active_terminology_exemption_invalidates_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    store = _released_ws(tmp_path, monkeypatch)
    (store.analysis_dir / "glossary.csv").write_text(
        "source,target,type,status\nFirst sentence,首句,term,confirmed\n", encoding="utf-8"
    )
    path = store.preprocessing_dir / "terminology_exemptions.csv"
    path.write_text("unit,source,reason\nch01,First sentence,文献题名保留原文\n", encoding="utf-8")
    flags = orch.g0_check(store)["flags"]
    assert any(
        flag["check"] == "terminology_exempt" and flag["blocking"] is False for flag in flags
    )
    epub = store.output_dir / f"{store.load_publication().slug}.epub"
    report = orch.qa(store, epub_path=str(epub))
    assert report["released"] is True, report.get("released_reason")
    assert report_state(store)["stale"] is False
    assert orch.status_all(store.dir.parent)[0]["progress"] == "released"

    if change == "reason":
        path.write_text(
            "unit,source,reason\nch01,First sentence,复核后保留原文\n", encoding="utf-8"
        )
    elif change == "remove-entry":
        path.write_text("unit,source,reason\n", encoding="utf-8")
    else:
        path.unlink()
    assert report_state(store)["stale"] is True
    overview = orch.status_all(store.dir.parent)
    assert overview[0]["report_stale"] is True
    assert overview[0]["progress"] == "built_not_released"
    if change != "reason":
        failed_report = orch.qa(store, epub_path=str(epub))
        assert failed_report["released"] is False
        assert any(
            flag["check"] == "terminology" and flag["blocking"]
            for flag in failed_report["g0_flags"]
        )


def test_notes_registration_change_invalidates_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """放行后注释登记摘要变化（重登记）→ 报告过期。"""
    store = _released_ws(tmp_path, monkeypatch)
    src_notes = {
        "schema_version": "1",
        "source_sha256": store.load_publication().meta.source_sha256,
        "inventory": "present",
        "notes": [
            {
                "note_id": "n-000001",
                "scope_id": "ch01",
                "source_label": "1",
                "note_type": "footnote",
                "source_markdown": "源注文。",
                "source_locations": [{"kind": "page", "page": 1}],
                "status": "verified",
                "orphan_ok": True,
                "orphan_reason": "原书未引用（测试）",
            }
        ],
        "references": [],
    }
    (store.structured_dir / "notes.json").write_text(
        json.dumps(src_notes, ensure_ascii=False), encoding="utf-8"
    )
    orch.register_notes(store)
    assert report_state(store)["stale"] is True


def test_insert_change_and_missing_referenced_file_invalidate_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """放行后 inserts 单文件变化或其引用资源缺失 → 报告过期（E_INSERT_MISSING_FILE 输入）。"""
    store = _released_ws(tmp_path, monkeypatch)
    raw = store.structured_dir / "raw"
    (raw / "inserts").mkdir(parents=True, exist_ok=True)
    (raw / "media").mkdir(parents=True, exist_ok=True)
    (raw / "media" / "fig1.png").write_bytes(b"PNG")
    (raw / "inserts" / "fig-0001.json").write_text(
        json.dumps(
            {
                "id": "fig-0001",
                "type": "image",
                "source": {"page": 1, "bbox": [0, 0, 1, 1], "xref": None, "method": "embedded"},
                "file": "media/fig1.png",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert report_state(store)["stale"] is True  # 新增 inserts 本身即摘要输入
    # 先重建报告使其有效，再删除被引用资源 → 仍必须过期
    epub = orch.build(store)
    report = orch.qa(store, epub_path=str(epub))
    assert report["released"] is True, report.get("released_reason")
    assert report_state(store)["stale"] is False
    before_digest = artifacts_digest(store)
    (raw / "media" / "fig1.png").unlink()
    assert report_state(store)["stale"] is True
    assert artifacts_digest(store) != before_digest
    failed_report = orch.qa(store, epub_path=str(epub))
    assert failed_report["released"] is False
    assert any(
        finding["code"] == "E_INSERT_MISSING_FILE"
        for finding in failed_report["provenance_findings"]
    )


@pytest.mark.parametrize("outside_exists", [True, False], ids=["outside-file", "outside-missing"])
def test_insert_symlink_escape_invalidates_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outside_exists: bool
) -> None:
    """仅改资源 symlink 目标：摘要过期且 QA 报缺失，不探测越界文件存在性。"""
    store = _released_ws(tmp_path, monkeypatch)
    raw = store.structured_dir / "raw"
    media = raw / "media"
    media.mkdir(parents=True, exist_ok=True)
    inside = media / "fig.png"
    inside.write_bytes(b"PNG")
    link = media / "linked.png"
    link.symlink_to(inside)
    record = InsertRecord(
        id="p001-img01",
        type="image",
        source=InsertSource(page=1, method="embedded"),
        file="media/linked.png",
        content_desc="插图",
    )
    write_inserts(raw, [record])
    epub = orch.build(store)
    report = orch.qa(store, epub_path=str(epub))
    assert report["released"] is True, report.get("released_reason")
    before_state = report_state(store)
    assert before_state["stale"] is False
    before_digest = artifacts_digest(store)
    assert before_digest == report["artifacts_digest"]

    outside = tmp_path / "outside.png"
    if outside_exists:
        outside.write_bytes(b"PNG")
    # 外部文件准备不应改变摘要；唯一被测产物变化是 symlink 的目标。
    assert artifacts_digest(store) == before_digest
    link.unlink()
    link.symlink_to(outside)
    original_is_file = Path.is_file

    def guarded_is_file(path: Path) -> bool:
        """越界目标不可进入文件存在性检查。"""
        assert path != outside
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", guarded_is_file)
    assert artifacts_digest(store) != before_digest
    after_state = report_state(store)
    assert after_state != before_state
    assert after_state["stale"] is True
    assert after_state["reason"] == "artifacts_changed"
    failed_report = orch.qa(store, epub_path=str(epub))
    assert failed_report["released"] is False
    assert any(
        finding["code"] == "E_INSERT_MISSING_FILE"
        for finding in failed_report["provenance_findings"]
    )


def test_malformed_insert_json_uses_production_tolerance_in_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """坏 inserts 保留字节失效证据，并按生产 schema 跳过，不令 status 崩溃。"""
    store = _released_ws(tmp_path, monkeypatch)
    raw = store.structured_dir / "raw"
    inserts = raw / "inserts"
    inserts.mkdir(parents=True, exist_ok=True)
    path = inserts / "bad.json"
    before_digest = artifacts_digest(store)
    for invalid in ("{broken", "null", "[]", '["not a record"]', '"text"', "7", '{"file": []}'):
        path.write_text(invalid, encoding="utf-8")
        assert read_inserts(raw) == []
        assert artifacts_digest(store) != before_digest
        assert report_state(store)["stale"] is True
        status = orch.status(store)
        assert any(item["reason"] == "report_stale" for item in status["stale"])
