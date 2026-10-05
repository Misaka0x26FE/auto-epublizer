"""S1：status --json 的 next_tasks 机器指针（从状态机/产物对账派生，零 token 可测）。"""

from __future__ import annotations

from pathlib import Path

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
