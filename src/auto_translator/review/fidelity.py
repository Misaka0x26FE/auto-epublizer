"""源保真校验（fidelity）：align 的 src 侧与 structured 原文的双向绑定。

对照表的 ``src`` 由 agent 手写摘抄——没有任何校验时，译文可能针对被改写/截断/
杜撰的「源」作答而不可见。本模块提供纯函数双向比对（块级、去空白）：

- **前向**（漏抄/漏译）：structured 的每个正文块都应能在 align src 拼接中找到；
  找不到 → 缺块（可能是合法剔除——版权残句/页眉残留，advisory）。
- **反向**（抄错/改写/杜撰）：align 每行的 src 都应能在 structured 全部非空行
  （含标题行）中找到；找不到 → src 不可信（硬缺陷，import 阻断）。

匹配语义：块级拼接子串匹配天然容忍拆句/并句/句序调整；勘误先例**只改 tgt**
并以 note ``corr:`` 前缀留痕（``g0.annotate_correction_notes`` 契约：不改 src/tgt
文本），src 被「顺手修正」会被反向检查抓出——这正是要抓的。

provenance 的逐段覆盖率与本模块共用同一套归一化/切块原语（单一实现防漂移）。
"""

from __future__ import annotations

import re
from typing import Any

from .g0 import G0Flag

# 纯 HTML 注释块（前向切块时跳过；正文中的注释残留由 G4 E_RESIDUE 管）
_COMMENT_BLOCK = re.compile(r"^\s*<!--.*-->\s*$", re.DOTALL)


def norm_text(text: str) -> str:
    """归一化：去除全部空白字符（块级/行级匹配统一用）。"""
    return re.sub(r"\s+", "", text or "")


def content_blocks(structured_md: str) -> list[str]:
    """structured md 的正文块：按空行切，跳标题行（# 开头）、空块、纯注释块。"""
    out: list[str] = []
    for block in re.split(r"\n\s*\n", (structured_md or "").strip("\n")):
        block = block.strip()
        if not block or block.startswith("#") or _COMMENT_BLOCK.match(block):
            continue
        out.append(block)
    return out


def all_lines(structured_md: str) -> list[str]:
    """全部非空行（含标题行）——反向匹配语料（agent 可把标题作为首行 src）。"""
    return [ln.strip() for ln in (structured_md or "").splitlines() if ln.strip()]


def fidelity_flags(structured_md: str, rows: list[dict[str, Any]]) -> list[G0Flag]:
    """双向源保真检查（块级）。

    前向缺块 → ``G0Flag("fidelity", "源文块未进对照表", ...)``（advisory 语义）；
    反向失配 → ``G0Flag("fidelity", "对照表 src 不在源文中（疑抄错/改写）", ...)``
    （硬缺陷语义，import 阻断）。
    """
    flags: list[G0Flag] = []
    src_concat = norm_text("".join(r.get("src") or "" for r in rows))
    for i, block in enumerate(content_blocks(structured_md), start=1):
        if norm_text(block) not in src_concat:
            flags.append(
                G0Flag(
                    "fidelity",
                    "源文块未进对照表",
                    {"block": i, "head": block[:40]},
                )
            )
    source_norm = norm_text("".join(all_lines(structured_md)))
    for r in rows:
        src = r.get("src") or ""
        if norm_text(src) not in source_norm:
            flags.append(
                G0Flag(
                    "fidelity",
                    "对照表 src 不在源文中（疑抄错/改写）",
                    {"seq": r.get("seq"), "head": src[:40]},
                )
            )
    return flags
