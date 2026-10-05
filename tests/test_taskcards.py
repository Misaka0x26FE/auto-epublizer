"""任务卡与 status --json 的 next_tasks.kind 一致性（drift guard）。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "skills" / "auto-epublizer" / "references" / "taskcards"

# S1 _derive_next_tasks 会产出的 kind（QA 触发 build/qa/delivery 三种）
KINDS = [
    "preprocess",
    "write_preprocessing",
    "repair",
    "analyze",
    "translate",
    "import",
    "review",
    "build",
    "qa",
    "delivery",
]

_CARDS = [
    "README",
    "preprocess",
    "write-preprocessing",
    "repair",
    "analyze",
    "translate-unit",
    "import-unit",
    "review-unit",
    "build-qa-delivery",
]


def test_taskcard_files_exist_bilingual() -> None:
    for name in _CARDS:
        assert (CARDS / f"{name}.md").is_file(), f"缺任务卡 {name}.md"
        assert (CARDS / f"{name}.zh.md").is_file(), f"缺任务卡 {name}.zh.md"


def test_taskcard_index_covers_all_kinds() -> None:
    text = (CARDS / "README.md").read_text(encoding="utf-8")
    for kind in KINDS:
        assert kind in text, f"taskcards/README.md 未覆盖 next_tasks kind: {kind}"


def test_manifest_lists_taskcards() -> None:
    manifest = json.loads((ROOT / "skills" / "auto-epublizer" / "manifest.json").read_text())
    assert "taskcards" in manifest["references"]
