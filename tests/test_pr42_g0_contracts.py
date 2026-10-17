# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""PR42：脚注硬门与纯标题空对照表的消费者边界。"""

from __future__ import annotations

import pytest

from auto_translator.glossary import Glossary
from auto_translator.review import g0_unit_flags
from auto_translator.review.fidelity import fidelity_flags


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
