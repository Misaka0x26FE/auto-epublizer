"""ingest 测试：TXT/MD 解析、PDF 按页切片、OCR 占位、分发。"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_epublizer.ingest import (
    KIND_HEADING,
    KIND_TEXT,
    IngestError,
    SourceDocument,
    load_document,
)
from auto_epublizer.ingest.ocr import FakeOcrBackend, create_ocr_backend
from auto_epublizer.ingest.pandoc_reader import parse_markdown_units
from auto_epublizer.ingest.text_reader import read_text
from auto_epublizer.workspace import init_workspace


def test_read_text_units(tmp_path: Path) -> None:
    p = tmp_path / "book.md"
    p.write_text(
        "# 第一章\n\n第一段内容。\n\n第二段内容。\n\n## 第一节\n\n小节内容。\n",
        encoding="utf-8",
    )
    doc = read_text(str(p))
    assert isinstance(doc, SourceDocument)
    assert doc.fmt == "text"
    assert len(doc.units) >= 1
    first = doc.units[0]
    assert first.segments[0].kind == KIND_HEADING
    assert any(s.kind == KIND_TEXT for s in first.segments)


def test_read_text_single_unit_without_heading(tmp_path: Path) -> None:
    p = tmp_path / "plain.txt"
    p.write_text("只有一段。\n", encoding="utf-8")
    doc = read_text(str(p))
    assert len(doc.units) == 1
    assert doc.units[0].segments[0].kind == KIND_TEXT


def test_parse_markdown_units() -> None:
    content = "# Title\n\nPara one.\n\nPara two.\n\n## Sub\n\nBody.\n"
    units = parse_markdown_units(content)
    assert units[0].title == "Title"
    assert any(s.kind == KIND_TEXT for s in units[0].segments)


def test_load_document_md(tmp_path: Path) -> None:
    p = tmp_path / "book.md"
    p.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    doc = load_document(p)
    assert doc.fmt == "text"


def test_load_document_unsupported(tmp_path: Path) -> None:
    p = tmp_path / "book.xyz"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(IngestError):
        load_document(p)


def test_load_document_pdf_text_layer(tmp_path: Path) -> None:
    import fitz

    pdf_path = tmp_path / "book.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 100), "Hello PDF text layer.")
    pdf.save(str(pdf_path))
    pdf.close()

    store = init_workspace(pdf_path, workspace_dir=tmp_path / "ws")
    doc = load_document(pdf_path, store=store)
    assert doc.fmt == "pdf"
    raw_dir = store.structured_dir / "raw"
    page_files = list(raw_dir.glob("page-*.json"))
    assert len(page_files) >= 1
    assert any("Hello" in s.source for u in doc.units for s in u.segments)


def test_load_document_pdf_no_text_raises(tmp_path: Path) -> None:
    import fitz

    pdf_path = tmp_path / "blank.pdf"
    pdf = fitz.open()
    pdf.new_page()
    pdf.save(str(pdf_path))
    pdf.close()
    with pytest.raises(IngestError):
        load_document(pdf_path)


def test_fake_ocr_backend() -> None:
    backend = FakeOcrBackend(text="识别文本")
    assert backend.ocr_image("nope.png") == "识别文本"


def test_create_ocr_backend() -> None:
    backend = create_ocr_backend("fake")
    assert backend.ocr_image("x.png") == "OCR 占位文本"
    with pytest.raises(ValueError):
        create_ocr_backend("nope")


def test_normalize_to_workspace(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    store = init_workspace(src, workspace_dir=tmp_path / "ws")
    doc = load_document(src, store=store)
    assert doc.fmt == "text"
