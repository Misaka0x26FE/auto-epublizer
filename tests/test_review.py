"""review G0 测试：对照表完整性、长度比、句数一致、脚注守恒。"""

from __future__ import annotations

from auto_translator.glossary import Glossary, GlossaryEntry
from auto_translator.review import (
    annotate_correction_notes,
    check_alignment,
    count_footnote_refs,
    detect_corrections,
    footnote_numbers,
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
        [GlossaryEntry(source="sample greeting", target="老兄", type="fixed_expr", status="confirmed")]
    )
    rows = [
        {"seq": 1, "src": "sample greeting", "tgt": "老伙计"},
        {"seq": 2, "src": "a very long source sentence", "tgt": ""},
    ]
    flags = g0_unit_flags(rows, g)
    assert any(f.check == "terminology" for f in flags)
    assert any(f.check == "length" and "空" in f.message for f in flags)


def test_length_ratio_short_source_protection() -> None:
    """回归（issue #39）：短源行的比值是纯噪声（0.01 即翻转判定），不得报长度比。"""
    g = Glossary()
    rows = [
        {"seq": 1, "src": "1", "tgt": "1"},
        {"seq": 2, "src": "Contents", "tgt": "目录"},
        {"seq": 3, "src": "Chapter One", "tgt": "第一章"},
        {"seq": 4, "src": "A Note on Suicide", "tgt": "自杀论札记"},
    ]
    assert not [f for f in g0_unit_flags(rows, g) if f.check == "length"]


def test_length_ratio_keeps_empty_target_check_on_short_source() -> None:
    """短源保护不豁免「译文为空」（issue #39 保留项）：页码源行漏译仍可见。"""
    rows = [{"seq": 1, "src": "1", "tgt": ""}]
    flags = [f for f in g0_unit_flags(rows, Glossary()) if f.check == "length"]
    assert len(flags) == 1
    assert "空" in flags[0].message
    assert flags[0].data["src_len"] == 1  # 长度上下文随告警给出


def test_length_ratio_long_source_flagged_with_length_context() -> None:
    """长源行仍按比值判定，且 data 带 src_len/tgt_len 上下文供 agent 复核。"""
    src = "See the discussion on pages 112-114 above."
    rows = [
        {"seq": 1, "src": src, "tgt": "见图。"},
        {"seq": 2, "src": src + " " + src, "tgt": "短。"},
    ]
    flags = [f for f in g0_unit_flags(rows, Glossary()) if f.check == "length"]
    assert len(flags) == 2  # 低于下限：疑似漏译
    assert flags[0].data["src_len"] == len(src)
    assert flags[0].data["tgt_len"] == 3
    assert flags[0].data["ratio"] < 0.30
    assert flags[1].data["ratio"] < 0.30


def test_length_ratio_min_src_chars_overridable() -> None:
    """短源下限可显式收紧（默认保护是阈值，不是硬编码判断）。"""
    rows = [{"seq": 1, "src": "Chapter One", "tgt": "第一章"}]
    flags = [f for f in g0_unit_flags(rows, Glossary(), min_src_chars=5) if f.check == "length"]
    assert len(flags) == 1  # 下限调低后，短行照常参与比值判定


def test_count_footnote_refs() -> None:
    assert count_footnote_refs("whole villages.1 And more") == 1
    assert count_footnote_refs("proved decisive.2") == 1
    assert count_footnote_refs("no footnote here") == 0


def test_count_footnote_refs_ignores_citation_punct() -> None:
    """引证/统计里的冒号分号数字不是注码（避免 conservation 误报硬缺陷）。"""
    assert count_footnote_refs("（USDHHS 1992:110—11）") == 0
    assert count_footnote_refs("每 300 支香烟砍一棵树；1 公顷烟草需 0.5 公顷林地") == 0
    assert count_footnote_refs("（Goodin 1989a:588）") == 0


def test_count_footnote_refs_ignores_cjk_and_percent_adjacent() -> None:
    """回归（issue #3）：句末标点后 1~3 位数字紧跟中文/百分号 = 统计数字，非注码。

    4 位年份本就被 ``(?!\\d)`` 回溯排除（issue 列出的 1881/1888 等样例不复现）；
    实际误报类是「。82个」「。95年」「。46%」。
    """
    assert count_footnote_refs("全俄铁路网扩张。82个车站投入运营") == 0
    assert count_footnote_refs("起义爆发。95年运动失败") == 0
    assert count_footnote_refs("燃料被取代。46%的机车改用石油") == 0
    assert count_footnote_refs("占比过半。50％来自顿巴斯") == 0


def test_count_footnote_refs_ignores_abbreviation_refs() -> None:
    """回归 #8：缩写点后的数字是页码/条款引用，不是脚注注码。

    现场案例（俄文政论/学术书）：源文 13 处 `стр.66` 一类的页码引用被误判为注码，
    因 `footnote` 守恒是硬门，只能去改源文排印。这里按「点号前是缩写词」排除。
    """
    assert count_footnote_refs("(стр.66)") == 0
    assert count_footnote_refs("Папюс на стр.168 своего сочинения") == 0
    assert count_footnote_refs("опубликованы на стр.146--158 посмертно") == 0
    assert count_footnote_refs("(с.859)") == 0
    assert count_footnote_refs("«За рубежом», стр.8)") == 0
    assert count_footnote_refs("в соответствии с п.5 настоящей статьи") == 0
    assert count_footnote_refs("перечисленные в п.1, ст.3 комиссии") == 0
    assert count_footnote_refs("Монте-Карло 11--12.Х.79 г.") == 0
    assert count_footnote_refs("«Правда», 20.Х.77 г.") == 0
    assert count_footnote_refs("см. рис.3 и табл.2") == 0


def test_count_footnote_refs_ignores_measure_words() -> None:
    """回归 #22：句末点后「数字 + 量词」是中文日期/时刻/口径写法，不是注码。

    现场：`。3 月` `。10 时` `。50 口径` 被计为注码，与源（英文无注码）对账后
    误报「脚注标记数量不守恒」硬缺陷。
    """
    assert count_footnote_refs("会议定于三月召开。3 月十五日之前") == 0
    assert count_footnote_refs("列车时刻。10 时发车。") == 0
    assert count_footnote_refs("时间戳 14 时 39 分。14 时 39") == 0
    assert count_footnote_refs("这是。50 口径的机枪") == 0
    assert count_footnote_refs("历时五年。5 年之后") == 0
    # 无单位跟随的真注码仍必须计入
    assert count_footnote_refs("正文结束。7") == 1


def test_count_footnote_refs_ignores_enumerators() -> None:
    """回归 #8：句末标点后的枚举号（列表序号）不是注码。

    现场案例（中文译文）：「结婚礼。1. 订婚。」里的 `1` 被当成注码，导致
    「脚注标记数量不守恒」硬缺陷，而源文根本没有脚注。
    """
    assert count_footnote_refs("结婚礼。1. 订婚。") == 0
    assert count_footnote_refs("正文。2) 婚礼。") == 0
    assert count_footnote_refs("标题。3、正文。") == 0
    assert count_footnote_refs("结束。4）婚礼。") == 0
    assert count_footnote_refs("见上文。5] 附录。") == 0


def test_count_footnote_refs_keeps_true_marker_forms() -> None:
    """真注码形态不受排除集影响：行尾 / 空格 / 英文粘连（此为已知残余风险边界）。"""
    assert count_footnote_refs("whole villages.1") == 1
    assert count_footnote_refs("proved decisive.2 And more") == 1
    assert count_footnote_refs("a long sentence.1The next one") == 1


def test_count_footnote_refs_keeps_cjk_sentence_final_markers() -> None:
    """回归：#8 缩写启发式不得吞掉中文真注码（点前中文词 ≤2 字也须计数）。

    「正文。1」「城。1」点前是 1~2 字中文词——若照搬「≤2 字符即缩写点」会被排除，
    译文侧真注码漏计、脚注守恒误报。
    """
    assert count_footnote_refs("正文。1") == 1
    assert count_footnote_refs("城。1 下一句") == 1
    assert count_footnote_refs("中华人民共和国。1") == 1


def test_g0_footnote_conservation_tolerates_stats_numbers() -> None:
    """统计数字（句末标点后紧跟中文/%）不触发守恒硬缺陷；真注码仍守恒（回归 #3）。"""
    g = Glossary()
    rows = [
        {
            "seq": 1,
            "src": "The network expanded. 82 stations opened",
            "tgt": "路网扩张。82个车站投入运营",
        },
        {"seq": 2, "src": "Fuel was replaced. 46% switched", "tgt": "燃料被取代。46%改用石油"},
        {"seq": 3, "src": "It was decisive.1 The end", "tgt": "这是决定性的。1"},
    ]
    flags = g0_unit_flags(rows, g)
    assert not [f for f in flags if f.check == "footnote" and "不守恒" in f.message]


def test_count_footnote_marks() -> None:
    from auto_translator.review import count_footnote_marks

    assert count_footnote_marks("text[^1] more") == 1
    assert count_footnote_marks("[^1]: note") == 1
    assert count_footnote_marks("no mark") == 0


def test_count_footnote_marks_superscript_notation() -> None:
    """注码的**上标数字记法**与 pandoc 记法同权（回归：sample-document-f 2192 处）。

    源侧写 ``[^1]``、译侧改用原书自身的上标排法写 ``¹``，纯记法差异
    不得被判成「脚注标记数量不守恒」（实测 19 个单元被打红）。
    """
    from auto_translator.review import count_footnote_marks

    assert count_footnote_marks("汉斯·弗兰克⁴ 在后来的岁月里") == 1
    assert count_footnote_marks("¹ 日记，1944 年 12 月 9 日") == 1
    # 多位注号算**一个**标记，不是逐位数字
    assert count_footnote_marks("见⁸²³ 与⁹⁹⁹") == 2
    # 与 pandoc 记法同权：源 `[^N]` 与译 `ⁿ` 计数相同 → 守恒判据两侧对齐
    assert count_footnote_marks("[^12]") == count_footnote_marks("¹²") == 1
    # 无上标时仍为 0（不误伤普通文本）
    assert count_footnote_marks("面积 5 平方公里") == 0


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


def test_g0_footnote_tgt_may_exceed_src_cjk_asymmetry() -> None:
    """译文侧注码**多于**源侧不报违例（跨语言计数不对称的必然结果）。

    源侧计数受缩写启发式影响：``_is_abbrev_dot`` 把点前 ≤2 字母的词当缩写点，
    故 ``…供职于 OT.24`` 的注号在英文/德文侧数不到；而该启发式对 CJK 句末的「。」
    明确豁免，同一个注号在中文译文侧数得到。逐字忠实的译文必然多于源侧，
    用 ``!=`` 比较会误判并把 ``g0_structure_open`` 顶到非 0 阻断放行
    （现场：builders-of-the-third-reich 正文 739 个注号 / 源侧只数到 629）。
    """
    g = Glossary()
    # 源侧：两个注码，其中一个紧跟 `OT.`（≤2 字母 → 源侧漏计）
    rows = [
        {
            "seq": 1,
            "src": "Many served in the OT.24 and 18,000 died.1",
            "tgt": "许多人在托德组织服役。24 ",
        },
        {"seq": 2, "src": "", "tgt": "18,000 人死亡。1 "},
    ]
    rows[1]["src"] = "Most of them were Polish."
    assert count_footnote_refs(rows[0]["src"]) == 1  # 源侧只数到 1 个
    assert count_footnote_refs(rows[0]["tgt"] + rows[1]["tgt"]) == 2  # 译文侧数到 2 个
    assert not [f for f in g0_unit_flags(rows, g) if f.check == "footnote"]
    # 反向：译文侧真的丢了注码 → 仍须报
    lost = [
        {"seq": 1, "src": "18,000 died.1 and later.2", "tgt": "18,000 人死亡。1 "},
    ]
    assert any(f.check == "footnote" for f in g0_unit_flags(lost, g))


def test_footnote_numbers_superscript_forms() -> None:
    """回归（issue #34）：上标注码（紧贴前一 token、前为收尾标点）必须提取到。"""
    assert footnote_numbers("(Zentralbauleitung)14 and more") == {14}
    assert footnote_numbers("(Krematorium)22 Head of the department") == {22}
    assert footnote_numbers("organigram:46 Head") == {46}
    assert footnote_numbers('signed "The Final Solution"14 next') == {14}
    assert footnote_numbers("（中央建筑管理局）14 及其后续") == {14}  # 译文侧同一判据
    assert footnote_numbers("组织图：46 后续") == {46}  # 全角冒号形态
    assert footnote_numbers("击打囚犯，39 一些监工") == {39}  # 全角逗号形态（现场实测）
    assert footnote_numbers("见〔240〕与[241]") == {240, 241}  # 括号式（译文侧注文）


def test_footnote_numbers_negative_controls() -> None:
    """负对照（issue #34）：与注码同形的非注码不得提取。"""
    assert footnote_numbers("4 departments and 11 Construction Offices") == set()
    assert footnote_numbers("in 1941 the war began") == set()
    assert footnote_numbers("an area of 6 km2 was cleared") == set()
    assert footnote_numbers("(6 square mile) area") == set()
    assert footnote_numbers("125,000 inmates were registered") == set()
    assert footnote_numbers("section 1a of the order") == set()
    assert footnote_numbers("see стр.66 and рис.3 above") == set()
    assert footnote_numbers("(in ’000 m2)164") == {164}  # 千分位刻度 000 不算注号


def test_footnote_numbers_keep_legacy_sentence_final() -> None:
    """句末式与上标式并存：``decisive.2`` 仍提取，且不因新分支重复。"""
    assert footnote_numbers("proved decisive.2 And more") == {2}
    assert footnote_numbers("whole villages.1") == {1}


def test_count_footnote_refs_gate_stays_sentence_final() -> None:
    """守恒门口径不变（issue #34 实证）：上标形态不进计数门，避免形态不对称误报。"""
    assert count_footnote_refs("(Zentralbauleitung)14 and more") == 0
    assert count_footnote_refs("（中央建筑管理局）14 及其后续") == 0
    assert count_footnote_refs("proved decisive.2 And more") == 1


def test_count_footnote_defs_separate_from_refs() -> None:
    """引用与定义分开统计：``[^label]:`` 定义行单独计数。"""
    from auto_translator.review import count_footnote_defs, count_footnote_marks

    text = "text[^1] more\n\n[^1]: note body\n"
    assert count_footnote_defs(text) == 1
    assert count_footnote_marks(text) == 2  # 引用 + 定义
    assert count_footnote_refs(text) == 0  # 数字式注码为 0


def test_g0_footnote_suspect_reports_missing_superscript_numbers() -> None:
    """回归（issue #34）：译文丢掉上标注码时，advisory 差集必须报出该注号与样本行。

    守恒计数门保持句末式口径（两侧同为 0，不报也不误报）；真丢失以集合差集
    报出，供 agent 逐条核证（N 阶段身份契约落地后由 ref_id 守恒阻断）。
    """
    g = Glossary()
    rows = [
        {
            "seq": 1,
            "src": "(Zentralbauleitung)14 and (Krematorium)22 were named",
            "tgt": "（中央建筑管理局）14 及其后",
        }
    ]
    flags = {f.check: f for f in g0_unit_flags(rows, g)}
    assert "footnote" not in flags  # 计数门不因放宽而改判
    suspect = flags["footnote_suspect"]
    assert suspect.data["numbers"] == [22]
    assert suspect.data["samples"] == [{"seq": 1, "number": 22}]


def test_g0_footnote_suspect_quiet_when_tgt_uses_other_forms() -> None:
    """译文用另一种排法承载同一注号时，差集判据不误报（形态无关）。"""
    g = Glossary()
    rows = [
        {"seq": 1, "src": "(Krematorium)22 was named", "tgt": "（焚尸场）22 被点名"},
        {"seq": 2, "src": "organigram:46 here", "tgt": "组织图：46 如下"},
        {"seq": 3, "src": "see 〔240〕", "tgt": "见〔240〕"},
    ]
    flags = [f for f in g0_unit_flags(rows, g) if f.check == "footnote_suspect"]
    assert not flags


def test_g0_footnote_breakdown_reports_refs_and_defs() -> None:
    """丢定义（而非引用）时 data 能区分两类计数（issue #34 分开统计）。"""
    g = Glossary()
    rows = [
        {"seq": 1, "src": "text[^1] and more words here", "tgt": "正文[^1]及更多词"},
        {"seq": 2, "src": "[^1]: note body", "tgt": ""},
    ]
    flags = [f for f in g0_unit_flags(rows, g) if f.check == "footnote"]
    assert len(flags) == 1
    data = flags[0].data
    assert data["src_refs"] == 0 and data["tgt_refs"] == 0  # 句末式：本例无
    assert data["src_defs"] == 1 and data["tgt_defs"] == 0
    assert data["src_marks"] == 2 and data["tgt_marks"] == 1


def test_g0_footnote_after_cjk_closing_quote_is_counted() -> None:
    """注码紧跟 CJK 闭合引号时也须计入（回归 issue #29）。

    中文排版把句末点放在引号内，闭合引号跟在句末点之后，于是注号紧跟 ``』``/``」``
    而不是 ``。``。只认 ``[.!?…。！？]`` 的计数器会少数十几个注码，在源侧可数偏多的
    单元上误报脚注不守恒（现场：builders-of-the-third-reich ch08 seq 44，源侧 3 /
    译文侧 1，而三个注码 33/34/35 一个都没丢）。
    """
    g = Glossary()
    src = (
        "‘Officers were not automatons. They hoped to deploy their prison labour force,’ "
        "Allen wrote.33 He noted that.34 Allen concluded.35"
    )
    tgt = "『军官绝非自动机器。他们希望投入囚犯劳动力。』33 他指出。34 艾伦总结道。35 "
    assert count_footnote_refs(src) == 3
    assert count_footnote_refs(tgt) == 3  # 修复前为 1
    assert not [
        f for f in g0_unit_flags([{"seq": 1, "src": src, "tgt": tgt}], g) if f.check == "footnote"
    ]
    # 真正丢失仍须报：译文侧只剩 2 个
    lost = tgt.replace("。35 ", "。")
    assert any(
        f.check == "footnote" for f in g0_unit_flags([{"seq": 1, "src": src, "tgt": lost}], g)
    )
    # 英文源侧不受影响：`'` 不是句末标点，`...product,' 5` 不计
    assert count_footnote_refs("…efficient industrial production,’ Allen wrote.33") == 1
    assert count_footnote_refs("…production,’ 33") == 0


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


def test_md_align_drift_clean() -> None:
    """交付审计 S1.1：md 与 align tgt 一致（含标题行/脚注定义/标记差异可归一化）。"""
    from auto_translator.review import md_align_drift

    md = "# 第一章\n\n正文一句[^1]。\n\n![图](media/x.png)\n\n[^1]: 注释文本。\n"
    rows = [
        {"seq": 1, "src": "Source one[^1].", "tgt": "正文一句[^1]。"},
        {"seq": 2, "src": "![img](media/x.png)", "tgt": "![图](media/x.png)"},
    ]
    assert md_align_drift(md, rows) == []


def test_md_align_drift_detects_missing_content() -> None:
    """交付审计 S1.1：md 丢图片段/脚注句（align 完整）→ 报告「align 有而 md 缺」。"""
    from auto_translator.review import md_align_drift

    md = "# 第一章\n\n正文一句[^1]。\n"  # 丢图片段与注释
    rows = [
        {"seq": 1, "src": "Source one[^1].", "tgt": "正文一句[^1]。"},
        {"seq": 2, "src": "![img](media/x.png)", "tgt": "![图](media/x.png)"},
    ]
    drift = md_align_drift(md, rows)
    assert len(drift) == 1
    assert "align 有而 md 缺" in drift[0] and "seq=2" in drift[0]


def test_md_align_drift_strict_defs_when_align_has_defs() -> None:
    """align 含脚注定义行时严格比对定义文本：md 丢定义 → 报告缺内容。"""
    from auto_translator.review import md_align_drift

    md = "# 第一章\n\n正文[^1]。\n"  # 丢定义
    rows = [
        {"seq": 1, "src": "text[^1]", "tgt": "正文[^1]。"},
        {"seq": 2, "src": "note src", "tgt": "[^1]: 注释文本。"},
    ]
    drift = md_align_drift(md, rows)
    assert drift and "align 有而 md 缺" in drift[0]


def test_md_align_drift_title_row_tolerated() -> None:
    """align 含标题行（与单元 title 对应）→ 剔除后比对通过。"""
    from auto_translator.review import md_align_drift

    md = "# 第一章\n\n正文。\n"
    rows = [
        {"seq": 1, "src": "Chapter I", "tgt": "第一章"},
        {"seq": 2, "src": "Body.", "tgt": "正文。"},
    ]
    assert md_align_drift(md, rows, title="Chapter I") == []


def test_md_align_drift_heading_row_without_trailing_newline() -> None:
    """回归 #8：首行 tgt 以 `## ` 开头且行尾无换行时，不得把整串当作标题行删掉。

    原实现用 `"".join(tgt)`（无分隔）拼接，`_HEADING_LINE` 逐行正则会吃掉整串 →
    误报「align 0 字符」并阻断 import（真实案例：单元内首段即 `## ` 小标题）。
    """
    from auto_translator.review import md_align_drift

    md = "# 标题\n\n## 第一章\n\n正文。\n"
    rows = [
        {"seq": 1, "src": "## ГЛАВАI", "tgt": "## 第一章"},
        {"seq": 2, "src": "Текст.", "tgt": "正文。"},
    ]
    assert md_align_drift(md, rows) == []


def test_g0_heading_conservation() -> None:
    """标题守恒（issue #12）：丢标题/换级/补标题告警；一致或缺 md 侧不告警。"""
    g = Glossary()
    rows = [{"seq": 1, "src": "text", "tgt": "正文"}]
    structured = "# 第一章\n\n## 第一节\n\n正文\n"
    # 一致 → 无 heading 告警
    assert not [
        f
        for f in g0_unit_flags(rows, g, structured_md=structured, translation_md=structured)
        if f.check == "heading"
    ]
    # 丢 ### → 告警（src/tgt 逐层计数入 data）
    lost = "# 第一章\n\n正文\n"
    flags = [
        f
        for f in g0_unit_flags(rows, g, structured_md=structured, translation_md=lost)
        if f.check == "heading"
    ]
    assert len(flags) == 1
    assert flags[0].data == {"src": {1: 1, 2: 1}, "tgt": {1: 1}}
    # 换级（##→###）→ 告警（现场报告 #10-B1 的 ch04 形态）
    shifted = "# 第一章\n\n### 第一节\n\n正文\n"
    assert any(
        f.check == "heading"
        for f in g0_unit_flags(rows, g, structured_md=structured, translation_md=shifted)
    )
    # 只给 structured 不给 translation → 跳过（convert / 未译场景）
    assert not [f for f in g0_unit_flags(rows, g, structured_md=structured) if f.check == "heading"]
