# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""合成坏样本：现场 T12 补丁本身不能产生新的假绿。"""

from pathlib import Path

import pytest
from test_release_truth_table import _report
from test_t12_gates import _epub, _page

from auto_epublizer import orchestrator as orch
from auto_epublizer.preprocess.artifacts import read_style_exemptions
from auto_epublizer.qa import artifacts_digest, audit_epub
from auto_translator.glossary import Glossary
from auto_translator.review.g0 import g0_unit_flags, language_identical


@pytest.mark.parametrize(
    "text",
    [
        "This entire paragraph was copied without translation.[^ref-000001]",
        "Это длинный абзац который вообще не перевели на другой язык.",
        "# Heading\n\nThis entire paragraph was copied without translation.",
        "[^a]: This entire footnote was copied without translation.",
    ],
)
def test_language_markers_do_not_hide_copied_prose(text: str) -> None:
    assert language_identical(text, text)


def test_duplicate_images_without_alt_are_still_counted(tmp_path: Path) -> None:
    path = _epub(tmp_path, _page('<h1>t</h1><img src="media/p001.png"/>' * 2))
    assert any(f.code == "W_IMAGE_DUPLICATE" for f in audit_epub(path).findings)


def test_each_figure_uses_its_own_caption(tmp_path: Path) -> None:
    body = (
        '<h1>t</h1><figure><img src="media/p001.png" alt=""/>'
        "<figcaption>说明文字</figcaption></figure>"
        '<figure><img src="media/p001.png" alt=""/>'
        "<figcaption>TODO</figcaption></figure>"
    )
    assert any(
        f.code == "E_CAPTION_PLACEHOLDER" for f in audit_epub(_epub(tmp_path, _page(body))).findings
    )


def test_single_quoted_image_attributes_are_checked(tmp_path: Path) -> None:
    body = "<h1>t</h1><img src='media/p001.png' alt='TODO'/>"
    assert any(
        f.code == "E_CAPTION_PLACEHOLDER" for f in audit_epub(_epub(tmp_path, _page(body))).findings
    )


def _workspace(tmp_path: Path):
    source = tmp_path / "source.md"
    source.write_text("# One\n\nSynthetic English prose for a test.\n", encoding="utf-8")
    return orch.init(str(source), workspace_dir=str(tmp_path / "ws"))


@pytest.mark.parametrize("extra", ["preprocessing/style_exemptions.csv", "analysis/style.md"])
def test_style_inputs_invalidate_digest(tmp_path: Path, extra: str) -> None:
    store = _workspace(tmp_path)
    before = artifacts_digest(store)
    path = store.dir / extra
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("changed gate input", encoding="utf-8")
    assert artifacts_digest(store) != before


def test_nav_switch_invalidates_digest(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    before = artifacts_digest(store)
    pub = store.load_publication()
    pub.units[0].meta["nav"] = False
    store.replace_units(pub.units)
    assert artifacts_digest(store) != before


def test_style_exemption_requires_actual_style_reference(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    path = store.preprocessing_dir / "style_exemptions.csv"
    path.write_text("unit,pattern,style_ref,reason\nch01,^Synthetic,,retained title\n")
    with pytest.raises(ValueError, match="style_ref"):
        read_style_exemptions(store)


@pytest.mark.parametrize("check", ["language", "length", "length_review"])
def test_new_blocking_checks_actually_block_release(check: str) -> None:
    report = _report(g0_flags=[{"check": check, "blocking": True, "message": "bad"}])
    assert not report.released


def test_import_does_not_silently_drop_language_findings(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    unit = store.load_publication().units[0]
    rel = unit.meta["rel_path"]
    import json

    text = (store.structured_dir / rel).read_text(encoding="utf-8")
    (store.translation_dir / rel).parent.mkdir(parents=True, exist_ok=True)
    (store.translation_dir / rel).write_text(text, encoding="utf-8")
    store.unit_align_path(unit.id).parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "seq": 1,
            "src": "Synthetic English prose for a test.",
            "tgt": "Synthetic English prose for a test.",
        }
    ]
    store.unit_align_path(unit.id).write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    result = orch.import_translations(store)
    assert result["failed"], result


def test_severely_short_nonempty_translation_requires_review() -> None:
    src = "This is synthetic prose containing several distinct facts and a long explanation. " * 3
    flags = g0_unit_flags([{"seq": 1, "src": src, "tgt": "村庄。"}], Glossary())
    assert any(f.check == "length_review" and f.blocking for f in flags)
    assert any(f.check == "length" and not f.blocking for f in flags)


def test_severe_short_review_has_specific_evidenced_exemption() -> None:
    import re

    src = "Synthetic source prose with many words and details. " * 4
    flags = g0_unit_flags(
        [{"seq": 1, "src": src, "tgt": "村庄。"}],
        Glossary(),
        language_exempt=[(re.compile("^Synthetic source prose"), "§5：已回源核证的特殊短句")],
    )
    assert any(f.check == "length_review_exempt" and not f.blocking for f in flags)
    assert not any(f.check == "length_review" and f.blocking for f in flags)


def test_malformed_source_note_inventory_is_not_treated_as_absent(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    (store.structured_dir / "notes.json").write_text("{bad json", encoding="utf-8")
    with pytest.raises(orch.OrchestrationError, match="源注文清单不可读"):
        orch._load_notes_context(store, store.load_publication())


@pytest.mark.parametrize("source,target", [("zh-CN", "zh-CN"), ("en", "en-GB")])
def test_same_language_conversion_does_not_require_translation(source: str, target: str) -> None:
    text = "This long passage deliberately remains in the same language."
    flags = g0_unit_flags(
        [{"seq": 1, "src": text, "tgt": text}],
        Glossary(),
        source_language=source,
        target_language=target,
    )
    assert not any(f.check == "language" for f in flags)


def test_copied_chinese_to_english_is_not_automatically_exempt() -> None:
    text = "这个段落是一段完全没有经过翻译的中文正文，而且它包含许多需要保留的细节。"
    assert language_identical(text, text, target_language="en")


def test_code_only_block_is_not_treated_as_severe_short_prose() -> None:
    text = "```python\n" + "long_literal_identifier = 123\n" * 12 + "```"
    flags = g0_unit_flags([{"seq": 1, "src": text, "tgt": "短"}], Glossary())
    assert not any(f.check == "length_review" for f in flags)


def test_whole_unit_exemption_does_not_waive_severe_short_review() -> None:
    import re

    flags = g0_unit_flags(
        [{"seq": 1, "src": "Synthetic long prose. " * 20, "tgt": "短"}],
        Glossary(),
        language_exempt=[(re.compile(""), "whole index")],
    )
    assert any(f.check == "length_review" and f.blocking for f in flags)


def test_duplicate_images_grouped_by_bytes_not_path_spelling(tmp_path: Path) -> None:
    import zipfile

    path = _epub(
        tmp_path,
        _page(
            '<h1>t</h1><img src="media/p001.png" alt="甲"/><img src="./media/copy.png" alt="乙"/>'
        ),
    )
    with zipfile.ZipFile(path, "a") as zf:
        zf.writestr("OEBPS/media/copy.png", zf.read("OEBPS/media/p001.png"))
    assert any(f.code == "W_IMAGE_DUPLICATE" for f in audit_epub(path).findings)


def test_style_reference_section_must_exist(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    (store.dir / "analysis").mkdir(exist_ok=True)
    (store.dir / "analysis/style.md").write_text("## 1. Basic style\n", encoding="utf-8")
    (store.preprocessing_dir / "style_exemptions.csv").write_text(
        "unit,pattern,style_ref,reason\nch01,^Synthetic,§9,retained title\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="style_ref"):
        read_style_exemptions(store)


def _copied_ws(tmp_path: Path):
    """合成工作区：译文与源文逐字相同（长正文）。"""
    import json as _json

    src = tmp_path / "book.md"
    prose = "This synthetic paragraph is deliberately copied verbatim without translation."
    src.write_text(f"# Chapter I\n\n{prose}\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    rel = store.load_publication().units[0].meta["rel_path"]
    (store.translation_dir / rel).parent.mkdir(parents=True, exist_ok=True)
    (store.translation_dir / rel).write_text(f"# Chapter I\n\n{prose}\n", encoding="utf-8")
    store.unit_align_path("ch01").parent.mkdir(parents=True, exist_ok=True)
    store.unit_align_path("ch01").write_text(
        _json.dumps({"seq": 1, "src": prose, "tgt": prose, "note": None}) + "\n",
        encoding="utf-8",
    )
    return store


def test_cli_import_blocks_copied_prose(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from auto_epublizer.cli import app

    store = _copied_ws(tmp_path)
    result = CliRunner().invoke(app, ["import", "--workspace", str(store.dir)])
    assert result.exit_code != 0, result.output
    assert "language" in result.output or "语言" in result.output, result.output
