"""术语注入过滤与命中检查（纯函数）。

- ``terms_in_text``：返回正文实际出现的术语子集（NFKC 归一化 + 词边界），用于批级注入。
- ``terminology_hits``：正文出现术语 source 但译文缺失对应 target 时报违例（G0 术语命中）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .csv_io import Glossary, GlossaryEntry, normalize

_CJK = "\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af"


def _boundary_pattern(source: str) -> re.Pattern[str]:
    """术语的正文匹配模式：CJK 术语用字面匹配，拉丁术语加词边界。"""
    escaped = re.escape(source)
    if re.search(f"[{_CJK}]", source):
        return re.compile(escaped)
    return re.compile(r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])")


@dataclass(frozen=True)
class TerminologyHit:
    source: str
    expected: str
    found: str | None


def terms_in_text(text: str, glossary: Glossary) -> list[GlossaryEntry]:
    """返回正文实际出现的术语条目（含 source 与别名命中）。

    source/alias 与正文一致做 NFKC 归一化后匹配（回归 issue #4：术语含全角
    括号、正文为半角形式时曾漏命中）。
    """
    normalized = normalize(text)
    if not normalized:
        return []
    seen: dict[str, GlossaryEntry] = {}
    for entry in glossary.entries():
        for candidate in [entry.source, *entry.aliases]:
            candidate = normalize(candidate)
            if not candidate:
                continue
            if _boundary_pattern(candidate).search(normalized):
                seen.setdefault(entry.source, entry)
    return list(seen.values())


def terminology_hits(src: str, tgt: str, glossary: Glossary) -> list[TerminologyHit]:
    """源句出现术语 source（或其别名），译文缺失对应 target 时报违例（G0 术语命中）。

    source/alias/target 与正文一致做 NFKC 归一化后比较（回归 issue #4：
    target 含全角括号时与归一化后的译文形式不一致，曾全部误报）。
    """
    src_norm = normalize(src)
    tgt_norm = normalize(tgt)
    if not src_norm or not tgt_norm:
        return []
    hits: list[TerminologyHit] = []
    seen: set[str] = set()
    for entry in glossary.entries():
        if entry.source in seen:
            continue
        target = normalize(entry.target)
        if not target:
            continue
        candidates = [c for c in (normalize(x) for x in [entry.source, *entry.aliases]) if c]
        matched = any(_boundary_pattern(c).search(src_norm) for c in candidates)
        if not matched:
            continue
        seen.add(entry.source)
        # 译文须含确认译法（按词边界）；缺失即违例
        if not _boundary_pattern(target).search(tgt_norm):
            hits.append(TerminologyHit(source=entry.source, expected=entry.target, found=None))
    return hits
