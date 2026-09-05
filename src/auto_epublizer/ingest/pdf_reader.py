"""PDF 读取器：pymupdf 按页切片抽文字层 + 版面块 → 逐页落 structured/raw/。

每页独立处理、独立落盘、可单独重跑（断点续跑粒度 = 页）；页级结果保留坐标与
类型信息，是后续结构聚合与对账的 ground truth。

无文字层（扫描件）时，若提供 OCR 后端则逐页渲染为图片并 OCR；渲染页图持久化到
``structured/raw/pages/pNNN.png``（传统 OCR 只识别字符，换行与插图由 agent 逐页
阅读 OCR 产物 + 看图兜底，见 skills lessons）。扫描件的最优先路径是 MinerU 外部
解析 API（见 ingest/mineru.py），本路径为次选。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import fitz  # pymupdf

from .formula import is_formula_block, is_math_font
from .images import (
    FULL_PAGE_AREA_RATIO,
    TEXT_COVERAGE_MAX,
    extract_embedded_images,
    large_image_rects,
    render_full_page,
)
from .inserts import InsertRecord, InsertSource, next_insert_id, write_inserts
from .models import KIND_HEADING, KIND_TEXT, SourceDocument, SourceSegment, SourceUnit
from .ocr import OcrBackend
from .reading_order import sort_reading_order
from .tables import extract_tables


class PdfError(RuntimeError):
    """PDF 解析失败。"""


_CHAPTER_KEYWORD = re.compile(
    r"第[0-9０-９一二三四五六七八九十百千]+[章話话节節回部巻卷]"
    r"|序章|終章|序幕|プロローグ|エピローグ|あとがき|まえがき"
    r"|Chapter\s+\d+|CHAPTER\s+\d+",
    re.IGNORECASE,
)


def _median_font_size(segments: list[SourceSegment]) -> float:
    sizes = sorted(
        float(s.meta.get("source_font_size") or 0)
        for s in segments
        if s.kind != KIND_HEADING and float(s.meta.get("source_font_size") or 0) > 0
    )
    if not sizes:
        return 0.0
    n = len(sizes)
    mid = n // 2
    return sizes[mid] if n % 2 else (sizes[mid - 1] + sizes[mid]) / 2.0


def _is_chapter_heading(seg: SourceSegment, body_median: float) -> bool:
    """标题启发式：章节关键词，或短文本且字号显著大于正文中位数（>1.3×）。"""
    text = seg.source.strip()
    if not text or len(text) > 80:
        return False
    if _CHAPTER_KEYWORD.search(text):
        return True
    size = float(seg.meta.get("source_font_size") or 0)
    return size > 0 and body_median > 0 and size >= body_median * 1.3


def _seg_page(seg: SourceSegment) -> int:
    """段所在页号（1-based；缺失/非法按第 1 页处理，保证总是落进某个单元）。"""
    try:
        p = int(seg.meta.get("source_page") or 0)
    except (TypeError, ValueError):
        return 1
    return p if p >= 1 else 1


def _level1_toc(toc: list[list] | None, page_count: int) -> list[tuple[int, str]]:
    """提取有效 level-1 书签（页号单调、去重、越界过滤）；少于 2 条视为无效。"""
    if not toc:
        return []
    entries: list[tuple[int, str]] = []
    for item in toc:
        try:
            level, title, page = int(item[0]), str(item[1]).strip(), int(item[2])
        except (TypeError, ValueError, IndexError):
            continue
        if level != 1 or not title or page < 1 or page > page_count:
            continue
        if entries and page <= entries[-1][0]:
            continue  # 非单调 / 同页重复：取首个
        entries.append((page, title))
    return entries if len(entries) >= 2 else []


def _aggregate_by_toc(
    segments: list[SourceSegment],
    *,
    book_title: str,
    page_count: int,
    entries: list[tuple[int, str]],
) -> list[SourceUnit]:
    """按书签切章：首个条目前的页 → frontmatter；末章延伸到全书末页。"""
    units: list[SourceUnit] = []
    first_start = entries[0][0]
    if first_start > 1:
        front = [s for s in segments if _seg_page(s) < first_start]
        if front:
            units.append(
                SourceUnit(
                    id="fm01",
                    kind="frontmatter",
                    title=book_title,
                    segments=front,
                    meta={"page_range": [1, first_start - 1], "aggregated": True},
                )
            )
    for i, (start_page, title) in enumerate(entries):
        end_page = entries[i + 1][0] - 1 if i + 1 < len(entries) else page_count
        segs = [s for s in segments if start_page <= _seg_page(s) <= end_page]
        units.append(
            SourceUnit(
                id=f"ch{i + 1:02d}",
                kind="chapter",
                title=title,
                segments=segs,
                meta={"page_range": [start_page, end_page], "aggregated": True},
            )
        )
    return units


def aggregate_pdf_chapters(
    segments: list[SourceSegment],
    *,
    book_title: str,
    page_count: int,
    toc: list[list] | None = None,
) -> list[SourceUnit]:
    """把 PDF 扁平段切分为章节单元：书签 TOC 优先，字号/关键词启发式降级。

    书签路径（≥2 条单调 level-1 条目）：level-1 页号为章边界，首条目前的页归
    frontmatter，末章延伸到全书末页。无有效书签时回落标题启发式（C9）：
    命中标题（章节关键词 / 大字号短文本）处起新单元；无任何标题信号时
    保持单单元（回退旧行为）。OCR 路径无字号信息，仅关键词可命中。
    """
    entries = _level1_toc(toc, page_count)
    if entries:
        return _aggregate_by_toc(
            segments, book_title=book_title, page_count=page_count, entries=entries
        )

    body_median = _median_font_size(segments)
    if not any(_is_chapter_heading(s, body_median) for s in segments):
        return [
            SourceUnit(
                id="ch01",
                kind="chapter",
                title=book_title,
                segments=segments,
                meta={"page_range": [1, page_count]},
            )
        ]

    units: list[SourceUnit] = []
    current_title: str | None = None
    current: list[SourceSegment] = []
    chapter_no = 0

    def _flush() -> None:
        nonlocal current_title, current, chapter_no
        if not current and current_title is None:
            return
        chapter_no += 1
        units.append(
            SourceUnit(
                id=f"ch{chapter_no:02d}",
                kind="chapter",
                title=current_title or book_title,
                segments=current,
                meta={"page_range": [1, page_count], "aggregated": True},
            )
        )
        current_title = None
        current = []

    for seg in segments:
        if _is_chapter_heading(seg, body_median):
            _flush()
            current_title = seg.source.strip()
            current = [seg.model_copy(update={"kind": KIND_HEADING})]
        else:
            current.append(seg)
    _flush()

    return units


def _page_blocks(page: fitz.Page) -> list[dict]:
    """抽取一页的版面块（text），保留 bbox、字体与数学字体标记。"""
    blocks: list[dict] = []
    for block in page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]:
        if block.get("type") != 0:
            continue
        lines: list[str] = []
        max_size = 0.0
        math_font: str | None = None
        math_font_chars = 0
        for line in block.get("lines", []):
            line_size = 0.0
            for span in line.get("spans", []):
                size = float(span.get("size", 0) or 0)
                line_size = max(line_size, size)
                font = span.get("font") or ""
                if is_math_font(font):
                    if math_font is None:
                        math_font = font
                    math_font_chars += len(span.get("text", ""))
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            if text.strip():
                lines.append(text)
                max_size = max(max_size, line_size)
        text = "\n".join(lines)
        if not text.strip():
            continue
        entry: dict = {
            "type": "text",
            "bbox": block.get("bbox"),
            "text": text,
            "font_size": max_size,
        }
        if math_font is not None:
            entry["math_font"] = math_font
            entry["math_font_chars"] = math_font_chars
        blocks.append(entry)
    return blocks


def _block_area(block: dict) -> float:
    bbox = block.get("bbox")
    if not bbox or len(bbox) != 4:
        return 0.0
    return max(0.0, float(bbox[2]) - float(bbox[0])) * max(0.0, float(bbox[3]) - float(bbox[1]))


def _center_inside(bbox: list[float] | None, boxes: list[list[float]]) -> bool:
    if not bbox or len(bbox) != 4:
        return False
    cx = (float(bbox[0]) + float(bbox[2])) / 2
    cy = (float(bbox[1]) + float(bbox[3])) / 2
    return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes)


def _page_extras(
    doc: fitz.Document,
    page: fitz.Page,
    text_blocks: list[dict],
    *,
    records: list[InsertRecord],
    media_dir,
) -> list[dict]:
    """P1 内容提取路由（docs/pdf-content-spec.md §3-§5）：整页图版 → 公式 → 表格 → 内嵌图。

    返回按阅读顺序合并的页面 blocks（含原 text_blocks，公式块原位转换）。
    """
    page_area = abs(page.rect) or 1.0
    text_chars = sum(len(b.get("text", "")) for b in text_blocks)
    text_cov = sum(_block_area(b) for b in text_blocks) / page_area
    img_rects = large_image_rects(page)
    img_cov = sum(r.width * r.height for r in img_rects) / page_area

    # 1) 整页图版：图占满页 + 文字极少（字数守卫保护带文字层的扫描页）
    if img_cov >= FULL_PAGE_AREA_RATIO and text_cov < TEXT_COVERAGE_MAX and text_chars < 200:
        return [render_full_page(page, records=records, media_dir=media_dir)]

    # 2) 公式检测：text 块原位转 formula（md 呈现 $$…$$），记录待 agent 手写 LaTeX
    formula_bboxes: list[list[float]] = []
    for b in text_blocks:
        if is_formula_block(b, page_width=page.rect.width, chapter_re=_CHAPTER_KEYWORD):
            b["type"] = "formula"
            iid = next_insert_id(records, page.number + 1, "formula")
            b["text"] = f"$${b['text']}$$"
            b["insert_id"] = iid
            records.append(
                InsertRecord(
                    id=iid,
                    type="formula",
                    source=InsertSource(
                        page=page.number + 1,
                        bbox=b.get("bbox"),
                        method="formula",
                    ),
                )
            )
            if b.get("bbox"):
                formula_bboxes.append(list(b["bbox"]))

    # 3) 表格双路径：纯文字 → md；含图/公式 → 区域裁剪图
    table_blocks = extract_tables(
        page,
        records=records,
        media_dir=media_dir,
        image_bboxes=[list(r) for r in img_rects],
        formula_bboxes=formula_bboxes,
    )
    table_bboxes = [b["bbox"] for b in table_blocks]

    # 4) 内嵌图：跳过扫描背景（文字多时）与已被表格覆盖的图
    img_blocks = extract_embedded_images(
        doc,
        page,
        records=records,
        media_dir=media_dir,
        skip_backgrounds=text_chars >= 200,
        skip_bboxes=table_bboxes,
    )

    # 5) 表格接管其区域内的文字/公式块（避免内容重复呈现）
    content = text_blocks
    if table_bboxes:
        content = [b for b in content if not _center_inside(b.get("bbox"), table_bboxes)]

    return sort_reading_order([*content, *table_blocks, *img_blocks])


def _ocr_page(
    page: fitz.Page, backend: OcrBackend, *, dpi: int, render_dir: Path | None
) -> list[dict]:
    """把一页渲染为图片并 OCR，返回该页的 text blocks。

    渲染图落 ``render_dir``（有 raw_dir 时持久化到 ``structured/raw/pages/pNNN.png``，
    供 agent 逐页阅读 OCR 产物、看图补换行/找插图——传统 OCR 只识别字符）。
    """
    if render_dir is None:
        return []
    pix = page.get_pixmap(dpi=dpi)
    render_dir.mkdir(parents=True, exist_ok=True)
    img_path = render_dir / f"p{page.number + 1:03d}.png"
    pix.save(str(img_path))
    text = backend.ocr_image(str(img_path))
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
    """读取 PDF：按页切片抽文字层，逐页写 page-NNN.json 到 raw_dir；扫描页走 OCR。

    扫描页（无文字层）渲染图持久化到 ``raw/pages/pNNN.png``，OCR 文本以
    ``ocr:true`` 块写入 page-NNN.json。
    """
    try:
        doc = fitz.open(str(path))
    except Exception as e:  # noqa: BLE001
        raise PdfError(f"无法打开 PDF：{e}") from e

    units: list[SourceUnit] = []
    segments: list[SourceSegment] = []
    records: list[InsertRecord] = []
    text_blocks_total = 0
    page_count = doc.page_count
    toc = doc.get_toc(simple=True)
    raw_path: Path | None = Path(raw_dir) if raw_dir is not None else None
    # 扫描页渲染目录：有 raw_dir 时持久化（raw/pages/，供 agent 看图找插图），
    # 否则退临时目录
    pages_dir: Path | None = raw_path / "pages" if raw_path is not None else None
    tmp_dir: str | None = None
    if ocr_backend is not None and pages_dir is None:
        tmp_dir = tempfile.mkdtemp(prefix="auto-epub-ocr-")
        pages_dir = Path(tmp_dir)
    if raw_path is not None:
        raw_path.mkdir(parents=True, exist_ok=True)
    try:
        for page_no in range(page_count):
            page = doc[page_no]
            blocks = _page_blocks(page)
            ocr_used = False
            if not blocks and ocr_backend is not None:
                blocks = _ocr_page(page, ocr_backend, dpi=page_dpi, render_dir=pages_dir)
                ocr_used = True
            if raw_path is not None:
                media_dir = raw_path / "media"
                if ocr_used:
                    # OCR 页属于扫描域：不做整页路由/表格/公式；扫描背景图跳过
                    blocks = sort_reading_order(
                        [
                            *blocks,
                            *extract_embedded_images(
                                doc,
                                page,
                                records=records,
                                media_dir=media_dir,
                                skip_backgrounds=True,
                            ),
                        ]
                    )
                else:
                    blocks = _page_extras(
                        doc,
                        page,
                        blocks,
                        records=records,
                        media_dir=media_dir,
                    )
            text_blocks_total += sum(1 for b in blocks if b.get("type") == "text")
            if raw_path is not None:
                (raw_path / f"page-{page_no + 1:03d}.json").write_text(
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
                meta = {
                    "source_page": page_no + 1,
                    "source_bbox": block.get("bbox"),
                    "source_font_size": block.get("font_size"),
                }
                if block.get("insert_id"):
                    meta["insert_id"] = block["insert_id"]
                    meta["insert_type"] = block["type"]
                segments.append(
                    SourceSegment(
                        index=idx,
                        source=block["text"],
                        kind=KIND_TEXT,
                        meta=meta,
                    )
                )
    finally:
        doc.close()
        if tmp_dir:
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)

    if text_blocks_total == 0 and not records:
        raise PdfError("该 PDF 没有可抽取的文字层；若是扫描件请走 OCR 路径")
    if raw_path is not None and records:
        write_inserts(raw_path, records)

    units = aggregate_pdf_chapters(
        segments,
        book_title=os.path.splitext(os.path.basename(str(path)))[0],
        page_count=page_count,
        toc=toc,
    )

    return SourceDocument(
        title=os.path.splitext(os.path.basename(str(path)))[0],
        source_path=os.path.abspath(str(path)),
        fmt="pdf",
        units=units,
        meta={"pages": page_count},
    )
