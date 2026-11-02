# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""D1 真值表：目录来源身份模型（结构视图 / 原版行去向 / 缺锚点 / 页码策略）。"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from auto_epublizer import orchestrator as orch
from auto_epublizer.toc_model import build_toc_model


def _workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text(
        "# Contents\n\n"
        "Chapter One 3\n"
        "§ Early 5\n"
        "Duplicate 7\n"
        "Unknown 9\n\n"
        "# Part One\n\nBody.\n\n"
        "## Chapter One\n\nBody.\n\n"
        "## Duplicate\n\nBody.\n\n"
        "## Duplicate\n\nBody.\n",
        encoding="utf-8",
    )
    return orch.init(str(src), workspace_dir=tmp_path / "ws")


def _unit(store, title: str):
    matches = [unit for unit in store.load_publication().units if unit.title == title]
    assert matches, title
    return matches[0]


def test_nodes_have_parent_order_and_complete_hrefs(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    model = build_toc_model(store)
    nodes = {node["unit"]: node for node in model["nodes"]}
    chapter = _unit(store, "Chapter One")
    part = _unit(store, "Part One")
    assert nodes[chapter.id]["parent"] == part.id
    assert nodes[chapter.id]["href"].endswith(".xhtml")
    assert nodes[part.id]["parent"] is None
    assert [node["order"] for node in model["nodes"]] == list(range(1, len(model["nodes"]) + 1))


def test_in_unit_subheading_anchor_carries_fragment(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    chapter = _unit(store, "Chapter One")
    path = store.structured_dir / chapter.meta["rel_path"]
    path.write_text(path.read_text(encoding="utf-8") + "\n### Sub A\n\nMore.\n", encoding="utf-8")
    node = next(item for item in build_toc_model(store)["nodes"] if item["unit"] == chapter.id)
    assert node["anchors"]
    anchor = node["anchors"][0]
    assert anchor["href"].startswith(node["href"] + "#")
    assert anchor["label"] == "Sub A"


def test_original_entries_bind_only_exact_labels(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    model = build_toc_model(store)
    toc = model["original"][0]
    entries = {entry["label"]: entry for entry in toc["entries"]}
    assert entries["Chapter One"]["destination"]["kind"] == "unit"
    assert entries["Chapter One"]["page"] == "3"
    assert entries["Chapter One"]["page_kind"] == "arabic"
    assert entries["Duplicate"]["match"] == "ambiguous"
    assert entries["Duplicate"]["destination"] is None
    assert entries["Unknown"]["match"] == "unresolved"
    assert entries["§ Early"]["match"] == "section_anchor_absent"


def test_section_marker_does_not_generate_heading_anchor(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    model = build_toc_model(store)
    labels = [anchor["label"] for node in model["nodes"] for anchor in node["anchors"]]
    assert "Early" not in labels
    assert any(item["reason"] == "section_anchor_absent" for item in model["unresolved"])


def test_page_policy_is_consumed_not_assumed(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    toc_unit = _unit(store, "Contents")
    store.preprocessing_dir.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["unit", "policy", "reason", "evidence"])
    writer.writeheader()
    writer.writerow(
        {"unit": toc_unit.id, "policy": "original", "reason": "源目录带原书页码", "evidence": ""}
    )
    (store.preprocessing_dir / "page_numbers.csv").write_text(buffer.getvalue(), encoding="utf-8")
    toc = build_toc_model(store)["original"][0]
    assert toc["page_policy"] == "original"
    assert toc["page_display"] == "original"


def test_undeclared_policy_keeps_pages_hidden(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    toc = build_toc_model(store)["original"][0]
    assert toc["page_policy"] is None
    assert toc["page_display"] is None


def test_model_is_read_only(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    before = {path: path.stat().st_mtime_ns for path in store.dir.rglob("*") if path.is_file()}
    result = build_toc_model(store)
    assert result["writes"] is False
    after = {path: path.stat().st_mtime_ns for path in store.dir.rglob("*") if path.is_file()}
    assert before == after
