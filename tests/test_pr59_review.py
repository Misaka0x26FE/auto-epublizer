# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""PR59 的独立消费者反例，不把投稿方回归通过当成边界已覆盖。"""

import json
import zipfile
from pathlib import Path

import pytest
from test_field_quality_followup import _workspace
from test_notes import _gap_ws, _read_epub, _write_gap_translation
from test_t12_gates import _epub, _page

from auto_epublizer import orchestrator as orch
from auto_epublizer.qa import audit_epub
from auto_translator.glossary import Glossary
from auto_translator.review.g0 import g0_unit_flags


def _change_notes(store, transform):
    path = store.structured_dir / "notes.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    transform(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    orch.register_notes(store)
    return data


@pytest.mark.parametrize("label", ["1", "1955", "1.2"])
def test_numeric_figure_labels_are_not_machine_filenames(tmp_path: Path, label: str) -> None:
    body = f'<h1>t</h1><figure><img src="media/p001.png" alt="{label}"/>'
    body += f"<figcaption>{label}</figcaption></figure>"
    findings = audit_epub(_epub(tmp_path, _page(body))).findings
    assert not [f for f in findings if f.code.startswith("E_CAPTION_")]


def test_symbol_fallback_reserves_later_original_numeric_label(tmp_path: Path) -> None:
    store, _ = _gap_ws(tmp_path)

    def edit(data):
        data["notes"][0]["source_label"] = "*"
        data["notes"][1].update(scope_id="ch01", source_label="1")

    _change_notes(store, edit)
    epub = orch.build(store)
    assert ">[2]<" in _read_epub(epub, "ch01.xhtml")
    assert ">[1]<" in _read_epub(epub, "ch02.xhtml")


def test_canonical_numeric_note_label_collision_is_rejected(tmp_path: Path) -> None:
    store, _ = _gap_ws(tmp_path)

    def edit(data):
        data["notes"][1].update(scope_id="ch01", source_label="01")

    with pytest.raises(orch.OrchestrationError, match="注号|显示号"):
        _change_notes(store, edit)


def test_superscript_symbol_label_does_not_crash_numeric_allocation(tmp_path: Path) -> None:
    store, _ = _gap_ws(tmp_path)
    _change_notes(store, lambda data: data["notes"][0].update(source_label="²"))
    epub = orch.build(store)
    assert ">[1]<" in _read_epub(epub, "ch01.xhtml")


def test_orphan_source_unit_takes_precedence_over_scope_name(tmp_path: Path) -> None:
    store, _ = _gap_ws(tmp_path)
    _change_notes(store, lambda data: data["notes"][1].update(scope_id="ch01"))
    epub = orch.build(store)
    assert "Third note." in _read_epub(epub, "ch02.xhtml")
    assert "Third note." not in _read_epub(epub, "ch01.xhtml")


def test_orphan_without_resolvable_host_does_not_guess_first_chapter(tmp_path: Path) -> None:
    store, _ = _gap_ws(tmp_path)
    _change_notes(
        store,
        lambda data: data["notes"][1].update(source_locations=[{"kind": "page", "page": 10}]),
    )
    with pytest.raises(orch.OrchestrationError, match="宿主|位置|单元"):
        orch.build(store)


@pytest.mark.parametrize("literal", ["`[^ref-000001]`", "```text\n[^ref-000001]\n```"])
def test_literal_note_examples_do_not_require_registration(tmp_path: Path, literal: str) -> None:
    store = _workspace(tmp_path)
    unit = store.load_publication().units[0]
    path = store.structured_dir / unit.meta["rel_path"]
    path.write_text(f"# Example\n\n{literal}\n", encoding="utf-8")
    epub = orch.build(store)
    with zipfile.ZipFile(epub) as zf:
        text = zf.read("OEBPS/ch01.xhtml").decode()
    assert "[^ref-000001]" in text
    assert 'epub:type="noteref"' not in text


def test_cjk_in_heading_does_not_hide_copied_foreign_body() -> None:
    text = "# 中文标题\n\nThis entire long foreign paragraph is copied without translation."
    flags = g0_unit_flags([{"seq": 1, "src": text, "tgt": text}], Glossary())
    assert any(f.check == "language" and f.blocking for f in flags)


def test_inline_code_is_not_counted_as_severely_short_translation_source() -> None:
    text = "Literal `" + "long_identifier = value; " * 20 + "` is shown."
    flags = g0_unit_flags([{"seq": 1, "src": text, "tgt": "示例。"}], Glossary())
    assert not any(f.check == "length_review" for f in flags)


def test_registered_note_does_not_rewrite_same_marker_inside_code() -> None:
    from auto_epublizer.build.html import NoteRef, markdown_to_xhtml

    body = markdown_to_xhtml(
        "Real[^ref-000001].\n\n`[^ref-000001]`\n\n```text\n[^ref-000001]\n```",
        note_refs={"ref-000001": NoteRef("ref-000001", "n-000001", 1)},
    )
    assert body.count('id="ref-000001"') == 1
    assert body.count("[^ref-000001]") == 2


def test_nav_exclusion_keeps_spine_and_does_not_hide_other_missing_entries(tmp_path: Path) -> None:
    import re

    from auto_common.config import Config

    src = tmp_path / "nav.md"
    src.write_text("# One\n\nFirst body.\n\n# Two\n\nSecond body.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    pub = store.load_publication()
    pub.units[1].meta["nav"] = False
    store.replace_units(pub.units)
    epub = orch.build(store)
    cfg = Config()
    cfg.qc.epubcheck.jar = str(tmp_path / "not-installed.jar")
    assert orch.qa(store, epub_path=str(epub), config=cfg)["g4_audit"] == "pass"
    bad = tmp_path / "missing-nav.epub"
    with zipfile.ZipFile(epub) as src_zip, zipfile.ZipFile(bad, "w") as dst:
        assert "Second body." in src_zip.read("OEBPS/ch02.xhtml").decode()
        assert "ch02.xhtml" not in src_zip.read("OEBPS/nav.xhtml").decode()
        for item in src_zip.infolist():
            data = src_zip.read(item.filename)
            if item.filename == "OEBPS/nav.xhtml":
                data = re.sub(r"<li>.*?</li>", "", data.decode(), flags=re.DOTALL).encode()
            dst.writestr(item, data)
    report = orch.qa(store, epub_path=str(bad), config=cfg)
    assert report["g4_audit"] == "fail"


def test_note_audit_rejects_nonempty_truncation(tmp_path: Path) -> None:
    from auto_epublizer import notes
    from auto_epublizer.qa import audit_notes_epub

    store, digest = _gap_ws(tmp_path)
    _write_gap_translation(store, digest)
    orch.import_translations(store)
    epub = orch.build(store)
    bad = tmp_path / "short-note.epub"
    with zipfile.ZipFile(epub) as src, zipfile.ZipFile(bad, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "OEBPS/ch02.xhtml":
                data = data.replace("第三条注。".encode(), "第三条".encode())
            dst.writestr(item, data)
    result = audit_notes_epub(
        bad,
        source_notes=notes.read_notes_json(notes.source_notes_path(store)),
        target_notes=notes.read_notes_json(notes.translation_notes_path(store)),
        media_root=store.structured_dir / "raw" / "media",
    )
    assert not result.ok


def test_note_audit_rejects_unregistered_added_note_content(tmp_path: Path) -> None:
    from auto_epublizer import notes
    from auto_epublizer.qa import audit_notes_epub

    store, digest = _gap_ws(tmp_path)
    _write_gap_translation(store, digest)
    orch.import_translations(store)
    epub = orch.build(store)
    bad = tmp_path / "added-note.epub"
    with zipfile.ZipFile(epub) as src, zipfile.ZipFile(bad, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "OEBPS/ch02.xhtml":
                data = data.replace("第三条注。".encode(), "第三条注。凭空追加的注文。".encode())
            dst.writestr(item, data)
    result = audit_notes_epub(
        bad,
        source_notes=notes.read_notes_json(notes.source_notes_path(store)),
        target_notes=notes.read_notes_json(notes.translation_notes_path(store)),
        media_root=store.structured_dir / "raw" / "media",
    )
    assert not result.ok


@pytest.mark.parametrize(
    "field,value", [("language", "en"), ("target_language", "en"), ("title", "Changed title")]
)
def test_gate_metadata_changes_invalidate_report_digest(
    tmp_path: Path, field: str, value: str
) -> None:
    from auto_epublizer.qa import artifacts_digest

    store = _workspace(tmp_path)
    before = artifacts_digest(store)
    pub = store.load_publication()
    setattr(pub.meta, field, value)
    store.save_publication(pub)
    # 后续制作信息页亦消费元数据，不允许旧报告仍 fresh。
    assert artifacts_digest(store) != before


@pytest.mark.parametrize(
    "note_text",
    [
        "说明。\n\n> 引用段落。",
        "说明。\n\n```text\n# literal_title\n\n**literal**\n```",
        "含 ``literal ` and _`` 的代码。",
        "说明。\n\n1) 原印第一条\n3) 原印第三条",
    ],
)
def test_complete_note_comparison_preserves_legal_block_syntax(
    tmp_path: Path, note_text: str
) -> None:
    from auto_epublizer import notes
    from auto_epublizer.qa import audit_notes_epub

    store, digest = _gap_ws(tmp_path)
    _write_gap_translation(store, digest)
    path = store.translation_dir / "notes.json"
    data = json.loads(path.read_text())
    data["notes"][1]["target_markdown"] = note_text
    path.write_text(json.dumps(data))
    assert not orch.import_translations(store)["failed"]
    epub = orch.build(store)
    result = audit_notes_epub(
        epub,
        source_notes=notes.read_notes_json(notes.source_notes_path(store)),
        target_notes=data,
        media_root=store.structured_dir / "raw" / "media",
    )
    assert result.ok, result.findings
