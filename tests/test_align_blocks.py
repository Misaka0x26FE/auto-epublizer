# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""B1 真值表：Markdown 块身份 ↔ align 连续句区间。

契约见 ``auto_translator/review/blocks.py``。这些用例固定「哪些变化不是结构变化」，
以及合并/拆分/乱序/缺句必须给出 issue 或不同基线，不能靠「全文归一化相等」蒙混。
"""

from __future__ import annotations

from auto_translator.review.blocks import block_spans, structure_digest


def _rows(*targets: str) -> list[dict]:
    return [
        {"seq": i, "src": f"src-{i}", "tgt": tgt, "note": None}
        for i, tgt in enumerate(targets, start=1)
    ]


def test_multi_sentence_paragraph_is_one_block() -> None:
    md = "甲乙。丙丁。\n\n戊。"
    spans, issues = block_spans(md, _rows("甲乙。", "丙丁。", "戊。"))
    assert issues == []
    assert [(s["block"], s["seq_start"], s["seq_end"]) for s in spans] == [(1, 1, 2), (2, 3, 3)]


def test_line_wrapping_does_not_change_structure() -> None:
    one_line = "甲乙。丙丁。\n\n戊。"
    wrapped = "甲乙。\n丙丁。\n\n戊。"
    rows = _rows("甲乙。", "丙丁。", "戊。")
    assert structure_digest(block_spans(one_line, rows)[0]) == structure_digest(
        block_spans(wrapped, rows)[0]
    )


def test_split_sentence_stays_in_one_block() -> None:
    """一句译文拆成两行 align（note=split）仍属同一块，seq 区间覆盖两行。"""
    rows = _rows("甲乙", "丙。")
    rows[1]["note"] = "split"
    spans, issues = block_spans("甲乙丙。", rows)
    assert issues == []
    assert (spans[0]["seq_start"], spans[0]["seq_end"]) == (1, 2)


def test_duplicate_text_blocks_keep_distinct_boundaries() -> None:
    spans, issues = block_spans("同一句。\n\n同一句。", _rows("同一句。", "同一句。"))
    assert issues == []
    assert [(s["block"], s["seq_start"], s["seq_end"]) for s in spans] == [(1, 1, 1), (2, 2, 2)]


def test_merged_blocks_change_the_baseline() -> None:
    rows = _rows("甲乙。", "丙丁。")
    split_md = "甲乙。\n\n丙丁。"
    merged_md = "甲乙。丙丁。"
    assert structure_digest(block_spans(split_md, rows)[0]) != structure_digest(
        block_spans(merged_md, rows)[0]
    )


def test_reordered_blocks_cannot_be_mapped_by_guessing() -> None:
    spans, issues = block_spans("丙丁。\n\n甲乙。", _rows("甲乙。", "丙丁。"))
    assert spans == []
    assert issues and "第 1 块" in issues[0]


def test_missing_align_sentence_is_an_issue() -> None:
    spans, issues = block_spans("甲乙。\n\n丙丁。", _rows("甲乙。"))
    assert [s["block"] for s in spans] == [1]
    assert issues and "未归属" not in issues[0]


def test_unowned_align_sentence_is_an_issue() -> None:
    spans, issues = block_spans("甲乙。", _rows("甲乙。", "多余的句子。"))
    assert [s["block"] for s in spans] == [1]
    assert issues and "未归属" in issues[0]


def test_fenced_code_block_is_its_own_kind() -> None:
    md = "```\nx = 1\n```\n\n正文。"
    spans, issues = block_spans(md, _rows("x = 1", "正文。"))
    assert issues == []
    assert [s["kind"] for s in spans] == ["code", "text"]


def test_structure_status_uses_registered_baseline() -> None:
    from auto_translator.review.g0 import align_structure_status

    rows = _rows("甲乙。", "丙丁。")
    split_md = "甲乙。\n\n丙丁。"
    baseline = structure_digest(block_spans(split_md, rows)[0])
    assert align_structure_status(split_md, rows, baseline)[0] == "ok"
    assert align_structure_status("甲乙。丙丁。", rows, baseline)[0] == "changed"
    assert align_structure_status(split_md, rows, None)[0] == "unknown"
    assert align_structure_status("丙丁。\n\n甲乙。", rows, baseline)[0] == "unknown"
