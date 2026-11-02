# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""B3 真值表：只读对照表重建提案（不改文件、不把相似度当正确性）。"""

from __future__ import annotations

from auto_translator.translation.align_proposal import propose_alignment


def _rows(*pairs: tuple[str, str]) -> list[dict]:
    return [
        {"seq": index, "src": src, "tgt": tgt, "note": None}
        for index, (src, tgt) in enumerate(pairs, start=1)
    ]


def test_exact_blocks_produce_sentence_rows() -> None:
    result = propose_alignment(
        "# 第一章\n\n甲乙。丙丁。\n\n戊。",
        "# 第一章\n\n甲译。丙译。\n\n戊译。",
        _rows(("甲乙。", "甲译。"), ("丙丁。", "丙译。"), ("戊。", "戊译。")),
    )
    assert result["writes"] is False
    assert [m["status"] for m in result["mappings"]] == ["exact", "exact"]
    assert [len(m["rows"]) for m in result["mappings"]] == [2, 1]
    assert result["uncovered"] == []
    assert result["mappings"][0]["rows"][0]["src"] == "甲乙。"


def test_merged_source_blocks_are_one_mapping() -> None:
    result = propose_alignment(
        "# 一\n\n甲乙。\n\n丙丁。",
        "# 一\n\n甲译。丙丁译。",
        _rows(("甲乙。", "甲译。"), ("丙丁。", "丙丁译。")),
    )
    (mapping,) = result["mappings"]
    assert mapping["status"] == "merge"
    assert mapping["source_blocks"] == [1, 2]
    assert result["uncovered"] == []


def test_split_target_blocks_keep_one_source_block() -> None:
    result = propose_alignment(
        "# 一\n\n甲乙。丙丁。",
        "# 一\n\n甲译。\n\n丙丁译。",
        _rows(("甲乙。", "甲译。"), ("丙丁。", "丙丁译。")),
    )
    assert [m["status"] for m in result["mappings"]] == ["split", "split"]
    assert [m["source_blocks"] for m in result["mappings"]] == [[1], [1]]
    assert result["uncovered"] == []


def test_block_without_rows_is_only_proposed() -> None:
    result = propose_alignment(
        "# 一\n\n甲乙。\n\n丙丁。",
        "# 一\n\n甲译。\n\n新写的译文。",
        _rows(("甲乙。", "甲译。")),
    )
    statuses = [m["status"] for m in result["mappings"]]
    assert statuses == ["exact", "propose"]
    assert result["mappings"][1]["rows"] == []
    assert result["mappings"][1]["source_blocks"] == []
    assert any("待核证" in issue for issue in result["issues"])


def test_uncovered_source_tail_is_reported() -> None:
    result = propose_alignment(
        "# 一\n\n甲乙。\n\n丙丁。",
        "# 一\n\n甲译。",
        _rows(("甲乙。", "甲译。")),
    )
    assert [item["source_block"] for item in result["uncovered"]] == [2]
