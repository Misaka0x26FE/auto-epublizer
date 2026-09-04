"""公式检测（确定性特征，docs/pdf-content-spec.md §5）。

三路特征任一命中即标记 type=formula：
1. 符号特征：短文本（≤200 字）且含 ≥2 个数学符号（含希腊/数学字母区）；
2. 字体特征：span 字体名含数学字体（Math / CMMI / CMSY / CMEX / Symbol）；
3. 独立行特征：单独成块、水平居中、短、无句末标点，且含 ≥1 个数学符号。

LaTeX 由 agent 手写（inserts 记录 latex 字段）；CLI 不调 LLM、不产出候选。
注意：CMR（Computer Modern Roman）是 TeX 正文默认字体，**不**作为数学字体，
否则纯 TeX 排版的书全篇误判。
"""

from __future__ import annotations

import re
from typing import Any

_MATH_CHARS = set("∫∑∏√∂∇∓±×÷¬≈≡≤≥∞∈∉∋∀∃·…°′″ℓ℘ℑℜ")
_GREEK_RE = re.compile(r"[\u0370-\u03ff\u2100-\u214f\U0001d400-\U0001d7ff]")
_MATH_FONT_RE = re.compile(r"Math|CMMI|CMSY|CMEX|Symbol", re.IGNORECASE)
_CHAPTER_PREFIX_RE = re.compile(
    r"第[0-9０-９一二三四五六七八九十百千]+[章話话节節回部巻卷]|Chapter\s+\d+",
    re.IGNORECASE,
)
_NO_END_PUNCT = "。．.!?！？；;，,：:"

MAX_FORMULA_TEXT = 200
MAX_ISOLATED_TEXT = 120
CENTER_TOLERANCE = 0.12  # 水平中心偏离页中心 ≤ 12% 页宽视为居中


def count_math_chars(text: str) -> int:
    """数学符号计数（数学字符 + 希腊/字母符号区命中数）。"""
    return sum(1 for ch in text if ch in _MATH_CHARS) + len(_GREEK_RE.findall(text))


def is_math_font(name: str | None) -> bool:
    """字体名是否为数学字体（CMR 除外）。"""
    return bool(name) and bool(_MATH_FONT_RE.search(name))


def is_formula_text(text: str) -> bool:
    """符号特征：短文本且含 ≥2 个数学符号。"""
    if not text or len(text) > MAX_FORMULA_TEXT:
        return False
    return count_math_chars(text) >= 2


def is_formula_block(
    block: dict[str, Any],
    *,
    page_width: float | None = None,
    chapter_re: re.Pattern[str] = _CHAPTER_PREFIX_RE,
) -> bool:
    """文本块是否为公式（三路特征任一命中；章节标题排除）。"""
    if block.get("type") != "text":
        return False
    text = (block.get("text") or "").strip()
    if not text or chapter_re.search(text):
        return False
    if is_math_font(block.get("math_font")):
        return True
    if is_formula_text(text):
        return True
    return _is_isolated_centered(block, page_width, text)


def _is_isolated_centered(block: dict[str, Any], page_width: float | None, text: str) -> bool:
    """独立行特征：单独成块、居中、短、句末无标点，且含 ≥1 个数学符号。"""
    if page_width is None or len(text) > MAX_ISOLATED_TEXT:
        return False
    if text[-1] in _NO_END_PUNCT:
        return False
    if count_math_chars(text) < 1:
        return False
    bbox = block.get("bbox")
    if not bbox or len(bbox) != 4:
        return False
    center = (float(bbox[0]) + float(bbox[2])) / 2
    return abs(center - page_width / 2) <= CENTER_TOLERANCE * page_width
