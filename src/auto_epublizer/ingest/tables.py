"""表格双路径提取（docs/pdf-content-spec.md §4）。

``page.find_tables()`` 检出表格后按内容分流：
- 纯文字表格（不与图/公式区域相交）→ ``table_to_markdown`` 生成自包含 md；
- 含图/公式表格 → 区域渲染裁剪图（method=table），内容进图片；
- 跨页表格不合并（后续扩展点）。
"""

from __future__ import annotations

from pathlib import Path

import fitz

from .images import _render_clip
from .inserts import InsertRecord, InsertSource, next_insert_id

MAX_TABLE_CELL_CHARS = 300  # 单格超此长度视为版面误检（整页被吞进一格），放弃该表
TABLE_MAX_AREA_RATIO = 0.5  # 表格 bbox 超页面积一半 → 粘连正文/代码/插图的误检，放弃


def table_to_markdown(rows: list[list[str | None]]) -> str | None:
    """单元格矩阵 → markdown 表格（首行表头 + 分隔行）；无有效内容返回 None。"""
    clean = [
        [(c or "").strip().replace("\n", " ").replace("|", "\\|") for c in row] for row in rows
    ]
    clean = [r for r in clean if any(c for c in r)]
    if not clean:
        return None
    width = max(len(r) for r in clean)
    clean = [r + [""] * (width - len(r)) for r in clean]
    lines = [
        "| " + " | ".join(clean[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in clean[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _overlaps(a: list[float], b: list[float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def extract_tables(
    page: fitz.Page,
    *,
    records: list[InsertRecord],
    media_dir: Path,
    image_bboxes: list[list[float]],
    formula_bboxes: list[list[float]],
) -> list[dict]:
    """提取一页的表格，返回 table blocks（md 或裁剪图引用）。"""
    try:
        finder = page.find_tables()
    except Exception:  # noqa: BLE001  表格检测失败：放弃该页表格
        return []
    page_no = page.number + 1
    page_area = abs(page.rect) or 1.0
    blocks: list[dict] = []
    for table in finder.tables:
        bbox = [float(v) for v in table.bbox]
        if (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) >= TABLE_MAX_AREA_RATIO * page_area:
            continue  # 版面误检：真表格很少占半页；粘连框会吞正文/插图（dogfooding 实证）
        has_graphic = any(_overlaps(bbox, ob) for ob in [*image_bboxes, *formula_bboxes])
        iid = next_insert_id(records, page_no, "table")
        if has_graphic:
            name = f"{iid}.png"
            rel = f"media/{name}"
            media_dir.mkdir(parents=True, exist_ok=True)
            _render_clip(page, fitz.Rect(*bbox)).save(str(media_dir / name))
            records.append(
                InsertRecord(
                    id=iid,
                    type="table",
                    source=InsertSource(page=page_no, bbox=bbox, method="table"),
                    file=rel,
                )
            )
            blocks.append(
                {
                    "type": "table",
                    "bbox": bbox,
                    "text": f"![{iid}](raw/{rel})",
                    "file": rel,
                    "insert_id": iid,
                }
            )
        else:
            cells = table.extract()
            md = table_to_markdown(cells)
            if md is None:
                continue
            longest = max((len((c or "").strip()) for row in cells for c in row), default=0)
            if longest > MAX_TABLE_CELL_CHARS:
                # 版面误检（正文/代码被吸进一格，真书 dogfooding 实证）：放弃，
                # 内容回归普通 text 块参与后续流程
                continue
            records.append(
                InsertRecord(
                    id=iid,
                    type="table",
                    source=InsertSource(page=page_no, bbox=bbox, method="table"),
                    markdown=md,
                )
            )
            blocks.append(
                {
                    "type": "table",
                    "bbox": bbox,
                    "text": md,
                    "markdown": md,
                    "file": None,
                    "insert_id": iid,
                }
            )
    return blocks
