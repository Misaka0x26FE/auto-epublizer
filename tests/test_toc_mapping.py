"""#16 S-B：facts 源 TOC → unit/unit#anchor 锚点级映射（W_TOC_MISSING 反映真实缺口）。"""

from __future__ import annotations

import json
from pathlib import Path

from auto_epublizer import orchestrator as orch


def _ws(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter One\n\n## The Subsection\n\nbody.\n\n# فصل دو\n\n## كتاب\n\nمتن.\n",
        encoding="utf-8",
    )
    return orch.init(str(src), workspace_dir=str(tmp_path / "ws"))


def test_toc_missing_maps_anchors_and_normalizes(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    facts = {
        "source": {
            "toc": [
                {"title": "The Subsection", "page": 3},  # 单元内锚点 → 覆盖
                {"title": "the subsection:", "page": 3},  # 标点/大小写差异 → 覆盖
                {"title": "کتاب", "page": 9},  # ك→ک 归一化 → 命中同名锚点
                {"title": "Missing Bookmark", "page": 99},  # 真缺口
            ]
        }
    }
    store.preprocessing_dir.mkdir(parents=True, exist_ok=True)
    (store.preprocessing_dir / "facts.json").write_text(
        json.dumps(facts, ensure_ascii=False), encoding="utf-8"
    )
    missing = orch._toc_missing_from_facts(store, orch.structure_entries(store))
    assert missing == ["Missing Bookmark"]


def test_toc_missing_empty_when_no_facts(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    assert orch._toc_missing_from_facts(store, orch.structure_entries(store)) == []
