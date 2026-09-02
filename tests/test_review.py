"""review G0 测试：对照表完整性、长度比、句数一致、脚注守恒。"""

from __future__ import annotations

from auto_translator.glossary import Glossary, GlossaryEntry
from auto_translator.review import (
    check_alignment,
    count_footnote_refs,
    g0_unit_flags,
    length_ratio,
)


def test_check_alignment_ok() -> None:
    rows = [
        {"seq": 1, "src": "a", "tgt": "甲"},
        {"seq": 2, "src": "b", "tgt": "乙"},
    ]
    assert check_alignment(rows) == []


def test_check_alignment_gap_and_empty() -> None:
    rows = [
        {"seq": 1, "src": "a", "tgt": "甲"},
        {"seq": 3, "src": "", "tgt": ""},
    ]
    flags = check_alignment(rows)
    codes = {f.check for f in flags}
    assert "align" in codes
    assert any("空" in f.message for f in flags)


def test_length_ratio() -> None:
    assert length_ratio("abcd", "甲乙丙丁") == 1.0
    assert length_ratio("", "x") == 0.0


def test_g0_unit_flags_terminology_and_length() -> None:
    g = Glossary(
        [GlossaryEntry(source="old sport", target="老兄", type="fixed_expr", status="confirmed")]
    )
    rows = [
        {"seq": 1, "src": "old sport", "tgt": "老伙计"},
        {"seq": 2, "src": "a very long source sentence", "tgt": ""},
    ]
    flags = g0_unit_flags(rows, g)
    assert any(f.check == "terminology" for f in flags)
    assert any(f.check == "length" and "空" in f.message for f in flags)


def test_count_footnote_refs() -> None:
    assert count_footnote_refs("whole villages.1 And more") == 1
    assert count_footnote_refs("proved decisive.2") == 1
    assert count_footnote_refs("no footnote here") == 0
