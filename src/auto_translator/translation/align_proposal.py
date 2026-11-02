# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""对照表重建提案（B3，只读、确定性）。

输入是已核验的 ``structured/`` 源文、agent 正在修订的 ``translation/`` 译文，以及
现有 ``align`` 行。它**不写任何正式文件**，也不把「文本相似」当成对应正确：
``src`` 只从源文块/已核验的 align 行摘取。

对应关系用版式/顺序证据建立，而不是跨语言字面相等：

1. 用 :func:`auto_translator.review.blocks.block_spans` 分别把 translation md 的块映射到
   align 的 ``tgt`` 句区间、把 structured md 的块映射到 ``src`` 句区间；
2. 译文块与源文块的 seq 区间重叠 → 一对一是 ``exact``，一对多是 ``merge``，
   多对一是 ``split``；
3. 没有任何 align 行覆盖的译文块 → ``propose``：只按剩余源文顺序给出**未核验**候选，
   不出行、不消耗源文；
4. 源文侧仍未被覆盖的块进 ``uncovered``。

低置信映射明确标为待核证，重复句/OCR 缺行/大幅改写不会被自动认可；``rows`` 只复制
现有已核 verify 行，拆句源归属留给 agent。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..review.blocks import block_spans
from ..review.fidelity import content_blocks


def _side_spans(
    md_text: str, rows: Sequence[Mapping[str, Any]], side: str
) -> tuple[dict[int, dict[str, Any]], list[str]]:
    adapted = [
        {
            "seq": row.get("seq"),
            "tgt": row.get("src") if side == "src" else row.get("tgt"),
        }
        for row in rows
    ]
    spans, issues = block_spans(md_text, adapted)
    return {int(span["block"]): span for span in spans}, issues


def _overlap(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    return int(a["seq_start"]) <= int(b["seq_end"]) and int(b["seq_start"]) <= int(a["seq_end"])


def propose_alignment(
    structured_md: str,
    translation_md: str,
    rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """按块/句区间对应提出重建方案；不写文件、不修改输入。"""
    rows = [dict(row) for row in rows]
    tgt_spans, tgt_issues = _side_spans(translation_md, rows, "tgt")
    src_spans, src_issues = _side_spans(structured_md, rows, "src")
    src_blocks = content_blocks(structured_md)
    tgt_blocks = content_blocks(translation_md)
    issues = [f"译文块身份：{issue}" for issue in tgt_issues]
    issues += [f"源文块身份：{issue}" for issue in src_issues]

    mappings: list[dict[str, Any]] = []
    used_src: set[int] = set()
    for tgt_index, tgt_text in enumerate(tgt_blocks, start=1):
        span = tgt_spans.get(tgt_index)
        if span is None:
            mappings.append(
                {
                    "target_block": tgt_index,
                    "status": "propose",
                    "source_blocks": [],
                    "seq_range": None,
                    "confidence": 0.0,
                    "rows": [],
                    "candidates": [],
                    "evidence": {"target_head": tgt_text[:60]},
                }
            )
            issues.append(f"第 {tgt_index} 个译文块没有 align 行覆盖，待核证")
            continue
        overlapping = [
            (index, other) for index, other in src_spans.items() if _overlap(span, other)
        ]
        if not overlapping:
            mappings.append(
                {
                    "target_block": tgt_index,
                    "status": "unmatched",
                    "source_blocks": [],
                    "seq_range": [span["seq_start"], span["seq_end"]],
                    "confidence": 0.0,
                    "rows": [],
                    "candidates": [],
                    "evidence": {"target_head": tgt_text[:60]},
                }
            )
            issues.append(f"第 {tgt_index} 个译文块的 seq 区间没有源文块与之重叠")
            continue
        source_blocks = sorted(index for index, _ in overlapping)
        used_src.update(source_blocks)
        status = "merge" if len(source_blocks) > 1 else "exact"
        seq_start, seq_end = int(span["seq_start"]), int(span["seq_end"])
        copied = [row for row in rows if seq_start <= int(row.get("seq") or 0) <= seq_end]
        mappings.append(
            {
                "target_block": tgt_index,
                "status": status,
                "source_blocks": source_blocks,
                "seq_range": [seq_start, seq_end],
                "confidence": 1.0,
                "rows": copied,
                "evidence": {
                    "source_head": src_blocks[source_blocks[0] - 1][:60],
                    "target_head": tgt_text[:60],
                },
            }
        )

    # 拆句：一个源文块被多个译文块共享时，两边的 status 都标 split
    for tgt_span in tgt_spans.values():
        shared = [
            index
            for index, src_span in src_spans.items()
            if _overlap(tgt_span, src_span)
            and sum(1 for other in tgt_spans.values() if _overlap(other, src_span)) > 1
        ]
        if shared:
            for mapping in mappings:
                if mapping["target_block"] == tgt_span["block"]:
                    mapping["status"] = "split"

    uncovered = [
        {
            "source_block": index,
            "seq_range": [span["seq_start"], span["seq_end"]],
            "source_head": src_blocks[index - 1][:60],
        }
        for index, span in sorted(src_spans.items())
        if index not in used_src
    ]
    for index, block in enumerate(src_blocks, start=1):
        if index not in src_spans:
            uncovered.append({"source_block": index, "seq_range": None, "source_head": block[:60]})
    uncovered.sort(key=lambda item: item["source_block"])

    return {
        "writes": False,
        "source_blocks": len(src_blocks),
        "target_blocks": len(tgt_blocks),
        "mappings": mappings,
        "uncovered": uncovered,
        "issues": issues,
    }
