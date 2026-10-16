"""S1：status --json 的 next_tasks 机器指针（从状态机/产物对账派生，零 token 可测）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_common.config import Config
from auto_epublizer import orchestrator as orch

# 干净源文（无整备信号），两章 → 两个单元
_BOOK = "# Chapter I\n\n完整的一句话。\n\n# Chapter II\n\n另一段完整文字。\n"


def _ws(tmp_path: Path, text: str = _BOOK):
    src = tmp_path / "book.md"
    src.write_text(text, encoding="utf-8")
    return orch.init(str(src), workspace_dir=str(tmp_path / "ws"))


def _complete_preprocessing(tmp_path: Path):
    """走到「预处理理解产物齐全」的现场（facts + capabilities/global/todo）。"""
    store = _ws(tmp_path)
    orch.preprocess(store, config=Config())
    for name in ("capabilities.md", "global.md", "todo.md"):
        (store.preprocessing_dir / name).write_text("x", encoding="utf-8")
    return store


def test_next_tasks_preprocess_when_no_facts(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    data = orch.status(store)
    assert data["next_tasks"][0]["kind"] == "preprocess"
    assert data["next_tasks"][0]["done_when"] == {"cmd": "preprocess"}


def test_next_tasks_write_preprocessing_in_order(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    orch.preprocess(store, config=Config())
    heads = orch.status(store)["next_tasks"]
    assert [t["kind"] for t in heads] == ["write_preprocessing"]
    assert heads[0]["done_when"] == {"file": "preprocessing/capabilities.md"}

    (store.preprocessing_dir / "capabilities.md").write_text("x", encoding="utf-8")
    head = orch.status(store)["next_tasks"][0]
    assert head["done_when"] == {"file": "preprocessing/global.md"}

    (store.preprocessing_dir / "global.md").write_text("x", encoding="utf-8")
    head = orch.status(store)["next_tasks"][0]
    assert head["done_when"] == {"file": "preprocessing/todo.md"}


def test_next_tasks_analyze_batch_then_translate_one_unit(tmp_path: Path) -> None:
    store = _complete_preprocessing(tmp_path)
    batch = orch.status(store)["next_tasks"]
    assert batch and all(t["kind"] == "analyze" for t in batch)
    assert len(batch) <= 5  # 每批 ≤5，防弱模型贪多
    assert batch[0]["done_when"]["file"].startswith("analysis/units/")

    store.analysis_dir.mkdir(parents=True, exist_ok=True)
    (store.analysis_dir / "overview.md").write_text("x", encoding="utf-8")
    heads = orch.status(store)["next_tasks"]
    assert len(heads) == 1  # 翻译一次只给一个单元
    assert heads[0]["kind"] == "translate"
    assert heads[0]["done_when"] == {"cmd": "import", "unit": heads[0]["unit"]}


def test_next_tasks_stale_import(tmp_path: Path) -> None:
    store = _complete_preprocessing(tmp_path)
    store.analysis_dir.mkdir(parents=True, exist_ok=True)
    (store.analysis_dir / "overview.md").write_text("x", encoding="utf-8")
    unit = store.load_publication().units[0]
    align = store.unit_align_path(unit.id)
    align.parent.mkdir(parents=True, exist_ok=True)
    align.write_text('{"seq": 1, "src": "a", "tgt": "b", "note": null}\n', encoding="utf-8")
    head = orch.status(store)["next_tasks"][0]
    assert head["kind"] == "import"
    assert head["done_when"] == {"cmd": "import", "unit": unit.id}


def test_next_tasks_review_before_next_translate(tmp_path: Path) -> None:
    """单元级原子循环：已 aligned 的单元先审校，再翻下一个（实测修正）。"""
    store = _complete_preprocessing(tmp_path)
    store.analysis_dir.mkdir(parents=True, exist_ok=True)
    (store.analysis_dir / "overview.md").write_text("x", encoding="utf-8")
    first = store.load_publication().units[0]
    store.set_unit_status(first.id, "aligned")
    head = orch.status(store)["next_tasks"][0]
    assert head["kind"] == "review"
    assert head["unit"] == first.id


def test_next_tasks_review_then_build_qa_delivery(tmp_path: Path) -> None:
    store = _complete_preprocessing(tmp_path)
    pub = store.load_publication()
    for u in pub.units:
        store.set_unit_status(u.id, "reviewed")

    head = orch.status(store)["next_tasks"][0]
    assert head["kind"] == "build" and head["done_when"] == {"cmd": "build"}

    store.output_dir.mkdir(parents=True, exist_ok=True)
    (store.output_dir / f"{pub.slug}.epub").write_bytes(b"PK")
    head = orch.status(store)["next_tasks"][0]
    assert head["kind"] == "qa" and head["done_when"] == {"cmd": "qa"}

    store.report_path.write_text("{}", encoding="utf-8")
    head = orch.status(store)["next_tasks"][0]
    assert head["kind"] == "delivery"

    store.reviews_dir.mkdir(parents=True, exist_ok=True)
    (store.reviews_dir / "delivery-2026.md").write_text("ok", encoding="utf-8")
    assert orch.status(store)["next_tasks"] == []


def test_next_tasks_repair_before_analysis(tmp_path: Path) -> None:
    """可疑信号（乱码/硬折行）→ 先语义整备，再进理解层。"""
    store = _ws(tmp_path, "# Chapter I\n\nÃ© garbled line\nline without punct\n")
    orch.preprocess(store, config=Config())
    for name in ("capabilities.md", "global.md", "todo.md"):
        (store.preprocessing_dir / name).write_text("x", encoding="utf-8")
    head = orch.status(store)["next_tasks"][0]
    assert head["kind"] == "repair"
    assert head["done_when"] == {"file": "preprocessing/repairs.jsonl"}


def test_next_tasks_report_stale_not_routed_as_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2：报告过期（伪 stale 项）按 build→qa 分派，不得出现 `import --unit report`。"""
    from auto_epublizer.qa.artifacts import report_state
    from auto_epublizer.qa.epubcheck import EpubcheckResult

    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "root"))
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n第一句话。\n", encoding="utf-8"
    )
    (store.translation_dir / "align").mkdir(parents=True, exist_ok=True)
    (store.unit_align_path("ch01")).write_text(
        json.dumps(
            {"seq": 1, "src": "First sentence.", "tgt": "第一句话。", "note": None},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    orch.preprocess(store, config=Config())  # facts 也是放行输入（摘要覆盖）
    for _name in ("capabilities.md", "global.md", "todo.md"):
        (store.preprocessing_dir / _name).write_text("x", encoding="utf-8")
    review_dir = store.reviews_dir / "review-20261015T000000"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "result.json").write_text(
        json.dumps({"issue_count": 0, "g2_confirmed": 0, "termination": "clean_confirmed"}),
        encoding="utf-8",
    )
    orch.import_translations(store)
    for u in store.load_publication().units:
        store.set_unit_status(u.id, "reviewed")
    epub = orch.build(store)
    monkeypatch.setattr(
        orch, "run_epubcheck", lambda *a, **k: EpubcheckResult(True, True, 0, 0, returncode=0)
    )
    report = orch.qa(store, epub_path=str(epub))
    assert report["released"] is True, report.get("released_reason")
    assert report_state(store)["stale"] is False
    # 使报告过期：新增未决 catalog（摘要输入变化）
    (store.preprocessing_dir / "catalog.csv").write_text(
        "item,kind,status,locator,unit_id,note\nX,figure,unresolved,page 9,,\n",
        encoding="utf-8",
    )
    rep = report_state(store)
    assert rep["stale"] is True, rep
    tasks = orch.status(store)["next_tasks"]
    assert tasks, "报告过期后必须给出下一步指针"
    assert tasks[0]["kind"] in ("build", "qa"), tasks
    for t_ in tasks:
        done = t_.get("done_when") or {}
        assert not (done.get("cmd") == "import" and done.get("unit") == "report"), tasks
