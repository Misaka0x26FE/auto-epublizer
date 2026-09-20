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


def test_import_reports_untranslated_as_pending(tmp_path: Path) -> None:
    """回归 #8：未译单元记入 `pending`（待译），不再计为 failed。

    旧行为把「还没有译文」当失败处理，并继续跑文档/表格/术语检查——于是源文的每个块
    都刷一条「源文块未进对照表」告警（现场：4 个已译 + 12 个未译 → 1318 条无效告警）。
    """
    store = _workspace(tmp_path)
    result = orch.import_translations(store)
    assert result["imported"] == []
    assert result["failed"] == []
    assert [p["unit"] for p in result["pending"]] == ["ch01"]
    assert any("缺少译文文件" in r for r in result["pending"][0]["reasons"])
    assert any("缺少对照表" in r for r in result["pending"][0]["reasons"])
    # 未译单元不产出任何告警（旧实现会为源文每个块刷 fidelity 前向缺块）
    assert result["warnings"] == []
    # 状态不得推进
    assert store.load_publication().units[0].status == "split"


def test_build_fallback_does_not_block_later_import(tmp_path: Path) -> None:
    """回归 #8：源文回退打包的单元不推进 built，之后补的译文仍能 import。

    旧行为：build 无条件把每个单元置 `built`，而 import 跳过 `built`——于是按
    「每 3–5 单元 build 一次」做冒烟构建后，登记路径整体失效（现场只能靠伪造结构
    变更把状态回退到 split）。
    """
    store = _workspace(tmp_path)
    epub = orch.build(store)  # 无译文 → 打包源文
    assert epub.is_file()
    assert store.load_publication().units[0].status == "split"

    _write_agent_products(store)  # 之后补上译文
    result = orch.import_translations(store)
    assert result["imported"] == ["ch01"]
    assert result["skipped"] == []
    assert store.load_publication().units[0].status == "aligned"

    orch.build(store)  # 有译文时 build 照常推进
    assert store.load_publication().units[0].status == "built"


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


def test_import_reviewed_marks_aligned_units(tmp_path: Path) -> None:
    """--reviewed：把 aligned 单元推进为 reviewed（幂等，reviewed/built 不动）。"""
    store = _workspace(tmp_path)
    _write_agent_products(store)
    orch.import_translations(store)  # → aligned
    result = orch.import_translations(store, mark_reviewed=True)
    assert result["reviewed"] == ["ch01"]
    assert store.load_publication().units[0].status == "reviewed"
    # 幂等：再次 --reviewed 不重复推进
    result2 = orch.import_translations(store, mark_reviewed=True)
    assert result2["reviewed"] == []
    assert store.load_publication().units[0].status == "reviewed"


def test_import_blocks_on_rewritten_src(tmp_path: Path) -> None:
    """S4.1：align src 与 structured 原文失配（改写/抄错）→ 阻断该单元登记。"""
    store = _workspace(tmp_path)
    _write_agent_products(store)
    # 把 align 的 src 改成源文里没有的句子
    rows = [
        {"seq": 1, "src": "First sentence here, buddy.", "tgt": "第一句话，伙计。"},
        {"seq": 2, "src": "Second sentence here.", "tgt": "第二句话。"},
    ]
    with open(store.unit_align_path("ch01"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    result = orch.import_translations(store)
    assert result["imported"] == []
    assert any("不在源文中" in e for e in result["failed"][0]["errors"])
    assert store.load_publication().units[0].status == "split"


def test_import_blocks_on_broken_table(tmp_path: Path) -> None:
    """S4.2：译文表格行列数与源不一致 → import 阻断（表格形状）。"""
    store = _workspace(tmp_path)
    # 源文加一张 3 行表
    src_path = store.structured_dir / "body" / "ch01.md"
    src_path.write_text(
        "# Chapter I\n\nFirst sentence here.\n\nSecond sentence here.\n\n"
        "| a | b |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n",
        encoding="utf-8",
    )
    _write_agent_products(store)
    # 译文表格少一行
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n第一句话。\n\n第二句话。\n\n| 甲 | 乙 |\n| --- | --- |\n| 一 | 二 |\n",
        encoding="utf-8",
    )
    result = orch.import_translations(store)
    assert result["imported"] == []
    assert any("表格形状" in e for e in result["failed"][0]["errors"])


def test_import_blocks_on_md_align_drift(tmp_path: Path) -> None:
    """交付审计 S1.1：md 与 align tgt 不一致（一侧缺内容）→ 阻断登记。"""
    store = _workspace(tmp_path)
    _write_agent_products(store)
    # md 删掉第二句（align 仍完整）——真实案例：md 丢图片段/脚注直达成品
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n第一句话。\n", encoding="utf-8"
    )
    result = orch.import_translations(store)
    assert result["imported"] == []
    assert result["failed"] and result["failed"][0]["unit"] == "ch01"
    assert any("文档一致性" in e for e in result["failed"][0]["errors"])


def test_import_passes_md_align_consistent_with_footnote(tmp_path: Path) -> None:
    """交付审计 S1.1 回归：md 含标题/脚注、align 对应 → 正常登记（不误报漂移）。"""
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence[^1].\n\n[^1]: Source note.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n第一句话[^1]。\n\n[^1]: 注释文本。\n", encoding="utf-8"
    )
    rows = [
        {"seq": 1, "src": "First sentence[^1].", "tgt": "第一句话[^1]。", "note": None},
        {"seq": 2, "src": "[^1]: Source note.", "tgt": "[^1]: 注释文本。", "note": None},
    ]
    with open(store.unit_align_path("ch01"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    result = orch.import_translations(store)
    assert result["imported"] == ["ch01"], result["failed"]
