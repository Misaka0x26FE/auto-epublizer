# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""源段落绑定的实际 PDF 字号与溢出诊断，不以全书中位数猜正文。"""

from __future__ import annotations

import pymupdf
import pytest

from auto_epublizer.pdfdiagnostics import collect_font_samples, diagnose_pdf


def _diagnose(doc, html):
    return diagnose_pdf(
        doc,
        samples=collect_font_samples(html),
        body_pt=10.5,
        note_pt=8.5,
        size_mm=(148, 210),
        margins_mm=(18, 16, 20, 16),
    )


@pytest.mark.parametrize("body_size", [10.5, 8.6])
def test_note_heavy_document_does_not_confuse_body_and_note_sizes(body_size: float) -> None:
    body = "Distinct body paragraph with enough characters for verified sampling."
    note = "Distinct note paragraph with bibliographic details and page numbers."
    with pymupdf.open() as doc:
        page = doc.new_page(width=420, height=595)
        page.insert_text((50, 80), body, fontsize=body_size)
        for index in range(15):
            page.insert_text((50, 120 + index * 20), note, fontsize=8.5)
        result = _diagnose(doc, f"<p>{body}</p><aside><p>{note}</p></aside>")
        assert result["fonts"]["body"]["observed_pt"] == pytest.approx(body_size, abs=0.02)
        assert result["fonts"]["notes"]["observed_pt"] == pytest.approx(8.5, abs=0.02)
        scale_findings = [f for f in result["findings"] if f["code"] == "E_PDF_FONT_SCALE"]
        assert bool(scale_findings) == (body_size == 8.6)


def test_image_only_or_unmatched_text_has_unknown_font_not_invented_measurements() -> None:
    with pymupdf.open() as doc:
        doc.new_page(width=420, height=595)
        result = _diagnose(doc, '<img src="image.png"/>')
        assert result["fonts"]["body"]["status"] == "unknown"
        assert result["fonts"]["body"]["observed_pt"] is None
        assert not any(f["code"] == "E_PDF_FONT_SCALE" for f in result["findings"])


def test_overflow_reports_actual_page_and_bbox() -> None:
    with pymupdf.open() as doc:
        page = doc.new_page(width=420, height=595)
        page.insert_text((360, 80), "Text outside the right margin", fontsize=10.5)
        result = _diagnose(doc, "<p>Text outside the right margin</p>")
        finding = next(f for f in result["findings"] if f["code"] == "E_PDF_OVERFLOW")
        assert finding["page"] == 1
        assert finding["bbox"][2] > 420 - 16 * 72 / 25.4


def test_identical_source_prefix_in_body_and_notes_is_not_classified_by_guessing() -> None:
    text = "Identical source paragraph repeated in both categories."
    with pymupdf.open() as doc:
        page = doc.new_page(width=420, height=595)
        page.insert_text((50, 80), text, fontsize=10.5)
        result = _diagnose(doc, f"<p>{text}</p><aside><p>{text}</p></aside>")
        assert result["fonts"]["body"]["status"] == "unknown"
        assert result["fonts"]["notes"]["status"] == "unknown"


def test_raster_overflow_is_reported_without_using_image_bytes_as_text_evidence() -> None:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 16, 16), False)
    pixmap.clear_with(127)
    with pymupdf.open() as doc:
        page = doc.new_page(width=420, height=595)
        page.insert_image(
            pymupdf.Rect(40, 100, 410, 570), stream=pixmap.tobytes("png"), keep_proportion=False
        )
        result = _diagnose(doc, '<img src="plate.png"/>')
        assert any(
            f["code"] == "E_PDF_OVERFLOW" and f["kind"] == "image" for f in result["findings"]
        )


def test_hanging_closing_punctuation_is_advisory_not_overflow() -> None:
    """CJK 行尾收标点悬挂（≤0.62em）是排版常态，不应算越界错误（真实书 11 页误报）。"""
    with pymupdf.open() as doc:
        page = doc.new_page(width=420, height=595)
        page.insert_text((370, 80), "）", fontsize=10.5, fontname="china-s")
        result = _diagnose(doc, "<p>正文句子。</p>")
        assert result["overflow_count"] == 0
        assert not any(f["code"] == "E_PDF_OVERFLOW" for f in result["findings"])
        assert any(f["code"] == "W_PDF_PUNCT_HANG" for f in result["findings"])


def test_punctuation_overflow_beyond_one_em_is_still_an_error() -> None:
    with pymupdf.open() as doc:
        page = doc.new_page(width=420, height=595)
        page.insert_text((400, 80), "）", fontsize=10.5)
        result = _diagnose(doc, "<p>正文句子。</p>")
        assert result["overflow_count"] == 1
        assert any(f["code"] == "E_PDF_OVERFLOW" for f in result["findings"])
