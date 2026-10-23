# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""跨栏/跨页证据保留精度与歧义，不自动清洗源文本或裁定注文。"""

import json
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from auto_epublizer import notes
from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app


def _ws(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# Chapter\n\n1 A synthetic source note.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    raw = store.structured_dir / "raw"
    raw.mkdir(exist_ok=True)
    return store, raw


def test_source_report_preserves_real_columns_and_all_ambiguous_locations(tmp_path: Path) -> None:
    store, raw = _ws(tmp_path)
    blocks = [
        {
            "type": "text",
            "text": "1 A synthetic source note.",
            "bbox": [x, 20, x + 80, 40],
            "font_size": 9,
            "column": col,
        }
        for x, col in [(10, 0), (130, 1)]
    ]
    (raw / "page-001.json").write_text(json.dumps({"page_idx": 1, "blocks": blocks}))
    before = {p: p.read_bytes() for p in store.dir.rglob("*") if p.is_file()}
    result = CliRunner().invoke(
        app, ["evidence", "source", "--workspace", str(store.dir), "--json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert [b["column"] for b in data["blocks"]] == [0, 1]
    assert data["blocks"][0]["bbox"] == [10, 20, 90, 40]
    matches = data["note_candidates"][0]["raw_matches"]
    assert len(matches) == 2
    assert data["note_candidates"][0]["location_status"] == "ambiguous"
    assert all(p.read_bytes() == value for p, value in before.items())
    assert set(before) == {p for p in store.dir.rglob("*") if p.is_file()}


def test_note_candidates_exclude_literal_code(tmp_path: Path) -> None:
    candidates = notes.extract_candidates(
        {"u": "```text\n1 A literal example.\n[^x]: literal definition\n```\n\n`[^literal]`\n"}
    )
    assert candidates == []


def test_breaks_record_both_pages_and_never_claim_gap_is_continuation(tmp_path: Path) -> None:
    store, raw = _ws(tmp_path)
    for page, text in [(1, "An unfinished head"), (3, "A later tail.")]:
        (raw / f"page-{page:03}.json").write_text(
            json.dumps({"page_idx": page, "blocks": [{"type": "text", "text": text}]})
        )
    orch.evidence_breaks(store)
    row = json.loads((store.preprocessing_dir / "breaks.jsonl").read_text())
    assert row["next_page"] == 3 and row["consecutive"] is False
    assert row["candidate"] is False


def test_product_residue_census_includes_asides_and_backmatter(tmp_path: Path) -> None:
    from test_quality_evidence import _report

    store, _ = _ws(tmp_path)
    epub = orch.build(store)
    bad = tmp_path / "residue.epub"
    with zipfile.ZipFile(epub) as src, zipfile.ZipFile(bad, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "OEBPS/ch01.xhtml":
                data = data.replace(
                    b"</body>",
                    '<aside epub:type="footnote" id="x"><p>注文¬尾部 $$</p></aside></body>'.encode(),
                )
            dst.writestr(item, data)
        dst.writestr(
            "OEBPS/back-extra.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>书目¬残片</p><pre><code>literal¬</code></pre></body></html>',
        )
    _, checks = _report(store, "--epub", bad)
    evidence = checks["product_residue"]["evidence"]
    assert any(f["scope"] == "semantic_note" for f in evidence["candidates"])
    assert any(f["member"] == "OEBPS/back-extra.xhtml" for f in evidence["candidates"])
    assert not any("literal" in f["text"] for f in evidence["candidates"])


def test_missing_precision_and_source_toc_remain_explicit(tmp_path: Path) -> None:
    store, raw = _ws(tmp_path)
    (raw / "page-001.json").write_text(
        json.dumps({"blocks": [{"type": "text", "text": "Unfinished fragment"}]})
    )
    (raw / "page-002.json").write_text(
        json.dumps({"page_idx": 1, "blocks": [{"type": "text", "text": "Continuation."}]})
    )
    store.preprocessing_dir.mkdir(exist_ok=True)
    toc = [{"title": "Original chapter", "level": 2, "page": 7}]
    (store.preprocessing_dir / "facts.json").write_text(json.dumps({"source": {"toc": toc}}))
    data = orch.source_evidence(store)
    assert data["source_toc"] == toc
    assert data["blocks"][0]["page"] is None
    assert all(data["blocks"][0][key] is None for key in ("bbox", "font_size", "column"))
    assert data["boundaries"][0]["candidate"] is False


def test_repeated_boundary_has_all_locations_not_a_guessed_first(tmp_path: Path) -> None:
    store, raw = _ws(tmp_path)
    unit = store.load_publication().units[0]
    (store.structured_dir / unit.meta["rel_path"]).write_text(
        "# Chapter\n\nRepeated header\n\nRepeated header\n\nTail.\n"
    )
    for page, text in [(1, "Repeated header"), (2, "Tail.")]:
        (raw / f"page-{page:03}.json").write_text(
            json.dumps({"page_idx": page, "blocks": [{"type": "text", "text": text}]})
        )
    row = orch.source_evidence(store)["boundaries"][0]
    assert len(row["prev_locations"]) == 2
    assert row["prev_block"] is None and row["prev_unit"] is None
