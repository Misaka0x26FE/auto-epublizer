# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""只读证据不能由旧报告、空串、截短或缺副本制造通过。"""

import json
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app


def _workspace(tmp_path: Path):
    source = tmp_path / "book.md"
    source.write_text(
        "# Chapter\n\nA complete synthetic paragraph with several facts.\n", encoding="utf-8"
    )
    store = orch.init(str(source), workspace_dir=str(tmp_path / "ws"))
    return store, orch.build(store)


def _report(store, *args):
    result = CliRunner().invoke(
        app, ["evidence", "report", "--workspace", str(store.dir), "--json", *map(str, args)]
    )
    assert result.exit_code in (0, 1), result.output
    data = json.loads(result.stdout)
    return data, {row["id"]: row for row in data["checks"]}


def _snapshot(root: Path):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_evidence_is_read_only_and_missing_external_source_stays_unknown(tmp_path: Path) -> None:
    store, _ = _workspace(tmp_path)
    before = _snapshot(store.dir)
    report, checks = _report(store)
    assert _snapshot(store.dir) == before
    assert checks["source_identity"]["status"] == "pass"
    assert checks["external_source"]["status"] == "unknown"
    assert checks["epub_body:ch01"]["status"] == "pass"
    assert checks["semantic_acceptance"]["status"] == "manual"
    assert report["input_digest"] and report["rule_version"]
    assert "released" not in report


def test_nonempty_truncation_and_missing_copy_are_failures(tmp_path: Path) -> None:
    store, epub = _workspace(tmp_path)
    bad = tmp_path / "truncated.epub"
    with zipfile.ZipFile(epub) as src, zipfile.ZipFile(bad, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "OEBPS/ch01.xhtml":
                data = data.replace(
                    b"A complete synthetic paragraph with several facts.", b"A complete"
                )
            dst.writestr(info, data)
    _, checks = _report(store, "--epub", bad, "--copy", tmp_path / "missing.epub")
    assert checks["epub_body:ch01"]["status"] == "fail"
    assert checks["copy:1"]["status"] == "fail"


def test_actual_source_identity_is_hashed_not_copied_from_metadata(tmp_path: Path) -> None:
    store, _ = _workspace(tmp_path)
    first, _ = _report(store)
    pub = store.load_publication()
    (store.dir / pub.meta.source).write_text("Different bytes.")
    second, checks = _report(store)
    assert checks["source_identity"]["status"] == "fail"
    assert second["input_digest"] != first["input_digest"]


def test_copy_bytes_match_and_registered_notes_have_separate_scope(tmp_path: Path) -> None:
    from test_notes import _gap_ws

    store, _ = _gap_ws(tmp_path)
    epub = orch.build(store)
    copy = tmp_path / "copy.epub"
    copy.write_bytes(epub.read_bytes())
    _, checks = _report(store, "--copy", copy)
    assert checks["copy:1"]["status"] == "pass"
    assert checks["registered_notes"]["status"] == "pass"
    assert checks["source_note_inventory"]["status"] == "manual"


def test_copying_current_qa_state_does_not_bind_a_different_product(tmp_path: Path) -> None:
    from auto_common.config import Config

    store, epub = _workspace(tmp_path)
    cfg = Config()
    cfg.qc.epubcheck.jar = str(tmp_path / "no-checker.jar")
    orch.qa(store, epub_path=str(epub), config=cfg)
    alternate = tmp_path / "other.epub"
    alternate.write_bytes(epub.read_bytes())
    _, checks = _report(store, "--epub", alternate)
    assert checks["qa_report_binding"]["status"] != "pass"


def test_fabricated_alignment_source_is_not_verified_by_target_agreement(tmp_path: Path) -> None:
    store, _ = _workspace(tmp_path)
    unit = store.load_publication().units[0]
    path = store.translation_dir / unit.meta["rel_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Chapter\n\n完整的合成译文段落。\n")
    align = store.unit_align_path(unit.id)
    align.parent.mkdir(parents=True, exist_ok=True)
    align.write_text(
        json.dumps({"seq": 1, "src": "Invented source text.", "tgt": "完整的合成译文段落。"}) + "\n"
    )
    orch.build(store)
    _, checks = _report(store)
    assert checks["align_source:ch01"]["status"] == "fail"
