# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""源语言与体裁检测（纯函数启发式，零 token；LLM 覆盖由 analyze 阶段按需补充）。"""

from __future__ import annotations

import re

_HAN = "\u3400-\u4dbf\u4e00-\u9fff"
_HIRAGANA = "\u3040-\u309f"
_KATAKANA = "\u30a0-\u30ff"
_HANGUL = "\uac00-\ud7af"
_CYRILLIC = "\u0400-\u04ff"
_ARABIC = "\u0600-\u06ff"

_RE_HAN = re.compile(f"[{_HAN}]")
_RE_KANA = re.compile(f"[{_HIRAGANA}{_KATAKANA}]")
_RE_HANGUL = re.compile(f"[{_HANGUL}]")
_RE_CYRILLIC = re.compile(f"[{_CYRILLIC}]")
_RE_ARABIC = re.compile(f"[{_ARABIC}]")
_RE_LATIN = re.compile("[A-Za-z]")


def detect_language(text: str) -> str:
    """按脚本启发式判定源语言，返回 ISO 639-1 码；无法判定时返回 'en'。"""
    sample = text or ""
    han = len(_RE_HAN.findall(sample))
    kana = len(_RE_KANA.findall(sample))
    if han or kana:
        # 假名占比高 → 日语；否则中文
        return "ja" if kana > han * 0.1 else "zh"
    if _RE_HANGUL.search(sample):
        return "ko"
    if _RE_CYRILLIC.search(sample):
        return "ru"
    if _RE_ARABIC.search(sample):
        return "ar"
    return "en"


def detect_source_language(sample: str) -> str:
    """源语言判定策略（EPUB 元数据/翻译共用的确定性规则）。

    - 空样本 → ``und``；
    - ``detect_language`` 判 en 但样本不含拉丁字母（无法判定脚本）→ ``und``：
      诚实标注未知，不把未知脚本误标为英文（C 组：规则自 orchestrator 迁入，
      编排层只负责采样与截断）。
    """
    text = sample or ""
    if not text.strip():
        return "und"
    detected = detect_language(text)
    if detected == "en" and not _RE_LATIN.search(text):
        return "und"
    return detected


# 学术/论文体裁的强信号关键词
_ACADEMIC_MARKERS = (
    "参考文献",
    "references",
    "bibliography",
    "bibliography",
    "appendix",
    "abstract",
    "footnote",
    "citation",
    "et al.",
    "doi",
)


def detect_genre(text: str) -> str:
    """按内容启发式判定体裁，默认 novel。"""
    lowered = (text or "").lower()
    hits = sum(1 for m in _ACADEMIC_MARKERS if m in lowered)
    if hits >= 2:
        return "academic"
    # 报刊信号：大量短标题/导语
    if re.search(r"(?m)^(?:[A-Z][A-Za-z ,'-]{3,40}\n){3,}", text):
        return "newspaper"
    return "novel"
