# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""D2 真值表：生成式目录页、独立对账与 lint。"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from auto_common.config import Config, OutputConfig
from auto_epublizer import orchestrator as orch
from auto_epublizer.qa.provenance import audit_provenance
from auto_epublizer.qa.toc_page import check_generated_toc, expected_toc


def _workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text(
        "# Contents\n\nOld line 3\n\n"
        "# Part One\n\nBody.\n\n"
        "## Chapter One\n\nBody.\n\n"
        "## Chapter Two\n\nBody.\n",
        encoding="utf-8",
    )
    return orch.init(str(src), workspace_dir=tmp_path / "ws")


def _build(store) -> Path:
    return orch.build(store, config=Config(output=OutputConfig(toc_page=True)))


def _toc_html(epub: Path) -> str:
    with zipfile.ZipFile(epub) as zf:
        name = next(item for item in zf.namelist() if item.endswith("front-toc.xhtml"))
        return zf.read(name).decode("utf-8")


def test_build_generates_clickable_nested_toc(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    chapter = next(unit for unit in store.load_publication().units if unit.title == "Chapter One")
    path = store.structured_dir / chapter.meta["rel_path"]
    path.write_text(path.read_text(encoding="utf-8") + "\n### Sub A\n\nMore.\n", encoding="utf-8")
    html = _toc_html(_build(store))
    assert 'data-aep="generated-toc"' in html
    assert "<ol>" in html and "<li>" in html
    assert "Part One" in html and "Chapter One" in html
    assert "Sub A" in html
    assert "#" in html  # 子标题锚点


def test_generated_toc_passes_independent_check_and_probe_skip(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    epub = _build(store)
    entries = orch.structure_entries(store)
    result = audit_provenance(store, entries, epub, nav_depth=3)
    assert result.toc_page_findings == []
    assert result.epub_coverage == 1.0
    assert not [item for item in result.epub_coverage_missing if "front-toc" in item]


def test_checker_detects_wrong_target(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    entries = orch.structure_entries(store)
    expected = expected_toc(store, entries, nav_depth=3)
    html = _toc_html(_build(store)).replace('href="ch02.xhtml"', 'href="wrong.xhtml"')
    assert any(item.startswith("toc_entry_href") for item in check_generated_toc(html, expected))


def test_checker_flags_compressed_and_missing_pages(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    entries = orch.structure_entries(store)
    expected = expected_toc(store, entries, nav_depth=3)
    compressed = "<p>甲<br/>乙<br/>丙</p>"
    findings = check_generated_toc(compressed, expected, pages={"ch01": "3"})
    assert any(item.startswith("toc_compressed") for item in findings)
    assert any(item.startswith("toc_missing_pages") for item in findings)


def test_page_numbers_come_only_from_explicit_mapping(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    store.preprocessing_dir.mkdir(parents=True, exist_ok=True)
    (store.preprocessing_dir / "toc_pages.csv").write_text("unit,page\nch01,3\n", encoding="utf-8")
    html = _toc_html(_build(store))
    assert 'class="toc-page">3</span>' in html


def test_invalid_page_mapping_is_rejected(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    store.preprocessing_dir.mkdir(parents=True, exist_ok=True)
    (store.preprocessing_dir / "toc_pages.csv").write_text("unit,page\nnope,3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="不在 publication.json"):
        _build(store)


def test_multi_level_subheadings_stay_nested(tmp_path: Path) -> None:
    """多级子标题必须保留层级，不能全压成同级（审查 P2）。"""
    from auto_epublizer.build.toc_page import build_toc_tree

    store = _workspace(tmp_path)
    chapter = next(unit for unit in store.load_publication().units if unit.title == "Chapter One")
    path = store.structured_dir / chapter.meta["rel_path"]
    path.write_text(
        path.read_text(encoding="utf-8") + "\n### Sub A\n\nMore.\n\n#### Sub A1\n\nDeep.\n",
        encoding="utf-8",
    )
    entries = orch.structure_entries(store)
    tree = build_toc_tree(store, entries, nav_depth=4)
    flat = {}

    def walk(nodes, depth):
        for node in nodes:
            flat[node["label"]] = depth
            walk(node["children"], depth + 1)

    walk(tree, 1)
    assert flat["Sub A"] == 3
    assert flat["Sub A1"] == 4


def test_source_only_toc_lines_are_preserved(tmp_path: Path) -> None:
    """生成目录不得丢掉原目录独有条目（审查 P1）。"""
    store = _workspace(tmp_path)
    toc = next(unit for unit in store.load_publication().units if unit.kind == "toc")
    path = store.structured_dir / toc.meta["rel_path"]
    path.write_text(path.read_text(encoding="utf-8") + "\n附录甲　未成章…………9\n", encoding="utf-8")
    html = _toc_html(_build(store))
    assert "附录甲" in html


def test_broken_generated_toc_link_blocks_release(tmp_path: Path) -> None:
    """成品目录存在明确错链时不得放行（审查 P1）。"""
    store = _workspace(tmp_path)
    epub = _build(store)
    broken = tmp_path / "broken.epub"
    with zipfile.ZipFile(epub) as src, zipfile.ZipFile(broken, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.endswith("front-toc.xhtml"):
                data = data.replace(b'href="ch01.xhtml"', b'href="missing.xhtml"')
            dst.writestr(item, data)
    report = orch.qa(store, epub_path=str(broken))
    assert report["released"] is False
    assert any(finding["code"] == "E_TOC_BROKEN_LINK" for finding in report["provenance_findings"])
