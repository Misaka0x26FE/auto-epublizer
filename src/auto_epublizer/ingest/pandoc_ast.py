# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""Pandoc JSON AST 试点：为复杂 DOCX/HTML 导入提供独立的结构对账。

工作区仍然以 ``pandoc -t markdown`` 的 Markdown 为可编辑真相（agent 要能读、能改），
AST **不替代** Markdown，只在导入时多跑一次 ``-t json``：

- 取标题层级与块序列，核对 Markdown 分单元没有吞段、并段或把正文误判成标题；
- 结果写入 ``SourceDocument.meta["ast_check"]``，agent/审计可据此判断是否需要
  ``preprocess --force`` 重建或逐块修复。

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
            elif kind in {"BlockQuote", "Div"}:
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


def _contains_in_order(haystack: list[str], needle: list[str]) -> bool:
    """needle 是否为 haystack 的有序子序列（对 Markdown 强调标记不敏感）。"""
    if not needle:
        return True
    it = iter(haystack)
    return all(token in it for token in needle)


def compare_with_units(ast: dict[str, Any], units: list[SourceUnit]) -> dict[str, Any]:
    """AST 与 Markdown 分单元对账：块计数与丢失块。

    比较按**词序列**而非字面串：Markdown 工作区保留 ``**强调**``/``*斜体*`` 标记，
    字面比较会把带格式的段落误判为丢失；词序列子序列检查能发现整段被吞、被并、
    或标题被当成正文，又不挑剔标记写法。
    """
    blocks = ast_blocks(ast)
    expected = [b for b in blocks if _tokens(b["text"])]
    actual_words = [
        word for unit in units for segment in unit.segments for word in _tokens(segment.source)
    ]
    missing = [b for b in expected if not _contains_in_order(actual_words, _tokens(b["text"]))]
    return {
        "headings": sum(1 for b in blocks if b["kind"] == "heading"),
        "paragraphs": sum(1 for b in blocks if b["kind"] == "paragraph"),
        "missing": missing[:20],
        "missing_count": len(missing),
    }


def ast_check(path: str | Path, units: list[SourceUnit]) -> dict[str, Any]:
    """运行试点对账；结果只记录，不阻断导入（缺口由 agent 判断修复）。"""
    return compare_with_units(run_pandoc_ast(path), units)
