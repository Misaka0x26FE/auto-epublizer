"""真实案例回归测试：从历史翻译工作成果提取的黄金语料。

数据来源（见 tests/fixtures/real_cases/）：
- glossary_fleming.csv —— 《One's Company》真实术语表（category,source,target,note）；
- glossary_morris.csv —— 《Israel's Border Wars》真实术语表；
- 错误向量 —— 摘自 fleming/morris 的 QA 报告与 quality-lessons.md。

这些是「真实任务质量」的检验：术语冲突（赤区/苏区）、人名用字错误（韩复渠→韩复榘）、
标记守恒（{fig:NNN} 32/32）、h1/h2 层级一致、段落 1:1、断字符修复、排印讹误（IDG→IDF）、
版权残句剔除、标点规范化（«»→《》）。
"""

from __future__ import annotations

from pathlib import Path

from auto_epublizer.glossary import (
    Glossary,
    GlossaryEntry,
    load_legacy_category_csv,
    terminology_hits,
)
from auto_epublizer.review import (
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
