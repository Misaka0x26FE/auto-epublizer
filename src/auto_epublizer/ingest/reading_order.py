"""多栏阅读顺序重排（纯函数，确定性）。

规则（docs/pdf-content-spec.md §6）：
1. 任一 block 无 bbox（OCR 路径）→ 原序返回；
2. 窄块按 x 区间聚类成列（band，列间按 x0 排序），无横向并存时退化为单列（列内按 y）；
3. 宽块（width ≥ 0.6×页宽，标题/通栏）按 y 切出纵向 zone：
   头部宽块（在所有窄块之上）→ 逐 zone（列序 → 列内 y）→ 中部宽块 → … → 尾部宽块。
输出实现「行内左→右（同 zone 列序）、行间上→下」，双栏文本整列先读（报刊式）。
"""

from __future__ import annotations

from typing import Any

_WIDE_RATIO = 0.6  # 宽块判定：宽 ≥ 0.6 × 页宽（标题/通栏元素）

BBox = list[float]


def _bbox(block: dict[str, Any]) -> BBox | None:
    bb = block.get("bbox")
    if isinstance(bb, (list, tuple)) and len(bb) == 4:
        try:
            return [float(v) for v in bb]
        except (TypeError, ValueError):
            return None
    return None


def _merge_bands(intervals: list[tuple[float, float]]) -> list[list[float]]:
    """x 区间聚类：重叠即同列；返回按 x0 排序的列区间。"""
    bands: list[list[float]] = []
    for x0, x1 in sorted(intervals):
        if bands and x0 <= bands[-1][1]:
            bands[-1][1] = max(bands[-1][1], x1)
        else:
            bands.append([x0, x1])
    return bands


def _band_index(bands: list[list[float]], bb: BBox) -> int:
    """块 x 中心 → 列序（中心落在列间隙取最近列）。"""
    center = (bb[0] + bb[2]) / 2
    best, best_dist = 0, float("inf")
    for i, (x0, x1) in enumerate(bands):
        if x0 <= center <= x1:
            return i
        dist = min(abs(center - x0), abs(center - x1))
        if dist < best_dist:
            best, best_dist = i, dist
    return best


def sort_reading_order(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按阅读顺序重排页面块（不修改输入；无坐标时原序返回）。"""
    bboxes: list[BBox] = []
    for b in blocks:
        bb = _bbox(b)
        if bb is None:
            return blocks  # OCR 等无坐标路径：保序
        bboxes.append(bb)
    if len(blocks) <= 1:
        return blocks

    page_width = max(bb[2] for bb in bboxes)
    wide_idx = [i for i, bb in enumerate(bboxes) if bb[2] - bb[0] >= _WIDE_RATIO * page_width]
    wide_set = set(wide_idx)
    narrow_idx = [i for i in range(len(blocks)) if i not in wide_set]
    if not narrow_idx:
        order = sorted(wide_idx, key=lambda i: (bboxes[i][1], bboxes[i][0]))
        return [blocks[i] for i in order]

    bands = _merge_bands([(bboxes[i][0], bboxes[i][2]) for i in narrow_idx])
    band_of = {i: _band_index(bands, bboxes[i]) for i in narrow_idx}

    narrow_min_y = min(bboxes[i][1] for i in narrow_idx)
    narrow_max_y = max(bboxes[i][3] for i in narrow_idx)
    head_idx = [i for i in wide_idx if bboxes[i][3] <= narrow_min_y]
    tail_idx = [i for i in wide_idx if bboxes[i][1] >= narrow_max_y]
    mid_set = wide_set - set(head_idx) - set(tail_idx)
    mids = sorted(mid_set, key=lambda i: bboxes[i][1])  # 中部宽块自上而下切 zone

    out: list[dict[str, Any]] = [
        blocks[i] for i in sorted(head_idx, key=lambda i: (bboxes[i][1], bboxes[i][0]))
    ]
    for z in range(len(mids) + 1):
        lo = bboxes[mids[z - 1]][1] if z > 0 else None
        hi = bboxes[mids[z]][1] if z < len(mids) else None
        zone = [
            i
            for i in narrow_idx
            if (lo is None or bboxes[i][1] >= lo) and (hi is None or bboxes[i][1] < hi)
        ]
        zone.sort(key=lambda i: (band_of[i], bboxes[i][1], bboxes[i][0]))
        out.extend(blocks[i] for i in zone)
        if z < len(mids):
            out.append(blocks[mids[z]])
    out.extend(blocks[i] for i in sorted(tail_idx, key=lambda i: (bboxes[i][1], bboxes[i][0])))
    return out
