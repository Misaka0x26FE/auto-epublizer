# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""Pandoc JSON AST 试点：为复杂 DOCX/HTML 导入提供独立的结构对账。

工作区仍然以 ``pandoc -t markdown`` 的 Markdown 为可编辑真相（agent 要能读、能改），
AST **不替代** Markdown，只在导入时多跑一次 ``-t json``：

- 取标题层级与块序列，核对 Markdown 分单元没有吞段、并段或重复段落少一份；
- 结果写入 ``SourceDocument.meta["ast_check"]``，由 ``write_structured`` 落到
  ``structured/raw/pandoc-ast-check.json``（工作区可审计），agent 可据此判断是否需要
  ``preprocess --force`` 重建或逐块修复。

边界：这是**文本覆盖探针**，不是结构验证。它按源序消费 AST 的可见词序列，只回答
「这一块的文字是否还在工作区里、且顺序没被打乱」；不校验标题层级、段落边界或块顺序，
因此「正文被误判成标题」只要文字仍在就不会报出。

试点默认关闭（``pandoc.ast_check: true`` 打开）：多一次 pandoc 进程，长文档有成本。
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .models import SourceUnit
from .pandoc_reader import PandocError, pandoc_available


def run_pandoc_ast(path: str | Path) -> dict[str, Any]:
    """调用 pandoc 输出 JSON AST（同一 cwd 规则，保证相对资源可解析）。"""
    if not pandoc_available():
        raise PandocError("未找到 pandoc；请安装 pandoc 或先把文件转为 PDF/TXT/Markdown")
    abs_path = Path(path).resolve()
    try:
        proc = subprocess.run(
            ["pandoc", str(abs_path), "-t", "json", "--wrap=none"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            cwd=abs_path.parent,
        )
    except OSError as e:
        raise PandocError(f"pandoc 执行失败：{e}") from e
    if proc.returncode != 0:
        raise PandocError(f"pandoc AST 处理失败：{proc.stderr.strip()[:300]}")
    try:
        ast = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise PandocError(f"pandoc AST 输出不是合法 JSON：{e}") from e
    if not isinstance(ast, dict) or not isinstance(ast.get("blocks"), list):
        raise PandocError("pandoc AST 缺少 blocks 数组")
    return ast


# 部分 inline 容器的 ``c`` 是 [属性/引号类型, inlines, …]，可见文字在其中一项；
# 强调类容器的 ``c`` 直接就是 inlines 列表。``None`` 表示取整个 c。
_INLINE_PAYLOAD: dict[str, int | None] = {
    "Emph": None,
    "Underline": None,
    "Strong": None,
    "Strikeout": None,
    "Superscript": None,
    "Subscript": None,
    "SmallCaps": None,
    "Quoted": 1,
    "Link": 1,
    "Span": 1,
    "Image": 1,
    "Cite": 1,
}


def inline_list(nodes: Any) -> str:
    if not isinstance(nodes, list):
        return ""
    return "".join(inline_text(node) for node in nodes)


def inline_text(node: Any) -> str:
    """把 inline AST 归约为可见文本（保留文字、代码与链接标签，丢弃格式标记）。"""
    if not isinstance(node, dict):
        return ""
    kind = node.get("t")
    value = node.get("c")
    if kind == "Str":
        return str(value) if isinstance(value, str) else ""
    if kind in {"Space", "SoftBreak", "LineBreak"}:
        return " "
    if kind == "Code":
        # [attr, text]：代码文字原样保留。
        return str(value[1]) if isinstance(value, list) and len(value) > 1 else ""
    if kind in {"Math", "RawInline", "Note"}:
        return ""
    if kind not in _INLINE_PAYLOAD or not isinstance(value, list):
        return ""
    index = _INLINE_PAYLOAD[str(kind)]
    if index is None:
        return inline_list(value)
    return inline_list(value[index]) if index < len(value) else ""


def ast_blocks(ast: dict[str, Any]) -> list[dict[str, Any]]:
    """把 AST 拍平成 (kind, level, text) 顺序块，用于与 Markdown 分单元对账。"""
    blocks: list[dict[str, Any]] = []

    def walk(items: Any) -> None:
        for block in items if isinstance(items, list) else []:
            if not isinstance(block, dict):
                continue
            kind = block.get("t")
            value = block.get("c")
            if kind == "Header":
                blocks.append(
                    {
                        "kind": "heading",
                        "level": int(value[0]) if isinstance(value, list) else 1,
                        "text": inline_list(value[2]) if isinstance(value, list) else "",
                    }
                )
            elif kind in {"Para", "Plain"}:
                blocks.append({"kind": "paragraph", "level": 0, "text": inline_list(value)})
            elif kind == "CodeBlock":
                blocks.append({"kind": "code", "level": 0, "text": str(value[1])})
            elif kind in {"BulletList", "OrderedList"}:
                items_value = value[1] if kind == "OrderedList" and len(value) > 1 else value
                for item in items_value if isinstance(items_value, list) else []:
                    walk(item)
            elif kind == "Div":
                # Div 的 c 是 [属性, blocks]：正文在第二项；遍历属性表等于整段隐身。
                walk(value[1] if isinstance(value, list) and len(value) > 1 else value)
            elif kind == "BlockQuote":
                walk(value)
            elif kind == "Table":
                blocks.append({"kind": "table", "level": 0, "text": ""})
            elif kind == "Figure":
                blocks.append({"kind": "figure", "level": 0, "text": ""})

    walk(ast.get("blocks"))
    return [b for b in blocks if b["kind"] in {"heading", "paragraph", "code"}]


_WORD = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text)


def _match_end(haystack: list[str], needle: list[str], start: int = 0) -> int | None:
    """needle 是否为 haystack[start:] 的有序子序列；返回匹配结束后的位置。

    按源序**消费**词序列：同一段落出现两次时，第二次必须消费到新的词，不能复用第一次
    已匹配的词（否则「整段被吞一次」会被误判为通过）。
    """
    if not needle:
        return start
    pos = start
    for token in needle:
        try:
            pos = haystack.index(token, pos) + 1
        except ValueError:
            return None
    return pos


def compare_with_units(ast: dict[str, Any], units: list[SourceUnit]) -> dict[str, Any]:
    """AST 与 Markdown 分单元对账：块计数与丢失块。

    比较按**词序列**而非字面串：Markdown 工作区保留 ``**强调**``/``*斜体*`` 标记，
    字面比较会把带格式的段落误判为丢失；按源序消费的子序列检查能发现整段被吞、被并、
    重复段落少了一份，又不挑剔标记写法。

    这是**文本覆盖探针**，不是结构验证：它不校验标题层级、段落边界或块顺序是否与 AST
    一致，也不能证明「正文被误判成标题」——那种缺陷只要文字仍在工作区就不会被报出。
    """
    blocks = ast_blocks(ast)
    expected = [b for b in blocks if _tokens(b["text"])]
    actual_words = [
        word for unit in units for segment in unit.segments for word in _tokens(segment.source)
    ]
    missing: list[dict[str, Any]] = []
    cursor = 0
    for block in expected:
        end = _match_end(actual_words, _tokens(block["text"]), cursor)
        if end is None:
            missing.append(block)
        else:
            cursor = end
    return {
        "headings": sum(1 for b in blocks if b["kind"] == "heading"),
        "paragraphs": sum(1 for b in blocks if b["kind"] == "paragraph"),
        "missing": missing[:20],
        "missing_count": len(missing),
    }


def ast_check(path: str | Path, units: list[SourceUnit]) -> dict[str, Any]:
    """运行试点对账；结果只记录，不阻断导入（缺口由 agent 判断修复）。"""
    return compare_with_units(run_pandoc_ast(path), units)
