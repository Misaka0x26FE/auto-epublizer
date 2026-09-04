"""PDF 插图提取与整页/内嵌路由（docs/pdf-content-spec.md §3/§7/§8）。

版面判据（确定性主判据）：
- 图占页面积 ≥ FULL_PAGE_AREA_RATIO 且文字覆盖率 < TEXT_COVERAGE_MAX 且
  页面文字 < 200 字 → 整页图版：渲染整页（method=full_page）；
  （字数守卫是扫描件的保护区：带 OCR 文字层的扫描页字数多，不走整页路由）
- 其余 ≥ MIN_IMAGE_SIZE 的内嵌图 → extract_image 原始字节（method=embedded）；
- 小于 MIN_IMAGE_SIZE 的图视为装饰，忽略。
"""

from __future__ import annotations

from pathlib import Path

import fitz

from .inserts import InsertRecord, InsertSource, next_insert_id

FULL_PAGE_AREA_RATIO = 0.70  # 整页插图判定：图占页面积比
TEXT_COVERAGE_MAX = 0.15  # 整页判定：页面文字覆盖率上限
MIN_IMAGE_SIZE = 32  # 短边小于该值（px）视为装饰（项目符号/分隔线），忽略
MAX_IMAGE_DIM = 1800  # 渲染类图片最长边上限
BACKGROUND_AREA_RATIO = 0.85  # 图占页面积超此值且页面文字多 → 判为扫描背景，跳过
RENDER_DPI = 150  # 渲染类（整页/裁剪）初始 dpi


def large_image_rects(page: fitz.Page) -> list[fitz.Rect]:
    """一页中 ≥ MIN_IMAGE_SIZE 的图片矩形（xref 去重；get_images 可能重复列出）。"""
    out: list[fitz.Rect] = []
    seen: set[int] = set()
    for info in page.get_images(full=True):
        xref = int(info[0])
        if xref in seen:
            continue
        seen.add(xref)
        for rect in page.get_image_rects(xref):
            if rect.width >= MIN_IMAGE_SIZE and rect.height >= MIN_IMAGE_SIZE:
                out.append(rect)
    return out


def render_full_page(
    page: fitz.Page,
    *,
    records: list[InsertRecord],
    media_dir: Path,
) -> dict:
    """整页图版路由：渲染整页为图，返回该页唯一的 image block。"""
    page_no = page.number + 1
    iid = next_insert_id(records, page_no, "image")
    name = f"p{page_no:03d}-page.png"
    media_dir.mkdir(parents=True, exist_ok=True)
    _render_clip(page, page.rect).save(str(media_dir / name))
    rel = f"media/{name}"
    records.append(
        InsertRecord(
            id=iid,
            type="image",
            source=InsertSource(page=page_no, bbox=list(page.rect), xref=None, method="full_page"),
            file=rel,
        )
    )
    return {
        "type": "image",
        "bbox": list(page.rect),
        "text": f"![{iid}](raw/{rel})",
        "file": rel,
        "method": "full_page",
        "insert_id": iid,
    }


def _render_clip(page: fitz.Page, rect: fitz.Rect) -> fitz.Pixmap:
    """渲染页内区域；最长边超 MAX_IMAGE_DIM 时按比例降低 zoom（纯 fitz）。"""
    zoom = RENDER_DPI / 72
    while True:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect)
        if max(pix.width, pix.height) <= MAX_IMAGE_DIM or zoom <= 0.4:
            return pix
        zoom *= 0.7


def extract_embedded_images(
    doc: fitz.Document,
    page: fitz.Page,
    *,
    records: list[InsertRecord],
    media_dir: Path,
    skip_backgrounds: bool = False,
    skip_bboxes: list[list[float]] | None = None,
) -> list[dict]:
    """提取一页的内嵌栅格图，返回 image blocks（bbox 保留，供阅读顺序重排）。

    - 小于 MIN_IMAGE_SIZE 的图视为装饰，忽略；
    - ``skip_backgrounds``：面积 ≥ BACKGROUND_AREA_RATIO×页面积 的图判为扫描
      背景（页面文字多时），跳过不提取；
    - ``skip_bboxes``：中心落在其中的图跳过（已被表格裁剪图覆盖）；
    - 同一 xref 多矩形：首次提取原始字节，其余矩形引用同一文件；
    - 提取失败的 xref 整体跳过（宁缺毋滥）。
    """
    blocks: list[dict] = []
    page_no = page.number + 1
    page_area = abs(page.rect) or 1.0
    file_by_xref: dict[int, str] = {}
    seen_xrefs: set[int] = set()
    for info in page.get_images(full=True):
        xref = int(info[0])
        if xref in seen_xrefs:
            continue  # get_images 可能重复列出同一对象；get_image_rects 已返回全部矩形
        seen_xrefs.add(xref)
        rects = page.get_image_rects(xref)
        if not rects:
            continue
        for rect in rects:
            if rect.width < MIN_IMAGE_SIZE or rect.height < MIN_IMAGE_SIZE:
                continue
            if skip_backgrounds and rect.width * rect.height >= BACKGROUND_AREA_RATIO * page_area:
                continue
            if _center_inside(list(rect), skip_bboxes or []):
                continue
            rel = file_by_xref.get(xref)
            if rel is None:
                try:
                    img = doc.extract_image(xref)
                except Exception:  # noqa: BLE001  损坏对象：跳过该 xref
                    break
                iid = next_insert_id(records, page_no, "image")
                name = f"{iid}.{img['ext']}"
                rel = f"media/{name}"
                media_dir.mkdir(parents=True, exist_ok=True)
                (media_dir / name).write_bytes(img["image"])
                file_by_xref[xref] = rel
                src = InsertSource(
                    page=page_no,
                    bbox=list(rect),
                    xref=xref,
                    method="embedded",
                )
                records.append(InsertRecord(id=iid, type="image", source=src, file=rel))
            else:
                iid = next_insert_id(records, page_no, "image")
                records.append(
                    InsertRecord(
                        id=iid,
                        type="image",
                        source=InsertSource(
                            page=page_no, bbox=list(rect), xref=xref, method="embedded"
                        ),
                        file=rel,
                    )
                )
            blocks.append(
                {
                    "type": "image",
                    "bbox": list(rect),
                    "text": f"![{iid}](raw/{rel})",
                    "file": rel,
                    "xref": xref,
                    "method": "embedded",
                    "insert_id": iid,
                }
            )
    return blocks


def _center_inside(bbox: list[float], boxes: list[list[float]]) -> bool:
    """bbox 中心是否落在任一 box 内。"""
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes if len(b) == 4)
