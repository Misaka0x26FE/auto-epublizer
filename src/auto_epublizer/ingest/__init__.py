"""输入解析：把源文件归一化为 Document → Unit → Segment 结构。

- 非 PDF 一律先走 pandoc → Markdown（纯文本）+ 抽取媒体；
- PDF 按页切片（pymupdf）→ structured/raw/page-NNN.json + 文字层；
- 扫描件 OCR（RapidOCR 离线默认）+ 视觉 LLM 兜底（占位，后续实现）。
"""

from __future__ import annotations

from .load import IngestError, load_document, normalize_to_workspace
from .models import (
    KIND_HEADING,
    KIND_TEXT,
    SourceDocument,
    SourceSegment,
    SourceUnit,
)

__all__ = [
    "IngestError",
    "KIND_HEADING",
    "KIND_TEXT",
    "SourceDocument",
    "SourceSegment",
    "SourceUnit",
    "load_document",
    "normalize_to_workspace",
]
