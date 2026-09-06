"""CLI 测试：命令解析、确定性命令链路、错误提示（CliRunner）。"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from auto_epublizer.cli import app

runner = CliRunner()


def _invoke(*args: str) -> CliRunner:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result


def test_version() -> None:
    result = _invoke("version")
    assert "auto-epublizer" in result.output


def test_init_and_status(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    ws = tmp_path / "ws"
    _invoke("init", str(src), "--workspace", str(ws))
    result = _invoke("status", "--workspace", str(ws), "--json")
    assert '"slug": "book"' in result.output
    # P0 回归：init 即完成四层结构拆分（CLI help 与文档承诺）
    assert (ws / "book" / "structured" / "body" / "ch01.md").is_file()
    assert '"status": "split"' in result.output


def test_convert_end_to_end(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    ws = tmp_path / "ws"
    result = _invoke("convert", str(src), "--workspace", str(ws))
    assert "已生成" in result.output
    assert (ws / "book" / "output" / "book.epub").is_file()


def test_init_missing_file_errors(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["init", str(tmp_path / "nope.md"), "--workspace", str(tmp_path / "w")]
    )
    assert result.exit_code != 0
    assert "失败" in result.output or "错误" in result.output


def test_status_requires_workspace(tmp_path: Path) -> None:
    result = runner.invoke(app, ["status", "--workspace", str(tmp_path / "nope")])
    assert result.exit_code != 0


def test_llm_commands_removed(tmp_path: Path) -> None:
    """唯一 LLM 原则：analyze/translate/review 命令已移除（语义工作是 agent 任务）。"""
    for name in ("analyze", "translate", "review"):
        result = runner.invoke(app, [name, "--workspace", str(tmp_path)])
        assert result.exit_code != 0
        assert "No such command" in result.output


def test_meta_command_updates_fields(tmp_path: Path) -> None:
    """S2.1：meta 命令更新元数据 + events 账本；空串清空；无参数报错。"""
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    ws = tmp_path / "ws"
    _invoke("init", str(src), "--workspace", str(ws))
    pub_path = ws / "book" / "publication.json"

    result = _invoke(
        "meta", "--translator", "OpenCode", "--publisher", "Test Press", "--workspace", str(ws)
    )
    assert "已更新" in result.output
    data = json.loads(pub_path.read_text(encoding="utf-8"))
    assert data["meta"]["translator"] == "OpenCode"
    assert data["meta"]["publisher"] == "Test Press"
    events = (ws / "book" / "events.jsonl").read_text(encoding="utf-8")
    assert '"meta_update"' in events and "translator" in events

    # 空串清空
    _invoke("meta", "--translator", "", "--workspace", str(ws))
    data = json.loads(pub_path.read_text(encoding="utf-8"))
    assert data["meta"]["translator"] == ""

    # 无任何字段 → 明确报错（helper 断言成功，这里要失败，直接 invoke）
    result = runner.invoke(app, ["meta", "--workspace", str(ws)])
    assert result.exit_code != 0
    assert "未指定" in result.output
