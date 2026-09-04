"""translation 测试：句级对齐与 align/ 对照表（确定性；翻译是 agent 任务）。"""

from __future__ import annotations

from auto_translator.translation import align_rows, split_sentences


def test_split_sentences() -> None:
    assert split_sentences("第一句。第二句！第三句？") == ["第一句。", "第二句！", "第三句？"]
    assert split_sentences("One. Two!") == ["One.", "Two!"]


def test_align_rows_1to1() -> None:
    rows = align_rows("甲。乙。", "A。B。")
    assert len(rows) == 2
    assert rows[0] == {"seq": 1, "src": "甲。", "tgt": "A。", "note": None}


def test_align_rows_split_declares_note() -> None:
    rows = align_rows("甲。乙。", "AB。")
    assert len(rows) == 2
    assert any(r["note"] for r in rows)
