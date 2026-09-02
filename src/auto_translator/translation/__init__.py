"""translation：切片翻译 + 句级对齐 + align/ 对照表。"""

from __future__ import annotations

from .align import align_rows, read_align, split_sentences, write_align
from .service import translate, translate_unit
from .slice import chunk_paragraphs, split_paragraph

__all__ = [
    "align_rows",
    "chunk_paragraphs",
    "read_align",
    "split_paragraph",
    "split_sentences",
    "translate",
    "translate_unit",
    "write_align",
]
