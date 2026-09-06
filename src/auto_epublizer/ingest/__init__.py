"""输入解析：把源文件归一化为 Document → Unit → Segment 结构。

- 非 PDF 一律先走 pandoc → Markdown（纯文本）+ 抽取媒体；
- PDF 按页切片（pymupdf）→ structured/raw/page-NNN.json + 文字层；
- 扫描件：MinerU 外部 API（首选，需 MINERU_API_KEY）或 RapidOCR 离线 OCR；
  无法识别的页面由 agent 逐页阅读兜底（唯一 LLM 原则：CLI 不调用任何模型）。
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
