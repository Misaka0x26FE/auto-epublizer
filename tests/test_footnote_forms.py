# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""#37：非语义脚注形态必须可见，不能以「零定义 / 零 aside」全绿放行。"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from auto_common.workspace import Publication, PublicationMeta
from auto_epublizer.build import build_epub
from auto_epublizer.build.html import FootnoteState, render_document
from auto_epublizer.qa.audit import audit_epub
from auto_epublizer.qa.footnote_forms import (
    candidate_footnote_paragraphs,
    candidate_footnotes_in_html,
)


def _codes(result) -> set[str]:
    return {finding.code for finding in result.findings}


def _pub() -> Publication:
    return Publication(
        slug="book",
        meta=PublicationMeta(title="测试书", creator="作者", target_language="zh-CN"),
    )


def _epub(tmp_path: Path, markdown: str) -> Path:
    entries = [{"id": "ch01", "region": "body", "title": "第一章"}]
    content = [
        (
            "ch01.xhtml",
            render_document(
                "第一章",
                f"# 第一章\n\n{markdown}\n",
                lang="zh-CN",
                fn_state=FootnoteState(),
            ),
        )
    ]
    return build_epub(
        _pub(),
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "book.epub",
    )


def test_markdown_candidates_cover_common_forms_but_not_code() -> None:
    md = (
        "正文。\n\n注 1. 这是注释。\n\n[2] 方括号注释。\n\n"
        "1. 第一条注。\n\n2. 第二条注。\n\n"
        "```\n注 9. 代码里的不算\n```\n\n`注 8. 行内代码不算`\n"
    )
    hits = candidate_footnote_paragraphs(md)
    assert any("注 1." in hit for hit in hits)
    assert any("[2]" in hit for hit in hits)
    assert sum(1 for hit in hits if hit[:2] in {"1.", "2."}) == 2
    assert not any("注 9." in hit or "注 8." in hit for hit in hits)


def test_single_numbered_paragraph_is_not_a_candidate() -> None:
    assert candidate_footnote_paragraphs("正文。\n\n1. 只是一个编号段。\n") == []


def test_html_candidates_ignore_code_and_unordered_lists() -> None:
    html = "<p>注 1. 注释</p><pre>注 2. 代码</pre><ul><li>1. 列表项</li></ul><p>普通段落</p>"
    hits = candidate_footnotes_in_html(html)
    assert hits == ["注 1. 注释"]


def test_audit_blocks_unregistered_non_semantic_footnotes(tmp_path: Path) -> None:
    epub = _epub(tmp_path, "注 1. 这是没有语义化的注释。")
    result = audit_epub(epub)
    assert not result.ok
    assert "E_FOOTNOTES_NOT_SEMANTIC" in _codes(result)


def test_audit_skips_when_notes_registered_or_asides_exist(tmp_path: Path) -> None:
    epub = _epub(tmp_path, "注 1. 这是没有语义化的注释。")
    registered = audit_epub(epub, notes_registered=True)
    assert "E_FOOTNOTES_NOT_SEMANTIC" not in _codes(registered)

    semantic = _epub(
        tmp_path / "semantic",
        "正文有注[^1]。\n\n[^1]: 真正的脚注。",
    )
    ok = audit_epub(semantic)
    assert "E_FOOTNOTES_NOT_SEMANTIC" not in _codes(ok)


def test_build_warns_and_logs_without_blocking(tmp_path: Path) -> None:
    from auto_epublizer import orchestrator as orch

    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n\n注 1. 这是注释。\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    with pytest.warns(UserWarning, match="疑似脚注"):
        out = orch.build(store)
    assert Path(out).is_file()
    events = (store.dir / "events.jsonl").read_text(encoding="utf-8")
    assert "footnotes_not_semantic" in events


def test_plain_numbered_list_is_not_a_blocking_footnote(tmp_path: Path) -> None:
    """正常有序列表（loose list）不得被当成非语义脚注阻断。"""
    epub = _epub(tmp_path, "1. first item\n\n2. second item")
    result = audit_epub(epub)
    assert "E_FOOTNOTES_NOT_SEMANTIC" not in _codes(result)
    assert "W_FOOTNOTES_AMBIGUOUS" in _codes(result)


def test_build_does_not_warn_for_plain_ordered_list(tmp_path: Path) -> None:
    """普通有序列表只由 QA 记 W_FOOTNOTES_AMBIGUOUS，不在 build 阶段刷警告。"""
    from auto_epublizer import orchestrator as orch

    src = tmp_path / "list.md"
    src.write_text("# 第一章\n\n正文。\n\n1. 第一项\n\n2. 第二项\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws-list"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        orch.build(store)
    assert not [w for w in caught if "疑似脚注" in str(w.message)]


def test_mixed_semantic_and_plain_note_paragraph_still_blocks(tmp_path: Path) -> None:
    """已有语义 aside 时，另一段 `注 1.` 仍必须阻断（不再只报 partial）。"""
    epub = _epub(
        tmp_path,
        "正文有注[^1]。\n\n[^1]: 真正的脚注。\n\n注 1. 另一段没有语义化的注文。",
    )
    import zipfile

    with zipfile.ZipFile(epub) as zf:
        xhtml = zf.read("OEBPS/ch01.xhtml").decode("utf-8")
    assert 'epub:type="footnote"' in xhtml  # 语义 aside 确实存在
    result = audit_epub(epub)
    assert not result.ok
    assert "E_FOOTNOTES_NOT_SEMANTIC" in _codes(result)


def test_note_inside_list_item_is_still_detected(tmp_path: Path) -> None:
    """注文写成 `<ol><li>注 1. …</li></ol>` 时不能因列表过滤而漏报。"""
    epub = _epub(tmp_path, "1. 注 1. 列表里的注文。\n\n2. 注 2. 第二条。")
    result = audit_epub(epub)
    assert "E_FOOTNOTES_NOT_SEMANTIC" in _codes(result)
