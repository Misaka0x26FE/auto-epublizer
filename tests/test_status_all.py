"""#32：多工作区总览 status --all + ledger 台账。"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app

runner = CliRunner()


def _two_workspaces(tmp_path: Path) -> Path:
    base = tmp_path / "work"
    for name, title in [("alpha", "Alpha"), ("beta", "Beta")]:
        src = tmp_path / f"{name}.md"
        src.write_text(f"# Chapter {title}\n\nBody text here.\n", encoding="utf-8")
        orch.init(str(src), workspace_dir=str(base))
    return base


def test_status_all_lists_workspaces(tmp_path: Path) -> None:
    base = _two_workspaces(tmp_path)
    rows = orch.status_all(base)
    assert {r["slug"] for r in rows} == {"alpha", "beta"}
    assert all(r["progress"] == "preprocessing" for r in rows)  # 无 report.json
    assert all(r["units_total"] == 1 for r in rows)


def test_render_ledger_has_machine_columns(tmp_path: Path) -> None:
    md = orch.render_ledger(orch.status_all(_two_workspaces(tmp_path)))
    assert "| slug | 书名 | 开工日期 | 进度 | 单元 | 词 | 领域 | 摘要 |" in md
    assert "`auto-epublizer status --all`" in md


def test_cli_status_all_json(tmp_path: Path) -> None:
    base = _two_workspaces(tmp_path)
    result = runner.invoke(app, ["status", "--all", "--json", "--workspace", str(base)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 2
