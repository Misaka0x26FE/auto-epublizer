"""CLI 测试：命令解析、无 LLM 命令链路、错误提示（CliRunner）。"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from auto_common.llm.providers.fake import FakeClient
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


def test_analyze_with_fake_client(tmp_path: Path, monkeypatch) -> None:
    import auto_epublizer.cli as cli_mod

    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nSome text here.\n", encoding="utf-8")
    ws = tmp_path / "ws"
    _invoke("convert", str(src), "--workspace", str(ws))

    client = FakeClient()
    client.enqueue("概览。")
    client.enqueue("全局。")
    client.enqueue("单元理解。")
    client.enqueue_json([])
    client.enqueue_json([])
    monkeypatch.setattr(cli_mod.orch, "make_client", lambda cfg: client)

    result = _invoke("analyze", "--workspace", str(ws / "book"))
    assert "分析完成" in result.output


def test_translate_with_fake_client(tmp_path: Path, monkeypatch) -> None:
    import auto_epublizer.cli as cli_mod

    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nSome text here.\n", encoding="utf-8")
    ws = tmp_path / "ws"
    _invoke("convert", str(src), "--workspace", str(ws))

    client = FakeClient()
    client.enqueue_json({"translations": [["第一章"], ["一些文本。"]]})
    monkeypatch.setattr(cli_mod.orch, "make_client", lambda cfg: client)

    result = _invoke("translate", "--workspace", str(ws / "book"))
    assert "翻译完成" in result.output
