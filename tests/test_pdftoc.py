# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""印刷目录按身份回填，不把相同条数或标题子串当定位证据。"""

from auto_epublizer.pdftoc import (
    canonical_href,
    inject_anchor_markers,
    is_toc_document,
    member_href,
    rewrite_toc,
)


def test_paragraph_toc_titles_can_span_multiple_blocks() -> None:
    entries = [(1, "Long title and subtitle", "OEBPS/ch.xhtml")]
    result = rewrite_toc(
        "<h1>Contents</h1><p>Long title</p><p>and subtitle 3</p>",
        entries,
        {"OEBPS/ch.xhtml": 17},
        owner_href="OEBPS/toc.xhtml",
    )
    assert "and subtitle 17" in result.html
    assert result.updates[0]["href"] == "OEBPS/ch.xhtml"
    assert not result.findings


def test_chapter_number_at_end_of_a_title_fragment_is_not_overwritten_as_page() -> None:
    entries = [(1, "Chapter 2 New directions", "OEBPS/ch.xhtml")]
    result = rewrite_toc(
        "<p>Chapter 2</p><p>New directions 39</p>",
        entries,
        {"OEBPS/ch.xhtml": 12},
        owner_href="OEBPS/toc.xhtml",
    )
    assert "Chapter 2" in result.html
    assert "New directions 12" in result.html
    assert not result.findings


def test_list_toc_preserves_author_markup_when_replacing_roman_page() -> None:
    entries = [(1, "序", "OEBPS/preface.xhtml")]
    result = rewrite_toc(
        "<li><strong>序</strong> — vii <em>Alice Author</em></li>",
        entries,
        {"OEBPS/preface.xhtml": 8},
        owner_href="OEBPS/toc.xhtml",
    )
    assert "— 8 " in result.html
    assert "<em>Alice Author</em>" in result.html
    assert not result.findings


def test_explicit_link_disambiguates_identical_titles_and_keeps_fragment_identity() -> None:
    entries = [(1, "Introduction", "OEBPS/a.xhtml#one"), (1, "Introduction", "OEBPS/b.xhtml#two")]
    result = rewrite_toc(
        '<p><a href="../b.xhtml#two">Introduction</a> 7</p>',
        entries,
        {"OEBPS/a.xhtml#one": 10, "OEBPS/b.xhtml#two": 26},
        owner_href="OEBPS/front/toc.xhtml",
    )
    assert "> 26<" in result.html or " 26</p>" in result.html
    assert result.updates[0]["href"] == "OEBPS/b.xhtml#two"


def test_equal_counts_in_a_different_order_do_not_pair_by_position() -> None:
    entries = [(1, "Alpha", "OEBPS/a.xhtml"), (1, "Beta", "OEBPS/b.xhtml")]
    result = rewrite_toc(
        "<p>Beta 1</p><p>Alpha 2</p>",
        entries,
        {"OEBPS/a.xhtml": 10, "OEBPS/b.xhtml": 20},
        owner_href="OEBPS/toc.xhtml",
    )
    assert "Beta 20" in result.html and "Alpha 10" in result.html


def test_ambiguous_or_unlocated_toc_entries_do_not_borrow_nearby_pages() -> None:
    entries = [
        (1, "Introduction", "OEBPS/a.xhtml"),
        (1, "Introduction", "OEBPS/b.xhtml"),
        (1, "Missing", "OEBPS/c.xhtml"),
    ]
    result = rewrite_toc(
        "<p>Introduction 7</p><p>Missing 9</p>",
        entries,
        {"OEBPS/a.xhtml": 10, "OEBPS/b.xhtml": 20},
        owner_href="OEBPS/toc.xhtml",
    )
    assert not result.updates
    assert len(result.findings) == 2
    assert "未定位" in result.html
    assert "原版页码" in result.html  # 保留数字时必须在成品中明确来源，不仅写日志


def test_index_document_is_not_implicitly_a_toc() -> None:
    assert not is_toc_document("<h1>Index</h1><p>Alpha 7</p>", title="Index")
    assert is_toc_document("<h1>Contents</h1><p>Alpha 7</p>", title="Contents")
    assert is_toc_document(
        '<section epub:type="toc"><p>Alpha 7</p></section>', title="Book outline"
    )


def test_text_only_prefix_stays_escaped_after_toc_rewrite() -> None:
    result = rewrite_toc(
        "&lt;script&gt;literal example&lt;/script&gt;<p>Alpha 7</p>",
        [(1, "Alpha", "OEBPS/a.xhtml")],
        {"OEBPS/a.xhtml": 10},
        owner_href="OEBPS/toc.xhtml",
    )
    assert "&lt;script&gt;" in result.html
    assert "<script>" not in result.html


def test_linked_row_without_original_page_still_reports_missing_target() -> None:
    result = rewrite_toc(
        '<li><a href="a.xhtml">Alpha</a></li>',
        [(1, "Alpha", "OEBPS/a.xhtml")],
        {},
        owner_href="OEBPS/toc.xhtml",
    )
    assert any(f["code"] == "E_PDF_TOC_UNLOCATED" for f in result.findings)
    assert "未定位" in result.html


def test_url_identity_keeps_literal_hash_filename_separate_from_fragment() -> None:
    assert (
        canonical_href("../text/part%23one.xhtml#first%20section", "OEBPS/front/toc.xhtml")
        == "OEBPS/text/part%23one.xhtml#first%20section"
    )
    assert member_href("part%2523one.xhtml", "OEBPS/nav.xhtml") == "OEBPS/part%23one.xhtml"
    assert member_href("#target", "OEBPS/nav.xhtml") == "OEBPS/nav.xhtml"
    assert member_href("", "OEBPS/nav.xhtml") is None


def test_anchor_marker_is_bound_to_actual_id_not_an_earlier_title_echo() -> None:
    inner = '<p>序 appears in the contents.</p><h2 id="preface">序</h2>'
    result = inject_anchor_markers(
        inner, [(1, "序", "OEBPS/ch.xhtml#preface")], owner_href="OEBPS/ch.xhtml"
    )
    marker = result.markers["OEBPS/ch.xhtml#preface"]
    assert result.html.index(marker) > result.html.index('id="preface"')
    assert result.html.startswith("<p>序 appears in the contents.</p>")
    assert not result.findings


def test_missing_and_duplicate_anchor_ids_remain_unlocated() -> None:
    result = inject_anchor_markers(
        '<h2 id="dup">One</h2><h2 id="dup">Two</h2>',
        [(1, "X", "OEBPS/ch.xhtml#missing"), (1, "Y", "OEBPS/ch.xhtml#dup")],
        owner_href="OEBPS/ch.xhtml",
    )
    assert not result.markers
    assert {f["code"] for f in result.findings} == {
        "E_PDF_ANCHOR_MISSING",
        "E_PDF_ANCHOR_AMBIGUOUS",
    }
