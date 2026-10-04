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


def test_status_json_is_parseable_with_newline_bearing_titles(tmp_path: Path) -> None:
    """回归：`status --json` 曾被 Rich 按终端宽度硬换行，输出不是合法 JSON。

    长中文书名或含内嵌换行的单元标题必然触发，json.loads 报 Invalid control
    character —— 而 --json 的唯一用途就是给机器读。
    """
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    ws = tmp_path / "ws"
    _invoke("init", str(src), "--workspace", str(ws))

    pub_path = ws / "book" / "publication.json"
    pub = json.loads(pub_path.read_text(encoding="utf-8"))
    # 故意塞入长中文书名 + 含换行的单元标题（真实 PDF 抽取的常见形态）
    pub["meta"]["title"] = (
        "强制劳动与灭绝：党卫队的经济帝国——奥斯瓦尔德·波尔与党卫队经济管理总局（1933—1945）"
    )
    pub["units"][0]["title"] = (
        "1. Allocation of Inmates to the Central Construction\nOffice\nfor Work"
    )
    pub_path.write_text(json.dumps(pub, ensure_ascii=False, indent=2), encoding="utf-8")

    result = _invoke("status", "--workspace", str(ws), "--json")
    data = json.loads(result.output)  # 解析失败即回归
    assert data["preprocessing_complete"] is False
    assert "1945" in data["title"]
    assert "\n" in data["units"][0]["title"]


def test_status_json_not_mangled_by_rich_markup(tmp_path: Path) -> None:
    """回归：console.print 还会把书名里的 ``[bold]`` 之类当 Rich 标记解析掉。"""
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    ws = tmp_path / "ws"
    _invoke("init", str(src), "--workspace", str(ws))

    pub_path = ws / "book" / "publication.json"
    pub = json.loads(pub_path.read_text(encoding="utf-8"))
    pub["meta"]["title"] = "序言 [bold]与[/bold] 附录"
    pub_path.write_text(json.dumps(pub, ensure_ascii=False, indent=2), encoding="utf-8")

    data = json.loads(_invoke("status", "--workspace", str(ws), "--json").output)
    assert data["title"] == "序言 [bold]与[/bold] 附录"


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


def test_qa_prints_release_reason(tmp_path: Path) -> None:
    """回归 #8：放行失败时控制台必须给出原因（否则只能去翻 report.json）。"""
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    ws = tmp_path / "ws"
    _invoke("init", str(src), "--workspace", str(ws))
    # init 的 --workspace 是「根目录」，实际工作区是 <根>/<slug>/
    book = ws / "book"
    pre = book / "preprocessing"
    pre.mkdir(parents=True, exist_ok=True)
    (pre / "catalog.csv").write_text(
        "item,kind,status,locator,unit_id,note\n未知插图,figure,unresolved,page ??,,待确认\n",
        encoding="utf-8",
    )
    _invoke("build", "--workspace", str(book))
    out = _invoke("qa", "--workspace", str(book)).output
    assert "G5 放行：否（原因：catalog_open）" in out


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
