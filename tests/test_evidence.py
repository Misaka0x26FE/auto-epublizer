"""#14：页边界证据导出（evidence breaks → preprocessing/breaks.jsonl）。"""

from __future__ import annotations

import json
from pathlib import Path

from auto_epublizer import orchestrator as orch


def _ws(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter I\n\nFirst sentence here.\n\nSecond sentence here.\n", encoding="utf-8"
    )
    return orch.init(str(src), workspace_dir=str(tmp_path / "ws"))


def _page(raw: Path, idx: int, text: str) -> None:
    (raw / f"page-{idx:03d}.json").write_text(
        json.dumps({"page_idx": idx, "blocks": [{"type": "text", "text": text}]}),
        encoding="utf-8",
    )


def test_evidence_breaks_locates_boundary(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    raw = store.structured_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    _page(raw, 1, "Chapter I\nFirst sentence here.")
    _page(raw, 2, "Second sentence here.")

    result = orch.evidence_breaks(store)
    assert result["breaks"] == 1
    out = store.preprocessing_dir / "breaks.jsonl"
    assert out.is_file()
    row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert row["unit"] == "ch01"
    assert row["page"] == 1
    assert row["prev_line"] == "First sentence here."
    assert row["next_line"] == "Second sentence here."
    assert row["prev_block"] == 2 and row["next_block"] == 3
    assert row["candidate"] is False  # 前一行以句末点收尾


def test_evidence_breaks_flags_candidate_without_terminal(tmp_path: Path) -> None:
    """跨页断段候选：前一行不以句末标点收尾 → candidate=True。"""
    store = _ws(tmp_path)
    raw = store.structured_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    _page(raw, 1, "First sentence here.")  # 末行是完整句
    _page(raw, 2, "Second sentence here.")
    # 直接构造一对跨页断行：末行改成无标点
    _page(raw, 1, "Chapter I\nFirst sentence")  # 无句末标点

    result = orch.evidence_breaks(store)
    assert result["breaks"] == 1
    assert result["candidates"] == 1
    row = json.loads((store.preprocessing_dir / "breaks.jsonl").read_text().splitlines()[0])
    assert row["prev_line"] == "First sentence" and row["candidate"] is True


def test_evidence_breaks_no_raw(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    result = orch.evidence_breaks(store)
    assert result["breaks"] == 0
