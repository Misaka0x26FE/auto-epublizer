"""translation：句级对齐 + align/ 对照表（翻译本身是 agent 任务，CLI 不调 LLM）。"""

from __future__ import annotations

from .align import align_rows, read_align, split_sentences, write_align

__all__ = [
    "align_rows",
    "read_align",
    "split_sentences",
    "write_align",
]
