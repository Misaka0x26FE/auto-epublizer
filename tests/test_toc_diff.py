# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""源目录 ↔ EPUB nav 逐项 diff（#58d）：匹配/单边/歧义/href 缺失。"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app
from auto_epublizer.preprocess.toc_diff import (
    collect_toc_diff,
    normalize_toc_label,
    parse_nav_entries,
    parse_printed_entries,
)


def _ws(tmp_path: Path):
    source = tmp_path / "book.md"
    source.write_text(
        "# 目录\n\nAlpha 1\n\nBeta 2\n\n# Alpha\n\nText.\n\n# Beta\n\nMore.\n",
        encoding="utf-8",
    )
    return orch.init(str(source), workspace_dir=str(tmp_path / "ws"))


# ── 印刷目录解析 ─────────────────────────────────────────────────────


def test_page_number_on_its_own_line_attaches_to_previous_entry() -> None:
    entries = parse_printed_entries("# 目录\n\nAlpha\n1\n\nBeta 2\n")
    assert [(entry["label"], entry["page"]) for entry in entries] == [
        ("Alpha", "1"),
        ("Beta", "2"),
    ]


def test_normalization_strips_numbering_quotes_and_spacing() -> None:
    assert normalize_toc_label("1．「小事  与伟业」") == normalize_toc_label("小事与伟业")
    assert normalize_toc_label("“每个民族的根基都是领土”") == "每个民族的根基都是领土"


# ── nav 解析 ─────────────────────────────────────────────────────────


def test_nav_entries_read_levels_and_report_missing_members(tmp_path: Path) -> None:
    import zipfile

    epub = tmp_path / "book.epub"
    nav = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<body><nav epub:type="toc"><ol>
<li><a href="ch01.xhtml">One</a><ol><li><a href="ch01.xhtml#s1">Sub</a></li></ol></li>
<li><a href="missing.xhtml">Gone</a></li>
</ol></nav></body></html>
"""
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("OEBPS/nav.xhtml", nav)
        zf.writestr("OEBPS/ch01.xhtml", "<html/>")
    data = parse_nav_entries(epub)
    assert [(entry["label"], entry["level"]) for entry in data["entries"]] == [
        ("One", 1),
        ("Sub", 2),
        ("Gone", 1),
    ]
    assert data["href_missing"] == ["missing.xhtml"]
    assert data["entries"][2]["file_present"] is False


# ── 工作区对账 ───────────────────────────────────────────────────────


def test_toc_diff_matches_printed_entries_against_built_nav(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    orch.build(store)
    data = collect_toc_diff(store)
    assert data["status"] == "ok"
    assert data["printed"]["kind"] == "structured"
    assert data["counts"] == {
        "printed": 2,
        "nav": 4,
        "matched": 2,
        "printed_only": 0,
        "ambiguous": 0,
        "nav_only": 2,
        "duplicate_nav_labels": 0,
        "href_missing": 0,
    }
    # nav 多出的制作信息/目录页只报单边证据，不反推印刷目录缺项。
    assert [entry["label"] for entry in data["nav_only"]] == ["制作信息", "目录"]


def test_toc_diff_prefers_translated_toc_and_reports_word_order_drift(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    orch.build(store)
    unit = next(u for u in store.load_publication().units if u.kind == "toc")
    translated = store.translation_dir / str(unit.meta["rel_path"])
    translated.parent.mkdir(parents=True, exist_ok=True)
    translated.write_text("# 目录\n\nAlpha 1\n\nRenamed 2\n", encoding="utf-8")
    data = collect_toc_diff(store)
    assert data["printed"]["kind"] == "translation"
    by_label = {entry["label"]: entry for entry in data["printed"]["entries"]}
    assert by_label["Alpha"]["match"] == "matched"
    assert by_label["Renamed"]["match"] == "printed_only"
    assert data["counts"]["printed_only"] == 1


def test_toc_diff_without_epub_is_unknown_and_read_only(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    before = {path: path.read_bytes() for path in store.dir.rglob("*") if path.is_file()}
    data = collect_toc_diff(store)
    assert data["status"] == "unknown" and data["reason"] == "epub_nav_missing"
    assert all(path.read_bytes() == value for path, value in before.items())


# ── CLI ─────────────────────────────────────────────────────────────


def test_cli_writes_toc_diff_and_reports_counts(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    orch.build(store)
    result = CliRunner().invoke(
        app, ["evidence", "toc-diff", "--workspace", str(store.dir), "--json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert "path" not in data
    assert data["counts"]["matched"] == 2

    written = json.loads((store.preprocessing_dir / "toc-diff.json").read_text(encoding="utf-8"))
    assert written["input_digest"] and written["nav"]["sha256"]
