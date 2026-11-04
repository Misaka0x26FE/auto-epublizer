# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""P1 排版样本册验收：结构对账、故障注入、主题/确定性、PDF 跨页与旧基线。

基线更新（版式有意变更时）：

    AEP_TYPOGRAPHY_UPDATE_BASELINE=1 uv run pytest tests/test_typography_fixtures.py -q

更新必须与「差异原因 / 相关提交 / 人工复核结论」一起提交；禁止失败后自动重录。
"""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest
import typography_book as tb

from auto_epublizer.pdfexport import find_chromium
from auto_epublizer.qa.epubcheck import run_epubcheck

_HAS_CHROMIUM = find_chromium() is not None

_CASE_TYPES = {
    "opening",
    "body",
    "mixed",
    "quote",
    "verse-code",
    "notes",
    "figures",
    "tables",
    "toc",
    "index",
    "roles",
    "extreme",
}


def test_manifest_covers_all_case_types() -> None:
    manifest = tb.load_manifest()
    ids = [case["case_id"] for case in manifest["cases"]]
    assert len(ids) == len(set(ids))
    assert set(ids) >= _CASE_TYPES
    unit_ids = [unit["unit_id"] for _case, unit in tb.iter_units(manifest)]
    assert len(unit_ids) == len(set(unit_ids))
    for _case, unit in tb.iter_units(manifest):
        assert (tb.FIXTURE_DIR / unit["markdown"]).is_file(), unit["markdown"]
        assert unit["expect"]["markers"] or unit["expect"]["images"]


def test_fixture_epub_passes_own_reconciliation(tmp_path: Path) -> None:
    built = tb.build_fixture_epub(tmp_path)
    assert tb.reconcile(built["epub"]) == []
    with zipfile.ZipFile(built["epub"]) as zf:
        names = zf.namelist()
        assert names[0] == "mimetype"
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert 'properties="cover-image"' in opf
        assert "typography-samples" in opf
        assert "cover.xhtml" not in names  # 封面单元是 front-cover.xhtml
        for unit_id in ("ch01", "ch06", "ch07", "back-index", "front-cover"):
            assert f"OEBPS/{unit_id}.xhtml" in names


def test_fixture_epub_runs_epubcheck(tmp_path: Path) -> None:
    built = tb.build_fixture_epub(tmp_path)
    result = run_epubcheck(built["epub"])
    if not result.available:
        pytest.skip("EPUBCheck 不可用")
    assert result.ran
    assert result.errors == 0, result.messages[:10]
    assert result.returncode == 0


def test_fault_injection_is_detected(tmp_path: Path) -> None:
    missing_media = tb.build_fixture_epub(tmp_path, drop_media="fig-wide.png", name="no-media.epub")
    media_problems = tb.reconcile(missing_media["epub"])
    assert any("media/fig-wide.png" in problem for problem in media_problems)

    missing_note = tb.build_fixture_epub(tmp_path, drop_aside="n101", name="no-note.epub")
    note_problems = tb.reconcile(missing_note["epub"])
    assert any("aside 期望 4 实际 3" in problem for problem in note_problems)


def test_themes_only_change_style(tmp_path: Path) -> None:
    digests = {
        theme: tb.layout_digest(tb.build_fixture_epub(tmp_path, theme=theme)["epub"])
        for theme in ("standard", "compact", "spacious")
    }
    assert len({d["style_sha256"] for d in digests.values()}) == 3
    assert len({d["content_sha256"] for d in digests.values()}) == 1


def test_build_is_deterministic(tmp_path: Path) -> None:
    first = tb.build_fixture_epub(tmp_path, name="a.epub")
    second = tb.build_fixture_epub(tmp_path, name="b.epub")
    assert first["epub"].read_bytes() == second["epub"].read_bytes()
    assert tb.layout_digest(first["epub"]) == tb.layout_digest(second["epub"])


@pytest.mark.skipif(not _HAS_CHROMIUM, reason="需要 Chromium/Chrome 做印刷排版")
def test_pdf_spans_pages_and_keeps_all_markers(tmp_path: Path) -> None:
    built = tb.build_fixture_epub(tmp_path)
    digest = tb.pdf_digest(built["epub"], tmp_path / "samples.pdf")
    assert digest["size_mm"] == [148, 210]
    assert digest["pages"] >= 6, "整册必须自然跨页，组件页通过不代替整册分页"

    import pymupdf

    with pymupdf.open(tmp_path / "samples.pdf") as doc:
        text = "\n".join(page.get_text("text") for page in doc)
    compact = "".join(text.split())  # 行内换行/断词可能落在标记中间
    for _case, unit in tb.iter_units(built["manifest"]):
        for marker in unit["expect"]["markers"]:
            assert marker in compact, f"PDF 文本层缺少标记 {marker}"


def _current_baseline(tmp_path: Path) -> dict:
    epub: dict[str, dict] = {}
    for theme in ("standard", "compact", "spacious"):
        built = tb.build_fixture_epub(tmp_path, theme=theme, name=f"base-{theme}.epub")
        epub[theme] = tb.layout_digest(built["epub"])
    payload = {
        "schema_version": 1,
        "generated_at": "2026-11-04",
        "manifest": "tests/fixtures/typography/manifest.json",
        "note": "版式基线：EPUB 摘要与 git 状态无关；PDF 摘要绑定 Chromium/字体环境，跨环境只比内容完整性。",
        "epub": epub,
        "pdf": None,
    }
    if _HAS_CHROMIUM:
        built = tb.build_fixture_epub(tmp_path, name="base-pdf.epub")
        payload["pdf"] = tb.pdf_digest(built["epub"], tmp_path / "base.pdf")
    return payload


def test_baseline_matches_current_build(tmp_path: Path) -> None:
    current = _current_baseline(tmp_path)
    if os.environ.get("AEP_TYPOGRAPHY_UPDATE_BASELINE") == "1":
        tb.BASELINE_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return
    assert tb.BASELINE_PATH.is_file(), "缺少基线文件；用 AEP_TYPOGRAPHY_UPDATE_BASELINE=1 生成"
    baseline = json.loads(tb.BASELINE_PATH.read_text(encoding="utf-8"))
    for theme, digest in current["epub"].items():
        assert baseline["epub"][theme] == digest, (
            f"{theme} 版式或内容与基线不一致；有意变更请重新登记基线并写明原因"
        )
    recorded = baseline.get("pdf")
    if not _HAS_CHROMIUM or recorded is None:
        pytest.skip("无 Chromium 或无 PDF 基线")
    if recorded["chromium"] != current["pdf"]["chromium"]:
        pytest.skip(f"Chromium 版本不同（基线 {recorded['chromium']}），PDF 基线不可比")
    assert recorded["pages"] == current["pdf"]["pages"]
    assert recorded["text_sha256"] == current["pdf"]["text_sha256"]
    assert recorded["size_mm"] == current["pdf"]["size_mm"]
