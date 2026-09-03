"""预处理（确定性事实层）：嗅探 + 元数据 + TOC + 体检 + 规模 → preprocessing/facts.*。

预处理是 agent 任务：本包只产出零 token 事实（facts.json/facts.md，含 agent 待办），
方案决策与分层理解（plan/global/units/terms/risks/report）由 agent 用自身能力撰写。
"""

from __future__ import annotations

from .facts import collect_facts, render_facts_md, write_facts
from .sniff import SniffError, sniff

__all__ = ["SniffError", "collect_facts", "render_facts_md", "sniff", "write_facts"]
