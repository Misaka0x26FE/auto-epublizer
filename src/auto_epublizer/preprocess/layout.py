# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""版面段落候选（C2，只读）：坐标/栏/缩进证据，不自动重排原文。

输入是 ``structured/raw/page-*.json`` 的块（``bbox``/``text``/``font_size``）。输出是
逐块候选：所在栏、页内阅读顺序、字符范围、字号、估算行高、缩进/列表/引文分类，以及
相邻块的边界候选（同段续行 / 新段）。**没有坐标就标 unknown**，不虚构几何；不按字符数
硬切原文，也不改写任何文本。

可疑信号只供 agent 核证：块的读者顺序仍沿用解析器已持久化的顺序，本模块不重排双栏或
RTL 内容。RTL 页面保留 ``rtl`` 标记，栏号按阅读顺序编号。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_LIST_MARKER = re.compile(r"^\s*(?:\d+[.)、]|[•·‣▪●○\-–—])\s+")
_TERMINAL = "。！？!?；;.…"


def _line_count(text: str) -> int:
    return max(1, len([line for line in text.splitlines() if line.strip()]))


def _columns(blocks: list[dict[str, Any]], page_width: float) -> list[int]:
    """按 x 中心聚类成栏；返回每个块（按输入顺序）的栏号。"""
    if not blocks:
        return []
    tolerance = max(page_width * 0.08, 1.0)
    centers = sorted(
        ((float(b["bbox"][0]) + float(b["bbox"][2])) / 2, index) for index, b in enumerate(blocks)
    )
    column_of: dict[int, int] = {}
    column = 0
    anchor = centers[0][0]
    for center, index in centers:
        if center - anchor > tolerance:
            column += 1
            anchor = center
        column_of[index] = column
    return [column_of[index] for index in range(len(blocks))]


def _page_candidates(payload: dict[str, Any]) -> dict[str, Any]:
    page = payload.get("page_idx")
    blocks = [
        block
        for block in payload.get("blocks") or []
        if isinstance(block, dict)
        and block.get("type") == "text"
        and str(block.get("text") or "").strip()
    ]
    located = [block for block in blocks if _valid_bbox(block.get("bbox"))]
    unknown = len(blocks) - len(located)
    if not located:
        return {
            "page": page,
            "rtl": bool(payload.get("rtl")),
            "status": "unknown",
            "reason": "no bbox coordinates",
            "blocks": [
                {"text": str(block.get("text") or "")[:40], "kind": "unknown"} for block in blocks
            ],
        }
    page_width = max(float(b["bbox"][2]) for b in located)
    columns = _columns(located, page_width)
    if payload.get("rtl") and columns:
        # 栏号按阅读方向编号：RTL 页最右栏为第 0 栏（解析器已给出阅读顺序）。
        widest = max(columns)
        columns = [widest - column for column in columns]
    fonts = sorted(float(b.get("font_size") or 0) for b in located if b.get("font_size"))
    body_font = fonts[len(fonts) // 2] if fonts else 0.0
    items: list[dict[str, Any]] = []
    cursor = 0
    for index, block in enumerate(located):
        text = str(block.get("text") or "")
        line_count = _line_count(text)
        bbox = [float(v) for v in block["bbox"]]
        height = max(0.0, bbox[3] - bbox[1])
        line_height = height / line_count if line_count else 0.0
        line_boxes = [
            line
            for line in block.get("lines") or []
            if isinstance(line, dict) and _valid_bbox(line.get("bbox"))
        ]
        font_size = float(block.get("font_size") or 0)
        column = columns[index]
        lefts = [float(other["bbox"][0]) for j, other in enumerate(located) if columns[j] == column]
        column_left = min(lefts) if lefts else bbox[0]
        indent = bbox[0] - column_left
        kind = "body"
        reasons: list[str] = []
        if font_size > body_font * 1.15 and line_count <= 2:
            kind = "heading"
            reasons.append("larger type, short block")
        elif _LIST_MARKER.match(text):
            kind = "list"
            reasons.append("list marker")
        elif indent > max(font_size * 0.8, 2.0):
            kind = "indent"
            reasons.append(f"indent {indent:.1f}pt")
        if kind == "indent" and indent > font_size * 2.5:
            kind = "quote"
            reasons.append("deep indent")
        boundaries: list[dict[str, Any]] = []
        if len(line_boxes) >= 2:
            rest = sorted(float(line["bbox"][0]) for line in line_boxes[1:])
            body_left = rest[len(rest) // 2]
            if float(line_boxes[0]["bbox"][0]) < body_left - max(font_size * 0.8, 2.0):
                reasons.append("hanging indent")
            for line_index in range(1, len(line_boxes)):
                prev = line_boxes[line_index - 1]
                current = line_boxes[line_index]
                gap = float(current["bbox"][1]) - float(prev["bbox"][3])
                ratio = gap / line_height if line_height else 0.0
                prev_text = str(prev.get("text") or "").rstrip()
                next_left = float(current["bbox"][0])
                if (
                    ratio >= 1.2
                    and prev_text
                    and prev_text[-1] in _TERMINAL
                    and next_left > column_left + max(font_size * 0.8, 2.0)
                ):
                    boundaries.append(
                        {
                            "after_line": line_index,
                            "kind": "new_paragraph_in_block",
                            "gap_ratio": round(ratio, 3),
                        }
                    )
        if index + 1 < len(located):
            nxt = located[index + 1]
            if columns[index + 1] == column:
                gap = float(nxt["bbox"][1]) - bbox[3]
                ratio = gap / line_height if line_height else 0.0
                ends_terminal = bool(text.rstrip()) and text.rstrip()[-1] in _TERMINAL
                if ratio < 0.35 and not ends_terminal:
                    boundaries.append(
                        {"with_block": index + 2, "kind": "continue", "gap_ratio": round(ratio, 3)}
                    )
                elif ratio >= 0.9:
                    boundaries.append(
                        {
                            "with_block": index + 2,
                            "kind": "new_paragraph",
                            "gap_ratio": round(ratio, 3),
                        }
                    )
        if line_count >= 4 and sum(text.count(mark) for mark in _TERMINAL) >= 2:
            reasons.append("possible merged paragraphs")
        items.append(
            {
                "block": index + 1,
                "column": column,
                "bbox": bbox,
                "font_size": font_size,
                "lines": line_count,
                "line_height": round(line_height, 3),
                "indent": round(indent, 3),
                "kind": kind,
                "chars": [cursor, cursor + len(text)],
                "text_head": " ".join(text.split())[:40],
                "text_tail": text.rstrip()[-20:],
                "reasons": reasons,
                "boundaries": boundaries,
            }
        )
        cursor += len(text) + 1
    return {
        "page": page,
        "rtl": bool(payload.get("rtl")),
        "status": "ok",
        "body_font": body_font,
        "columns": max(columns) + 1 if columns else 0,
        "unknown_blocks": unknown,
        "blocks": items,
        "page_chars": cursor,
    }


def _valid_bbox(bbox: Any) -> bool:
    return (
        isinstance(bbox, (list, tuple))
        and len(bbox) == 4
        and all(isinstance(value, (int, float)) for value in bbox)
    )


def collect_layout_candidates(store: Any) -> dict[str, Any]:
    """读取 raw 页 JSON 并输出只读版面候选；不写文件。"""
    raw = Path(store.structured_dir) / "raw"
    pages: list[dict[str, Any]] = []
    for path in sorted(raw.glob("page-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidate = _page_candidates(payload)
        candidate["raw_file"] = path.name
        pages.append(candidate)
    counts: dict[str, int] = {}
    cross_page = 0
    for previous, current in zip(pages, pages[1:], strict=False):
        if previous.get("status") != "ok" or current.get("status") != "ok":
            continue
        last = next(
            (block for block in reversed(previous.get("blocks") or []) if block.get("bbox")),
            None,
        )
        first = next((block for block in current.get("blocks") or [] if block.get("bbox")), None)
        if last is None or first is None:
            continue
        tail = str(last.get("text_tail") or "")
        if tail and tail[-1] not in _TERMINAL:
            last.setdefault("boundaries", []).append(
                {"with_page": current.get("page"), "kind": "continue_across_pages"}
            )
            cross_page += 1
    for page in pages:
        for block in page.get("blocks") or []:
            key = str(block.get("kind") or "unknown")
            counts[key] = counts.get(key, 0) + 1
    return {
        "writes": False,
        "pages": pages,
        "page_count": len(pages),
        "unknown_pages": [p["page"] for p in pages if p.get("status") == "unknown"],
        "cross_page_candidates": cross_page,
        "counts": counts,
    }
