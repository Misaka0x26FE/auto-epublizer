# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""审校数据模型：G0Flag（确定性告警）、Issue（G1 产出/G2 定谳）、
Patch（G3 影子修订）、收敛判定。

G0Flag 归本模块而非 g0.py（C 组最小重构）：fidelity.py 与 g0.py 都要用它，
放在共享模型层可消除二者之间的双向依赖（原 g0 定义 → fidelity 模块级导入、
g0 函数内再延迟导入 fidelity）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# G1 问题类型
ISSUE_TYPES = ("missing", "added", "mistranslation", "terminology", "pronoun")

# G2 裁决
VERDICT_CONFIRMED = "confirmed"
VERDICT_DISMISSED = "dismissed"

# G3 收敛终态
TERMINATION_CLEAN = "clean_confirmed"
TERMINATION_MAX_ROUNDS = "max_rounds"
TERMINATION_NO_PROGRESS = "no_progress"
TERMINATION_UNRESOLVED = "unresolved_fixes"


@dataclass(frozen=True)
class G0Flag:
    """一条确定性告警。

    ``blocking``：是否属于**放行硬门**（默认 True）。advisory 类告警显式置 False
    （如 fidelity 前向缺块、footnote_suspect、length）——import / qa 汇总 / CLI 渲染
    统一读该字段，避免「同一告警在 import 是 advisory、在放行汇总是硬门」的口径分叉
    （B 组真值表核对发现：forward fidelity 曾被 g0_structure_open 计为硬门）。
    """

    check: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    blocking: bool = True


@dataclass
class Issue:
    issue_id: str
    chapter: str
    index: int
    seq: list[int] = field(default_factory=list)
    type: str = "mistranslation"
    detail: str = ""
    suggestion: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    consistency: str | None = None
    verdict: str | None = None  # confirmed | dismissed（G2 定谳）
    status: str = "open"

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "chapter": self.chapter,
            "index": self.index,
            "seq": self.seq,
            "type": self.type,
            "detail": self.detail,
            "suggestion": self.suggestion,
            "evidence_refs": self.evidence_refs,
            "consistency": self.consistency,
            "verdict": self.verdict,
            "status": self.status,
        }


@dataclass
class Patch:
    patch_id: str
    chapter: str
    index: int
    before_hash: str
    after: str
    issue_ids: list[str] = field(default_factory=list)
    review_round: int = 1
    status: str = "provisional"

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "chapter": self.chapter,
            "index": self.index,
            "before_hash": self.before_hash,
            "after": self.after,
            "issue_ids": self.issue_ids,
            "review_round": self.review_round,
            "status": self.status,
        }
