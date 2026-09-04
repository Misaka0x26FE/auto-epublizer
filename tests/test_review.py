"""review G0 测试：对照表完整性、长度比、句数一致、脚注守恒。"""

from __future__ import annotations

from auto_translator.glossary import Glossary, GlossaryEntry
from auto_translator.review import (
    annotate_correction_notes,
    check_alignment,
    count_footnote_refs,
    detect_corrections,
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


def test_detect_and_annotate_corrections() -> None:
    """勘误留痕：detect_corrections 命中先例；annotate 给 align 行补 corr: 前缀不改文本。"""
    assert detect_corrections("IDG reported in 19487") == [("IDG", "IDF"), ("19487", "1948")]
    assert detect_corrections("正常文本") == []
    rows = [
        {"seq": 1, "src": "The IDG strike began.", "tgt": "IDG 罢工开始。", "note": None},
        {"seq": 2, "src": "正常句。", "tgt": "正常译。", "note": "split"},
    ]
    out = annotate_correction_notes(rows)
    assert out[0]["note"] == "corr:IDG→IDF"
    assert out[0]["src"] == rows[0]["src"] and out[0]["tgt"] == rows[0]["tgt"]
    assert out[1]["note"] == "split"  # 未命中保持原 note
