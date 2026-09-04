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


def test_review_protocol_violation_retries_batch(tmp_path: Path) -> None:
    """G1 协议违例（缺 complete:true）须整批重试而非中断整个审校。"""
    store = _workspace_with_alignment(tmp_path)
    client = FakeClient()
    # R1 第一次：违例输出；第二次：合法 clean
    client.enqueue_json({"issues": [], "reviewed_segments": 2})
    client.enqueue_json({"issues": [], "reviewed_segments": 2, "complete": True})
    # R2：clean → clean_confirmed
    client.enqueue_json({"issues": [], "reviewed_segments": 2, "complete": True})

    result = review(store, client)
    assert result["termination"] == "clean_confirmed"


def test_review_protocol_violation_exhausted_raises(tmp_path: Path) -> None:
    """连续协议违例耗尽重试次数后，须报明确中文错误。"""
    import pytest

    store = _workspace_with_alignment(tmp_path)
    client = FakeClient()
    client.enqueue_json({"issues": []})
    client.enqueue_json({"issues": []})
    client.enqueue_json({"issues": []})

    with pytest.raises(RuntimeError, match="审校"):
        review(store, client)


class _CountingConcurrentClient(FakeClient):
    """并发计数 + 回显 client：审校返回 clean，翻译回显；记录最大并发（C7）。

    G1 批次并行时 complete_json 的并发调用数应 >1（真并发而非串行包装）。
    """

    def __init__(self, delay: float = 0.05) -> None:
        super().__init__()
        self._delay = delay
        self._active = 0
        self._max_active = 0

    def complete_json(
        self,
        messages,
        *,
        tier="strong",
        max_tokens=None,
        stage=None,
    ):
        import re
        import time

        with self._lock:
            self._active += 1
            self._max_active = max(self._max_active, self._active)
        try:
            time.sleep(self._delay)
            if stage == "review":
                return {"issues": [], "reviewed_segments": 1, "complete": True}
            user = next(m["content"] for m in messages if m["role"] == "user")
            paras = re.findall(r"^\[(\d+)\] (.+)$", user, re.MULTILINE)
            paras = [p for _, p in sorted(paras, key=lambda x: int(x[0]))]
            return {"translations": [[f"译:{p}"] for p in paras]}
        finally:
            with self._lock:
                self._active -= 1


def test_review_g1_batch_concurrency(tmp_path: Path) -> None:
    """多单元多批审校：G1 真并发（max_active>1），两轮 clean 收敛（C7 稳定序合并）。"""
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter One\n\n"
        "First content sentence. Second content sentence.\n\n"
        "# Chapter Two\n\n"
        "Third content sentence. Fourth content sentence.\n\n"
        "# Chapter Three\n\n"
        "Fifth content sentence. Sixth content sentence.\n",
        encoding="utf-8",
    )
    store = init_workspace(src, workspace_dir=tmp_path / "ws")
    from auto_epublizer.ingest import load_document
    from auto_epublizer.structure import rebuild_structure, write_structured

    doc = load_document(store.dir / store.load_publication().meta.source, store=store)
    entries = rebuild_structure(doc, store.load_publication())
    write_structured(store, doc, entries)
    store.set_units(entries)
    assert len(store.load_publication().units) == 3, "fixture 应有 3 个单元"

    client = _CountingConcurrentClient(delay=0.05)
    translate(store, client)
    client._max_active = 0  # 重置：只统计审校阶段并发
    result = review(store, client)
    assert result["termination"] == "clean_confirmed"
    assert client._max_active >= 2, "G1 批次未真并发（max_active=1）"
    assert all(u.status == "reviewed" for u in store.load_publication().units), (
        "三个单元都应通过审校"
    )
