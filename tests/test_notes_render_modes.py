"""注文宿主、实际来源和成品模式的消费者回归。"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from auto_common.config import Config
from auto_epublizer import notes as notes_mod
from auto_epublizer import orchestrator as orch


def _workspace(tmp_path: Path):
    source = tmp_path / "book.md"
    source.write_text("# Chapter I\n\nFirst sentence.\n\n# Chapter II\n\nSecond sentence.\n")
    return orch.init(str(source), workspace_dir=str(tmp_path / "workspace"))


def _register(store, *, second_note: bool = False, orphan: bool = False, cross_ref: bool = False):
    notes = [
        {
            "note_id": "n-000001",
            "scope_id": "ch01",
            "source_label": "1",
            "note_type": "footnote",
            "source_markdown": "SOURCE NOTE ONE",
            "source_locations": [{"kind": "page", "page": 1}],
            "status": "verified",
            "orphan_ok": orphan,
            "orphan_reason": "Original standalone note." if orphan else "",
        }
    ]
    refs = []
    for uid, text, rid in (
        ("ch01", "First sentence.", "ref-000001"),
        ("ch02", "Second sentence.", "ref-000002"),
    ):
        include = not orphan and (uid == "ch01" or second_note or cross_ref)
        path = store.structured_dir / "body" / f"{uid}.md"
        path.write_text(f"# {uid}\n\n{text}" + (f"[^{rid}]" if include else "") + "\n")
        if include:
            refs.append(
                {
                    "ref_id": rid,
                    "note_id": "n-000002" if second_note and uid == "ch02" else "n-000001",
                    "unit": uid,
                    "scope_id": uid,
                    "label_text": "1",
                    "context": text,
                    "status": "verified",
                }
            )
    if second_note:
        notes.append(
            {
                **notes[0],
                "note_id": "n-000002",
                "scope_id": "ch02",
                "source_markdown": "SOURCE NOTE TWO",
            }
        )
    data = {
        "schema_version": "1",
        "source_sha256": store.load_publication().meta.source_sha256,
        "inventory": "present",
        "notes": notes,
        "references": refs,
    }
    (store.structured_dir / "notes.json").write_text(json.dumps(data))
    orch.register_notes(store)
    return data


def _translate(store, uid: str, marker: str = ""):
    path = store.translation_dir / "body" / f"{uid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {uid}\n\nTranslated paragraph.{marker}\n")


def _target(store, texts: dict[str, str], *, stale: bool = False):
    (store.translation_dir / "notes.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "source_notes_sha256": "0" * 64
                if stale
                else notes_mod.file_digest(store.structured_dir / "notes.json"),
                "notes": [{"note_id": nid, "target_markdown": text} for nid, text in texts.items()],
            }
        )
    )


def _content(epub: Path, uid: str) -> str:
    with zipfile.ZipFile(epub) as zf:
        return zf.read(f"OEBPS/{uid}.xhtml").decode()


def _notes_findings(store, epub: Path, tmp_path: Path):
    cfg = Config()
    cfg.qc.epubcheck.jar = str(tmp_path / "not-installed.jar")
    return orch.qa(store, epub_path=str(epub), config=cfg)["notes_findings"]


def test_source_host_does_not_require_translation_for_later_cross_reference(tmp_path: Path):
    store = _workspace(tmp_path)
    _register(store, cross_ref=True)
    _translate(store, "ch02", "[^ref-000002]")
    epub = orch.build(store)
    assert "SOURCE NOTE ONE" in _content(epub, "ch01")
    assert 'href="ch01.xhtml#fn-n-000001"' in _content(epub, "ch02")


def test_mixed_product_audits_only_the_translation_notes_actually_used(tmp_path: Path):
    store = _workspace(tmp_path)
    _register(store, second_note=True)
    _translate(store, "ch02", "[^ref-000002]")
    _target(store, {"n-000001": "UNUSED TRANSLATION", "n-000002": "ACTUAL TRANSLATION"})
    epub = orch.build(store)
    assert "SOURCE NOTE ONE" in _content(epub, "ch01")
    assert "UNUSED TRANSLATION" not in _content(epub, "ch01")
    assert "ACTUAL TRANSLATION" in _content(epub, "ch02")
    assert _notes_findings(store, epub, tmp_path) == []
    before = epub.read_bytes()
    # 未用译注即使仍是空占位，也不应阻断源文宿主或改变成品。
    _target(store, {"n-000001": "", "n-000002": "ACTUAL TRANSLATION"})
    assert orch.build(store).read_bytes() == before
    assert _notes_findings(store, epub, tmp_path) == []


def test_source_fallback_ignores_malformed_unused_target_in_build_and_qa(tmp_path: Path):
    store = _workspace(tmp_path)
    _register(store)
    (store.translation_dir / "notes.json").write_text("{bad json")
    epub = orch.build(store)
    assert "SOURCE NOTE ONE" in _content(epub, "ch01")
    assert _notes_findings(store, epub, tmp_path) == []


def test_convert_uses_source_notes_even_when_translated_markdown_exists(tmp_path: Path):
    store = _workspace(tmp_path)
    _register(store)
    _translate(store, "ch01", "[^ref-000001]")
    (store.translation_dir / "notes.json").write_text("{bad json")
    epub = orch.convert(store)
    assert "SOURCE NOTE ONE" in _content(epub, "ch01")
    assert "Translated paragraph" not in _content(epub, "ch01")
    assert _notes_findings(store, epub, tmp_path) == []


def test_translated_orphan_cannot_use_stale_target_in_build_or_qa(tmp_path: Path):
    store = _workspace(tmp_path)
    _register(store, orphan=True)
    _translate(store, "ch01")
    _target(store, {"n-000001": "CURRENT TRANSLATION"})
    epub = orch.build(store)
    assert "CURRENT TRANSLATION" in _content(epub, "ch01")
    _target(store, {"n-000001": "STALE TRANSLATION"}, stale=True)
    before = epub.read_bytes()
    with pytest.raises(orch.OrchestrationError):
        orch.build(store)
    assert "E_NOTES_STALE" in {f["code"] for f in _notes_findings(store, epub, tmp_path)}
    assert epub.read_bytes() == before


def test_qa_rejects_registered_product_without_render_mode(tmp_path: Path):
    """缺少成品来源模式时，不得凭当前工作区文件猜配源/译注文。"""
    from xml.dom import minidom

    store = _workspace(tmp_path)
    _register(store)
    epub = orch.build(store)
    ambiguous = tmp_path / "no-mode.epub"
    with zipfile.ZipFile(epub) as source, zipfile.ZipFile(ambiguous, "w") as target:
        for info in source.infolist():
            data = source.read(info)
            if info.filename == "OEBPS/content.opf":
                document = minidom.parseString(data)
                for meta in list(document.getElementsByTagName("meta")):
                    if meta.getAttribute("property") == "aep:render-mode":
                        meta.parentNode.removeChild(meta)
                data = document.toxml(encoding="utf-8")
            target.writestr(info, data)
    assert "E_NOTES_STALE" in {
        finding["code"] for finding in _notes_findings(store, ambiguous, tmp_path)
    }
