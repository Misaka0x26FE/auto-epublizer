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


def test_status_all_nested_layout_and_schema_filter(tmp_path: Path) -> None:
    """R0：支持真实嵌套布局 <base>/<slug>/book/，并跳过其它工具 schema 的工作区。"""
    base = tmp_path / "work"
    src = tmp_path / "book.md"
    src.write_text("# Chapter\n\nBody text.\n", encoding="utf-8")
    orch.init(str(src), workspace_dir=str(base / "real-book"))  # → base/real-book/book/

    foreign = base / "other-tool" / "book"
    foreign.mkdir(parents=True)
    (foreign / "publication.json").write_text(
        json.dumps({"schema_version": "epub-builder/v1alpha1"}), encoding="utf-8"
    )

    rows = orch.status_all(base)
    assert [r["slug"] for r in rows] == ["real-book"]  # 嵌套发现 + schema 过滤


def test_cli_status_all_json(tmp_path: Path) -> None:
    base = _two_workspaces(tmp_path)
    result = runner.invoke(app, ["status", "--all", "--json", "--workspace", str(base)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 2


def _scaffold_publication(path: Path) -> None:
    """写一份与 CLI 自带 template/publication.json 同形的脚手架（未 init 的工作区）。"""
    from auto_common.workspace.models import SCHEMA_VERSION

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "slug": "the-great-gatsby-fitzgerald",
                "meta": {"title": "The Great Gatsby"},
                "units": [{"id": "ch01", "status": "split"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_status_all_skips_tool_tree_template(tmp_path: Path) -> None:
    """回归（issue #33）：工作根内的 CLI 仓库副本（含 template/）不得扫成工作区。"""
    base = _two_workspaces(tmp_path)
    tool = base / "auto-epublizer"  # AGENTS.md 记载的工作根布局：<work-root>/auto-epublizer/
    (tool / "src" / "auto_epublizer").mkdir(parents=True)
    (tool / "pyproject.toml").write_text('[project]\nname = "auto-epublizer"\n', encoding="utf-8")
    _scaffold_publication(tool / "template" / "publication.json")

    rows = orch.status_all(base)
    assert {r["slug"] for r in rows} == {"alpha", "beta"}  # 工具模板被排除
    assert all(r["units_total"] == 1 for r in rows)  # 单元数不因脚手架虚增


def test_status_all_keeps_plain_template_named_workspace(tmp_path: Path) -> None:
    """不误伤：名字含 template 但不属于工具树的目录仍按原行为扫描（避免过度过滤）。"""
    base = _two_workspaces(tmp_path)
    _scaffold_publication(base / "loose" / "template" / "publication.json")
    rows = orch.status_all(base)
    assert "the-great-gatsby-fitzgerald" in {r["slug"] for r in rows}


def test_cli_ledger_stdout_not_wrapped_by_rich(tmp_path: Path) -> None:
    """回归（issue #33）：ledger stdout 曾按终端宽度折行，打散 markdown 表格。"""
    base = tmp_path / "work"
    title = "一部标题非常非常长的书" * 6  # 远超 80 列：修复前 Rich 会插入真实换行
    src = tmp_path / "long.md"
    src.write_text(f"# {title}\n\n正文。\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(base))
    orch.set_meta(store, title=title)

    result = runner.invoke(app, ["ledger", "--workspace", str(base)])
    assert result.exit_code == 0, result.output
    title_lines = [ln for ln in result.output.splitlines() if title in ln]
    assert len(title_lines) == 1  # 标题完整落在同一行内，未被拆行
    assert title_lines[0].startswith("| ") and title_lines[0].rstrip().endswith("|")


def test_cli_ledger_file_output_single_line_rows(tmp_path: Path) -> None:
    """-o 写文件同样保持「一条记录一行」（issue #33 缺陷 1 的文件侧契约）。"""
    base = _two_workspaces(tmp_path)
    out = tmp_path / "ledger.md"
    result = runner.invoke(app, ["ledger", "--workspace", str(base), "-o", str(out)])
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    for slug in ("alpha", "beta"):
        rows = [ln for ln in text.splitlines() if ln.startswith(f"| {slug} ")]
        assert len(rows) == 1, text
        assert rows[0].rstrip().endswith("|")
