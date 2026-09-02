"""PDF 读取器：pymupdf 按页切片抽文字层 + 版面块 → 逐页落 structured/raw/。

每页独立处理、独立落盘、可单独重跑（断点续跑粒度 = 页）；页级结果保留坐标与
类型信息，是后续结构聚合与对账的 ground truth。

无文字层（扫描件）时，若提供 OCR 后端则逐页渲染为图片并 OCR；否则报错提示走 OCR 路径。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import fitz  # pymupdf

from .models import KIND_TEXT, SourceDocument, SourceSegment, SourceUnit
from .ocr import OcrBackend


class PdfError(RuntimeError):
    """PDF 解析失败。"""


def _page_blocks(page: fitz.Page) -> list[dict]:
    """抽取一页的版面块（text/image），保留 bbox 与字体信息。"""
    blocks: list[dict] = []
    for block in page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]:
        if block.get("type") != 0:
            continue
        lines: list[str] = []
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            if text.strip():
                lines.append(text)
        text = "\n".join(lines)
        if not text.strip():
            continue
        blocks.append(
            {
                "type": "text",
                "bbox": block.get("bbox"),
                "text": text,
            }
        )
    return blocks


def _ocr_page(page: fitz.Page, backend: OcrBackend, *, dpi: int, tmp_dir: str) -> list[dict]:
    """把一页渲染为图片并 OCR，返回该页的 text blocks。"""
    pix = page.get_pixmap(dpi=dpi)
    img_path = os.path.join(tmp_dir, f"ocr-{page.number + 1:03d}.png")
    pix.save(img_path)
    text = backend.ocr_image(img_path)
    if not text.strip():
        return []
    return [{"type": "text", "bbox": None, "text": text.strip(), "ocr": True}]


def read_pdf(
    path: str | Path,
    *,
    raw_dir: str | Path | None = None,
    ocr_backend: OcrBackend | None = None,
    page_dpi: int = 150,
) -> SourceDocument:
    """读取 PDF：按页切片抽文字层，逐页写 page-NNN.json 到 raw_dir；扫描件走 OCR。"""
    try:
        doc = fitz.open(str(path))
    except Exception as e:  # noqa: BLE001
        raise PdfError(f"无法打开 PDF：{e}") from e

    units: list[SourceUnit] = []
    segments: list[SourceSegment] = []
    total_blocks = 0
    page_count = doc.page_count
    tmp_dir: str | None = None
    if ocr_backend is not None:
        tmp_dir = tempfile.mkdtemp(prefix="auto-epub-ocr-")
    try:
        for page_no in range(page_count):
            page = doc[page_no]
            blocks = _page_blocks(page)
            if not blocks and ocr_backend is not None:
                blocks = _ocr_page(page, ocr_backend, dpi=page_dpi, tmp_dir=tmp_dir or "")
            total_blocks += len(blocks)
            if raw_dir is not None:
                raw_dir = Path(raw_dir)
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / f"page-{page_no + 1:03d}.json").write_text(
                    json.dumps(
                        {
                            "page_idx": page_no + 1,
                            "blocks": blocks,
                            "source": str(path),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            for block in blocks:
                idx = len(segments)
                segments.append(
                    SourceSegment(
                        index=idx,
                        source=block["text"],
                        kind=KIND_TEXT,
                        meta={
                            "source_page": page_no + 1,
                            "source_bbox": block.get("bbox"),
                        },
                    )
                )
    finally:
        doc.close()
        if tmp_dir:
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)

    if total_blocks == 0:
        raise PdfError("该 PDF 没有可抽取的文字层；若是扫描件请走 OCR 路径")

    if segments:
        units.append(
            SourceUnit(
                id="ch01",
                kind="chapter",
                title=os.path.splitext(os.path.basename(str(path)))[0],
                segments=segments,
                meta={"page_range": [1, page_count]},
            )
        )

    return SourceDocument(
        title=os.path.splitext(os.path.basename(str(path)))[0],
        source_path=os.path.abspath(str(path)),
        fmt="pdf",
        units=units,
        meta={"pages": page_count},
    )
