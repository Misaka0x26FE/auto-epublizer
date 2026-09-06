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


def test_count_footnote_marks() -> None:
    from auto_translator.review import count_footnote_marks

    assert count_footnote_marks("text[^1] more") == 1
    assert count_footnote_marks("[^1]: note") == 1
    assert count_footnote_marks("no mark") == 0


def test_g0_marker_conservation() -> None:
    """单元级总量守恒：标记丢失告警；拆句挪位（总量相等）不误报。"""
    g = Glossary()
    # 丢一个 {fig:2}
    rows = [
        {"seq": 1, "src": "see {fig:1} and {fig:2}.", "tgt": "见图 {fig:1}。"},
    ]
    flags = g0_unit_flags(rows, g)
    marker_flags = [f for f in flags if f.check == "marker"]
    assert len(marker_flags) == 1
    assert marker_flags[0].data == {"src": 2, "tgt": 1}
    # 拆句：标记在 tgt 行间挪位但总量相等 → 不告警
    rows_ok = [
        {"seq": 1, "src": "see {fig:1} and", "tgt": "见图 {fig:1}"},
        {"seq": 2, "src": "{fig:2} here.", "tgt": "和 {fig:2}。"},
    ]
    assert not [f for f in g0_unit_flags(rows_ok, g) if f.check == "marker"]


def test_g0_footnote_conservation() -> None:
    """脚注守恒：pandoc 与数字式两种表示都查；跨行挪位不误报。"""
    g = Glossary()
    # pandoc 式：tgt 丢定义
    rows = [
        {"seq": 1, "src": "text[^1] here.", "tgt": "正文在这里。"},
        {"seq": 2, "src": "[^1]: note", "tgt": ""},
    ]
    flags = [f for f in g0_unit_flags(rows, g) if f.check == "footnote"]
    assert len(flags) == 1
    # 数字式：tgt 丢句末注码
    rows2 = [{"seq": 1, "src": "proved decisive.2", "tgt": "证明是决定性的。"}]
    assert any(f.check == "footnote" for f in g0_unit_flags(rows2, g))
    # 跨行挪位：总量相等 → 不告警
    rows3 = [
        {"seq": 1, "src": "text[^1] and", "tgt": "正文[^1]"},
        {"seq": 2, "src": "[^1]: note", "tgt": "[^1]: 注"},
    ]
    assert not [f for f in g0_unit_flags(rows3, g) if f.check == "footnote"]


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
