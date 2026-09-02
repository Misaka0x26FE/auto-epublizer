"""审校数据模型：Issue（G1 产出/G2 定谳）、Patch（G3 影子修订）、收敛判定。"""

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
