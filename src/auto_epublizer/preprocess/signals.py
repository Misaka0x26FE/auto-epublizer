"""结构化文本可疑信号检测（语义整备信号层；零 token 纯函数，只出信号不做判断）。

给 agent 指路「哪些单元可能有解析/OCR 缺陷」——信号是线索不是缺陷，全部为保守
计数、advisory，不进任何放行门。判读与修复由 agent 完成（`docs/semantic-repair.md`、
`references/repair.md`）。
"""

from __future__ import annotations

import re
from collections import Counter

SIGNAL_KEYS = (
    "hard_wrap_lines",
    "hyphen_eol",
    "duplicate_paras",
    "garbled_marks",
    "ascii_punct_cjk",
    "long_latin_run",
)

# 行尾强句末标点（hard_wrap 判定：段内非末行缺少它 → 疑似硬换行）
_SENTENCE_END = ("。", "！", "？", "；", "…", "!", "?", ";")
# 乱码标记：替换符 + 常见 mojibake 序列（UTF-8 被按 Latin-1/GBK 误解的典型片段）
_GARBLED_RE = re.compile(r"\ufffd|Ã[\x80-\xbf]|â€|ï¿½")
# CJK 紧邻 ASCII 引号/逗号/句号等（中西标点混用）
_ASCII_PUNCT_CJK_RE = re.compile(r"[\u4e00-\u9fff][\"',.;:!?]|[\"',.;:!?][\u4e00-\u9fff]")
# 无空格拉丁长串（OCR 粘连；≥20 字符）
_LONG_LATIN_RE = re.compile(r"[A-Za-z]{20,}")
# 行尾连字符（西文断词）
_HYPHEN_EOL_RE = re.compile(r"[A-Za-z]-$")
# 列表行（结构性块，不计硬换行）
_LIST_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
# 独立图片引用行
_IMG_ONLY = re.compile(r"^!\[[^\]]*\]\([^)]*\)$")


def _is_structural_block(lines: list[str]) -> bool:
    """结构性块（标题/列表/引文/诗行/表格/纯图片）——换行是刻意的，不计 hard_wrap。"""
    stripped = [ln.strip() for ln in lines if ln.strip()]
    if not stripped:
        return True
    if stripped[0].startswith("#"):
        return True
    if all(_LIST_LINE.match(ln) for ln in stripped):
        return True
    if all(ln.startswith(">") for ln in stripped):
        return True
    if all(ln.startswith("|") for ln in stripped):
        return True
    return len(stripped) == 1 and bool(_IMG_ONLY.match(stripped[0]))


def repair_signals(text: str) -> dict[str, int]:
    """统计一份 structured md 的可疑信号（全部为保守计数，0 = 无信号）。

    - ``hard_wrap_lines``：正文段内非末行、行尾无强句末标点——疑似解析硬换行；
    - ``hyphen_eol``：行尾連字符（西文断词）；
    - ``duplicate_paras``：完全重复的非空段落数（多余份数）；
    - ``garbled_marks``：``\\ufffd`` 与常见 mojibake 序列；
    - ``ascii_punct_cjk``：CJK 紧邻 ASCII 标点（中西标点混用）；
    - ``long_latin_run``：无空格拉丁长串（≥20 字符，OCR 粘连）。
    """
    text = text or ""
    hard_wrap = hyphen = 0
    paras: list[str] = []
    for block in re.split(r"\n\s*\n", text.strip("\n")):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if _is_structural_block(lines):
            continue
        paras.append("".join(ln.strip() for ln in lines))
        for i, line in enumerate(lines):
            body = line.rstrip()
            if i < len(lines) - 1 and not body.endswith(_SENTENCE_END):
                hard_wrap += 1
            if _HYPHEN_EOL_RE.search(body):
                hyphen += 1
    dup = sum(count - 1 for count in Counter(paras).values() if count > 1)
    return {
        "hard_wrap_lines": hard_wrap,
        "hyphen_eol": hyphen,
        "duplicate_paras": dup,
        "garbled_marks": len(_GARBLED_RE.findall(text)),
        "ascii_punct_cjk": len(_ASCII_PUNCT_CJK_RE.findall(text)),
        "long_latin_run": len(_LONG_LATIN_RE.findall(text)),
    }
