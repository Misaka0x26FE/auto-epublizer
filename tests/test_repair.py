"""语义整备留痕契约测试（S2）：repairs.jsonl 校验 + qa 报告与提示。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_epublizer import orchestrator as orch
from auto_translator.translation.align import write_align


def _workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nBody text.\n", encoding="utf-8")
    return orch.init(str(src), workspace_dir=str(tmp_path / "ws"))


def _write_repairs(store, rows: list[dict]) -> None:
    p = store.preprocessing_dir / "repairs.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )


def test_read_repairs_absent_none(tmp_path: Path) -> None:
    """无留痕文件 → None（零破坏：老工作区/convert 路径无感）。"""
    assert orch.read_repairs(_workspace(tmp_path)) is None


def test_read_repairs_valid(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    _write_repairs(
        store,
        [
            {
                "unit": "ch01",
                "kind": "line_join",
                "pages": [1],
                "count": 3,
                "summary": "重断段",
                "status": "done",
            },
            {"unit": "ch01", "kind": "ocr_char", "summary": "存疑", "status": "unresolved"},
        ],
    )
    rows = orch.read_repairs(store)
    assert rows is not None and len(rows) == 2 and rows[1]["status"] == "unresolved"


@pytest.mark.parametrize(
    "row,fragment",
    [
        ({"unit": "nope", "kind": "line_join", "summary": "x", "status": "done"}, "unit 不存在"),
        ({"unit": "ch01", "kind": "bogus", "summary": "x", "status": "done"}, "kind 非法"),
        ({"unit": "ch01", "kind": "other", "summary": "x", "status": "nope"}, "status 非法"),
        ({"unit": "ch01", "kind": "other", "summary": "  ", "status": "done"}, "summary 必填"),
        (
            {
                "unit": "ch01",
                "kind": "other",
                "summary": "x",
                "evidence": "/etc/passwd",
                "status": "done",
            },
            "evidence",
        ),
        (
            {
                "unit": "ch01",
                "kind": "other",
                "summary": "x",
                "evidence": "structured/nope.png",
                "status": "done",
            },
            "evidence",
        ),
        (
            {"unit": "ch01", "kind": "other", "summary": "x", "pages": "1", "status": "done"},
            "pages",
        ),
        (
            {"unit": "ch01", "kind": "other", "summary": "x", "count": "3", "status": "done"},
            "count",
        ),
    ],
)
def test_read_repairs_contract_errors(tmp_path: Path, row: dict, fragment: str) -> None:
    store = _workspace(tmp_path)
    _write_repairs(store, [row])
    with pytest.raises(orch.OrchestrationError) as e:
        orch.read_repairs(store)
    assert fragment in str(e.value) and "第 1 行" in str(e.value)


def test_read_repairs_bad_json_line(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    p = store.preprocessing_dir / "repairs.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    valid = '{"unit": "ch01", "kind": "other", "summary": "x", "status": "done"}'
    p.write_text(f"{valid}\nnot-json\n", encoding="utf-8")
    with pytest.raises(orch.OrchestrationError) as e:
        orch.read_repairs(store)
    assert "第 2 行" in str(e.value)


def test_qa_reports_repairs_unresolved(tmp_path: Path) -> None:
    """unresolved 修复 → 报告计数 + W_REPAIR_UNRESOLVED 提示（不阻断放行，D2）。"""
    store = _workspace(tmp_path)
    rel = store.load_publication().units[0].meta["rel_path"]
    (store.translation_dir / rel).parent.mkdir(parents=True, exist_ok=True)
    (store.translation_dir / rel).write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    write_align(
        store.unit_align_path("ch01"),
        [{"seq": 1, "src": "Body text.", "tgt": "正文。", "note": None}],
    )
    assert orch.import_translations(store)["imported"] == ["ch01"]
    epub = orch.build(store)
    _write_repairs(
        store,
        [{"unit": "ch01", "kind": "ocr_char", "summary": "一格存疑", "status": "unresolved"}],
    )
    report = orch.qa(store, epub_path=str(epub))
    assert report["repairs_total"] == 1 and report["repairs_unresolved"] == 1
    assert any(f["code"] == "W_REPAIR_UNRESOLVED" for f in report["provenance_findings"])
