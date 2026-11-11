# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""PR42：脚注硬门与纯标题空对照表的消费者边界。"""

from __future__ import annotations

import pytest

from auto_translator.glossary import Glossary
from auto_translator.review import g0_unit_flags
from auto_translator.review.fidelity import fidelity_flags
from auto_translator.review.g0 import count_footnote_refs, footnote_numbers


@pytest.mark.parametrize("tail", ["........551", "…....200", "．·．.226", ".......... [431]"])
def test_toc_leader_pages_are_not_note_references(tail: str) -> None:
    source = "Глава XII " + tail
    assert count_footnote_refs(source) == 0
    assert footnote_numbers(source) == set()
    flags = g0_unit_flags([{"seq": 1, "src": source, "tgt": "第十二章"}], Glossary())
    assert not [f for f in flags if f.check in {"footnote", "footnote_suspect"}]


def test_toc_leader_does_not_exempt_real_notes_in_same_text() -> None:
    source = "Contents ........551\nIntroduction.7\nAppendix[^ref-1]"
    assert count_footnote_refs(source) == 1
    assert footnote_numbers(source) == {7}
    flags = g0_unit_flags([{"seq": 1, "src": source, "tgt": "目录\n导言\n附录"}], Glossary())
    assert any(f.check == "footnote" and f.blocking for f in flags)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ('He called it "a failure".1', "他称之为「失败」。"),
        ("He hesitated...1", "他迟疑了……"),
        ("An area of 6 km2 was cleared[^1].", "清理了6 km²的区域。"),
        ("The meeting ended.5 Fifty thousand workers arrived.", "会议已经结束。5万名工人到场。"),
    ],
    ids=["ascii-quote", "ellipsis", "mathematical-exponent", "quantity-scale"],
)
def test_real_lost_reference_is_not_compensated_by_unrelated_notation(
    source: str, target: str
) -> None:
    flags = g0_unit_flags([{"seq": 1, "src": source, "tgt": target}], Glossary())
    assert any(flag.check == "footnote" and flag.blocking for flag in flags)


def test_heading_only_translation_needs_no_body_alignment() -> None:
    flags = g0_unit_flags([], Glossary(), structured_md="# Part I\n", translation_md="# 第一部分\n")
    assert not any(flag.blocking for flag in flags)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (None, "# 第一部分\n"),
        ("", "# 第一部分\n"),
        ("# Part I\nBody immediately follows.\n", "# 第一部分\n"),
        ("# Part I\n", "# 第一部分\nUnaligned extra body.\n"),
    ],
    ids=["missing-source", "empty-source", "source-body-without-blank", "target-extra-body"],
)
def test_empty_alignment_is_not_allowed_for_unknown_or_real_body(
    source: str | None, target: str
) -> None:
    flags = g0_unit_flags([], Glossary(), structured_md=source, translation_md=target)
    assert any(flag.check == "align" and flag.blocking for flag in flags)


def test_heading_only_exception_keeps_heading_level_conservation() -> None:
    flags = g0_unit_flags(
        [], Glossary(), structured_md="# Part I\n", translation_md="## 第一部分\n"
    )
    assert any(flag.check == "heading" and flag.blocking for flag in flags)


def test_fidelity_does_not_drop_body_on_heading_continuation() -> None:
    source = "# Chapter\nBody immediately follows.\n"
    missing = fidelity_flags(source, [])
    assert any(flag.check == "fidelity" for flag in missing)
    covered = fidelity_flags(
        source, [{"seq": 1, "src": "Body immediately follows.", "tgt": "正文。"}]
    )
    assert covered == []


def test_code_heading_cannot_compensate_a_lost_real_heading() -> None:
    flags = g0_unit_flags(
        [{"seq": 1, "src": "Body.", "tgt": "正文。"}],
        Glossary(),
        structured_md="# Chapter\n\n## Real section\nBody.\n",
        translation_md="# 第一章\n\n```markdown\n## literal code\n```\n\n正文。\n",
    )
    assert any(flag.check == "heading" and flag.blocking for flag in flags)


def test_roman_chapter_page_without_leaders_is_not_a_note() -> None:
    """#89：目录单元的 `XII.551` 是罗马章节号+页码；正文的 `Text.551` 仍是注码。"""
    assert footnote_numbers("Contents XII.551", toc_like=True) == set()
    assert count_footnote_refs("Contents XII.551", toc_like=True) == 0
    assert 551 in footnote_numbers("Text.551")
    # 正文里的省略号/罗马数字序号不能按目录引导线豁免。
    assert 5 in footnote_numbers("World War II.5")
    assert 1 in footnote_numbers("He hesitated ...1")


def test_toc_kind_downgrades_footnote_gate_to_advisory() -> None:
    """#89：目录/索引单元的注号差异降 advisory，不再阻断放行。"""
    rows = [{"seq": 1, "src": "Chapter.7", "tgt": "目录"}]
    flags = g0_unit_flags(rows, Glossary(), structured_md="Chapter.7", unit_kind="toc")
    mismatch = [f for f in flags if f.check == "footnote"]
    assert mismatch and mismatch[0].blocking is False


def test_spaced_ellipsis_before_note_is_not_a_toc_leader() -> None:
    """#89：紧贴单词的三点省略号后是真注码，不是目录引导线。"""
    assert 1 in footnote_numbers("He hesitated...1")
    assert count_footnote_refs("He hesitated...1") == 1
