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


def test_count_footnote_refs_ignores_citation_punct() -> None:
    """引证/统计里的冒号分号数字不是注码（避免 conservation 误报硬缺陷）。"""
    assert count_footnote_refs("（USDHHS 1992:110—11）") == 0
    assert count_footnote_refs("每 300 支香烟砍一棵树；1 公顷烟草需 0.5 公顷林地") == 0
    assert count_footnote_refs("（Goodin 1989a:588）") == 0


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


def test_fidelity_flags_clean() -> None:
    """双向干净：块全进对照表、src 全在源文 → 0 flag（标题作 src 也不误报）。"""
    from auto_translator.review import fidelity_flags

    md = "# 第一章\n\nFirst sentence here.\n\nSecond sentence here.\n"
    rows = [
        {"seq": 1, "src": "# 第一章", "tgt": "第一章"},
        {"seq": 2, "src": "First sentence here.", "tgt": "第一句话。"},
        {"seq": 3, "src": "Second sentence here.", "tgt": "第二句话。"},
    ]
    assert fidelity_flags(md, rows) == []


def test_fidelity_flags_reverse_catches_rewrite() -> None:
    """反向：src 被改写/杜撰（不在源文中）→ fidelity flag（head 含原文片段）。"""
    from auto_translator.review import fidelity_flags

    md = "# C1\n\nFirst sentence here.\n"
    rows = [{"seq": 1, "src": "First sentence here, friend!", "tgt": "第一句话，朋友！"}]
    flags = fidelity_flags(md, rows)
    reverse = [f for f in flags if "不在源文中" in f.message]
    assert reverse and all(f.data.get("seq") == 1 for f in reverse)


def test_fidelity_flags_forward_missing_block() -> None:
    """前向：structured 有块未进对照表（合法剔除场景）→ 缺块 flag（advisory 语义）。"""
    from auto_translator.review import fidelity_flags

    md = "# C1\n\nPara one.\n\nPara two.\n\nAll rights reserved. Printed in USA.\n"
    rows = [
        {"seq": 1, "src": "Para one.", "tgt": "段一。"},
        {"seq": 2, "src": "Para two.", "tgt": "段二。"},
    ]
    flags = fidelity_flags(md, rows)
    assert any("未进对照表" in f.message for f in flags)
    # 合法剔除：版权残句不留反向失配（src 都在源文中）
    assert not any("不在源文中" in f.message for f in flags)


def test_fidelity_tolerates_split_merge() -> None:
    """拆并句容忍：拼接子串匹配，句序调整/拆分不误报。"""
    from auto_translator.review import fidelity_flags

    md = "# C1\n\nAlpha beta gamma. Delta epsilon.\n"
    rows = [
        {"seq": 1, "src": "Alpha beta gamma.", "tgt": "甲乙丙。"},
        {"seq": 2, "src": "Delta epsilon.", "tgt": "丁戊。"},
    ]
    assert fidelity_flags(md, rows) == []


def test_parse_md_tables() -> None:
    """S4.2 解析器：基本表/无分隔行不算表/围栏内跳过/转义管道不增列。"""
    from auto_translator.review import parse_md_tables

    good = "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
    assert parse_md_tables(good) == [{"rows": 3, "cols": 2}]
    # 无分隔行 → 不算表
    assert parse_md_tables("| a | b |\n| 1 | 2 |\n") == []
    # 围栏内的表跳过
    fenced = "```\n| a | b |\n| --- | --- |\n```\n" + good
    assert parse_md_tables(fenced) == [{"rows": 3, "cols": 2}]
    # 转义管道不增列
    escaped = "| a | b \\| c |\n| --- | --- |\n"
    assert parse_md_tables(escaped) == [{"rows": 2, "cols": 2}]


def test_table_shape_flags() -> None:
    """S4.2 守恒：同形 0 flag；少行/多表各 1 条含形状数据。"""
    from auto_translator.review import table_shape_flags

    src = "| a | b |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n"
    assert table_shape_flags(src, src) == []
    tgt_short = "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
    flags = table_shape_flags(src, tgt_short)
    assert len(flags) == 1 and flags[0].data == {"index": 1, "src": "4x2", "tgt": "3x2"}
    tgt_extra = src + "\n| x | y |\n| --- | --- |\n| 9 | 9 |\n"
    flags2 = table_shape_flags(src, tgt_extra)
    assert len(flags2) == 1 and "数量" in flags2[0].message
