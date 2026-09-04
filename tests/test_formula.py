"""公式检测测试：符号/字体/独立行三路特征（docs/pdf-content-spec.md §5）。"""

from __future__ import annotations

from auto_epublizer.ingest.formula import (
    count_math_chars,
    is_formula_block,
    is_formula_text,
    is_math_font,
)
from auto_epublizer.ingest.pdf_reader import _CHAPTER_KEYWORD as _RE


def test_count_math_chars_and_symbols() -> None:
    assert count_math_chars("2 × 3 ± 4") == 2
    assert count_math_chars("alpha β γ") == 2
    assert count_math_chars("plain text") == 0


def test_formula_text_symbol_feature() -> None:
    assert is_formula_text("x = a ± b × c")
    assert is_formula_text("∑x + ∫y")
    assert not is_formula_text("plain sentence without math.")
    assert not is_formula_text("×")  # 单符号不命中
    assert not is_formula_text("× " * 120)  # 超长不命中（>200 字）


def test_math_font_names() -> None:
    assert is_math_font("CMMI12")
    assert is_math_font("CMSY10")
    assert is_math_font("CMEX10")
    assert is_math_font("NimbusRomNo9L-Math")
    assert is_math_font("Symbol")
    # CMR 是 TeX 正文默认字体，不是数学字体
    assert not is_math_font("CMR10")
    assert not is_math_font("Helvetica")
    assert not is_math_font(None)


def test_formula_block_font_feature() -> None:
    block = {"type": "text", "text": "anything", "bbox": [0, 0, 100, 20], "math_font": "CMMI12"}
    assert is_formula_block(block, page_width=612, chapter_re=_RE)


def test_formula_block_chapter_title_excluded() -> None:
    block = {"type": "text", "text": "第一章 开始", "bbox": [0, 0, 100, 20]}
    assert not is_formula_block(block, page_width=612, chapter_re=_RE)


def test_formula_block_isolated_centered_short_math() -> None:
    # 居中、短、句末无标点、含数学符号
    block = {
        "type": "text",
        "text": "a2 + b2 = c2 × 2",
        "bbox": [256, 400, 356, 420],
    }
    assert is_formula_block(block, page_width=612, chapter_re=_RE)


def test_formula_block_centered_caption_not_formula() -> None:
    # 句末有标点的居中说明文字 → 非公式
    block = {
        "type": "text",
        "text": "Figure 2: growth × speed.",
        "bbox": [236, 400, 376, 420],
    }
    assert not is_formula_block(block, page_width=612, chapter_re=_RE)


def test_formula_block_ignores_non_text() -> None:
    assert not is_formula_block({"type": "image", "text": "±×"}, page_width=612)
