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


def _production_page(tmp_path: Path, pub: Publication, *, lang: str = "zh-CN") -> Path:
    """无 copyright 单元 → 触发独立制作信息页（非线性 spine）的构建。"""
    entries = [{"id": "ch01", "region": "body", "title": "第一章"}]
    content_files = [("ch01.xhtml", render_document("第一章", "# 第一章\n\n正文。\n", lang=lang))]
    return build_epub(
        pub,
        entries,
        content_files,
        lang=lang,
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "page.epub",
    )


_GENERATION_TOOLS = [
    {
        "name": "DeepSeek-V3",
        "version": "2026-10",
        "task": "翻译",
        "url": "https://example.invalid/deepseek",
        "license": "MIT",
    },
    {"name": "GPT-5", "task": "复核"},
]


def test_production_page_carries_publication_and_generation_tools(tmp_path: Path) -> None:
    """制作页带出版/版权信息块与生成模型（LLM）条目，页面身份仍与指纹逐字一致。"""
    pub = Publication(
        slug="book",
        meta=PublicationMeta(
            title="测试书",
            creator="原作者",
            translator="OpenCode",
            publisher="测试出版社",
            date="2026-01-01",
            rights="© 原作者；保留所有权利",
            generation_tools=list(_GENERATION_TOOLS),
        ),
    )
    out = _production_page(tmp_path, pub)
    with zipfile.ZipFile(out) as zf:
        _, data = _read_fingerprint(zf)
        assert data["publication"] == {
            "title": "测试书",
            "creator": "原作者",
            "translator": "OpenCode",
            "publisher": "测试出版社",
            "date": "2026-01-01",
            "rights": "© 原作者；保留所有权利",
        }
        assert data["generation_tools"] == _GENERATION_TOOLS
        page = data["generated_page"]
        assert page and fingerprint.generated_pages(zf) == {page}
        text = zf.read("OEBPS/" + page).decode()
        assert _document_fingerprints(text) == [data]
    assert "版权与出版信息" in text
    assert "书名：测试书" in text
    assert "译者：OpenCode" in text
    assert "出版社：测试出版社" in text
    assert "生成模型（LLM）" in text
    assert "DeepSeek-V3 2026-10 — 翻译" in text
    assert "GPT-5 版本未记录 — 复核" in text  # 版本未知如实标注，不伪造
    assert text.index("版权与出版信息") < text.index("生成模型（LLM）")
    xhtml = "{http://www.w3.org/1999/xhtml}"
    section = ET.fromstring(text).find(f".//{xhtml}section[@class='software-provenance']")
    assert section is not None
    uls = section.findall(f"{xhtml}ul")
    assert len(uls) == 2  # 出版信息块在前，工具列表在后
    assert [li.text for li in uls[0].findall(f"{xhtml}li")] == [
        "书名：测试书",
        "作者：原作者",
        "译者：OpenCode",
        "出版社：测试出版社",
        "出版日期：2026-01-01",
        "版权/许可：© 原作者；保留所有权利",
    ]
    top_items = uls[1].findall(f"{xhtml}li")
    assert top_items[0].text == "生成模型（LLM）"
    assert len(top_items[0].findall(f"{xhtml}ul/{xhtml}li")) == 2
    assert len(top_items) == 1 + 2  # 生成模型标签 + Python/Pydantic
    assert audit_epub(out).ok


def test_production_page_without_publication_or_generation_tools_still_validates(
    tmp_path: Path,
) -> None:
    """旧工作区（无出版信息/生成模型）：制作页仍被识别，且不渲染空块/空列表。"""
    out = _production_page(tmp_path, Publication(slug="plain"), lang="en")
    with zipfile.ZipFile(out) as zf:
        _, data = _read_fingerprint(zf)
        assert data["publication"] == {}
        assert data["generation_tools"] is None
        page = data["generated_page"]
        assert page and fingerprint.generated_pages(zf) == {page}
        text = zf.read("OEBPS/" + page).decode()
    assert "Publication and rights information" not in text
    assert "Generation models (LLM)" not in text
    assert "Production software and open-source tools" in text
    assert audit_epub(out).ok


def test_software_section_renders_new_blocks_in_both_languages() -> None:
    """zh/en 两版文案：出版信息标签、生成模型条目标签与条目形式。"""
    data = fingerprint.build_fingerprint(
        Publication(
            slug="b",
            meta=PublicationMeta(
                title="测试书", creator="作者", generation_tools=list(_GENERATION_TOOLS)
            ),
        )
    )
    zh = fingerprint.software_section(data, "zh-CN", heading="h1")
    en = fingerprint.software_section(data, "en", heading="h1")
    assert "<h2>版权与出版信息</h2>" in zh
    assert "书名：测试书" in zh and "作者：作者" in zh
    assert "<li>生成模型（LLM）<ul>" in zh
    assert "<li>DeepSeek-V3 2026-10 — 翻译</li>" in zh
    assert "<h2>Publication and rights information</h2>" in en
    assert "Title: 测试书" in en and "Creator: 作者" in en
    assert "<li>Generation models (LLM)<ul>" in en
    assert "<li>DeepSeek-V3 2026-10 — 翻译</li>" in en
    assert en.index("Publication and rights information") < en.index("Generation models (LLM)")


def test_valid_accepts_new_optional_keys_without_loosening_identity() -> None:
    """_valid 接受新增可选键，但不放宽任何既有身份校验。"""
    data = fingerprint.build_fingerprint(Publication(slug="b"))
    assert fingerprint._valid(data)
    assert fingerprint._valid({**data, "publication": {"title": "T"}, "generation_tools": []})
    assert fingerprint._valid({**data, "publication": {}, "generation_tools": None})
    assert not fingerprint._valid({**data, "publication": ["title"]})
    assert not fingerprint._valid({**data, "generation_tools": "DeepSeek-V3"})
    assert not fingerprint._valid({**data, "project": {"name": "other"}})
    assert not fingerprint._valid({k: v for k, v in data.items() if k != "runtime"})


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
