"""按扩展名分发到对应读取器，并把归一化结果落到工作区 structured/raw/。"""

from __future__ import annotations

from pathlib import Path

from auto_common.workspace import RunStore

from .models import SourceDocument
from .pandoc_reader import PandocError, read_pandoc
from .pdf_reader import PdfError, read_pdf
from .text_reader import read_text


class IngestError(RuntimeError):
    """用户可见的输入处理错误。"""


_SUPPORTED = {".txt", ".md", ".markdown", ".html", ".htm", ".xhtml", ".docx", ".epub", ".pdf"}

_PANDOC_FORMATS = {
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".docx": "docx",
    ".epub": "epub",
}


def load_document(
    source_path: str | Path,
    *,
    store: RunStore | None = None,
    ocr_backend=None,
) -> SourceDocument:
    """按扩展名读取源文件并归一化为 SourceDocument。

    ``ocr_backend``：扫描 PDF 无文字层时的 OCR 后端（None 则报错提示走 OCR）。
    """
    path = Path(source_path)
    ext = path.suffix.lower()
    if ext not in _SUPPORTED:
        raise IngestError(
            f"不支持的格式：{ext}（支持 {' '.join(sorted(_SUPPORTED))}；或先转为 PDF/TXT/Markdown）"
        )

    raw_dir = store.structured_dir / "raw" if store is not None else None

    if ext in (".txt", ".md", ".markdown"):
        return read_text(str(path))
    if ext == ".pdf":
        try:
            return read_pdf(path, raw_dir=raw_dir, ocr_backend=ocr_backend)
        except PdfError as e:
            raise IngestError(str(e)) from e
    # 非 PDF 走 pandoc
    fmt = _PANDOC_FORMATS[ext]
    try:
        return read_pandoc(path, fmt=fmt, media_dir=raw_dir / "media" if raw_dir else None)
    except PandocError as e:
        raise IngestError(str(e)) from e


def normalize_to_workspace(store: RunStore) -> SourceDocument:
    """读取工作区 source 主文件并归一化，中间产物落 structured/raw/。"""
    pub = store.require_initialized()
    src_path = store.dir / pub.meta.source
    if not src_path.is_file():
        raise IngestError(f"源文件缺失：{src_path}")
    return load_document(src_path, store=store)
