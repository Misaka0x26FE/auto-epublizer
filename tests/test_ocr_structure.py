# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""OCR 结构化结果：每行保留坐标与置信度，并按段落合并为页内块。"""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from auto_epublizer.ingest.ocr import OcrLine, RapidOcrBackend, lines_from_engine_result
from auto_epublizer.ingest.pdf_reader import read_pdf


def _page_blocks(raw: Path) -> list[dict]:
    page = json.loads((raw / "page-001.json").read_text(encoding="utf-8"))
    return page["blocks"]


def _blank_pdf(path: Path) -> Path:
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(path)
    return path


class _LinesBackend:
    """结构化后端：刻意不实现 ocr_image，验证读取器优先用 ocr_lines。"""

    def ocr_lines(self, image_path: str) -> list[OcrLine]:
        assert Path(image_path).read_bytes().startswith(b"\x89PNG")
        return [
            OcrLine("first line", (10.0, 20.0, 110.0, 40.0), 0.9),
            OcrLine("second line", (10.0, 45.0, 110.0, 65.0), 0.7),
            OcrLine("next paragraph", (10.0, 300.0, 110.0, 320.0), 0.5),
        ]


def test_ocr_lines_become_blocks_with_page_coordinates(tmp_path: Path) -> None:
    source = _blank_pdf(tmp_path / "scan.pdf")
    raw = tmp_path / "raw"
    read_pdf(source, raw_dir=raw, ocr_backend=_LinesBackend(), page_dpi=100)

    page = json.loads((raw / "page-001.json").read_text(encoding="utf-8"))
    blocks = [b for b in page["blocks"] if b.get("ocr")]
    assert [b["text"] for b in blocks] == ["first line\nsecond line", "next paragraph"]
    # 渲染图像素 → PDF 点：dpi=100 时乘 72/100。
    assert blocks[0]["bbox"] == pytest.approx([7.2, 14.4, 79.2, 46.8], abs=1e-6)
    assert blocks[0]["ocr_confidence"] == pytest.approx(0.8)
    assert blocks[0]["ocr_lines"] == 2
    assert blocks[0]["ocr_source"].endswith("pages/p001.png")
    assert blocks[1]["bbox"] == pytest.approx([7.2, 216.0, 79.2, 230.4], abs=1e-6)


def test_coordinate_less_line_keeps_text_between_located_blocks(tmp_path: Path) -> None:
    """混合后端：无坐标行不得被丢弃，也不得冒用相邻行的坐标。"""

    class _MixedBackend:
        def ocr_lines(self, image_path: str) -> list[OcrLine]:
            return [
                OcrLine("located one", (10.0, 20.0, 110.0, 40.0), 0.9),
                OcrLine("no geometry", None, 0.4),
                OcrLine("located two", (10.0, 300.0, 110.0, 320.0), 0.8),
            ]

    source = _blank_pdf(tmp_path / "scan.pdf")
    raw = tmp_path / "raw"
    read_pdf(source, raw_dir=raw, ocr_backend=_MixedBackend(), page_dpi=100)

    blocks = [b for b in _page_blocks(raw) if b.get("ocr")]
    assert [b["text"] for b in blocks] == ["located one", "no geometry", "located two"]
    assert blocks[1]["bbox"] is None
    assert blocks[1]["ocr_confidence"] == pytest.approx(0.4)
    assert blocks[0]["bbox"] == pytest.approx([7.2, 14.4, 79.2, 28.8], abs=1e-6)


def test_plain_text_backend_keeps_previous_single_block(tmp_path: Path) -> None:
    source = _blank_pdf(tmp_path / "scan.pdf")
    raw = tmp_path / "raw"

    class _TextOnly:
        def ocr_image(self, image_path: str) -> str:
            return "plain ocr text"

    read_pdf(source, raw_dir=raw, ocr_backend=_TextOnly())
    page = json.loads((raw / "page-001.json").read_text(encoding="utf-8"))
    blocks = [b for b in page["blocks"] if b.get("ocr")]
    assert len(blocks) == 1
    block = blocks[0]
    assert block["text"] == "plain ocr text"
    assert block["bbox"] is None
    assert block["ocr_lines"] == 1
    assert block["ocr_source"].endswith("pages/p001.png")
    assert "ocr_confidence" not in block


def test_segments_carry_ocr_confidence_and_geometry(tmp_path: Path) -> None:
    source = _blank_pdf(tmp_path / "scan.pdf")
    doc = read_pdf(source, raw_dir=tmp_path / "raw", ocr_backend=_LinesBackend(), page_dpi=100)
    metas = [s.meta for u in doc.units for s in u.segments]
    assert metas[0]["source_page"] == 1
    assert metas[0]["source_bbox"] == pytest.approx([7.2, 14.4, 79.2, 46.8], abs=1e-6)
    assert metas[0]["ocr_confidence"] == pytest.approx(0.8)


def test_legacy_rapidocr_result_is_parsed_with_quad_boxes() -> None:
    result = [
        [[[10, 20], [110, 20], [110, 40], [10, 40]], "legacy line", 0.93],
        [[[10, 50], [110, 50], [110, 70], [10, 70]], "second", 0.81],
    ]
    lines = lines_from_engine_result(result)
    assert [line.text for line in lines] == ["legacy line", "second"]
    assert lines[0].bbox == (10.0, 20.0, 110.0, 40.0)
    assert lines[0].confidence == pytest.approx(0.93)


def test_v3_rapidocr_output_is_parsed() -> None:
    class _Output:
        txts = ("modern line",)
        boxes = ([[1, 2], [21, 2], [21, 12], [1, 12]],)
        scores = (0.88,)

    lines = lines_from_engine_result(_Output())
    assert lines == [OcrLine("modern line", (1.0, 2.0, 21.0, 12.0), pytest.approx(0.88))]


def test_rapidocr_backend_prefers_structured_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = object.__new__(RapidOcrBackend)
    backend._engine = lambda image: (
        [
            [[[0, 0], [10, 0], [10, 8], [0, 8]], "page line", 0.75],
        ],
        None,
    )
    lines = backend.ocr_lines("ignored.png")
    assert lines == [OcrLine("page line", (0.0, 0.0, 10.0, 8.0), pytest.approx(0.75))]
    assert backend.ocr_image("ignored.png") == "page line"


def test_unlocated_structured_lines_keep_confidence_and_source(tmp_path: Path) -> None:
    """无坐标的结构化行仍须带行数、来源与置信度均值：证据不能因缺几何而丢失。"""

    class _NoGeometry:
        def ocr_lines(self, image_path: str) -> list[OcrLine]:
            return [OcrLine("first line", None, 0.5), OcrLine("second line", None, 0.7)]

    source = _blank_pdf(tmp_path / "scan.pdf")
    raw = tmp_path / "raw"
    read_pdf(source, raw_dir=raw, ocr_backend=_NoGeometry(), page_dpi=100)

    blocks = [b for b in _page_blocks(raw) if b.get("ocr")]
    assert len(blocks) == 1
    block = blocks[0]
    assert block["text"] == "first line\nsecond line"
    assert block["bbox"] is None
    assert block["ocr_lines"] == 2
    assert block["ocr_source"].endswith("pages/p001.png")
    assert block["ocr_confidence"] == pytest.approx(0.6)


def test_split_block_paragraphs_uses_line_indent_without_changing_text() -> None:
    """#86：段首缩进把整块切成两段；续行抖动不切。"""
    from auto_epublizer.ingest.pdf_reader import split_block_paragraphs

    block = {
        "text": "First sentence.\nfirst continuation.\nSecond paragraph starts.\nsecond continuation.",
        "bbox": [10, 10, 110, 90],
        "font_size": 10,
        "lines": [
            {"text": "First sentence.", "bbox": [10, 10, 110, 20]},
            {"text": "first continuation.", "bbox": [10.5, 21, 110, 31]},
            {"text": "Second paragraph starts.", "bbox": [30, 32, 110, 42]},
            {"text": "second continuation.", "bbox": [10, 43, 110, 53]},
        ],
    }
    parts = split_block_paragraphs(block)
    assert [part["text"] for part in parts] == [
        "First sentence.\nfirst continuation.",
        "Second paragraph starts.\nsecond continuation.",
    ]
    assert parts[0]["bbox"][2] == 110


def test_group_ocr_lines_keeps_line_boxes_for_indent_evidence() -> None:
    """#86：OCR 合并块必须保留行框，后续才能判段首缩进。"""
    from auto_epublizer.ingest.pdf_reader import _group_ocr_lines

    lines = [
        OcrLine("first sentence.", (10.0, 20.0, 110.0, 40.0), 0.9),
        OcrLine("second paragraph.", (30.0, 45.0, 110.0, 65.0), 0.9),
    ]
    blocks = _group_ocr_lines(lines, scale=1.0, source="test")
    # 合并后按段首缩进切成两块；两块都必须保留行框。
    assert len(blocks) == 2
    assert all(block["lines"] for block in blocks)
    assert blocks[1]["text"] == "second paragraph."
    assert blocks[1]["lines"][0]["bbox"][0] == 30.0


def test_assign_columns_marks_two_column_geometry() -> None:
    """#58：双栏页标 0/1；单栏或证据不足不标。"""
    from auto_epublizer.ingest.pdf_reader import _assign_columns

    blocks = [
        {"type": "text", "bbox": [20, 10, 180, 40]},
        {"type": "text", "bbox": [25, 50, 180, 80]},
        {"type": "text", "bbox": [320, 10, 480, 40]},
        {"type": "text", "bbox": [322, 50, 480, 80]},
    ]
    _assign_columns(blocks, 500)
    assert [b.get("column") for b in blocks] == [0, 0, 1, 1]

    single = [{"type": "text", "bbox": [20, 10, 480, 40]}]
    _assign_columns(single, 500)
    assert "column" not in single[0]


def test_split_block_paragraphs_recomputes_group_font_size() -> None:
    """#86：拆段后字号按组取最大，不把标题字号带进正文段。"""
    from auto_epublizer.ingest.pdf_reader import split_block_paragraphs

    block = {
        "type": "text",
        "text": "Heading\\nBody one.\\nBody two.",
        "bbox": [10, 10, 200, 60],
        "font_size": 20,
        "lines": [
            {"text": "Heading.", "bbox": [10, 10, 200, 30], "size": 20},
            {"text": "Body one.", "bbox": [30, 31, 200, 45], "size": 10},
            {"text": "Body two.", "bbox": [30, 46, 200, 60], "size": 10},
        ],
    }
    parts = split_block_paragraphs(block)
    assert [part["font_size"] for part in parts] == [20, 10]


def test_assign_columns_ignores_centered_title_above_body() -> None:
    """居中标题 + 下方正文不构成双栏（垂直无重叠）。"""
    from auto_epublizer.ingest.pdf_reader import _assign_columns

    blocks = [
        {"type": "text", "bbox": [180, 10, 320, 30]},  # 居中标题
        {"type": "text", "bbox": [20, 100, 480, 140]},  # 正文
        {"type": "text", "bbox": [22, 150, 480, 190]},
    ]
    _assign_columns(blocks, 500)
    assert all("column" not in block for block in blocks)
