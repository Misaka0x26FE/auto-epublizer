"""真实案例回归测试：从历史翻译工作成果提取的黄金语料。

数据来源（见 tests/fixtures/real_cases/）：
- glossary_fleming.csv —— 《One's Company》真实术语表（category,source,target,note）；
- glossary_morris.csv —— 《Israel's Border Wars》真实术语表；
- glossary_samarqandi_fa.csv —— 波斯语真实术语表（RTL，权威 schema：
  source,target,type,aliases,gender,reading,status,note），摘自 15 世纪波斯编年史
  《مطلع سعدین و مجمع بحرین》第一卷中译（workspace matla-al-sadayn-1）；
- 错误向量 —— 摘自 fleming/morris 的 QA 报告与 quality-lessons.md。

这些是「真实任务质量」的检验：术语冲突（赤区/苏区）、人名用字错误（韩复渠→韩复榘）、
标记守恒（{fig:NNN} 32/32）、h1/h2 层级一致、段落 1:1、断字符修复、排印讹误（IDG→IDF）、
版权残句剔除、标点规范化（«»→《》）、以及 RTL 源语言的术语命中（波斯语 → 中文）。
"""

from __future__ import annotations

from pathlib import Path

from auto_translator.glossary import (
    Glossary,
    GlossaryEntry,
    load_glossary_csv,
    load_legacy_category_csv,
    terminology_hits,
)
from auto_translator.review import (
    apply_corrections,
    count_heading_levels,
    count_markers,
    count_paragraph_blocks,
    markers_conserved,
    normalize_punctuation,
    repair_missing_hyphens,
    strip_copyright_boilerplate,
)

FIXTURES = Path(__file__).parent / "fixtures" / "real_cases"


def test_load_fleming_glossary() -> None:
    entries = load_legacy_category_csv(FIXTURES / "glossary_fleming.csv")
    assert len(entries) >= 30
    by_source = {e.source: e for e in entries}
    assert by_source["Peter Fleming"].target == "彼得·弗莱明"
    assert by_source["Peter Fleming"].type == "person"
    assert by_source["Kiangsi"].type == "place"
    assert by_source["Comintern"].type == "term"
    assert by_source["Chiang Kai-shek"].target == "蒋介石"


def test_load_morris_glossary() -> None:
    entries = load_legacy_category_csv(FIXTURES / "glossary_morris.csv")
    assert len(entries) >= 60
    by_source = {e.source: e for e in entries}
    assert by_source["Israel Defence Forces (IDF)"].type == "org"
    assert by_source["fedayeen"].type == "term"
    assert by_source["David Ben-Gurion"].target == "戴维·本-古里安"
    assert by_source["Qibya"].type == "place"


def test_load_samarqandi_persian_glossary() -> None:
    """波斯语真实术语表（RTL，权威 schema）：别名用 ``|`` 分隔、全部 confirmed。"""
    entries = load_glossary_csv(FIXTURES / "glossary_samarqandi_fa.csv")
    assert len(entries) >= 30
    by_source = {e.source: e for e in entries}
    assert by_source["امیر تیمور"].target == "帖木儿"
    assert by_source["امیر تیمور"].type == "person"
    assert "تیمور گورکان" in by_source["امیر تیمور"].aliases
    assert by_source["خراسان"].type == "place"
    assert by_source["ماوراء النهر"].target == "河中地区"
    assert by_source["صاحبقران"].target == "幸运之主"
    assert all(e.status == "confirmed" for e in entries)


def test_terminology_hit_rtl_persian() -> None:
    """真实教训（RTL）：波斯语源出现术语（或别名）而译文缺失中文对应时必须命中。"""
    g = Glossary(load_glossary_csv(FIXTURES / "glossary_samarqandi_fa.csv"))
    src = "و امیر تیمور به ماوراء النهر رفت و خراسان را گرفت"
    # 主词条已译、只漏呼罗珊 → 只报 خراسان
    hits = terminology_hits(src, "帖木儿去了河中地区", g)
    assert [h.source for h in hits] == ["خراسان"]
    assert hits[0].expected == "呼罗珊"
    # 全部译出 → 零命中
    assert terminology_hits(src, "帖木儿去了河中地区并夺取了呼罗珊", g) == []
    # 别名 تیمور گورکان 同样命中主词条 امیر تیمور（译文缺对应 target 时报）
    hits2 = terminology_hits("تیمور گورکان لشکر آراست", "整军", g)
    assert [(h.source, h.expected) for h in hits2] == [("امیر تیمور", "帖木儿")]


def test_terminology_conflict_soviet_area() -> None:
    """真实教训：同一概念赤区/苏区混用，须外置冲突待裁决。"""
    g = Glossary(
        [
            GlossaryEntry(source="Soviet area", target="赤区", type="term", status="confirmed"),
            GlossaryEntry(source="Soviet area", target="苏区", type="term", status="candidate"),
        ]
    )
    conflicts = g.detect_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0].existing_target == "赤区"
    assert conflicts[0].proposed_target == "苏区"


def test_terminology_hit_han_fuju() -> None:
    """真实教训：人名用字错误（韩复渠→韩复榘）应被术语命中捕获。"""
    g = Glossary(
        [GlossaryEntry(source="Han Fu Chu", target="韩复榘", type="person", status="confirmed")]
    )
    # 译文写错字
    hits = terminology_hits("Han Fu Chu governed Shandong", "韩复渠主政山东", g)
    assert any(h.source == "Han Fu Chu" and h.expected == "韩复榘" for h in hits)
    # 正确译法不报
    assert terminology_hits("Han Fu Chu governed Shandong", "韩复榘主政山东", g) == []


def test_marker_conservation() -> None:
    """真实教训：插入元素标记数量守恒（{fig:NNN} 32/32）。"""
    src = "图 {fig:1} 与 {fig:2} 与 {fig:3}"
    tgt = "Figure {fig:1} and {fig:2} and {fig:3}"
    assert count_markers(src) == 3
    assert markers_conserved(src, tgt)
    assert not markers_conserved(src, "图 {fig:1} 与 {fig:2}")


def test_heading_levels_conservation() -> None:
    """真实教训：h1/h2 层级数量与源文一致。"""
    src = "# A\n\n## B\n\n## C\n\n### D\n"
    tgt = "# 甲\n\n## 乙\n\n## 丙\n\n### 丁\n"
    assert count_heading_levels(src) == count_heading_levels(tgt) == {1: 1, 2: 2, 3: 1}


def test_paragraph_blocks_1to1() -> None:
    """真实教训：段落块数量 1:1。"""
    src = "p1\n\np2\n\np3"
    tgt = "t1\n\nt2\n\nt3"
    assert count_paragraph_blocks(src) == count_paragraph_blocks(tgt) == 3


def test_repair_missing_hyphens() -> None:
    """真实教训：断字符修复（IsraelEgypt、BenGurion、19491955）。"""
    assert repair_missing_hyphens("IsraelEgypt") == "Israel-Egypt"
    assert repair_missing_hyphens("BenGurion") == "Ben-Gurion"
    assert repair_missing_hyphens("19491955") == "1949-1955"


def test_apply_corrections_print_error() -> None:
    """真实教训：排印讹误按先例修正（IDG→IDF、19487→1948）。"""
    assert apply_corrections("the IDG was active") == "the IDF was active"
    assert apply_corrections("in 19487 the war") == "in 1948 the war"


def test_strip_copyright_boilerplate() -> None:
    """真实教训：版权残句剔除。"""
    lines = [
        "正文第一段。",
        "正文第二段。",
        "All rights reserved. No part of this publication may be reproduced.",
    ]
    out = strip_copyright_boilerplate(lines)
    assert out == ["正文第一段。", "正文第二段。"]


def test_normalize_punctuation_guillemets() -> None:
    assert normalize_punctuation("«战争与和平»") == "《战争与和平》"


def test_normalize_punctuation_quotes() -> None:
    assert normalize_punctuation('他说"你好"') == "他说「你好」"
    assert normalize_punctuation('He said "hi"', lang="en") == 'He said "hi"'
