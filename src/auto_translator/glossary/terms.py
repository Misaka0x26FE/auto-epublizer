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
    """术语的正文匹配模式：CJK 术语用字面匹配，非 CJK 术语加**Unicode 词边界**。

    ``\\w`` 在 Python 的 str 模式下涵盖西里尔/希腊等字母与数字，故 ``СС`` 不会命中
    ``СССР``/``АССР`` 内部（回归：曾用 ``[A-Za-z0-9]`` 作边界，俄文术语大量误报）。

    但 ``\\w`` **也包含 CJK 表意文字**：中文译文里保留拉丁的术语（如 ``NATO成员国``）
    会被误判为「无边界」而报缺失，故对 CJK 单独放行——CJK 术语本就走字面分支，
    这里把 CJK 视为合法边界。
    """
    escaped = re.escape(source)
    if re.search(f"[{_CJK}]", source):
        return re.compile(escaped)
    return re.compile(
        r"(?:(?<=[" + _CJK + r"])|(?<!\w))" + escaped + r"(?:(?=[" + _CJK + r"])|(?!\w))"
    )


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


# 可省略的结构助词（仅用于术语命中的形态容错）
_CJK_PARTICLES = "的地得"


def _target_forms(target: str) -> list[str]:
    """target 的可接受形态：原形 + 去尾部结构助词（的/地/得）的构词形。

    中文术语表常把定语形式写进 target（`犹太-共济会的`、`反锡安主义的`），而正文里
    作定语时不带「的」（`犹太-共济会三角形`、`反锡安主义反共济会阵线`）。现场报告
    #8 中 6 处硬缺陷全部来自这一形态差：译文是对的，却只能靠改术语表才能放行。
    """
    forms = [target]
    if len(target) > 1 and target[-1] in _CJK_PARTICLES:
        forms.append(target[:-1])
    return forms


def terminology_hits(src: str, tgt: str, glossary: Glossary) -> list[TerminologyHit]:
    """源句出现术语 source（或其别名），译文缺失对应 target 时报违例（G0 术语命中）。

    source/alias/target 与正文一致做 NFKC 归一化后比较（回归 issue #4：
    target 含全角括号时与归一化后的译文形式不一致，曾全部误报）。
    target 以结构助词结尾时，同时接受去助词的构词形（回归 #8）。
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
        # 译文须含确认译法（按词边界，允许去尾部结构助词的构词形）；缺失即违例
        if not any(_boundary_pattern(f).search(tgt_norm) for f in _target_forms(target)):
            hits.append(TerminologyHit(source=entry.source, expected=entry.target, found=None))
    return hits
