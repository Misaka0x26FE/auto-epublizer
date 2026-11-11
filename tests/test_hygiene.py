# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""C1 真值表：只读卫生扫描的候选与负对照。"""

from __future__ import annotations

import json
from pathlib import Path

from auto_epublizer import orchestrator as orch
from auto_epublizer.hygiene import scan_unit, scan_workspace


def _codes(findings: list[dict]) -> set[str]:
    return {item["code"] for item in findings}


def test_unbalanced_quote_is_reported() -> None:
    findings = scan_unit("ch01", "他说“没有说完。\n")
    assert "unbalanced_quote" in _codes(findings)


def test_quotes_balanced_across_blocks() -> None:
    findings = scan_unit("ch01", "他说：“开头。\n\n结尾。”\n")
    assert "unbalanced_quote" not in _codes(findings)


def test_duplicate_word_and_long_paragraph() -> None:
    findings = scan_unit("ch01", "这是研究研究的结果。\n\n" + "字" * 1201 + "。\n")
    codes = _codes(findings)
    assert "duplicate_word" in codes
    assert "long_paragraph" in codes


def test_half_sentence_and_tail_loss() -> None:
    findings = scan_unit("ch01", "这是一个没有结束的句子\n")
    assert "half_sentence" in _codes(findings)
    findings = scan_unit("ch01", "他继续说，\n")
    assert {"half_sentence", "tail_loss"} <= _codes(findings)


def test_colon_lead_in_is_not_tail_loss() -> None:
    findings = scan_unit("ch01", "他列出以下各点：\n\n第一点。\n")
    assert "tail_loss" not in _codes(findings)
    assert "half_sentence" not in _codes(findings)


def test_fenced_code_is_ignored() -> None:
    findings = scan_unit("ch01", "```\n研究研究 没结束\n```\n\n正文。\n")
    assert "duplicate_word" not in _codes(findings)
    assert "half_sentence" not in _codes(findings)


def test_gloss_in_parentheses_is_not_primitive_word() -> None:
    findings = scan_unit("ch01", "马克思（Marx）与中世纪研究。\n")
    assert "primitive_word" not in _codes(findings)


def _workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nBody.\n\n# Bibliography\n\nItems.\n", encoding="utf-8")
    return orch.init(str(src), workspace_dir=tmp_path / "ws")


def test_bibliography_is_skipped_but_body_scanned(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body/ch01.md").write_text(
        "# 第一章\n\n研究研究的结果。\n", encoding="utf-8"
    )
    (store.translation_dir / "backmatter").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "backmatter/bibliography.md").write_text(
        "# 参考文献\n\n研究研究。\n", encoding="utf-8"
    )
    result = scan_workspace(store)
    assert result["writes"] is False
    units = {item["unit"] for item in result["findings"]}
    assert "ch01" in units
    assert "back-bibliography" not in units


def test_notes_are_scanned(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body/ch01.md").write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    (store.translation_dir / "notes.json").write_text(
        json.dumps(
            {
                "notes": [
                    {"note_id": "n1", "target_markdown": "研究研究的结果。"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = scan_workspace(store)
    assert any(item.get("note_id") == "n1" for item in result["findings"])


def test_english_period_is_terminal_and_english_block_has_no_primitive_word() -> None:
    findings = scan_unit("ch01", "This is a complete English sentence.\n")
    codes = _codes(findings)
    assert "half_sentence" not in codes and "tail_loss" not in codes
    assert "primitive_word" not in codes


def test_tilde_fence_and_inline_code_are_excluded() -> None:
    findings = scan_unit("ch01", '~~~\n研究研究 没结束\n~~~\n\n使用 `"` 符号。\n')
    codes = _codes(findings)
    assert "duplicate_word" not in codes and "unbalanced_quote" not in codes


def test_bad_notes_json_is_a_structured_error(tmp_path: Path) -> None:
    import pytest

    store = _workspace(tmp_path)
    (store.translation_dir / "notes.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="notes.json"):
        scan_workspace(store)


def test_unit_scan_covers_notes_referenced_by_that_unit(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body/ch01.md").write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    notes = {
        "schema_version": "1",
        "inventory": "present",
        "notes": [
            {"note_id": "n1", "target_markdown": "研究研究的注释。"},
            {"note_id": "n2", "target_markdown": "另一条注释。"},
        ],
        "references": [
            {"unit": "ch01", "ref_id": "r1", "note_id": "n1"},
            {"unit": "ch02", "ref_id": "r2", "note_id": "n2"},
        ],
    }
    (store.translation_dir / "notes.json").write_text(
        json.dumps(notes, ensure_ascii=False), encoding="utf-8"
    )
    result = scan_workspace(store, unit_id="ch01")
    scanned = {item["unit"] for item in result["units"]}
    assert "notes:n1" in scanned and "notes:n2" not in scanned
    assert result["coverage"]["notes_scope"] == "referenced"


def test_lowercase_next_block_is_cross_page_fragment_not_half_sentence() -> None:
    """#85：下一块像续文时报跨页候选，不催成“半句”。"""
    findings = scan_unit("ch01", "这是一个没有结束的句子\n\ncontinued on the next page.\n")
    codes = _codes(findings)
    assert "cross_page_fragment" in codes
    assert "half_sentence" not in codes

    new_para = scan_unit("ch01", "这是一个没有结束的句子\n\nAnother paragraph starts here.\n")
    assert "half_sentence" in _codes(new_para)


def test_cjk_continuation_is_cross_page_fragment() -> None:
    """#85：下一块以中文承接连词开头时按跨页续文报，而不是半句。"""
    findings = scan_unit("ch01", "这一段没有结束并且\n\n而且下一页接着说完。\n")
    codes = _codes(findings)
    assert "cross_page_fragment" in codes
    assert "half_sentence" not in codes


def test_hygiene_summary_reports_error_instead_of_silent_zero(tmp_path: Path, monkeypatch) -> None:
    """#85：QA 取卫生计数失败时必须留下错误，不能静默当作 0 条候选。"""
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws-summary"))

    def boom(_store):
        raise ValueError("扫描器坏了")

    monkeypatch.setattr("auto_epublizer.hygiene.scan_workspace", boom)
    summary = orch._hygiene_summary(store)
    assert summary["candidates"] == 0
    assert summary["error"] == "扫描器坏了"


def test_table_rows_and_short_verse_are_not_half_sentences() -> None:
    """#85：表格行与短引用诗不是半句；普通引用散文仍检查。"""
    table = "| term | gloss |\n| --- | --- |\n| a | b |"
    assert "half_sentence" not in _codes(scan_unit("ch01", table))

    verse = "> 山色空蒙雨亦奇\n> 水光潋滟晴方好"
    assert "half_sentence" not in _codes(scan_unit("ch01", verse))

    prose = "> 这是一段没有结束的引用散文\n"
    assert "half_sentence" in _codes(scan_unit("ch01", prose))


def test_quote_tail_dropped_is_distinct_from_plain_tail_loss() -> None:
    """#93：引号内以逗号/破折号收尾，报引文丢尾而不是普通丢尾。"""
    findings = scan_unit("ch01", "他说：“这句话没有收尾，\n")
    assert "quote_tail_dropped" in _codes(findings)
    balanced = scan_unit("ch01", "他说：“这句话已经完整。”\n")
    assert "quote_tail_dropped" not in _codes(balanced)


def test_confirmed_glossary_terms_and_abbreviations_are_not_primitive(tmp_path: Path) -> None:
    """#93：confirmed 术语与全大写缩写不算残留外文；seed 术语仍报。"""
    store = _workspace(tmp_path)
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body/ch01.md").write_text(
        "# 第一章\n\nWehrmacht 与 NKVD 的档案。\n", encoding="utf-8"
    )
    glossary = store.analysis_dir / "glossary.csv"
    glossary.write_text(
        "source,target,type,aliases,gender,reading,status,note\n"
        'Wehrmacht,国防军,term,,,,"confirmed",\n',
        encoding="utf-8",
    )
    result = scan_workspace(store)
    assert all(
        item["detail"].get("word") not in {"Wehrmacht", "NKVD"} for item in result["findings"]
    )

    glossary.write_text(
        'source,target,type,aliases,gender,reading,status,note\nWehrmacht,国防军,term,,,,"seed",\n',
        encoding="utf-8",
    )
    seeded = scan_workspace(store)
    assert any(
        item["code"] == "primitive_word" and item["detail"].get("word") == "Wehrmacht"
        for item in seeded["findings"]
    )


def test_unbalanced_quote_gets_block_location() -> None:
    """#93：整单元失衡时给逐块位置，跨段合法引文仍不报。"""
    findings = scan_unit("ch01", "第一段。\n\n他说“没有说完。\n")
    located = [item for item in findings if item["code"] == "unbalanced_quote" and item["block"]]
    assert located and located[0]["block"] == 2
    balanced = scan_unit("ch01", "他说：“开头。\n\n结尾。”\n")
    assert not [
        item for item in balanced if item.get("block") and item["code"] == "unbalanced_quote"
    ]
