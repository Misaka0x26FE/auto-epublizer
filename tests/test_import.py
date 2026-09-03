"""路径 B（agent 手写产物）集成测试：import / g0 / 术语冲突外置 / build 闭环。"""

from __future__ import annotations

import json
from pathlib import Path

from auto_epublizer import orchestrator as orch


def _workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter I\n\nFirst sentence here.\n\nSecond sentence here.\n", encoding="utf-8"
    )
    return orch.init(str(src), workspace_dir=tmp_path / "ws")


def _write_agent_products(store, *, broken: bool = False) -> None:
    """模拟 agent 手写：译文 + align（broken=True 时制造 seq 断号）。"""
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n第一句话。\n\n第二句话。\n", encoding="utf-8"
    )
    rows = [
        {"seq": 1, "src": "First sentence here.", "tgt": "第一句话。", "note": None},
        {"seq": 2, "src": "Second sentence here.", "tgt": "第二句话。", "note": None},
    ]
    if broken:
        rows[1]["seq"] = 3  # 断号
    (store.translation_dir / "align").mkdir(parents=True, exist_ok=True)
    with open(store.unit_align_path("ch01"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_import_registers_agent_products_and_advances_state(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    _write_agent_products(store)
    result = orch.import_translations(store)
    assert result["imported"] == ["ch01"]
    assert result["failed"] == []
    assert store.load_publication().units[0].status == "aligned"

    # build 不需要 LLM，直接从译文封装
    epub = orch.build(store)
    assert epub.is_file()


def test_import_blocks_on_broken_align(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    _write_agent_products(store, broken=True)
    result = orch.import_translations(store)
    assert result["imported"] == []
    assert result["failed"][0]["unit"] == "ch01"
    assert any("seq 不连续" in e for e in result["failed"][0]["errors"])
    # 状态不得推进
    assert store.load_publication().units[0].status == "split"


def test_import_reports_missing_files(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    result = orch.import_translations(store)
    assert result["imported"] == []
    assert any("缺少译文文件" in e for e in result["failed"][0]["errors"])
    assert any("缺少对照表" in e for e in result["failed"][0]["errors"])


def test_import_detects_glossary_conflicts(tmp_path: Path) -> None:
    """agent 更新术语表后 import 应把冲突外置到 glossary_conflicts.jsonl（阶段 3 接线）。"""
    store = _workspace(tmp_path)
    _write_agent_products(store)
    store.analysis_dir.mkdir(parents=True, exist_ok=True)
    glossary = store.analysis_dir / "glossary.csv"
    glossary.write_text(
        "source,target,type,aliases,gender,reading,status,note\n"
        "zone,赤区,term,,,,confirmed,\n"
        "zone,苏区,term,,,,seed,\n",
        encoding="utf-8",
    )
    result = orch.import_translations(store)
    assert result["imported"] == ["ch01"]
    assert result["conflicts_open"] >= 1
    conflicts = json.loads(
        (store.analysis_dir / "glossary_conflicts.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert conflicts["source"] == "zone"
    assert set(conflicts["targets"]) == {"赤区", "苏区"}


def test_import_terms_option_proposes_new_entries(tmp_path: Path) -> None:
    """--terms 导入新术语提案 → seed 落入 glossary.csv。"""
    store = _workspace(tmp_path)
    _write_agent_products(store)
    store.analysis_dir.mkdir(parents=True, exist_ok=True)
    terms_file = tmp_path / "new_terms.csv"
    terms_file.write_text(
        "source,target,type,aliases,gender,reading,status,note\ncriticize,批评,term,,,,seed,\n",
        encoding="utf-8",
    )
    orch.import_translations(store, terms_path=str(terms_file))
    content = (store.analysis_dir / "glossary.csv").read_text(encoding="utf-8")
    assert "criticize" in content and "批评" in content


def test_g0_check_reports_flags(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    _write_agent_products(store)
    orch.import_translations(store)
    result = orch.g0_check(store)
    assert "ch01" in result["checked_units"]
    # 长度比英文→中文可能告警，但结构上不应有 align 断号
    assert all(f["check"] in ("length", "terminology") for f in result["flags"])
