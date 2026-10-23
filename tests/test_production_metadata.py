# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""制作页元数据的公共入口、未知值语义与安全字段边界。"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from auto_common.workspace import Publication
from auto_epublizer import fingerprint
from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app
from auto_epublizer.qa import artifacts_digest


def _ws(tmp_path: Path):
    source = tmp_path / "book.md"
    source.write_text("# Chapter\n\nSynthetic body.\n", encoding="utf-8")
    return orch.init(str(source), workspace_dir=str(tmp_path / "ws"))


def test_generation_tool_metadata_roundtrip_and_invalidates_product(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    before = artifacts_digest(store)
    data = [{"name": "Synthetic Model", "version": None, "task": "translation"}]
    result = CliRunner().invoke(
        app, ["meta", "--workspace", str(store.dir), "--generation-tools", json.dumps(data)]
    )
    assert result.exit_code == 0, result.output
    assert store.load_publication().meta.generation_tools == data
    assert artifacts_digest(store) != before


@pytest.mark.parametrize("language", ["zh-CN", "en"])
def test_explicit_no_models_is_visible_and_distinct_from_unknown(language: str) -> None:
    pub = Publication(slug="book")
    unknown = fingerprint.software_section(fingerprint.build_fingerprint(pub), language)
    pub.meta.generation_tools = []
    explicit = fingerprint.software_section(fingerprint.build_fingerprint(pub), language)
    expected = "明确未使用生成模型" if language == "zh-CN" else "No generation model was used"
    assert expected in explicit
    assert expected not in unknown


@pytest.mark.parametrize("bad", ['[{"name":"X","api_key":"not-a-secret"}]', '[{"name":3}]', "{}"])
def test_bad_generation_metadata_never_changes_publication(tmp_path: Path, bad: str) -> None:
    store = _ws(tmp_path)
    before = store.publication_path.read_bytes()
    result = CliRunner().invoke(
        app, ["meta", "--workspace", str(store.dir), "--generation-tools", bad]
    )
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert store.publication_path.read_bytes() == before


def test_fingerprint_checks_new_tool_items_not_just_outer_list() -> None:
    data = fingerprint.build_fingerprint(Publication(slug="book"))
    assert not fingerprint._valid({**data, "generation_tools": ["invalid tool"]})
    assert not fingerprint._valid({**data, "publication": {"title": ["invalid"]}})
