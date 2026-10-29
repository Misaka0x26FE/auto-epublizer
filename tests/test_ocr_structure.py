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


def test_plain_text_backend_keeps_previous_single_block(tmp_path: Path) -> None:
    source = _blank_pdf(tmp_path / "scan.pdf")
    raw = tmp_path / "raw"

    class _TextOnly:
        def ocr_image(self, image_path: str) -> str:
            return "plain ocr text"

    read_pdf(source, raw_dir=raw, ocr_backend=_TextOnly())
    page = json.loads((raw / "page-001.json").read_text(encoding="utf-8"))
    blocks = [b for b in page["blocks"] if b.get("ocr")]
    assert blocks == [{"type": "text", "bbox": None, "text": "plain ocr text", "ocr": True}]


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
