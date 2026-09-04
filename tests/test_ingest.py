"""ingest 测试：TXT/MD 解析、PDF 按页切片、OCR 占位、分发。"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_common.workspace import init_workspace
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


def test_load_document_pdf_ocr_fallback(tmp_path: Path) -> None:
    import fitz

    from auto_epublizer.ingest.ocr import FakeOcrBackend

    pdf_path = tmp_path / "scan.pdf"
    pdf = fitz.open()
    pdf.new_page()  # 无文字层
    pdf.save(str(pdf_path))
    pdf.close()

    doc = load_document(pdf_path, ocr_backend=FakeOcrBackend(text="OCR 识别出的正文"))
    assert doc.fmt == "pdf"
    assert any("OCR 识别出的正文" in s.source for u in doc.units for s in u.segments)


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


def _make_pdf(path: Path, pages: list[list[tuple[str, float]]]) -> Path:
    """构造多页 PDF：每页一组 (文本, 字号)，字号>正文即标题信号。"""
    import fitz

    pdf = fitz.open()
    for page_items in pages:
        page = pdf.new_page()
        y = 72
        for text, size in page_items:
            page.insert_text((72, y), text, fontsize=size)
            y += max(size * 1.5, 24)
    pdf.save(str(path))
    pdf.close()
    return path


def test_load_document_pdf_chapter_aggregation(tmp_path: Path) -> None:
    """PDF 按字号/章节关键词切分章节单元（C9）：大字号标题 → 多单元。"""
    pdf_path = _make_pdf(
        tmp_path / "book.pdf",
        [
            [("Chapter One", 24), ("The opening paragraph of the first chapter.", 12)],
            [("Chapter Two", 24), ("Second chapter body text here.", 12)],
        ],
    )
    store = init_workspace(pdf_path, workspace_dir=tmp_path / "ws")
    doc = load_document(pdf_path, store=store)
    titles = [u.title for u in doc.units]
    assert titles == ["Chapter One", "Chapter Two"], f"应聚合为两章，got {titles}"
    assert [u.id for u in doc.units] == ["ch01", "ch02"]
    # 每章首段是标题 kind=heading
    assert doc.units[0].segments[0].kind == "heading"
    assert doc.units[1].segments[0].kind == "heading"


def test_load_document_pdf_chapter_aggregation_keyword(tmp_path: Path) -> None:
    """章节关键词兜底：同字号下「第N章」文本也命中标题（C9 纯函数层）。

    直接用 aggregate_pdf_chapters 构造段，避免 PDF 默认字体无法渲染 CJK
    字形导致抽取文本变成占位符。
    """
    from auto_epublizer.ingest.models import KIND_TEXT, SourceSegment
    from auto_epublizer.ingest.pdf_reader import aggregate_pdf_chapters

    def seg(text: str, size: float = 12.0) -> SourceSegment:
        return SourceSegment(
            index=0,
            source=text,
            kind=KIND_TEXT,
            meta={"source_page": 1, "source_font_size": size},
        )

    segments = [
        seg("第一章 开始"),
        seg("正文内容若干。"),
        seg("第二章 发展"),
        seg("更多正文。"),
    ]
    units = aggregate_pdf_chapters(segments, book_title="book", page_count=2)
    assert [u.title for u in units] == ["第一章 开始", "第二章 发展"]
    assert units[0].segments[0].kind == "heading"


def test_load_document_pdf_no_heading_single_unit(tmp_path: Path) -> None:
    """无标题信号（同字号正文）时保持单单元回退（C9 不破坏旧行为）。"""
    pdf_path = _make_pdf(
        tmp_path / "book.pdf",
        [
            [("Plain running text page one.", 12)],
            [("More plain running text page two.", 12)],
        ],
    )
    store = init_workspace(pdf_path, workspace_dir=tmp_path / "ws")
    doc = load_document(pdf_path, store=store)
    assert len(doc.units) == 1
    assert doc.units[0].id == "ch01"
    assert doc.units[0].meta.get("aggregated") is not True
