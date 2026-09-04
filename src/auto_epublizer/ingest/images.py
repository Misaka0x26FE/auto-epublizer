"""PDF 插图提取：内嵌栅格图落盘 raw/media/ 并生成 image block + 描述记录。

S2（P0）范围：内嵌图（extract_image 原始字节）；整页/裁剪路由与表格见 P1。
版面判据、常量与 md 表示见 docs/pdf-content-spec.md §2.3/§3/§7/§8。
"""

from __future__ import annotations

from pathlib import Path

import fitz

from .inserts import InsertRecord, InsertSource, next_insert_id

FULL_PAGE_AREA_RATIO = 0.70  # 整页插图判定：图占页面积比（P1 生效）
TEXT_COVERAGE_MAX = 0.15  # 整页判定：页面文字覆盖率上限（P1 生效）
MIN_IMAGE_SIZE = 32  # 短边小于该值（px）视为装饰（项目符号/分隔线），忽略
MAX_IMAGE_DIM = 1800  # 渲染类图片最长边上限（P1 生效）


def extract_embedded_images(
    doc: fitz.Document,
    page: fitz.Page,
    *,
    records: list[InsertRecord],
    media_dir: Path,
) -> list[dict]:
    """提取一页的内嵌栅格图，返回 image blocks（bbox 保留，供阅读顺序重排）。

    - 小于 MIN_IMAGE_SIZE 的图视为装饰，忽略；
    - 同一 xref 多矩形（贴图重复引用）：首次提取原始字节，其余矩形引用同一文件；
    - 提取失败的 xref 整体跳过（宁缺毋滥）。
    """
    blocks: list[dict] = []
    page_no = page.number + 1
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
