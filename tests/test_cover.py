# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""issue #63 回归：扫描件封面候选发现与确认登记。

现场：596 页扫描书第 1 页就是封面整页图，但它不是 cover 单元的图片引用，
build 因此不写 ``cover-image``，EPUB 书架空白，只能手工抽图改包。
本文件验证三件事：候选只读且按魔数判格式；未确认绝不自动当封面；
确认后复用既有 cover-image 路径且媒体字节不变。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app
from auto_epublizer.preprocess.cover import (
    collect_cover_candidates,
    cover_status,
    read_confirmed_cover,
)

# 最小 JPEG 文件头（格式判定只读魔数，不需要可解码的完整图像）
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _ws(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nBody text.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    raw = store.structured_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    return store, raw


def _page_with_image(raw: Path, name: str = "p001-page.png", data: bytes = JPEG) -> str:
    media = raw / "media"
    media.mkdir(parents=True, exist_ok=True)
    (media / name).write_bytes(data)
    (raw / "page-001.json").write_text(
        json.dumps(
            {
                "page_idx": 1,
                "blocks": [
                    {
                        "type": "image",
                        "file": f"media/{name}",
                        "bbox": [0, 0, 600, 800],
                        "method": "full_page",
                        "insert_id": "ins-1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return f"structured/raw/media/{name}"


def test_candidates_use_magic_not_extension(tmp_path: Path) -> None:
    store, raw = _ws(tmp_path)
    _page_with_image(raw, "cover.png", JPEG)
    (candidate,) = collect_cover_candidates(store)
    assert candidate["format"] == "jpeg"  # 扩展名 .png 不作判据
    assert candidate["page"] == 1 and candidate["method"] == "full_page"
    assert candidate["bytes"] == len(JPEG)
    assert candidate["file"] == "structured/raw/media/cover.png"


def test_unconfirmed_candidate_never_becomes_cover(tmp_path: Path) -> None:
    store, raw = _ws(tmp_path)
    _page_with_image(raw)
    epub = orch.build(store)
    with zipfile.ZipFile(epub) as zf:
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
    assert "cover-image" not in opf
    assert '<meta name="cover"' not in opf
    status = cover_status(store)
    assert status["confirmed"] is None
    assert len(status["candidates"]) == 1
    assert status["missing"] is True  # 未确认 = 缺封面（可定位，不猜）


def test_confirmed_cover_uses_existing_cover_image_path(tmp_path: Path) -> None:
    store, raw = _ws(tmp_path)
    rel = _page_with_image(raw)
    cover_json = store.preprocessing_dir / "cover.json"
    cover_json.write_text(
        json.dumps({"file": rel, "evidence": "第 1 页整页图，与书名页比对确认"}), encoding="utf-8"
    )
    confirmed = read_confirmed_cover(store)
    assert confirmed is not None and confirmed["format"] == "jpeg"
    assert confirmed["epub_path"] == "media/p001-page.png"

    epub = orch.build(store)
    with zipfile.ZipFile(epub) as zf:
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert 'properties="cover-image"' in opf
        assert '<meta name="cover"' in opf
        # 媒体字节原样（不重编码、不改名）
        assert zf.read("OEBPS/media/p001-page.png") == JPEG
    events = (store.dir / "events.jsonl").read_text(encoding="utf-8")
    assert "cover_confirmed_used" in events


def test_invalid_cover_records_are_explicit_errors(tmp_path: Path) -> None:
    store, raw = _ws(tmp_path)
    _page_with_image(raw)
    cover_json = store.preprocessing_dir / "cover.json"

    for payload, reason in (
        ({"file": "structured/raw/media/p001-page.png"}, "evidence"),
        ({"file": "source/../source/book.md", "evidence": "x"}, "越界"),
        ({"file": "structured/raw/media/missing.png", "evidence": "x"}, "不存在"),
    ):
        cover_json.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match=reason):
            read_confirmed_cover(store)

    cover_json.write_text(json.dumps({"file": "source/../source/book.md", "evidence": "x"}))
    with pytest.raises(orch.OrchestrationError):
        orch.build(store)


def test_declared_cover_unit_without_image_is_located(tmp_path: Path) -> None:
    store, _ = _ws(tmp_path)
    pub = store.load_publication()
    pub.units[0].kind = "cover"
    store.replace_units(pub.units)
    orch.build(store)
    status = cover_status(store)
    assert status["declared"] and status["has_image"] is False
    assert status["missing"] is True
    events = (store.dir / "events.jsonl").read_text(encoding="utf-8")
    assert "cover_without_image" in events


def test_evidence_source_exposes_cover_candidates(tmp_path: Path) -> None:
    store, raw = _ws(tmp_path)
    _page_with_image(raw, "p001-page.png", PNG)
    data = orch.source_evidence(store)
    (candidate,) = data["cover_candidates"]
    assert candidate["format"] == "png"

    result = CliRunner().invoke(
        app, ["evidence", "source", "--workspace", str(store.dir), "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["cover_candidates"][0]["format"] == "png"
