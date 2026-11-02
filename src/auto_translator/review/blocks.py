# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""Markdown 内容块 ↔ align 句区间的身份契约（B1 纯函数）。

对齐表仍是**逐句**的 ``{seq,src,tgt,note}``；段落身份不写进 align，而由本条规则
从 md 与 align 的当前内容**确定性推导**：

- 块 = ``fidelity.content_blocks`` 的正文块（跳过标题/纯注释，围栏代码独立成块），
  块号从 1 起，与溯源覆盖率、源保真使用同一套切块；
- 一个块对应 align 的一**段连续** ``seq`` 区间；块内多句是常态，拆句/并句只改变句数；
- 归一化只去空白（与 ``norm_text`` 相同），换行/缩进变化不改变块身份；
- 无法用连续句精确还原某块（缺句、顺序不符、跨块借句）时返回 issue，**不猜测**边界。

``structure_digest`` 把块号、类型、seq 区间和块文本摘要哈希成一个基线。块增删、
合并/拆分、乱序或换块都会改变基线；只改块内换行不会。基线由 import 登记（B2 接线），
历史工作区没有基线时状态是 unknown，而不是「曾经有几段」的推测。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

from .fidelity import content_blocks, norm_text


def _block_kind(block: str) -> str:
    return "code" if block.lstrip().startswith("```") else "text"


def _block_text(block: str) -> str:
    """代码块的围栏是 Markdown 语法，不是字面内容；align 行只有代码正文。"""
    if _block_kind(block) != "code":
        return block
    lines = block.strip().splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)


def block_spans(
    md_text: str, rows: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """推导每个 md 正文块的连续 seq 区间；返回 ``(spans, issues)``。

    ``rows`` 必须是用于同一次比对的 align 行（标题容错行由调用方先剔除）。
    空 ``tgt`` 行（拆句/缺句，``note`` 已声明）不产生 md 文本，也不单独成块；
    它们不参与边界，仍保留在 align 中供句级审校。
    """
    blocks = content_blocks(md_text)
    ordered = sorted(rows, key=lambda r: int(r.get("seq") or 0))
    spans: list[dict[str, Any]] = []
    issues: list[str] = []
    cursor = 0
    for index, block in enumerate(blocks, start=1):
        target = norm_text(_block_text(block))
        if not target:
            continue
        acc = ""
        start_seq: int | None = None
        end_seq: int | None = None
        start_cursor = cursor
        while cursor < len(ordered) and len(acc) < len(target):
            seq = int(ordered[cursor].get("seq") or 0)
            part = norm_text(str(ordered[cursor].get("tgt") or ""))
            if part:
                if start_seq is None:
                    start_seq = seq
                acc += part
                end_seq = seq
            cursor += 1
        if acc != target or start_seq is None or end_seq is None:
            issues.append(
                f"第 {index} 块无法由连续句还原（块 {len(target)} 字符 / 已归 {len(acc)}）"
            )
            cursor = start_cursor
            return spans, issues
        spans.append(
            {
                "block": index,
                "kind": _block_kind(block),
                "seq_start": start_seq,
                "seq_end": end_seq,
                "text_sha256": sha256(target.encode("utf-8")).hexdigest(),
            }
        )
    leftover = [
        int(row.get("seq") or 0) for row in ordered[cursor:] if norm_text(str(row.get("tgt") or ""))
    ]
    if leftover:
        issues.append(f"align 有未归属句：seq={','.join(str(s) for s in leftover[:8])}")
    return spans, issues


def structure_digest(spans: Sequence[Mapping[str, Any]]) -> str:
    """块边界基线：块号/类型/seq 区间/块文本摘要的确定性哈希。"""
    payload = [
        {key: span[key] for key in ("block", "kind", "seq_start", "seq_end", "text_sha256")}
        for span in spans
    ]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()
