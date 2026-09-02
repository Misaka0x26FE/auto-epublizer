"""review 收敛状态机 + G1-G3 服务测试（FakeClient）。"""

from __future__ import annotations

from pathlib import Path

from auto_common.llm.providers.fake import FakeClient
from auto_common.workspace import init_workspace
from auto_translator.review.convergence import ConvergenceState, advance
from auto_translator.review.service import review
from auto_translator.translation import translate


def test_convergence_clean_confirmed() -> None:
    state = ConvergenceState()
    assert advance(state, has_issues=False, shadow_summary=None, unresolved=False).done is False
    result = advance(state, has_issues=False, shadow_summary=None, unresolved=False)
    assert result.done is True
    assert result.termination == "clean_confirmed"


def test_convergence_no_progress_oscillation() -> None:
    state = ConvergenceState()
    advance(state, has_issues=True, shadow_summary="A", unresolved=False)
    advance(state, has_issues=True, shadow_summary="B", unresolved=False)
    result = advance(state, has_issues=True, shadow_summary="A", unresolved=False)
    assert result.termination == "no_progress"


def test_convergence_max_rounds() -> None:
    state = ConvergenceState()
    result = None
    for _ in range(10):
        result = advance(
            state,
            has_issues=True,
            shadow_summary=f"S{state.rounds}",
            unresolved=False,
            clean_confirmations=2,
            fix_max_rounds=1,
        )
        if result.done:
            break
    assert result is not None and result.termination == "max_rounds"


def _workspace_with_alignment(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence. Second sentence.\n", encoding="utf-8")
    store = init_workspace(src, workspace_dir=tmp_path / "ws")

    from auto_epublizer.ingest import load_document
    from auto_epublizer.structure import rebuild_structure, write_structured

    doc = load_document(store.dir / store.load_publication().meta.source, store=store)
    entries = rebuild_structure(doc, store.load_publication())
    write_structured(store, doc, entries)
    store.set_units(entries)

    client = FakeClient()
    client.enqueue_json({"translations": [["第一章"], ["第一句。第二句。"]]})
    translate(store, client)
    return store


def test_review_clean_terminates(tmp_path: Path) -> None:
    store = _workspace_with_alignment(tmp_path)
    client = FakeClient()
    # 两轮 clean（无 issue）
    client.enqueue_json({"issues": [], "reviewed_segments": 2, "complete": True})
    client.enqueue_json({"issues": [], "reviewed_segments": 2, "complete": True})
    result = review(store, client)
    assert result["termination"] == "clean_confirmed"
    assert result["rounds"] == 2
    review_dirs = [p for p in store.reviews_dir.iterdir() if p.is_dir()]
    assert len(review_dirs) == 1
    assert (review_dirs[0] / "result.json").is_file()


def test_review_issue_fixed_then_clean(tmp_path: Path) -> None:
    store = _workspace_with_alignment(tmp_path)
    client = FakeClient()
    # R1：报 1 个术语问题
    client.enqueue_json(
        {
            "issues": [
                {"seq": 1, "type": "terminology", "detail": "术语不一致", "suggestion": "改为X"}
            ],
            "reviewed_segments": 2,
            "complete": True,
        }
    )
    # G2 取证：confirmed
    client.enqueue_json({"verdict": "confirmed", "evidence_refs": [], "reason": ""})
    # G3 fixer
    client.enqueue_json({"after": "修订后的第一句。", "complete": True})
    # R2 盲审：clean
    client.enqueue_json({"issues": [], "reviewed_segments": 2, "complete": True})
    # R3 盲审：clean → clean_confirmed
    client.enqueue_json({"issues": [], "reviewed_segments": 2, "complete": True})

    result = review(store, client)
    assert result["termination"] == "clean_confirmed"
    assert result["rounds"] == 3
    assert result["issue_count"] == 1
