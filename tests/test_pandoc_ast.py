# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""Pandoc JSON AST 试点：结构对账不改变 Markdown 工作区。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from auto_epublizer.ingest.models import KIND_HEADING, KIND_TEXT, SourceSegment, SourceUnit
from auto_epublizer.ingest.pandoc_ast import ast_blocks, compare_with_units, inline_text
from auto_epublizer.ingest.pandoc_reader import pandoc_available, read_pandoc


def _str(text: str) -> dict:
    return {"t": "Str", "c": text}


def _space() -> dict:
    return {"t": "Space", "c": []}


SYNTHETIC_AST = {
    "blocks": [
        {"t": "Header", "c": [2, ["ch", [], []], [_str("Chapter"), _space(), _str("One")]]},
        {
            "t": "Para",
            "c": [
                {"t": "Strong", "c": [_str("bold")]},
                _space(),
                {"t": "Code", "c": [["", [], []], "a_b"]},
                _space(),
                {"t": "Link", "c": [["", [], []], [_str("label")], ["https://e.org", ""]]},
            ],
        },
        {
            "t": "BulletList",
            "c": [
                [{"t": "Plain", "c": [_str("first item")]}],
                [{"t": "Plain", "c": [_str("second item")]}],
            ],
        },
        {"t": "CodeBlock", "c": [["", [], []], "literal <code>"]},
        {"t": "Table", "c": [{}, [], [], [], []]},
    ]
}


def test_ast_blocks_flatten_structure() -> None:
    blocks = ast_blocks(SYNTHETIC_AST)
    assert blocks[0] == {"kind": "heading", "level": 2, "text": "Chapter One"}
    assert blocks[1]["text"] == "bold a_b label"
    assert [b["text"] for b in blocks[2:4]] == ["first item", "second item"]
    assert blocks[4] == {"kind": "code", "level": 0, "text": "literal <code>"}
    assert all(b["kind"] != "table" for b in blocks)


def test_inline_text_keeps_literal_code_and_drops_math() -> None:
    assert inline_text({"t": "Code", "c": [["", [], []], "x_y"]}) == "x_y"
    assert inline_text({"t": "Math", "c": [{"t": "InlineMath"}, "x^2"]}) == ""
    assert inline_text({"t": "Quoted", "c": [{"t": "DoubleQuote"}, [_str("q")]]}) == "q"


def test_compare_reports_missing_paragraphs() -> None:
    units = [
        SourceUnit(
            id="u001",
            title="Chapter One",
            segments=[
                SourceSegment(index=0, source="Chapter One", kind=KIND_HEADING),
                SourceSegment(index=1, source="bold a_b label", kind=KIND_TEXT),
            ],
        )
    ]
    result = compare_with_units(SYNTHETIC_AST, units)
    assert result["headings"] == 1
    assert result["paragraphs"] == 3  # 段落 + 两个列表项
    assert {item["text"] for item in result["missing"]} == {
        "first item",
        "second item",
        "literal <code>",
    }
    # 代码块也是正文内容：该单元里没有，必须被报为丢失。
    assert result["missing_count"] == 3


@pytest.mark.skipif(not pandoc_available(), reason="需要真实 pandoc")
def test_real_docx_ast_check_reconciles_markdown_workspace(tmp_path: Path) -> None:
    html = tmp_path / "input.html"
    html.write_text(
        "<h1>Book Title</h1>"
        "<h2>Section <em>One</em></h2>"
        "<p>First paragraph with <strong>emphasis</strong> and "
        "<code>code_span</code>.</p>"
        "<ul><li>alpha</li><li>beta</li></ul>"
        "<h2>Section Two</h2><p>Second paragraph.</p>",
        encoding="utf-8",
    )
    docx = tmp_path / "book.docx"
    subprocess.run(["pandoc", str(html), "-o", str(docx)], check=True, timeout=60)

    doc = read_pandoc(docx, fmt="docx", ast_check=True)
    check = doc.meta["ast_check"]
    assert check["headings"] == 3
    assert check["missing_count"] == 0
    # 工作区仍是 Markdown：正文段保留原始标记，未被 AST 输出替换。
    text = "\n".join(s.source for u in doc.units for s in u.segments)
    assert "**emphasis**" in text and "code_span" in text
    assert doc.meta["via"] == "pandoc"


def test_ast_check_defaults_to_off(tmp_path: Path) -> None:
    from auto_common.config import Config

    assert Config().pandoc.ast_check is False
    html = tmp_path / "plain.html"
    html.write_text("<h1>Title</h1><p>Body.</p>", encoding="utf-8")
    doc = read_pandoc(html, fmt="html")
    assert "ast_check" not in doc.meta


def test_prepare_structure_passes_ast_check_from_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """配置开关必须接到导入路径；这里只观察调用参数，不依赖真实 pandoc 输出。"""
    from auto_common.config import Config
    from auto_epublizer import orchestrator as orch

    source = tmp_path / "book.html"
    source.write_text("<h1>Chapter</h1><p>Body text.</p>", encoding="utf-8")
    store = orch.init(str(source), workspace_dir=str(tmp_path / "ws"))
    captured: dict = {}

    def loader(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop-after-capture")

    monkeypatch.setattr(orch, "load_document", loader)
    cfg = Config()
    cfg.pandoc.ast_check = True
    with pytest.raises(RuntimeError):
        orch.prepare_structure(store, config=cfg)
    assert captured["pandoc_ast"] is True


@pytest.mark.skipif(not pandoc_available(), reason="需要真实 pandoc")
def test_real_ast_is_valid_json_with_blocks(tmp_path: Path) -> None:
    from auto_epublizer.ingest.pandoc_ast import run_pandoc_ast

    source = tmp_path / "a.html"
    source.write_text("<h1>Title</h1><p>Body text.</p>", encoding="utf-8")
    ast = run_pandoc_ast(source)
    assert isinstance(ast.get("blocks"), list)
    json.dumps(ast)
