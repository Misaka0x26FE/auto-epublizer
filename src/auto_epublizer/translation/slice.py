"""翻译切片：段落 → 字符预算拆分 → 批次打包（纯函数）。

- 单段超过 ``max_chars_per_segment`` 则按句末标点再拆，续段标 ``cont`` 回并；
- 批次是一次 LLM 调用的边界，按 ``max_chars_per_batch`` 贪心打包；
- 批次边界即断点续跑检查点。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SENT_END = re.compile(r"[。！？!?；;…]|(?<=[.!?])\s+|\n")


@dataclass(frozen=True)
class Slice:
    text: str
    cont: bool = False  # 续段：回并到上一段，不另起段落


def split_paragraph(text: str, max_chars: int) -> list[Slice]:
    """把超长段落按句末标点拆成 ≤ max_chars 的片，首片为主、其余标 cont。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [Slice(text=text, cont=False)]

    pieces: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if len(buf) >= max_chars and _SENT_END.match(ch):
            pieces.append(buf)
            buf = ""
    if buf.strip():
        pieces.append(buf)

    # 合并过短尾片，避免最后一片过碎
    if len(pieces) >= 2 and len(pieces[-1]) < max_chars * 0.25:
        pieces[-2] += pieces.pop()

    return [Slice(text=p.strip(), cont=(i > 0)) for i, p in enumerate(pieces) if p.strip()]


def batch_slices(slices: list[Slice], max_batch: int) -> list[list[Slice]]:
    """按字符预算贪心打包成批次，返回批次数组。"""
    batches: list[list[Slice]] = []
    current: list[Slice] = []
    current_len = 0
    for s in slices:
        if current and current_len + len(s.text) > max_batch:
            batches.append(current)
            current = []
            current_len = 0
        current.append(s)
        current_len += len(s.text)
    if current:
        batches.append(current)
    return batches


def chunk_paragraphs(
    paragraphs: list[str],
    *,
    max_chars_per_segment: int = 1200,
    max_chars_per_batch: int = 1800,
) -> list[list[Slice]]:
    """把段落数组切成批次（每批内元素为 Slice，含 cont 标记）。"""
    slices: list[Slice] = []
    for para in paragraphs:
        slices.extend(split_paragraph(para, max_chars_per_segment))
    return batch_slices(slices, max_chars_per_batch)
