# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""源注独立清点与跨页注尾配对（#58，只读）。

清点**只依据原始页/块的排版证据**（字号、纵向位置、行首注号），不读
``structured/notes.json`` 来反推数量；注册表只作为对照值出现。结果是候选证据，
不是“源书共有 N 条注”的结论：脚注编号按页/节重排，块也可能把多条注合并。

跨页注尾配对只回答“上一页最后一条注文与下一页第一条注文是否像同一条的续写”，
输出截断原因（连字符/无终止标点）与两端原文，供 agent 回原页核证。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from statistics import median
from typing import Any

from auto_common.workspace import RunStore

_TERMINAL = tuple(".!?。！？:;…\"'”’)]}»")
_LABEL_START = re.compile(r"^(?P<label>\d{1,3})(?:(?:[.)]\s*|\s+)(?=\S)|(?=[A-ZÀ-ÖØ-Þ“\"‘'(]))")
_HEADING_LIKE = re.compile(r"^(?:chapter|part|section|contents|index|notes|bibliography)\b", re.I)
_RUNNING_HEAD = re.compile(
    r"^\d{1,4}\s*(?:\n\s*)?(?:notes|bibliography|index|contents|chapter|part)\b", re.I
)
_NOTES_HEAD = re.compile(r"^\d{1,4}\s*(?:\n\s*)?notes\b", re.I)


def _block_text(block: dict[str, Any]) -> str:
    return str(block.get("text") or "").strip()


def _block_box(block: dict[str, Any]) -> list[float] | None:
    box = block.get("bbox")
    if isinstance(box, (list, tuple)) and len(box) == 4:
        try:
            return [float(value) for value in box]
        except (TypeError, ValueError):
            return None
    return None


def _body_font_size(blocks: list[dict[str, Any]]) -> float | None:
    """按文本长度加权的中位字号；页眉/页码等短块不足以代表正文。"""
    sizes: list[float] = []
    for block in blocks:
        size = block.get("font_size")
        text = _block_text(block)
        if not isinstance(size, (int, float)) or not text:
            continue
        weight = max(1, len(text) // 20)
        sizes.extend([float(size)] * weight)
    return median(sizes) if sizes else None


def _note_labels(text: str, *, relaxed: bool = False) -> list[str]:
    """块内注号；正文脚注块用“上一行以终止标点收尾”抑制卷次误计。

    ``relaxed=True`` 用于整页都是注文的 endnotes 页：块可能从注文中段开始，
    不能要求首行或前一行终止标点，否则会漏掉半页注号。
    """
    labels: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = _LABEL_START.match(line.strip())
        if not match:
            continue
        if relaxed or index == 0:
            labels.append(match.group("label"))
            continue
        previous = lines[index - 1].rstrip()
        if previous and previous[-1] in ".!?)\"'”’":
            labels.append(match.group("label"))
    return labels


def _looks_note_block(
    block: dict[str, Any],
    body_size: float | None,
    page_bottom: float | None,
    artifacts: set[str],
) -> bool:
    text = _block_text(block)
    if len(text) < 20:
        return False
    if re.sub(r"\W+", "", text).casefold() in artifacts:
        return False
    compact = text.strip()
    if _RUNNING_HEAD.match(compact) and len(compact) < 90:
        return False
    if compact.isupper() and len(compact) < 100:
        return False
    if len(re.findall(r"\.\s*\.", compact)) >= 5:  # 目录点线
        return False
    size = block.get("font_size")
    box = _block_box(block)
    small = (
        isinstance(size, (int, float)) and body_size is not None and float(size) <= body_size - 1.2
    )
    bottom = bool(box and page_bottom and box[1] >= page_bottom * 0.55)
    labels = _note_labels(text)
    # 正文页只认“小字号 + 页脚位置”；行首数字在参考文献/目录页会误伤。
    return bool(small and (bottom or len(labels) >= 1))


def _artifact_texts(pages: list[dict[str, Any]]) -> set[str]:
    """跨多页重复、且不带注号的页脚/版式文字不计入注文候选。"""
    counts: dict[str, int] = {}
    for page in pages:
        blocks = page["blocks"]
        body_size = _body_font_size(blocks)
        bottom = max(((_block_box(block) or [0, 0, 0, 0])[3] for block in blocks), default=0)
        seen: set[str] = set()
        for block in blocks:
            text = _block_text(block)
            if len(text) < 12 or _note_labels(text):
                continue
            size = block.get("font_size")
            if not isinstance(size, (int, float)) or body_size is None:
                continue
            box = _block_box(block)
            if float(size) > body_size - 1.2 or not (box and bottom and box[1] >= bottom * 0.55):
                continue
            key = re.sub(r"\W+", "", text).casefold()
            if key and key not in seen:
                seen.add(key)
                counts[key] = counts.get(key, 0) + 1
    return {key for key, count in counts.items() if count >= 3}


def _raw_pages(store: RunStore) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for path in sorted((store.structured_dir / "raw").glob("page-*.json")):
        data = json.loads(path.read_bytes())
        if not isinstance(data, dict):
            raise ValueError(f"raw 页不是对象：{path.name}")
        blocks = data.get("blocks")
        if not isinstance(blocks, list):
            raise ValueError(f"raw 页缺 blocks 数组：{path.name}")
        pages.append(
            {
                "page": data.get("page_idx"),
                "raw_file": path.name,
                "blocks": [block for block in blocks if isinstance(block, dict)],
            }
        )
    return pages


def _registered_summary(store: RunStore) -> dict[str, Any]:
    path = store.structured_dir / "notes.json"
    if not path.is_file():
        return {"registered": False, "total": 0, "inventory": None, "sha256": None}
    payload = path.read_bytes()
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {"registered": False, "total": 0, "inventory": None, "sha256": None}
    notes = data.get("notes") if isinstance(data, dict) else None
    return {
        "registered": True,
        "inventory": data.get("inventory") if isinstance(data, dict) else None,
        "total": len(notes) if isinstance(notes, list) else 0,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def collect_note_inventory(store: RunStore) -> dict[str, Any]:
    """逐页注文候选块 + 跨页续写候选；注册注文只作对照，不参与清点。"""
    pages = _raw_pages(store)
    artifacts = _artifact_texts(pages)
    head_pages = {
        page["page"]
        for page in pages
        if isinstance(page["page"], int)
        and any(_NOTES_HEAD.match(_block_text(block)) for block in page["blocks"])
    }
    notes_span = (min(head_pages), max(head_pages)) if head_pages else None
    page_rows: list[dict[str, Any]] = []
    note_blocks: list[dict[str, Any]] = []
    tails: list[dict[str, Any]] = []
    previous_last_note: dict[str, Any] | None = None
    previous_page: int | None = None

    for page in pages:
        page_no = page["page"]
        blocks = page["blocks"]
        body_size = _body_font_size(blocks)
        page_bottom = (
            max(((_block_box(block) or [0, 0, 0, 0])[3] for block in blocks), default=0) or None
        )
        notes_page = bool(
            notes_span and isinstance(page_no, int) and notes_span[0] <= page_no <= notes_span[1]
        )
        rows: list[dict[str, Any]] = []
        first_text: dict[str, Any] | None = None
        for index, block in enumerate(blocks, start=1):
            text = _block_text(block)
            if (
                first_text is None
                and len(text) >= 20
                and not _NOTES_HEAD.match(text)
                and not re.fullmatch(r"\d{1,4}", text.strip())
                and not text.strip().isupper()
            ):
                first_text = {
                    "block": index,
                    "text": text,
                    "font_size": block.get("font_size"),
                    "raw_file": page["raw_file"],
                }
            if notes_page:
                if (
                    not text
                    or _NOTES_HEAD.match(text)
                    or re.fullmatch(r"\d{1,4}", text.strip())
                    or re.sub(r"\W+", "", text).casefold() in artifacts
                    or text.strip().isupper()
                    or len(re.findall(r"\.\s*\.", text)) >= 5
                ):
                    continue
            elif not _looks_note_block(block, body_size, page_bottom, artifacts):
                continue
            labels = _note_labels(text, relaxed=notes_page)
            box = _block_box(block)
            row = {
                "raw_file": page["raw_file"],
                "page": page_no,
                "block": index,
                "font_size": block.get("font_size"),
                "bbox": box,
                "labels": labels,
                "notes_page": notes_page,
                "text": text,
            }
            rows.append(row)
            note_blocks.append(row)

        page_rows.append(
            {
                "page": page_no,
                "raw_file": page["raw_file"],
                "body_font_size": body_size,
                "note_blocks": len(rows),
                "note_labels": [label for row in rows for label in row["labels"]],
                # 页面级证据：块位置/字号/注号/摘要；完整块文本留在 raw 页里，不复制。
                "blocks": [
                    {
                        "block": row["block"],
                        "font_size": row["font_size"],
                        "bbox": row["bbox"],
                        "labels": row["labels"],
                        "text_head": row["text"][:120],
                    }
                    for row in rows
                ],
            }
        )

        consecutive = (
            isinstance(page_no, int)
            and isinstance(previous_page, int)
            and page_no == previous_page + 1
        )
        if previous_last_note is not None and consecutive:
            # 续文可能在下一页顶部（整页注文页/小字号），也可能从页脚注文区继续。
            top_size = (first_text or {}).get("font_size")
            top_like = notes_page or (
                isinstance(top_size, (int, float))
                and body_size is not None
                and float(top_size) <= body_size - 1.2
            )
            if top_like and first_text is not None:
                first = first_text
            elif rows:
                first = {
                    "block": rows[0]["block"],
                    "text": rows[0]["text"],
                    "font_size": rows[0]["font_size"],
                    "raw_file": rows[0]["raw_file"],
                }
            else:
                first = None
            if first is not None:
                prev_text = previous_last_note["text"].rstrip()
                head = first["text"].lstrip()
                # 上一页最后一条注文必须带注号/位于整页注文页，才可能是续写。
                reason = None
                if prev_text.endswith(("-", "‐", "‑")):
                    reason = "hyphenated"
                elif prev_text and prev_text[-1] not in _TERMINAL:
                    reason = "no_terminal"
                prev_last_line = prev_text.splitlines()[-1] if prev_text else ""
                head_first_line = head.splitlines()[0] if head else ""
                head_char = head_first_line.lstrip()[:1]
                # 续写通常从句子中间开始（小写/引号）；大写开头多半是下一条或正文。
                continues = bool(head_char) and not head_char.isupper()
                if (
                    (previous_last_note["labels"] or previous_last_note["notes_page"])
                    and reason
                    and (continues or reason == "hyphenated")
                    and len(re.findall(r"[^\W\d_]", prev_last_line)) >= 3
                    and len(re.findall(r"[^\W\d_]", head_first_line)) >= 3
                    and not _HEADING_LIKE.match(prev_text)
                    and not _HEADING_LIKE.match(head)
                ):
                    tails.append(
                        {
                            "prev_page": previous_page,
                            "prev_raw_file": previous_last_note["raw_file"],
                            "prev_block": previous_last_note["block"],
                            "prev_tail": prev_text[-160:],
                            "next_page": page_no,
                            "next_raw_file": first["raw_file"],
                            "next_block": first["block"],
                            "next_head": head[:160],
                            "reason": reason,
                        }
                    )
        # 中间夹着无注文页时，不能把上一页的注尾配到更后一页的正文。
        previous_last_note = rows[-1] if rows else None
        previous_page = page_no

    # 同一段文本在连续页反复成为“结尾”，是重复版式/固定注，不是跨页续写。
    tail_counts: dict[str, int] = {}
    for tail in tails:
        key = re.sub(r"\W+", "", tail["prev_tail"][-80:]).casefold()
        tail_counts[key] = tail_counts.get(key, 0) + 1
    tails = [
        tail
        for tail in tails
        if tail_counts[re.sub(r"\W+", "", tail["prev_tail"][-80:]).casefold()] < 3
    ]

    labels = [label for row in note_blocks for label in row["labels"]]
    registered = _registered_summary(store)
    return {
        "schema_version": "1",
        "rule_version": "note-inventory-1",
        "raw_pages": len(pages),
        "pages": page_rows,
        "counts": {
            "note_like_blocks": len(note_blocks),
            "labeled_notes": len(labels),
            "distinct_labels": len(set(labels)),
            "pages_with_notes": sum(1 for row in page_rows if row["note_blocks"]),
            "continued_tail_candidates": len(tails),
        },
        "continued_tails": tails,
        "registered": registered,
        "comparison": {
            "registered_notes": registered["total"],
            "note_like_blocks": len(note_blocks),
            "label_scope": "page_or_section_local",
            "note": "脚注按页/节重排、块可合并多条注；两列计数不可相减当作漏注数，也不据此判定译文缺失",
        },
    }


def registered_note_inventory(store: RunStore) -> dict[str, Any] | None:
    """只读注册摘要；不存在时返回 None（供 evidence source 轻量消费）。"""
    summary = _registered_summary(store)
    return summary if summary["registered"] else None


def inventory_path(store: RunStore) -> Path:
    return store.preprocessing_dir / "note-inventory.json"
