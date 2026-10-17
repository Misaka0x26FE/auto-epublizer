"""SVG image resources retain complete media identity through build and QA."""

from __future__ import annotations

import base64
import zipfile
from pathlib import Path

import pytest

from auto_common.workspace import Publication, PublicationMeta, RunStore
from auto_epublizer.build import build_epub, collect_media
from auto_epublizer.build.html import NoteItem, NoteRef, render_document
from auto_epublizer.qa.notes_audit import audit_notes_epub
from auto_epublizer.qa.provenance import audit_provenance


def _svg_product(tmp_path: Path, attr: str, placement: str, *, source_exists: bool = True):
    store = RunStore(tmp_path / "ws")
    store.ensure_skeleton()
    media_root = store.structured_dir / "raw" / "media"
    for directory in ("a", "b"):
        path = media_root / directory / "shared%41.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        if source_exists or directory == "b":
            path.write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
                    "/x8AAwMCAO+a9f8AAAAASUVORK5CYII="
                )
            )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink">'
        f'<image {attr}="a/shared%2541.png" width="1" height="1"/></svg>'
    )
    body = svg if placement == "body" else "Body.[^ref-000001]"
    md = f"# Chapter\n\n{body}\n"
    path = store.structured_dir / "body" / "ch01.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(md, encoding="utf-8")
    entries = [
        {
            "id": "ch01",
            "kind": "chapter",
            "region": "body",
            "title": "Chapter",
            "level": 1,
            "rel_path": "body/ch01.md",
        }
    ]
    rewritten, media, _ = collect_media(md, media_root)
    options = {}
    source_notes = {"inventory": "present", "notes": [], "references": []}
    if placement == "note":
        note_md, note_media, _ = collect_media(svg, media_root)
        media.extend(note_media)
        options = {
            "note_refs": {"ref-000001": NoteRef("ref-000001", "n-000001", 1)},
            "note_items": [NoteItem("n-000001", 1, note_md, ("ch01.xhtml#ref-000001",))],
            "href_by_note": {"n-000001": "ch01.xhtml"},
        }
        source_notes["notes"] = [{"note_id": "n-000001", "source_markdown": svg}]
        source_notes["references"] = [{"ref_id": "ref-000001", "note_id": "n-000001"}]
    html = render_document("Chapter", rewritten, lang="en", unit_id="ch01", **options)
    epub = store.output_dir / "book.epub"
    build_epub(
        Publication(slug="book", meta=PublicationMeta(title="Book", language="en")),
        entries,
        [("ch01.xhtml", html)],
        lang="en",
        modified="2026-01-01T00:00:00Z",
        out_path=epub,
        media_files=media,
    )
    return store, entries, epub, source_notes, media_root


def _audit(product, placement: str):
    store, entries, epub, source_notes, media_root = product
    if placement == "note":
        return audit_notes_epub(
            epub, source_notes=source_notes, target_notes=None, media_root=media_root
        )
    return audit_provenance(store, entries, epub, prefer_translation=False)


@pytest.mark.parametrize("attr", ["href", "xlink:href"])
@pytest.mark.parametrize("placement", ["body", "note"])
def test_svg_media_identity_survives_real_packaging(tmp_path: Path, attr: str, placement: str):
    product = _svg_product(tmp_path, attr, placement)
    assert _audit(product, placement).ok


@pytest.mark.parametrize("attr", ["href", "xlink:href"])
@pytest.mark.parametrize("placement", ["body", "note"])
def test_svg_same_basename_in_wrong_directory_is_rejected(
    tmp_path: Path, attr: str, placement: str
):
    product = _svg_product(tmp_path, attr, placement)
    epub = product[2]
    bad = tmp_path / "wrong-media.epub"
    with zipfile.ZipFile(epub) as source, zipfile.ZipFile(bad, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "OEBPS/ch01.xhtml":
                data = data.replace(b"media/a/shared%2541.png", b"media/b/shared%2541.png")
            target.writestr(item, data)
        target.writestr(
            "OEBPS/media/b/shared%41.png",
            (product[4] / "b" / "shared%41.png").read_bytes(),
        )
    product = (*product[:2], bad, *product[3:])
    result = _audit(product, placement)
    expected = "E_NOTES_MEDIA_MISSING" if placement == "note" else "E_MEDIA_EPUB_LOST"
    assert expected in {finding["code"] for finding in result.findings}


@pytest.mark.parametrize("placement", ["body", "note"])
def test_svg_missing_local_source_is_rejected(tmp_path: Path, placement: str):
    product = _svg_product(tmp_path, "href", placement, source_exists=False)
    result = _audit(product, placement)
    expected = "E_NOTES_MEDIA_MISSING" if placement == "note" else "E_MEDIA_EPUB_LOST"
    assert expected in {finding["code"] for finding in result.findings}
