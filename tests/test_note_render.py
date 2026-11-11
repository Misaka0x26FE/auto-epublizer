# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""按需注文裁剪图（#72-1）：显式渲染、幂等复用、审阅状态与存储上限。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app
from auto_epublizer.preprocess.note_render import ledger_path, mark_reviewed, render_note_crops

pymupdf = pytest.importorskip("pymupdf")


def _pdf(tmp_path: Path) -> Path:
    path = tmp_path / "book.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Note one text", fontsize=12)
    doc.save(path)
    doc.close()
    return path


def _store(tmp_path: Path, *, pdf: bool = True):
    source = _pdf(tmp_path) if pdf else None
    if source is None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        source = tmp_path / "book.md"
        source.write_text("# Chapter\n\nText.\n", encoding="utf-8")
    return orch.init(str(source), workspace_dir=str(tmp_path / "ws"))


def _notes(store, rows: list[dict]) -> None:
    data = {"schema_version": "1", "inventory": "present", "notes": rows, "references": []}
    (store.structured_dir / "notes.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _note(note_id: str = "n-000001", *, page: int = 1, box: list[float] | None = None) -> dict:
    return {
        "note_id": note_id,
        "source_label": "1",
        "scope_id": "ch01",
        "note_type": "footnote",
        "status": "verified",
        "source_markdown": "Note one text",
        "source_locations": [{"page": page, "bbox": [60, 60, 220, 90] if box is None else box}],
    }


def test_render_writes_local_crop_and_reuses_it(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _notes(store, [_note()])
    first = render_note_crops(store, dpi=120)
    assert first["counts"]["rendered"] == 1
    image = store.dir / "preprocessing/notes-render/n-000001-p0001.png"
    assert image.is_file() and image.stat().st_size > 0
    digest = first["notes"][0]["sha256"]
    assert first["notes"][0]["reviewed"] is False

    mark_reviewed(store, ["n-000001"])
    second = render_note_crops(store, dpi=120)
    assert second["counts"]["reused"] == 1
    assert second["notes"][0]["sha256"] == digest
    assert second["notes"][0]["reviewed"] is True


def test_rerender_with_new_dpi_resets_reviewed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _notes(store, [_note()])
    render_note_crops(store, dpi=72)
    mark_reviewed(store, ["n-000001"])
    changed = render_note_crops(store, dpi=144)
    assert changed["counts"]["rendered"] == 1
    assert changed["notes"][0]["reviewed"] is False


def test_subset_render_preserves_other_ledger_entries(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _notes(store, [_note("n-000001"), _note("n-000002")])
    render_note_crops(store)
    render_note_crops(store, note_ids=["n-000001"])
    ledger = json.loads(ledger_path(store).read_text(encoding="utf-8"))
    assert {row["note_id"] for row in ledger["notes"]} == {"n-000001", "n-000002"}
    assert all(row["status"] == "rendered" for row in ledger["notes"])


def test_max_crops_defers_the_rest_without_claiming_missing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _notes(store, [_note("n-000001"), _note("n-000002")])
    data = render_note_crops(store, max_crops=1)
    statuses = {row["note_id"]: row["status"] for row in data["notes"]}
    assert statuses == {"n-000001": "rendered", "n-000002": "deferred"}
    assert data["counts"]["deferred"] == 1


def test_missing_bbox_page_and_non_pdf_are_explicit(tmp_path: Path) -> None:
    store = _store(tmp_path)
    no_box = _note("n-000001")
    no_box["source_locations"] = [{"page": 1}]
    _notes(
        store,
        [
            no_box,
            _note("n-000002", page=99),
            _note("n-000003"),
        ],
    )
    data = render_note_crops(store)
    statuses = {row["note_id"]: row["status"] for row in data["notes"]}
    assert statuses == {
        "n-000001": "page_only",
        "n-000002": "missing_page",
        "n-000003": "rendered",
    }

    md_store = _store(tmp_path / "md", pdf=False)
    _notes(md_store, [_note()])
    assert render_note_crops(md_store)["notes"][0]["status"] == "source_missing"


def test_mark_reviewed_reports_unknown_ids(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _notes(store, [_note()])
    render_note_crops(store)
    result = mark_reviewed(store, ["n-000001", "n-999999"])
    assert result["changed"] == 1
    assert result["missing_note_ids"] == ["n-999999"]
    ledger = json.loads(ledger_path(store).read_text(encoding="utf-8"))
    assert ledger["counts"]["reviewed"] == 1


def test_cli_render_is_explicit_and_json_excludes_ledger_path(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _notes(store, [_note()])
    result = CliRunner().invoke(
        app,
        ["evidence", "notes", "--workspace", str(store.dir), "--render", "--json"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["render"]["counts"]["rendered"] == 1
    assert "path" not in data
    assert (store.dir / "preprocessing/notes-render/n-000001-p0001.png").is_file()
