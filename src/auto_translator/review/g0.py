"""G0 零 token 静态校验（纯函数，翻译后立即、离线、确定性）。

输入来自 ``translation/align/<id>.jsonl``、``structured/<id>.md`` 与 ``analysis/glossary.csv``。
G0 不烧 token、不出"裁决"，只出确定性告警，作为 G1 的输入线索。

历史实践提炼（docs/quality-lessons.md + 旧真实案例）：
- 插入元素标记数量守恒（``{fig:NNN}`` 32/32）；
- 注码/脚注引用守恒（1:1）；
- h1/h2 层级数量与源文一致；
- 段落块数量 1:1（允许页断残句合并的合理差异）；
- 断字符修复（IsraelEgypt→Israel-Egypt、BenGurion→Ben-Gurion、19491955→1949-1955）；
- 排印讹误按先例修正（IDG→IDF、19487→1948）；
- 标点规范化（«»→《》、""→「」、...→…）；
- 术语命中（glossary source 出现时译文须含 target）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..glossary import Glossary, terminology_hits

# 插入元素标记，如 {fig:NNN}、{table:NNN}
_MARKER_RE = re.compile(r"\{\w+:\d+\}")

# 近似脚注注码：句末标点后紧跟 1~3 位数字（排除小数如 3.14）
_FOOTNOTE_REF_RE = re.compile(r"(?<!\d)[.!?…，。；：](\d{1,3})(?!\d)")

_HEADING_RE = re.compile(r"^(#{1,6})\s+", re.MULTILINE)

# 常见排印讹误先例（源文勘误，来自旧真实案例）
_DEFAULT_CORRECTIONS: dict[str, str] = {
    "IDG": "IDF",
    "19487": "1948",
    "67 December": "6-7 December",
}

# OUP 等版权残句特征（构建/审校时统一剔除）
_COPYRIGHT_MARKERS = (
    "All rights reserved",
    "First published",
    "Printed in",
    "Library of Congress Cataloging",
    "British Library Cataloguing",
)


@dataclass(frozen=True)
class G0Flag:
    """一条确定性告警。"""

    check: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


def count_markers(text: str, pattern: re.Pattern[str] = _MARKER_RE) -> int:
    """统计插入元素标记（{fig:NNN} 等）数量。"""
    return len(pattern.findall(text or ""))


def markers_conserved(src: str, tgt: str, pattern: re.Pattern[str] = _MARKER_RE) -> bool:
    """标记数量守恒：源与译的标记数一致。"""
    return count_markers(src, pattern) == count_markers(tgt, pattern)


def count_footnote_refs(text: str) -> int:
    """统计句末注码（脚注引用）数量。"""
    return len(_FOOTNOTE_REF_RE.findall(text or ""))


def count_heading_levels(text: str) -> dict[int, int]:
    """统计各标题层级（h1~h6）数量。"""
    levels: dict[int, int] = {}
    for m in _HEADING_RE.finditer(text or ""):
        level = len(m.group(1))
        levels[level] = levels.get(level, 0) + 1
    return levels


def count_paragraph_blocks(text: str) -> int:
    """统计段落块数量（按空行分隔）。"""
    parts = re.split(r"\n\s*\n", (text or "").strip("\n"))
    return len([p for p in parts if p.strip()])


def length_ratio(src: str, tgt: str) -> float:
    """译文/源文长度比；空源文返回 0。"""
    s = len((src or "").strip())
    if s == 0:
        return 0.0
    return len((tgt or "").strip()) / s


def repair_missing_hyphens(text: str) -> str:
    """修复缺失的连字符/连接号（IsraelEgypt→Israel-Egypt、19491955→1949-1955 等）。

    规则：两个字母之间、或相邻两段 4 位年份之间缺连字符时补上。
    """
    out = text or ""
    # 字母-字母：IsraelEgypt / BenGurion
    out = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", "-", out)
    # 年份粘连：19491955 → 1949-1955
    out = re.sub(r"(?<=\d{4})(?=\d{4})", "-", out)
    return out


def apply_corrections(text: str, corrections: dict[str, str] | None = None) -> str:
    """按先例修正排印讹误（IDG→IDF 等），返回 (修正后文本, 命中的修正项)。"""
    mapping = {**(_DEFAULT_CORRECTIONS if corrections is None else corrections)}
    out = text or ""
    for wrong, right in mapping.items():
        out = out.replace(wrong, right)
    return out


def strip_copyright_boilerplate(lines: list[str]) -> list[str]:
    """剔除版权残句（从含版权特征的连续块开始截断到末尾）。"""
    text = "\n".join(lines)
    for marker in _COPYRIGHT_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            # 截断自该版权块起始行
            head = text[:idx].rstrip("\n")
            return head.split("\n") if head else []
    return lines


def normalize_punctuation(text: str, lang: str = "zh-CN") -> str:
    """标点规范化：«»→《》、""→「」、...→…（纯函数，目标语言为中文时）。"""
    t = (text or "").replace("«", "《").replace("»", "》").replace("...", "…")
    if lang not in ("zh-CN", "zh-TW", "ja"):
        return t
    out: list[str] = []
    open_stack: list[str] = []
    for ch in t:
        if ch == '"':
            if open_stack:
                out.append(open_stack.pop())
            else:
                open_stack.append("」")
                out.append("「")
        else:
            out.append(ch)
    while open_stack:
        out.append(open_stack.pop())
    return "".join(out)


def check_alignment(rows: list[dict[str, Any]]) -> list[G0Flag]:
    """对照表完整性：seq 连续 1..N 无缺号无重复、每行 src/tgt 非空。"""
    flags: list[G0Flag] = []
    seqs = [r.get("seq") for r in rows]
    if not seqs:
        flags.append(G0Flag("align", "对照表为空"))
        return flags
    if seqs != list(range(1, len(rows) + 1)):
        flags.append(G0Flag("align", "seq 不连续", {"seqs": seqs}))
    empty_src = [r["seq"] for r in rows if not (r.get("src") or "").strip()]
    empty_tgt = [r["seq"] for r in rows if not (r.get("tgt") or "").strip()]
    if empty_src:
        flags.append(G0Flag("align", "存在空原文", {"seq": empty_src}))
    if empty_tgt:
        flags.append(G0Flag("align", "存在空译文", {"seq": empty_tgt}))
    return flags


def g0_unit_flags(
    rows: list[dict[str, Any]],
    glossary: Glossary,
    *,
    too_short: float = 0.30,
    too_long: float = 3.0,
) -> list[G0Flag]:
    """对一个单元执行全部 G0 检查，返回告警列表。"""
    flags = list(check_alignment(rows))
    for r in rows:
        src = r.get("src") or ""
        tgt = r.get("tgt") or ""
        seq = r.get("seq")
        ratio = length_ratio(src, tgt)
        if not tgt.strip():
            flags.append(G0Flag("length", "译文为空", {"seq": seq}))
        elif ratio < too_short:
            flags.append(G0Flag("length", "长度比过低（疑漏译）", {"seq": seq, "ratio": ratio}))
        elif ratio > too_long:
            flags.append(G0Flag("length", "长度比过高（疑失控）", {"seq": seq, "ratio": ratio}))
        for hit in terminology_hits(src, tgt, glossary):
            flags.append(
                G0Flag(
                    "terminology",
                    f"术语 {hit.source} 译文缺失 {hit.expected}",
                    {"seq": seq, "source": hit.source, "expected": hit.expected},
                )
            )
    return flags
