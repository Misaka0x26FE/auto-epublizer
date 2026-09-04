"""review 收敛状态机测试（纯函数、确定性）。

G1–G3 的语义审校由操作 CLI 的 agent 完成（写 reviews/review-<ts>/result.json）；
CLI 只保留收敛状态机作为 agent 判定收敛的参照契约。
"""

from __future__ import annotations

from auto_translator.review.convergence import (
    TERMINATION_CLEAN,
    TERMINATION_MAX_ROUNDS,
    TERMINATION_NO_PROGRESS,
    ConvergenceState,
    advance,
)


def test_convergence_clean_confirmed() -> None:
    state = ConvergenceState()
    assert advance(state, has_issues=False, shadow_summary=None, unresolved=False).done is False
    result = advance(state, has_issues=False, shadow_summary=None, unresolved=False)
    assert result.done is True
    assert result.termination == TERMINATION_CLEAN == "clean_confirmed"


def test_convergence_no_progress_oscillation() -> None:
    state = ConvergenceState()
    advance(state, has_issues=True, shadow_summary="A", unresolved=False)
    advance(state, has_issues=True, shadow_summary="B", unresolved=False)
    result = advance(state, has_issues=True, shadow_summary="A", unresolved=False)
    assert result.termination == TERMINATION_NO_PROGRESS == "no_progress"


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
    assert result is not None and result.termination == TERMINATION_MAX_ROUNDS == "max_rounds"
