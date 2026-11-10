"""D3：源文实印疑误登记（只记录证据，不改写 source）。"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app
from auto_epublizer.errata import read_errata, register_errata


def _store(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    return orch.init(str(src), workspace_dir=str(tmp_path / "ws"))


def _row(**kw):
    base = {
        "unit": "ch01",
        "locator": "p.12/b3",
        "source_text": "teh",
        "reading": "the",
        "evidence": "原页扫描 p.12 第 3 块（OCR 误识）",
        "status": "proposed",
    }
    base.update(kw)
    return base


def test_register_requires_evidence_and_valid_unit(tmp_path: Path) -> None:
    store = _store(tmp_path)
    report = register_errata(store, [_row(), _row(unit="ch99"), _row(evidence="")])
    assert len(report.entries) == 1
    assert any("ch99" in e for e in report.errors)
    assert any("evidence" in e for e in report.errors)
    assert not (store.preprocessing_dir / "errata.jsonl").exists()  # 默认只预检


def test_apply_writes_sorted_jsonl_and_digest(tmp_path: Path) -> None:
    store = _store(tmp_path)
    source_path = store.structured_dir / "body" / "ch01.md"
    source_before = source_path.read_bytes()
    report = register_errata(
        store,
        [_row(locator="p.20/b1"), _row(locator="p.12/b3", status="confirmed")],
        apply=True,
    )
    assert report.errors == []
    rows, digest = read_errata(store)
    assert [r["locator"] for r in rows] == ["p.12/b3", "p.20/b1"]
    assert digest and len(digest) == 64
    # 不改写源文（按完整字节断言，而不是挑一个原本不存在的词）
    assert source_path.read_bytes() == source_before


def test_cli_import_and_status(tmp_path: Path) -> None:
    store = _store(tmp_path)
    path = tmp_path / "errata.jsonl"
    path.write_text(
        '{"unit":"ch01","locator":"p.1","source_text":"a","reading":"b","evidence":"scan"}\n'
    )
    runner = CliRunner()
    bad = runner.invoke(
        app,
        [
            "errata",
            "import",
            str(path),
            "--workspace",
            str(store.dir),
            "--apply",
        ],
    )
    assert bad.exit_code == 0, bad.output  # 缺省 status=proposed 合法
    path.write_text(
        '{"unit":"ch01","locator":"p.1","source_text":"a","reading":"b"}\n',
        encoding="utf-8",
    )
    invalid = runner.invoke(app, ["errata", "import", str(path), "--workspace", str(store.dir)])
    assert invalid.exit_code == 1
    assert "evidence" in invalid.output
    status = runner.invoke(app, ["errata", "status", "--json", "--workspace", str(store.dir)])
    assert status.exit_code == 0
    assert '"total": 1' in status.output


def test_apply_merges_batches_and_rejects_empty_overwrite(tmp_path: Path) -> None:
    """P0：逐批登记不得覆盖既有台账；空批次不清理。"""
    store = _store(tmp_path)
    register_errata(store, [_row(locator="p.1")], apply=True)
    register_errata(store, [_row(locator="p.2")], apply=True)
    rows, _digest = read_errata(store)
    assert [r["locator"] for r in rows] == ["p.1", "p.2"]

    empty = register_errata(store, [], apply=True)
    assert empty.errors
    rows, _digest = read_errata(store)
    assert len(rows) == 2


def test_duplicate_key_in_one_batch_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    report = register_errata(store, [_row(), _row()], apply=True)
    assert any("重复" in e for e in report.errors)
    assert not (store.preprocessing_dir / "errata.jsonl").exists()
