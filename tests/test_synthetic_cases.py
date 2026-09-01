"""合成多语回归向量；不包含真实书稿或真实任务术语表。"""

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

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic_cases"


def test_load_legacy_a_glossary() -> None:
    entries = load_legacy_category_csv(FIXTURES / "glossary_legacy_a.csv")

    by_source = {e.source: e for e in entries}
    assert by_source["Sample A entry 01"].target == "示例A词语01"
    assert by_source["Sample A entry 01"].type == "person"
    assert by_source["Sample A entry 24"].type == "place"
    assert by_source["Sample A entry 17"].type == "term"
    assert by_source["Sample A entry 02"].target == "示例A词语02"


def test_load_legacy_b_glossary() -> None:
    entries = load_legacy_category_csv(FIXTURES / "glossary_legacy_b.csv")

    by_source = {e.source: e for e in entries}
    assert by_source["Sample B entry 36"].type == "org"
    assert by_source["Sample B entry 05"].type == "term"
    assert by_source["Sample B entry 13"].target == "示例B词语13"
    assert by_source["Sample B entry 52"].type == "place"


def test_terminology_conflict_sample_area() -> None:
    """合成边界：同一概念晨区/晓区混用，须外置冲突待裁决。"""
    g = Glossary(
        [
            GlossaryEntry(source="Sample area", target="晨区", type="term", status="confirmed"),
            GlossaryEntry(source="Sample area", target="晓区", type="term", status="candidate"),
        ]
    )
    conflicts = g.detect_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0].existing_target == "晨区"
    assert conflicts[0].proposed_target == "晓区"


def test_terminology_hit_sample_name() -> None:
    """合成边界：人名用字错误（示例人物误字→示例A词语10）应被术语命中捕获。"""
    g = Glossary(
        [GlossaryEntry(source="Sample A entry 10", target="示例A词语10", type="person", status="confirmed")]
    )
    # 译文写错字
    hits = terminology_hits("Sample A entry 10 visited Sample Place", "示例人物误字访问示例地点", g)
    assert any(h.source == "Sample A entry 10" and h.expected == "示例A词语10" for h in hits)
    # 正确译法不报
    assert terminology_hits("Sample A entry 10 visited Sample Place", "示例A词语10访问示例地点", g) == []


def test_marker_conservation() -> None:
    """合成边界：插入元素标记数量守恒（{fig:NNN} 32/32）。"""
    src = "图 {fig:1} 与 {fig:2} 与 {fig:3}"
    tgt = "Figure {fig:1} and {fig:2} and {fig:3}"
    assert count_markers(src) == 3
    assert markers_conserved(src, tgt)
    assert not markers_conserved(src, "图 {fig:1} 与 {fig:2}")


def test_heading_levels_conservation() -> None:
    """合成边界：h1/h2 层级数量与源文一致。"""
    src = "# A\n\n## B\n\n## C\n\n### D\n"
    tgt = "# 甲\n\n## 乙\n\n## 丙\n\n### 丁\n"
    assert count_heading_levels(src) == count_heading_levels(tgt) == {1: 1, 2: 2, 3: 1}


def test_paragraph_blocks_1to1() -> None:
    """合成边界：段落块数量 1:1。"""
    src = "p1\n\np2\n\np3"
    tgt = "t1\n\nt2\n\nt3"
    assert count_paragraph_blocks(src) == count_paragraph_blocks(tgt) == 3


def test_repair_missing_hyphens() -> None:
    """合成边界：断字符修复（AlphaBeta、GammaDelta、19491955）。"""
    assert repair_missing_hyphens("AlphaBeta") == "Alpha-Beta"
    assert repair_missing_hyphens("GammaDelta") == "Gamma-Delta"
    assert repair_missing_hyphens("19491955") == "1949-1955"


def test_apply_corrections_print_error() -> None:
    """合成边界：排印讹误按先例修正（IDG→IDF、19487→1948）。"""
    assert apply_corrections("the IDG was active") == "the IDF was active"
    assert apply_corrections("in 19487 the war") == "in 1948 the war"


def test_strip_copyright_boilerplate() -> None:
    """合成边界：版权残句剔除。"""
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
