"""成品内的软件来源与书稿权利分离，工具历史不由当前环境倒推。"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from auto_common.workspace import Publication, PublicationMeta
from auto_epublizer import fingerprint
from auto_epublizer import orchestrator as orch
from auto_epublizer.build import build_epub
from auto_epublizer.build.html import render_document
from auto_epublizer.qa.audit import audit_epub
from auto_epublizer.qa.provenance import audit_provenance

NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}


def _read_fingerprint(zf: zipfile.ZipFile) -> tuple[ET.Element, dict]:
    opf = ET.fromstring(zf.read("OEBPS/content.opf"))
    node = opf.find("opf:metadata/opf:meta[@property='aep:build']", NS)
    assert node is not None
    return opf, json.loads(node.text)


def _document_fingerprints(text: str) -> list[dict]:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.fromstring(text, parser=parser)
    prefix = "auto-epublizer-build "
    return [
        json.loads(node.text.strip()[len(prefix) :])
        for node in root.iter()
        if node.tag is ET.Comment and node.text.strip().startswith(prefix)
    ]


def _package(tmp_path: Path, pub: Publication, *, comment: str = "") -> Path:
    entries = [{"id": "copyright", "kind": "copyright", "region": "frontmatter", "title": "版权"}]
    text = render_document("版权", "# 版权\n\n原书权利声明保留。", lang="zh-CN")
    text = text.replace("</head>", comment + "</head>")
    return build_epub(
        pub,
        entries,
        [("copyright.xhtml", text)],
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "book.epub",
    )


def test_copyright_and_all_machine_fields_use_current_build_not_init(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(fingerprint, "__version__", "9.7.3")
    old_tool = {
        "name": "Pandoc",
        "version": "2.19--custom<&>",
        "url": "https://pandoc.org/",
        "license": "GPL-2.0-or-later",
        "kind": "software",
    }
    pub = Publication(
        slug="book",
        meta=PublicationMeta(
            title="Book",
            creator="Original author",
            translator="Translator",
            rights="© Original rights holder; all book rights reserved.",
            producer="auto-epublizer@0.0.2",
            processing_tools=[old_tool],
        ),
    )
    out = _package(tmp_path, pub)
    with zipfile.ZipFile(out) as zf:
        opf, data = _read_fingerprint(zf)
        assert data["project"]["version"] == "9.7.3"
        assert data["project"]["url"] == fingerprint.PROJECT_URL
        assert data["processing_tools"] == [old_tool]
        assert data["generated_page"] is None
        assert opf.find("opf:metadata/dc:rights", NS).text == pub.meta.rights
        assert [n.text for n in opf.findall("opf:metadata/dc:creator", NS)] == [
            "Original author",
            "Translator",
        ]
        page = zf.read("OEBPS/copyright.xhtml").decode()
        root = ET.fromstring(page)
        assert "原书权利声明保留。" in "".join(root.itertext())
        assert (
            root.find(".//{http://www.w3.org/1999/xhtml}section[@class='software-provenance']")
            is not None
        )
        comments = _document_fingerprints(page)
        assert comments == [data]
        assert len(zf.namelist()) == len(set(zf.namelist()))
    assert pub.meta.producer == "auto-epublizer@0.0.2"
    assert audit_epub(out).ok


def test_legacy_workspace_marks_processing_history_unknown_not_current_installation(
    tmp_path: Path,
) -> None:
    out = _package(tmp_path, Publication(slug="old", meta=PublicationMeta(title="Old book")))
    with zipfile.ZipFile(out) as zf:
        _, data = _read_fingerprint(zf)
        assert data["processing_tools"] is None
        assert {tool["name"] for tool in data["runtime"]} == {"Python", "Pydantic"}
        assert all(tool["version"] for tool in data["runtime"])


def test_generated_page_is_not_an_unknown_source_unit_and_rebuild_is_deterministic(
    tmp_path: Path,
) -> None:
    src = tmp_path / "book.md"
    src.write_text("# Chapter\n\nBody text.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    units = store.load_publication().units
    source_bytes = src.read_bytes()
    out = orch.convert(store)
    first = out.read_bytes()
    orch.convert(store)
    assert out.read_bytes() == first
    assert src.read_bytes() == source_bytes
    assert [u.id for u in store.load_publication().units] == [u.id for u in units]
    with zipfile.ZipFile(out) as zf:
        opf, data = _read_fingerprint(zf)
        page = data["generated_page"]
        assert fingerprint.generated_pages(zf) == {page}
        ref = opf.find(f"opf:spine/opf:itemref[@idref='{page}']", NS)
        assert ref is not None and ref.attrib["linear"] == "no"
        landmarks = ET.fromstring(zf.read("OEBPS/landmarks.xhtml"))
        target = landmarks.find(
            ".//{http://www.w3.org/1999/xhtml}a[@{http://www.idpf.org/2007/ops}type='copyright-page']"
        )
        assert target is not None and target.attrib["href"] == page
        for name in (page, "ch01.xhtml"):
            comments = _document_fingerprints(zf.read("OEBPS/" + name).decode())
            assert comments == [data]
    report = audit_provenance(store, orch.structure_entries(store), out, prefer_translation=False)
    assert not report.units_unexpected
    assert not report.units_missing
    assert report.units_order_ok
    assert audit_epub(out).ok


def test_generated_page_does_not_overwrite_same_named_book_content(tmp_path: Path) -> None:
    name = "auto-epublizer-build-info.xhtml"
    original = render_document("Chapter", "# Chapter\n\nActual book content.", lang="en")
    out = build_epub(
        Publication(slug="book"),
        [{"id": "auto-epublizer-build-info", "title": "Chapter", "region": "body"}],
        [(name, original)],
        lang="en",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "book.epub",
    )
    with zipfile.ZipFile(out) as zf:
        _, data = _read_fingerprint(zf)
        assert data["generated_page"] != name
        assert "Actual book content." in zf.read("OEBPS/" + name).decode()
        assert fingerprint.generated_pages(zf) == {data["generated_page"]}
        assert len(zf.namelist()) == len(set(zf.namelist()))


@pytest.mark.parametrize(
    "comment",
    ["<!-- unfinished editorial material -->", "<!-- auto-epublizer-build {broken json} -->"],
)
def test_fingerprint_allowance_does_not_hide_editorial_residue(
    tmp_path: Path, comment: str
) -> None:
    out = _package(tmp_path, Publication(slug="book"), comment=comment)
    findings = audit_epub(out).findings
    assert any(f.code == "E_RESIDUE" and f.level == "error" for f in findings)


def test_auxiliary_page_requires_matching_manifest_metadata_and_page_identity(
    tmp_path: Path,
) -> None:
    src = tmp_path / "book.md"
    src.write_text("# Chapter\n\nBody text.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    out = orch.convert(store)
    changed = tmp_path / "tampered.epub"
    with zipfile.ZipFile(out) as source, zipfile.ZipFile(changed, "w") as target:
        _, data = _read_fingerprint(source)
        for member in source.infolist():
            payload = source.read(member.filename)
            if member.filename == "OEBPS/" + data["generated_page"]:
                payload = re.sub(
                    r"<!-- auto-epublizer-build .*?-->", "", payload.decode(), flags=re.DOTALL
                ).encode()
            target.writestr(member, payload)
    report = audit_provenance(
        store, orch.structure_entries(store), changed, prefer_translation=False
    )
    assert data["generated_page"] in report.units_unexpected
    assert any(f["code"] == "E_UNIT_ORDER" for f in report.findings)
