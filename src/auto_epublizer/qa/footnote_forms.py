# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""非语义脚注形态检测（issue #37）：识别没走 ``[^label]:`` / notes.json 的注文。

现场最常见的两种写法是 ``注 1. …`` 与行首 ``[1] …``；它们会被构建器当成普通段落，
``provenance`` 只数 ``[^label]:`` 定义、``audit`` 只遍历已存在的 ``<aside>``，
于是零定义、零 aside 时两侧同为 0，**整章注文以“全绿”放行**。

本模块只做确定性候选识别，不判断内容对错，也不改写文本。调用方在
``notes_registered`` 时跳过（独立注释门负责），避免双报。
"""

from __future__ import annotations

import re
from html import unescape

from auto_common.markdown import inline_code_chunks, markdown_chunks

#: 中文标注式：``注 1.`` / ``注12：`` / ``注［3］``
_LIST_PREFIX = r"^(?:(?:[-*+]|\d{1,3}[.)])\s+)?"
_CJK_NOTE = re.compile(_LIST_PREFIX + r"注\s*[\[［（(]?\s*(\d{1,4})\s*[\]］）).、:：]?\s+\S")
#: 方括号式：``[1] 注文``（行首）
_BRACKET_NOTE = re.compile(_LIST_PREFIX + r"\[(\d{1,4})\]\s+\S")
#: 行首编号式：``1. 注文`` / ``1、注文``（需连续递增才算，见 :func:`_numbered_sequence`）
_NUMBERED_NOTE = re.compile(r"^\s*(\d{1,4})[.、]\s+\S")

_TAG = re.compile(r"<[^>]+>")
_PARA = re.compile(r"<p\b[^>]*>(.*?)</p>", re.DOTALL | re.IGNORECASE)
_CODE_BLOCK = re.compile(r"<(pre|code)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_LIST_ITEM = re.compile(r"<li\b[^>]*>(.*?)</li>", re.DOTALL | re.IGNORECASE)
_ASIDE_BLOCK = re.compile(r"<aside\b[^>]*>.*?</aside>", re.DOTALL | re.IGNORECASE)


def _cjk_or_bracket(text: str) -> bool:
    return bool(_CJK_NOTE.match(text) or _BRACKET_NOTE.match(text))


def _numbered_sequence(paragraphs: list[str]) -> set[int]:
    """连续编号且从 1 开始（步长 1）的段落索引；单项不认，避免误伤普通编号段。"""
    matched: set[int] = set()
    expected = 1
    run: list[int] = []
    for index, text in enumerate(paragraphs):
        match = _NUMBERED_NOTE.match(text)
        if match and int(match.group(1)) == expected:
            run.append(index)
            expected += 1
            continue
        if len(run) >= 2:
            matched.update(run)
        run, expected = [], 1
        if match and int(match.group(1)) == 1:
            run = [index]
            expected = 2
    if len(run) >= 2:
        matched.update(run)
    return matched


def _scan(paragraphs: list[str], *, include_numbered: bool = False) -> list[str]:
    hits = [text.strip() for text in paragraphs if _cjk_or_bracket(text)]
    if include_numbered:
        for index in sorted(_numbered_sequence(paragraphs)):
            text = paragraphs[index].strip()
            if text not in hits:
                hits.append(text)
    return hits


def candidate_footnote_paragraphs(md_text: str, *, include_numbered: bool = True) -> list[str]:
    """Markdown 中疑似非语义脚注的段落（代码围栏/行内代码内不算）。

    ``include_numbered=False`` 只返回强形态（``注 N.``/``[N]``）；构建/import
    警告用它，避免把普通有序列表当注文刷屏——连续编号的弱形态由 QA 单独
    ``W_FOOTNOTES_AMBIGUOUS`` 提示。
    """
    paragraphs: list[str] = []
    for kind, chunk in markdown_chunks(md_text):
        if kind != "text":
            continue
        visible = "".join(
            "".join("x" for _ in part) if is_code else part
            for is_code, part in inline_code_chunks(chunk)
        )
        paragraphs.extend(block.strip() for block in re.split(r"\n\s*\n", visible) if block.strip())
    return _scan(paragraphs, include_numbered=include_numbered)


def _html_paragraphs(html: str) -> list[str]:
    """正文段落 + 列表项文字（注文也可能整段落在 ``<ol><li>`` 里）。"""
    stripped = _ASIDE_BLOCK.sub("", _CODE_BLOCK.sub("", html))
    paragraphs = [
        unescape(_TAG.sub("", match.group(1))).strip() for match in _PARA.finditer(stripped)
    ]
    paragraphs.extend(
        unescape(_TAG.sub("", match.group(1))).strip() for match in _LIST_ITEM.finditer(stripped)
    )
    seen: set[str] = set()
    out: list[str] = []
    for text in paragraphs:
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def candidate_footnotes_in_html(html: str) -> list[str]:
    """成品 XHTML 中**强形态**非语义脚注（``注 N.`` / ``[N]``；列表与代码不算）。"""
    return _scan(_html_paragraphs(html))


def candidate_numbered_in_html(html: str) -> list[str]:
    """仅连续编号段（弱形态）：可能是有序列表，调用方只能记 warning。"""
    return _scan(_html_paragraphs(html), include_numbered=True)
