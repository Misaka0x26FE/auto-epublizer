"""G3 收敛状态机（纯逻辑，可测）。

终态判定（对齐 docs/quality-control.md §5）：
- 连续 ``clean_confirmations`` 轮无 issue → ``clean_confirmed``；
- 超过轮数上限 → ``max_rounds``；
- 影子译文整体摘要（SHA-256）出现 A↔B 循环 → ``no_progress``；
- Fixer 失败积压且复审不再报 → ``unresolved_fixes``。

轮数上限 = ``(fix_max_rounds + 1) × clean_confirmations``（默认 3 × 2 = 6）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .models import (
    TERMINATION_CLEAN,
    TERMINATION_MAX_ROUNDS,
    TERMINATION_NO_PROGRESS,
    TERMINATION_UNRESOLVED,
)


def summarize(rows: list[dict]) -> str:
    """对影子译文整体做摘要（用于振荡检测）。"""
    payload = "\n".join(str(r.get("tgt", "")) for r in sorted(rows, key=lambda r: r.get("seq", 0)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class ConvergenceState:
    clean_streak: int = 0
    rounds: int = 0
    seen_summaries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConvergenceResult:
    termination: str  # clean_confirmed | max_rounds | no_progress | unresolved_fixes | ""
    rounds: int
    clean_streak: int
    done: bool


def max_rounds_limit(fix_max_rounds: int, clean_confirmations: int) -> int:
    return (fix_max_rounds + 1) * clean_confirmations


def advance(
    state: ConvergenceState,
    *,
    has_issues: bool,
    shadow_summary: str | None,
    unresolved: bool,
    clean_confirmations: int = 2,
    fix_max_rounds: int = 2,
) -> ConvergenceResult:
    """推进一轮，返回收敛判定。"""
    state.rounds += 1
    limit = max_rounds_limit(fix_max_rounds, clean_confirmations)

    if has_issues:
        state.clean_streak = 0
        state.seen_summaries.append(shadow_summary or "")
    else:
        state.clean_streak += 1

    # 振荡检测：摘要出现 A↔B 循环（最近两轮交替）
    if len(state.seen_summaries) >= 3 and state.seen_summaries[-1] == state.seen_summaries[-3]:
        return ConvergenceResult(TERMINATION_NO_PROGRESS, state.rounds, state.clean_streak, True)

    if state.clean_streak >= clean_confirmations:
        return ConvergenceResult(TERMINATION_CLEAN, state.rounds, state.clean_streak, True)

    if unresolved and not has_issues:
        return ConvergenceResult(TERMINATION_UNRESOLVED, state.rounds, state.clean_streak, True)

    if state.rounds >= limit:
        return ConvergenceResult(TERMINATION_MAX_ROUNDS, state.rounds, state.clean_streak, True)

    return ConvergenceResult("", state.rounds, state.clean_streak, False)
