# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""渲染、静态核对和媒体扫描共用的 Markdown 代码上下文。"""

from __future__ import annotations

import re

CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.*?)(?<!`)\1(?!`)", re.DOTALL)
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\n]*)$")


def inline_code_chunks(text: str) -> list[tuple[bool, str]]:
    """保留代码跨度的原始分隔符；显式 pandoc raw 标记不属于显示代码。"""
    chunks: list[tuple[bool, str]] = []
    previous = 0
    for match in CODE_SPAN_RE.finditer(text):
        if re.match(r"\s*\{\s*=\s*html\s*\}", text[match.end() :]):
            continue
        chunks.append((False, text[previous : match.start()]))
        chunks.append((True, match.group(0)))
        previous = match.end()
    chunks.append((False, text[previous:]))
    return chunks


def fence_info(line: str) -> tuple[str, str] | None:
    """读取合法围栏的分隔符与 info string。"""
    match = _FENCE_OPEN.match(line.rstrip("\r\n"))
    if not match or (match[1].startswith("`") and "`" in match[2]):
        return None
    return match[1], match[2].strip()


def _closes_fence(line: str, fence: str) -> bool:
    stripped = line.rstrip("\r\n").lstrip(" ")
    return (
        len(line.rstrip("\r\n")) - len(stripped) <= 3
        and len(stripped.rstrip(" \t")) >= len(fence)
        and set(stripped.rstrip(" \t")) == {fence[0]}
    )


def markdown_chunks(md: str) -> list[tuple[str, str]]:
    """保留原始布局，按围栏上下文区分 text / code / 显式 pandoc raw。"""
    chunks: list[tuple[str, str]] = []
    lines: list[str] = []
    fence: str | None = None
    kind = "text"
    for line in md.splitlines(keepends=True):
        if fence is not None:
            lines.append(line)
            if _closes_fence(line, fence):
                chunks.append((kind, "".join(lines)))
                lines = []
                fence = None
                kind = "text"
            continue
        opening = fence_info(line)
        if opening is not None:
            if lines:
                chunks.append(("text", "".join(lines)))
            fence, info = opening
            kind = "raw" if re.fullmatch(r"\{=\s*html\s*\}", info) else "code"
            lines = [line]
        else:
            lines.append(line)
    if lines:
        chunks.append((kind, "".join(lines)))
    return chunks


def fence_body(block: str) -> str:
    """去掉开/闭围栏；未闭合围栏按 Markdown 规则延续至文末。"""
    lines = block.splitlines(keepends=True)
    opening = fence_info(lines[0])
    assert opening is not None
    if len(lines) > 1 and _closes_fence(lines[-1], opening[0]):
        return "".join(lines[1:-1])
    return "".join(lines[1:])


def paragraph_blocks(markdown: str) -> list[str]:
    """文本按空行切段；普通代码和显式 raw 围栏始终作为完整一段。"""
    blocks: list[str] = []
    for kind, chunk in markdown_chunks(markdown):
        parts = re.split(r"\n\s*\n", chunk) if kind == "text" else [chunk]
        blocks.extend(part.strip("\n") for part in parts if part.strip())
    return blocks
