"""E2：CLI 机器/人类契约（退出码、中文错误、JSON stdout、next_tasks 与真实命令一致）。"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from auto_common.config import Config
from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app

runner = CliRunner()


def _cli_command_names() -> set[str]:
    """已注册的 CLI 名称（顶层命令 + 子命令组 + 「组 子命令」组合）。"""
    names: set[str] = set()
    for cmd in app.registered_commands:
        names.add(cmd.name or (cmd.callback.__name__ if cmd.callback else ""))
    for group in app.registered_groups:
        group_name = group.name or ""
        if group_name:
            names.add(group_name)
        sub = group.typer_instance
        if sub is None:
            continue
        for cmd in sub.registered_commands:
            sub_name = cmd.name or (cmd.callback.__name__ if cmd.callback else "")
            names.add(sub_name)
            if group_name and sub_name:
                names.add(f"{group_name} {sub_name}")
    return {n for n in names if n}


def test_next_tasks_done_when_commands_are_real_cli_commands(tmp_path: Path) -> None:
    """机器指针一致性：next_tasks 的 done_when.cmd 必须是已注册的 CLI 子命令。"""
    registered = _cli_command_names()
    assert {"preprocess", "import", "build", "qa", "g0", "notes"} <= registered

    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\n第一句话。\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    seen_cmds: set[str] = set()
    states = []
    states.append(orch.status(store))
    orch.preprocess(store, config=Config())
    states.append(orch.status(store))
    for name in ("capabilities.md", "global.md", "todo.md"):
        (store.preprocessing_dir / name).write_text("x", encoding="utf-8")
    states.append(orch.status(store))
    (store.analysis_dir / "overview.md").write_text("x", encoding="utf-8")
    (store.analysis_dir / "global.md").write_text("x", encoding="utf-8")
    states.append(orch.status(store))

    for data in states:
        for task in data.get("next_tasks") or []:
            done = task.get("done_when") or {}
            if "cmd" in done:
                seen_cmds.add(str(done["cmd"]))
                assert str(done["cmd"]) in registered, (task, registered)
            # file 型判据不得是空串，避免「指针指向不存在处」
            if "file" in done:
                assert done["file"]
    assert seen_cmds, "测试未覆盖任何 cmd 型指针"


def test_cli_error_contract_exit_codes_and_chinese_messages(tmp_path: Path) -> None:
    """可预期错误：非零退出码 + 中文提示 + 不打印 traceback（机器/人类契约）。"""
    missing = runner.invoke(app, ["status", "--workspace", str(tmp_path / "nope")])
    assert missing.exit_code != 0
    assert "Traceback" not in missing.output
    assert "工作区" in missing.output

    bad_src = tmp_path / "x.unknown"
    bad_src.write_text("x", encoding="utf-8")
    bad_init = runner.invoke(app, ["init", str(bad_src), "--workspace", str(tmp_path / "ws2")])
    assert bad_init.exit_code != 0
    assert "Traceback" not in bad_init.output
    assert "不支持" in bad_init.output or "初始化" in bad_init.output

    unknown = runner.invoke(app, ["definitely-not-a-command"])
    assert unknown.exit_code == 2  # typer 用法错误


def test_status_json_is_stdout_only_and_parseable_under_long_titles(tmp_path: Path) -> None:
    """机器协议：长标题下 `--json` 仍是可解析 JSON（不被 Rich 折行污染）。"""
    src = tmp_path / "book.md"
    title = "一部标题非常非常长的书" * 8
    src.write_text(f"# {title}\n\n第一句话。\n", encoding="utf-8")
    ws = tmp_path / "ws"
    assert runner.invoke(app, ["init", str(src), "--workspace", str(ws)]).exit_code == 0
    result = runner.invoke(app, ["status", "--workspace", str(ws), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["notes"]["registered"] is None
    assert data["report"]["exists"] is False
