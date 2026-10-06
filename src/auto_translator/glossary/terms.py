# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""术语注入过滤与命中检查（纯函数）。

- ``terms_in_text``：返回正文实际出现的术语子集（NFKC 归一化 + 词边界），用于批级注入。
- ``terminology_hits``：正文出现术语 source 但译文缺失对应 target 时报违例（G0 术语命中）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .csv_io import Glossary, GlossaryEntry, normalize

_CJK = "\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af"

# 连字符族：英语里连字符接起来的是**一个**正字法 token，因此 ``Brest`` 不应命中
# ``Brest-Litovsk`` 内部（该复合地名另有词条，译文形态不同）。若把 ``-`` 当成合法
# 边界，短词条就会被长复合词条抢先命中，报出「术语命中译文缺失」这种无法靠改译文
# 放行的假阳性（2026-10-06 于 ch08 的 ``Brest`` / ``Brest–Litovsk`` 词条对撞）。
# 代价是 ``NATO-members`` 这类前缀复合体不再触发——方向上是安全的假阴性。
#
# ⚠ **中文破折号 `——`（em dash 连写两个）必须放行**（2026-10-07 于 hans-frank /
# forced-labour）：中文破折号紧跟术语是常态，
#     `DAP——NSDAP 的前身`   /   `巴尔——德国法学会会长`
# 若 em dash 一律算词内连接符，左边界就认为「前一个字还在词内」，
# 于是术语**命中不了译文**，报出「术语 NSDAP 译文缺失 NSDAP」这种**自相矛盾**的告警，
# 而且**改译文也放行不了**（换别的标点只会制造新的不一致）。
# 单个 em dash（`Brest—Litovsk`）仍按词内连接符处理，与 2026-10-06 的
# 连字符族口径一致；用定长负向后顾 `(?<!——)` 把「连写两个」单独放行即可
# （Python `re` 的后顾必须定长，`——` 正好是 2 字符）。
_HYPHENS = "\\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
_CJK_DASH = "——"      # 中文破折号 = 两个 em dash 连写


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
    edge = r"[\w" + _HYPHENS + r"]"
    dash = re.escape(_CJK_DASH)
    return re.compile(
        r"(?:(?<=[" + _CJK + r"])|(?<=" + dash + r")|(?<!" + edge + r"))"
        + escaped
        + r"(?:(?=[" + _CJK + r"])|(?=" + dash + r")|(?!" + edge + r"))"
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
