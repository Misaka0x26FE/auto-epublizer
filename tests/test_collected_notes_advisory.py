# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""真实 EPUB/report/orchestrator 消费者；无语义裁决或外部 checker mock。"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_common.config import Config
from auto_common.workspace import Publication, PublicationMeta
from auto_epublizer import orchestrator as orch
from auto_epublizer.build import build_epub
from auto_epublizer.build.html import render_document
from auto_epublizer.qa import audit_epub, generate_report
from auto_epublizer.qa.epubcheck import EpubcheckResult

CODE = "W_COLLECTED_NOTES_UNSEGMENTED"
MEMBER = "OEBPS/back-notes.xhtml"


def _flat(count: int = 8, *, chars: int = 0) -> str:
    text = "Collected: " + " ".join(f"{number}. Note text." for number in range(1, count + 1))
    return text + "x" * max(0, chars - len(text))


def _package(tmp_path: Path, markdown: str, *, body: str | None = None) -> Path:
    pub = Publication(
        slug="book",
        meta=PublicationMeta(title="Notes fixture", creator="Fixture", target_language="en"),
    )
    entries = [{"id": "back-notes", "region": "backmatter", "title": "Notes"}]
    document = render_document("Notes", "# Notes\n\n" + markdown, lang="en")
    if body is not None:
        start = document.index("<body>") + len("<body>")
        end = document.index("</body>")
        document = document[:start] + "<h1>Notes</h1>" + body + document[end:]
    return build_epub(
        pub,
        entries,
        [("back-notes.xhtml", document)],
        lang="en",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "book.epub",
    )


def _context(markdown: str, *, kind: str = "notes") -> dict[str, dict[str, str]]:
    return {
        MEMBER: {
            "kind": kind,
            "unit": "back-notes",
            "markdown": markdown,
            "input_path": "structured/backmatter/notes.md",
        }
    }


def _warnings(result):
    return [finding for finding in result.findings if finding.code == CODE]


def test_imbalance_has_locatable_evidence_and_reaches_report(tmp_path: Path) -> None:
    markdown = _flat()
    result = audit_epub(_package(tmp_path, markdown), notes_context=_context(markdown))
    assert result.ok, result.findings
    (finding,) = _warnings(result)
    assert finding.level == "warning"
    # 检查报告真值表，不把构造的进程结果当成真实 EPUBCheck 验证。
    report = generate_report(
        "book",
        result,
        EpubcheckResult(available=True, ran=True, returncode=0, errors=0, warnings=0),
    ).to_dict()
    assert report["released"] is True
    assert report["released_reason"] == "ok"
    (saved,) = [f for f in report["audit"]["findings"] if f["code"] == CODE]
    assert saved["data"]["paragraph_indices"] == [1]
    assert saved["data"]["paragraphs"][0]["candidate_count"] == 8
    assert saved["data"]["input_candidate_count"] == 8
    assert saved["data"]["longest_block_chars"] == len(markdown)
    assert saved["data"]["reasons"] == ["candidate_paragraph_imbalance"]
    assert all("data" not in f for f in report["audit"]["findings"] if f["code"] != CODE)
    # advisory 不能覆盖独立 N 门的硬失败。
    blocked = generate_report(
        "book",
        result,
        EpubcheckResult(available=True, ran=True, returncode=0, errors=0, warnings=0),
        notes_audit={"findings": [{"level": "error", "code": "E_NOTES_CONTENT"}]},
    )
    assert not blocked.released and blocked.released_reason == "notes_open"


@pytest.mark.parametrize("count,paragraphs,expected", [(7, 1, False), (8, 2, True), (8, 3, False)])
def test_imbalance_thresholds(tmp_path: Path, count: int, paragraphs: int, expected: bool) -> None:
    markdown = _flat(count) + "\n\nContinuation." * (paragraphs - 1)
    result = audit_epub(_package(tmp_path, markdown), notes_context=_context(markdown))
    assert bool(_warnings(result)) is expected


@pytest.mark.parametrize(
    "chars,count,expected", [(999, 2, False), (1000, 2, True), (1000, 1, False)]
)
def test_long_paragraph_thresholds(tmp_path: Path, chars: int, count: int, expected: bool) -> None:
    markdown = _flat(count, chars=chars)
    result = audit_epub(_package(tmp_path, markdown), notes_context=_context(markdown))
    assert bool(_warnings(result)) is expected
    if expected:
        assert _warnings(result)[0].data["longest_paragraph_chars"] == chars


@pytest.mark.parametrize("kind", [None, "chapter", "appendix"])
def test_filename_and_body_numbers_do_not_authorize_scan(tmp_path: Path, kind: str | None) -> None:
    markdown = _flat(chars=1200)
    context = None if kind is None else _context(markdown, kind=kind)
    assert not _warnings(audit_epub(_package(tmp_path, markdown), notes_context=context))


def test_context_uses_exact_member_not_basename(tmp_path: Path) -> None:
    markdown = _flat(chars=1200)
    context = {"back-notes.xhtml": _context(markdown)[MEMBER]}
    assert not _warnings(audit_epub(_package(tmp_path, markdown), notes_context=context))


@pytest.mark.parametrize("semantics", ['epub:type="endnotes"', 'role="doc-endnotes"'])
def test_explicit_collection_scans_only_its_own_paragraphs(tmp_path: Path, semantics: str) -> None:
    body = (
        f"<p>{_flat(chars=1400)}</p>"
        f'<section id="collected" {semantics}><section epub:type="endnotes">'
        f"<p>Short introduction.</p><p>{_flat(2, chars=1000)}</p></section></section>"
    )
    result = audit_epub(_package(tmp_path, "", body=body))
    (finding,) = _warnings(result)
    assert finding.data["scope"] == "semantic_collection"
    assert finding.data["region_id"] == "collected"
    assert finding.data["paragraph_indices"] == [3]
    assert finding.data["paragraph_count"] == 2
    assert finding.data["input_candidate_count"] is None
    assert finding.data["rendered_candidate_count"] == 2


@pytest.mark.parametrize(
    "markdown",
    [
        "\n\n".join(f"{i}\\. One note.\n\nA continuation paragraph." for i in range(1, 9)),
        "\n".join(f"{i}. Ordered note." for i in range(1, 9)),
        "\n\n".join(f"{i}\\. One note.\n\n- First item\n- Second item" for i in range(1, 9)),
        "1\\. A note citing vol. 2. and chapter 3. in a short paragraph.",
    ],
)
def test_legitimate_multiblock_notes_and_short_citations_are_not_candidates(
    tmp_path: Path, markdown: str
) -> None:
    result = audit_epub(_package(tmp_path, markdown), notes_context=_context(markdown))
    assert not _warnings(result)


@pytest.mark.parametrize("literal", ["inline", "fenced", "raw"])
def test_code_literals_do_not_supply_candidate_numbers(tmp_path: Path, literal: str) -> None:
    numbers = _flat(8, chars=1200)
    if literal == "inline":
        markdown = f"A note: `{numbers}`."
    elif literal == "fenced":
        markdown = f"A note.\n\n```text\n{numbers}\n```"
    else:
        markdown = f"A note.\n\n```{{=html}}\n<pre><code>{numbers}</code></pre>\n```"
    result = audit_epub(_package(tmp_path, markdown), notes_context=_context(markdown))
    assert not _warnings(result)


def test_code_counts_cannot_inflate_imbalance(tmp_path: Path) -> None:
    markdown = _flat(2) + f"\n\n```\n{_flat(8)}\n```\n\n`{_flat(8)}`"
    assert not _warnings(audit_epub(_package(tmp_path, markdown), notes_context=_context(markdown)))


def test_escaped_markers_and_xml_entities_use_visible_text(tmp_path: Path) -> None:
    markdown = _flat().replace(". ", "\\. ")
    body = "<p>1. A &amp; B. " + " ".join(f"{i}. Text." for i in range(2, 9)) + "</p>"
    (finding,) = _warnings(
        audit_epub(_package(tmp_path, markdown, body=body), notes_context=_context(markdown))
    )
    assert finding.data["input_candidate_count"] == 8
    assert finding.data["rendered_candidate_count"] == 8
    assert finding.data["longest_paragraph_chars"] == len(
        "1. A & B. " + " ".join(f"{i}. Text." for i in range(2, 9))
    )


def test_semantic_individual_note_can_have_long_citations_and_multiple_paragraphs(
    tmp_path: Path,
) -> None:
    body = (
        '<section epub:type="endnotes"><aside epub:type="footnote" id="fn-n1">'
        f"<p>{_flat(chars=1500)}</p><p>Continuation.</p></aside></section>"
    )
    assert not _warnings(audit_epub(_package(tmp_path, "", body=body), notes_registered=True))


def _workspace(tmp_path: Path, markdown: str):
    source = tmp_path / "input.md"
    # 解析来源与后续实际渲染的 legacy 注释夹具独立。
    source.write_text("# Chapter I\n\nA plain body.\n", encoding="utf-8")
    store = orch.init(str(source), workspace_dir=str(tmp_path / "ws"))
    orch.ensure_structure(store)
    pub = store.load_publication()
    assert len(pub.units) == 1
    pub.units[0].kind = "notes"
    store.replace_units(pub.units)
    (entry,) = orch.structure_entries(store)
    (store.structured_dir / entry["rel_path"]).write_text(
        "# Notes\n\n" + markdown, encoding="utf-8"
    )
    return store, entry


@pytest.mark.parametrize("render", ["source", "translation", "fallback"])
def test_production_qa_supplies_actual_render_inputs(tmp_path: Path, render: str) -> None:
    store, entry = _workspace(tmp_path, _flat())
    if render != "fallback":
        translated = store.translation_dir / entry["rel_path"]
        translated.parent.mkdir(parents=True, exist_ok=True)
        translated.write_text("# Notes\n\n" + _flat(12), encoding="utf-8")
    epub = orch.convert(store) if render == "source" else orch.build(store)
    cfg = Config()
    cfg.qc.epubcheck.jar = str(tmp_path / "unavailable.jar")
    report = orch.qa(store, epub_path=str(epub), config=cfg)
    (finding,) = [f for f in report["audit"]["findings"] if f["code"] == CODE]
    expected_count = 12 if render == "translation" else 8
    expected_root = "translation" if render == "translation" else "structured"
    assert finding["data"]["input_candidate_count"] == expected_count
    assert finding["data"]["rendered_candidate_count"] == expected_count
    assert finding["data"]["input_path"] == f"{expected_root}/{entry['rel_path']}"
    assert finding["data"]["unit"] == entry["id"]
    assert report["g4_audit"] == "pass"
    assert not report["epubcheck"]["ran"]
    assert not report["released"]  # No invented external-check evidence.


def test_production_conversion_does_not_count_unrendered_translation(tmp_path: Path) -> None:
    store, entry = _workspace(tmp_path, "1\\. A single source note.")
    translated = store.translation_dir / entry["rel_path"]
    translated.parent.mkdir(parents=True, exist_ok=True)
    translated.write_text("# Notes\n\n" + _flat(), encoding="utf-8")
    epub = orch.convert(store)
    cfg = Config()
    cfg.qc.epubcheck.jar = str(tmp_path / "unavailable.jar")
    report = orch.qa(store, epub_path=str(epub), config=cfg)
    assert not [f for f in report["audit"]["findings"] if f["code"] == CODE]


def test_flat_notes_inside_one_ordered_list_item_are_candidates(tmp_path: Path) -> None:
    markdown = " ".join(f"{number}. Note content." for number in range(1, 9))
    # 形状由显式 body 给出：本用例考的是检测器对「一批注文挤在一个 <li> 里」的反应，
    # 不是渲染器怎样从 markdown 生成该形状（单项块现在按段落输出，见 test_build.py）。
    body = f"<ol><li>{markdown}</li></ol>"
    result = audit_epub(_package(tmp_path, markdown, body=body), notes_context=_context(markdown))
    assert result.ok
    (finding,) = _warnings(result)
    assert finding.data["paragraph_count"] == 0
    assert finding.data["list_item_count"] == 1
    assert finding.data["input_candidate_count"] == 8
    assert finding.data["list_item_indices"] == [1]
    assert finding.data["paragraph_indices"] == []


def test_long_semantic_note_list_item_has_a_real_locator(tmp_path: Path) -> None:
    markdown = _flat(chars=1200)
    body = f'<section epub:type="endnotes"><ol><li>{markdown}</li></ol></section>'
    result = audit_epub(_package(tmp_path, markdown, body=body))
    (finding,) = _warnings(result)
    assert finding.data["scope"] == "semantic_collection"
    assert finding.data["input_candidate_count"] is None
    assert finding.data["list_item_indices"] == [1]
    assert finding.data["longest_list_item_chars"] >= 1200


def test_nested_note_list_containers_do_not_merge_child_evidence(tmp_path: Path) -> None:
    items = "".join(
        f"<li>{number}. " + "A complete individually segmented note. " * 5 + "</li>"
        for number in range(1, 9)
    )
    body = (
        f'<section epub:type="endnotes"><ol><li>Chapter notes<ol>{items}</ol></li></ol></section>'
    )
    result = audit_epub(_package(tmp_path, "", body=body))
    assert not _warnings(result)
