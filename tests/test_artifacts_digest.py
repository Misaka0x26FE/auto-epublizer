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
from auto_epublizer import orchestrator as orch
from auto_epublizer.qa.artifacts import report_state
from auto_epublizer.qa.epubcheck import EpubcheckResult


def _released_ws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    monkeypatch.setattr(orch, "run_epubcheck", lambda *a, **k: EpubcheckResult(True, True, 0, 0))
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
    (store.analysis_dir / "glossary.csv").write_text(
        "source,target,type,status\nSS,党卫队,term,confirmed\n", encoding="utf-8"
    )
    (store.analysis_dir / "glossary_conflicts.jsonl").write_text(
        json.dumps(
            {
                "source": "WVHA",
                "existing": "党卫队经济管理总局",
                "proposed": "党卫队经济行政总中心",
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
    (raw / "media" / "fig1.png").unlink()
    assert report_state(store)["stale"] is True
