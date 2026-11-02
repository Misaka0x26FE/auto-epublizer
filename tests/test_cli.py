"""CLI 测试：命令解析、确定性命令链路、错误提示（CliRunner）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
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


def test_status_json_not_corrupted_by_rich_wrapping(tmp_path: Path) -> None:
    """回归（2026-10-05 真书实测）：长标题不得被 rich 折行，--json 必须可解析。"""
    src = tmp_path / "book.md"
    src.write_text("# " + "A" * 300 + "\n\n正文。\n", encoding="utf-8")
    ws = tmp_path / "ws"
    _invoke("init", str(src), "--workspace", str(ws))
    result = _invoke("status", "--workspace", str(ws), "--json")
    data = json.loads(result.output)  # 折行会抛 JSONDecodeError
    assert data["next_tasks"]


@pytest.mark.parametrize("artifact", ["catalog.csv", "repairs.jsonl"])
def test_status_json_contract_error_is_structured(tmp_path: Path, artifact: str) -> None:
    src = tmp_path / "book.md"
    src.write_text("# One\n\nBody.\n", encoding="utf-8")
    _invoke("init", str(src), "--workspace", str(tmp_path / "ws"))
    ws = tmp_path / "ws/book"
    content = (
        "item,kind,status,locator,unit_id,note\nX,bad,included,p1,ch01,\n"
        if artifact == "catalog.csv"
        else json.dumps(
            {
                "unit": "ch01",
                "kind": "ocr_char",
                "status": "done",
                "summary": "修复",
                "evidence": "missing.png",
            }
        )
        + "\n"
    )
    (ws / "preprocessing" / artifact).write_text(content, encoding="utf-8")

    result = runner.invoke(app, ["status", "--json", "--workspace", str(ws)])

    assert result.exit_code != 0
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "E_ARTIFACT_CONTRACT"
    assert error["artifact"] == artifact
    assert error["line"] == (2 if artifact == "catalog.csv" else 1)
    assert error["field"] == ("kind" if artifact == "catalog.csv" else "evidence")


def test_status_json_missing_workspace_is_structured(tmp_path: Path) -> None:
    result = runner.invoke(app, ["status", "--json", "--workspace", str(tmp_path)])
    assert result.exit_code != 0
    assert json.loads(result.stdout)["error"]["code"] == "E_INPUT"


@pytest.mark.parametrize("command", ["build", "qa", "import", "g0"])
def test_pipeline_json_missing_workspace_is_structured(tmp_path: Path, command: str) -> None:
    result = runner.invoke(app, [command, "--json", "--workspace", str(tmp_path)])
    assert result.exit_code != 0
    assert json.loads(result.stdout)["error"]["code"] == "E_INPUT"


def test_pipeline_json_outputs_results_without_text_noise(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# One\n\nBody.\n", encoding="utf-8")
    _invoke("init", str(src), "--workspace", str(tmp_path / "ws"))
    ws = tmp_path / "ws/book"

    built = json.loads(_invoke("build", "--json", "--workspace", str(ws)).stdout)
    assert Path(built["epub"]).is_file()
    assert built["fallback_units"] == ["ch01"]
    imported = json.loads(_invoke("import", "--json", "--workspace", str(ws)).stdout)
    assert imported["pending"][0]["unit"] == "ch01"
    checked = json.loads(_invoke("g0", "--json", "--workspace", str(ws)).stdout)
    assert "checked_units" in checked and "flags" in checked
    qa = json.loads(_invoke("qa", "--json", "--workspace", str(ws)).stdout)
    assert qa["released"] == json.loads((ws / "report.json").read_text())["released"]
    rows = json.loads(_invoke("ledger", "--json", "--workspace", str(tmp_path / "ws")).stdout)
    assert rows[0]["slug"] == "book"


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
        "强制劳动与灭绝：党卫队的经济帝国——奥斯瓦尔德·波尔与示例标准署（1933—1945）"
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


def test_qa_flags_block_boundary_change_after_import(tmp_path: Path) -> None:
    """#87/B2：import 后把两段合成一段（全文归一化仍相等）必须被 qa 定位。"""
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter I\n\nFirst sentence here.\n\nSecond sentence here.\n", encoding="utf-8"
    )
    _invoke("init", str(src), "--workspace", str(tmp_path / "ws"))
    book = tmp_path / "ws/book"
    target = book / "translation/body/ch01.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# 第一章\n\n第一句话。\n\n第二句话。\n", encoding="utf-8")
    align = book / "translation/align/ch01.jsonl"
    align.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"seq": 1, "src": "First sentence here.", "tgt": "第一句话。", "note": None},
        {"seq": 2, "src": "Second sentence here.", "tgt": "第二句话。", "note": None},
    ]
    align.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    _invoke("import", "--workspace", str(book))
    assert store_baseline(book)  # 基线已随 import 登记

    target.write_text("# 第一章\n\n第一句话。第二句话。\n", encoding="utf-8")
    _invoke("build", "--workspace", str(book))
    payload = json.loads(_invoke("qa", "--json", "--workspace", str(book)).stdout)
    assert payload["align_md_drift"] >= 1
    assert not payload["released"]
    messages = json.dumps(payload["provenance_findings"], ensure_ascii=False)
    assert "块边界" in messages


def store_baseline(book: Path) -> str:
    data = json.loads((book / "publication.json").read_text(encoding="utf-8"))
    return str(data["units"][0]["meta"].get("align_structure") or "")


def test_align_propose_is_read_only(tmp_path: Path) -> None:
    """B3：提案只读，返回映射与未覆盖块，不改工作区任何文件。"""
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.\n", encoding="utf-8")
    _invoke("init", str(src), "--workspace", str(tmp_path / "ws"))
    book = tmp_path / "ws/book"
    target = book / "translation/body/ch01.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# 第一章\n\n第一句。\n", encoding="utf-8")
    align = book / "translation/align/ch01.jsonl"
    align.parent.mkdir(parents=True, exist_ok=True)
    align.write_text(
        json.dumps(
            {"seq": 1, "src": "First sentence.", "tgt": "第一句。", "note": None},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    before = {path: path.stat().st_mtime_ns for path in book.rglob("*") if path.is_file()}
    payload = json.loads(_invoke("align-propose", "--workspace", str(book)).stdout)
    assert payload["writes"] is False
    assert payload["units"][0]["mappings"][0]["status"] == "exact"
    assert payload["units"][0]["uncovered"] == []
    after = {path: path.stat().st_mtime_ns for path in book.rglob("*") if path.is_file()}
    assert before == after


def test_align_apply_cli_dry_run(tmp_path: Path) -> None:
    """B4：CLI 默认只读预检，计划绑定翻译/对照表摘要。"""
    import hashlib

    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence here.\n", encoding="utf-8")
    _invoke("init", str(src), "--workspace", str(tmp_path / "ws"))
    book = tmp_path / "ws/book"
    target = book / "translation/body/ch01.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# 第一章\n\n第一句。\n", encoding="utf-8")
    align = book / "translation/align/ch01.jsonl"
    align.parent.mkdir(parents=True, exist_ok=True)
    align.write_text(
        json.dumps(
            {"seq": 1, "src": "First sentence here.", "tgt": "第一句。", "note": None},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _invoke("import", "--workspace", str(book))
    pub = json.loads((book / "publication.json").read_text(encoding="utf-8"))
    plan = {
        "schema_version": "1",
        "rule_version": "align-rebuild-1",
        "source_sha256": pub["meta"]["source_sha256"],
        "units": [
            {
                "unit": "ch01",
                "translation_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "align_sha256": hashlib.sha256(align.read_bytes()).hexdigest(),
                "rows": [
                    {"seq": 1, "src": "First sentence here.", "tgt": "第一句。", "note": "rebuilt"}
                ],
                "approved": True,
            }
        ],
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    before = align.read_bytes()
    payload = json.loads(_invoke("align-apply", str(plan_path), "--workspace", str(book)).stdout)
    assert payload["status"] == "dry_run"
    assert align.read_bytes() == before


def test_hygiene_cli_is_read_only(tmp_path: Path) -> None:
    """C1：卫生扫描输出候选 JSON，不改译文。"""
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nBody.\n", encoding="utf-8")
    _invoke("init", str(src), "--workspace", str(tmp_path / "ws"))
    book = tmp_path / "ws/book"
    target = book / "translation/body/ch01.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# 第一章\n\n他说“没有说完。\n", encoding="utf-8")
    before = target.read_bytes()
    payload = json.loads(_invoke("hygiene", "--workspace", str(book)).stdout)
    assert payload["writes"] is False
    assert payload["counts"]["unbalanced_quote"] == 1
    assert target.read_bytes() == before


def test_evidence_layout_cli_is_read_only(tmp_path: Path) -> None:
    """C2：evidence layout 输出只读版面候选。"""
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nBody.\n", encoding="utf-8")
    _invoke("init", str(src), "--workspace", str(tmp_path / "ws"))
    book = tmp_path / "ws/book"
    raw = book / "structured/raw/page-001.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(
        json.dumps(
            {
                "page_idx": 1,
                "blocks": [
                    {
                        "type": "text",
                        "text": "左栏。",
                        "bbox": [50, 100, 250, 140],
                        "font_size": 10,
                    },
                    {
                        "type": "text",
                        "text": "右栏。",
                        "bbox": [320, 100, 520, 140],
                        "font_size": 10,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    before = raw.read_bytes()
    payload = json.loads(_invoke("evidence", "layout", "--workspace", str(book), "--json").stdout)
    assert payload["writes"] is False
    assert payload["pages"][0]["columns"] == 2
    assert raw.read_bytes() == before


def test_evidence_toc_cli_is_read_only(tmp_path: Path) -> None:
    """D1：目录来源模型输出结构视图与原版行去向，不改工作区。"""
    src = tmp_path / "book.md"
    src.write_text(
        "# Contents\n\nChapter One 3\n\n# Part One\n\nBody.\n\n## Chapter One\n\nBody.\n",
        encoding="utf-8",
    )
    _invoke("init", str(src), "--workspace", str(tmp_path / "ws"))
    book = tmp_path / "ws/book"
    pub = book / "publication.json"
    before = pub.read_bytes()
    payload = json.loads(_invoke("evidence", "toc", "--workspace", str(book), "--json").stdout)
    assert payload["writes"] is False
    assert payload["nodes"]
    assert payload["original"][0]["entries"][0]["label"] == "Chapter One"
    assert pub.read_bytes() == before


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


def test_qa_exposes_missing_source_blocks_in_json_and_text(tmp_path: Path) -> None:
    """#90：真实 QA 链路导出缺段身份和预览，不需调用私有复算函数。"""
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n第一段。\n\n遗漏的第二段。\n", encoding="utf-8")
    _invoke("init", str(src), "--workspace", str(tmp_path / "ws"))
    book = tmp_path / "ws/book"
    align = book / "translation/align/ch01.jsonl"
    align.parent.mkdir(parents=True, exist_ok=True)
    align.write_text(json.dumps({"seq": 1, "src": "第一段。", "tgt": "第一段。"}) + "\n")
    _invoke("build", "--workspace", str(book))
    payload = json.loads(_invoke("qa", "--json", "--workspace", str(book)).stdout)
    assert payload["coverage_missing"] == ["ch01:2"]
    assert payload["coverage_missing_details"][0]["preview"] == "遗漏的第二段。"
    saved = json.loads((book / "report.json").read_text())
    assert saved["coverage_missing_details"] == payload["coverage_missing_details"]
    output = _invoke("qa", "--workspace", str(book)).stdout
    assert "ch01:2" in output
    assert "遗漏的第二段。" in output


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


def test_meta_generation_tools_json_round_trip_and_errors(tmp_path: Path) -> None:
    """--generation-tools：JSON 数组写回（[] 表示未使用）；坏 JSON/非数组明确报错。"""
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    ws = tmp_path / "ws"
    _invoke("init", str(src), "--workspace", str(ws))
    pub_path = ws / "book" / "publication.json"
    tools = [{"name": "DeepSeek-V3", "version": "2026-10", "task": "翻译"}]

    _invoke("meta", "--generation-tools", json.dumps(tools), "--workspace", str(ws))
    data = json.loads(pub_path.read_text(encoding="utf-8"))
    assert data["meta"]["generation_tools"] == tools

    _invoke("meta", "--generation-tools", "[]", "--workspace", str(ws))
    data = json.loads(pub_path.read_text(encoding="utf-8"))
    assert data["meta"]["generation_tools"] == []

    for bad in ("{broken", "{}", '["DeepSeek-V3"]', '[{"name": 3}]'):
        result = runner.invoke(app, ["meta", "--generation-tools", bad, "--workspace", str(ws)])
        assert result.exit_code != 0, bad
        assert "generation-tools" in result.output, bad
    # 坏输入不得覆盖已写回的值（不是静默 no-op）
    data = json.loads(pub_path.read_text(encoding="utf-8"))
    assert data["meta"]["generation_tools"] == []
