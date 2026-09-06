"""S4.4 SourceCatalog 最小形态：catalog.csv 契约校验 + status/qa 接线。"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_epublizer import orchestrator as orch


def _workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter I\n\nFirst sentence here.\n\nSecond sentence here.\n", encoding="utf-8"
    )
    return orch.init(str(src), workspace_dir=tmp_path / "ws")


def _write_catalog(store, rows: list[str]) -> None:
    store.preprocessing_dir.mkdir(parents=True, exist_ok=True)
    lines = ["item,kind,status,locator,unit_id,note", *rows]
    (store.preprocessing_dir / "catalog.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_read_catalog_none_when_missing(tmp_path: Path) -> None:
    """catalog.csv 不存在 → None（零破坏）。"""
    store = _workspace(tmp_path)
    assert orch.read_catalog(store) is None


def test_read_catalog_valid_and_contract_errors(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    _write_catalog(
        store,
        [
            "Chapter I,toc,included,page 1,ch01,",
            "Dust jacket,physical,physical,cover,,有意不进 EPUB",
            "Old preface,section,excluded,page ix,,重复内容，作者后删",
        ],
    )
    rows = orch.read_catalog(store)
    assert rows is not None and len(rows) == 3
    assert rows[0]["unit_id"] == "ch01"

    # kind 非法
    _write_catalog(store, ["X,badkind,included,p1,ch01,"])
    with pytest.raises(orch.OrchestrationError, match="kind 非法"):
        orch.read_catalog(store)

    # included 缺 unit_id
    _write_catalog(store, ["X,toc,included,p1,,"])
    with pytest.raises(orch.OrchestrationError, match="unit_id"):
        orch.read_catalog(store)

    # excluded 缺理由
    _write_catalog(store, ["X,toc,excluded,p1,,"])
    with pytest.raises(orch.OrchestrationError, match="理由"):
        orch.read_catalog(store)


def test_status_catalog_binding(tmp_path: Path) -> None:
    """status：included 绑定到存在单元 → bound；指向不存在单元 → stale 提示。"""
    store = _workspace(tmp_path)
    _write_catalog(store, ["Chapter I,toc,included,page 1,ch01,"])
    data = orch.status(store)
    assert data["catalog"] == {"present": True, "items": 1, "included_bound": True, "unresolved": 0}

    _write_catalog(store, ["Ghost,toc,included,page 9,nope,"])
    data = orch.status(store)
    assert data["catalog"]["included_bound"] is False
    assert any(s["id"] == "catalog" for s in data["stale"])


def test_qa_catalog_unresolved_blocks_release(tmp_path: Path) -> None:
    """qa：catalog 含 unresolved → catalog_unresolved_open>0 → 不放行（reason=catalog_open）。"""

    store = _workspace(tmp_path)
    _write_catalog(
        store,
        [
            "Chapter I,toc,included,page 1,ch01,",
            "Unknown figure,figure,unresolved,page ??,,待确认是否插图",
        ],
    )
    # 最小成品（qa 需要 epub 存在；两句全译避免 fidelity 前向缺块干扰 reason）
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# Chapter I\n\n第一句。\n\n第二句。\n", encoding="utf-8"
    )
    import json

    rows = [
        {"seq": 1, "src": "First sentence here.", "tgt": "第一句。", "note": None},
        {"seq": 2, "src": "Second sentence here.", "tgt": "第二句。", "note": None},
    ]
    (store.translation_dir / "align").mkdir(parents=True, exist_ok=True)
    with open(store.unit_align_path("ch01"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    orch.import_translations(store)
    epub = orch.build(store)
    result = orch.qa(store, epub_path=str(epub))
    assert result["catalog_unresolved_open"] == 1
    assert result["released"] is False
    assert result["released_reason"] == "catalog_open"


def test_generate_report_catalog_open() -> None:
    """report 级：catalog_unresolved_open=1 → 不放行，reason=catalog_open。"""
    from auto_epublizer.qa import AuditResult, EpubcheckResult, generate_report

    result = generate_report(
        "book",
        AuditResult(ok=True),
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0),
        review={
            "g1_candidates": 0,
            "g2_confirmed": 0,
            "g3_patched": 0,
            "termination": "clean_confirmed",
            "rounds": 1,
        },
        g0_flags=[],
        total_sentences=10,
        catalog_unresolved_open=1,
    )
    assert result.released is False
    assert result.released_reason == "catalog_open"
