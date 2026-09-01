"""术语表数据模型与三态生命周期。

权威存储是 ``analysis/glossary.csv``（人类/agent 可读），冲突外置到
``analysis/glossary_conflicts.jsonl``。三态：``seed → candidate → conflict → confirmed``。

- seed：analyze 播种 + references/user 导入的初始译法；
- candidate：翻译 worker 追加的提案；
- conflict：同一 source 出现多个不同 target，待裁决；
- confirmed：已确认译法，翻译与审校必须遵守。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

STATUS_SEED = "seed"
STATUS_CANDIDATE = "candidate"
STATUS_CONFLICT = "conflict"
STATUS_CONFIRMED = "confirmed"

TERM_STATUSES = (STATUS_SEED, STATUS_CANDIDATE, STATUS_CONFLICT, STATUS_CONFIRMED)

# 术语类别白名单（对应出版物规范 1.5 的类别）
TERM_TYPES = (
    "person",  # 人物
    "place",  # 地名
    "org",  # 政党/组织
    "term",  # 术语
    "event",  # 事件
    "period",  # 历史时期
    "work",  # 作品
    "fixed_expr",  # 固定表达/口头禅
)

# 人物性别
GENDERS = ("", "male", "female", "other")


class GlossaryEntry(BaseModel):
    """一条术语记录。"""

    source: str
    target: str = ""
    type: str = "term"
    aliases: list[str] = Field(default_factory=list)
    gender: str = ""
    reading: str = ""
    status: str = STATUS_SEED
    note: str = ""


class GlossaryConflict(BaseModel):
    """同一 source 出现多个不同 target 的冲突记录。"""

    source: str
    targets: list[str] = Field(default_factory=list)
    existing_target: str = ""
    proposed_target: str = ""
    type: str = "term"
    status: str = "open"

    def as_jsonl(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
