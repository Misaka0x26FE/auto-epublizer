# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""源分区账本（issue #62 / #58）：每一行原始文本去了哪里，逐次可追踪。

问题：``restructure`` / 抽样复核只能看「structured 里有没有这条文本」的集合判断，
同一文本出现两次、等量替换、拆分合并都无法区分；丢行与「合法剔除」也长得一样。
本模块给**只读**的分区账本：源侧每一行按 ``raw 文件摘要 + page + block + 行内 span``
取身份（不用文本集合，重复行逐次对位），逐行标注去向：

- ``body``：进入正文单元；
- ``note``：进入独立 notes 单元（``kind == "notes"``）；
- ``noise``：只有 ``catalog.csv`` 明确 ``excluded``/``absent`` 且写明理由的文本；
- ``unresolved``：没有去向的源行（真实丢行的最小判据）。

目标端多出的行（结构重建生成的标题、改写文本）单独列 ``destination_extra``，
不反过来把源行判成丢行。缺 ``structured/raw/`` 时 ``status=unknown``——没有原始
证据就不声称完整，也不按数量相等判通过。本模块不写任何文件、不改状态。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from auto_common.workspace import RunStore

from .artifacts import read_catalog

_HEADING_RE = re.compile(r"^#{1,6}\s+")
_ANCHOR_RE = re.compile(r"\[\]\{#[^}]*\}")
_SPAN_ONLY_RE = re.compile(r"^:::\s*(\{[^}]*\})?\s*$")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_QUOTE_RE = re.compile(r"^>\s?")


def _norm(text: str) -> str:
    """身份规范化：只折叠空白，不做同义/近似匹配（近似会吞掉真实差异）。"""
    return re.sub(r"\s+", "", text)


def _dest_text(line: str) -> str:
    """目标行去掉结构产物（标题井号、页锚点、容器行、图片）后的可见文本。"""
    text = line.strip()
    text = _HEADING_RE.sub("", text)
    text = _QUOTE_RE.sub("", text)
    text = _ANCHOR_RE.sub("", text)
    text = _IMAGE_RE.sub("", text)
    return text.strip()


def _source_lines(raw: Path) -> tuple[list[dict[str, Any]], dict[str, str], str | None]:
    """读 ``structured/raw/page-*.json`` → 逐行源条目 + 页摘要；缺失返回原因。"""
    pages = sorted(raw.glob("page-*.json")) if raw.is_dir() else []
    if not pages:
        return [], {}, "raw_missing"
    items: list[dict[str, Any]] = []
    digests: dict[str, str] = {}
    for path in pages:
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        digests[path.name] = digest
        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return [], digests, f"raw_unreadable:{path.name}"
        if not isinstance(data, dict) or not isinstance(data.get("blocks"), list):
            return [], digests, f"raw_bad_blocks:{path.name}"
        for block_index, block in enumerate(data["blocks"], start=1):
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            offset = 0
            for text in str(block.get("text") or "").splitlines():
                stripped = text.strip()
                start = offset + (len(text) - len(text.lstrip()))
                offset += len(text) + 1
                if not stripped:
                    continue
                items.append(
                    {
                        "raw_file": path.name,
                        "raw_digest": digest,
                        "page": data.get("page_idx"),
                        "block": block_index,
                        "span": [start, start + len(stripped)],
                        "text": stripped,
                        "norm": _norm(stripped),
                    }
                )
    return items, digests, None


def _destination_lines(store: RunStore) -> list[dict[str, Any]]:
    """按发布顺序读全部 structured 单元 → 目标行（含单元与行号）。"""
    pub = store.load_publication()
    items: list[dict[str, Any]] = []
    for unit in pub.units:
        rel = str((unit.meta or {}).get("rel_path") or "")
        path = store.structured_dir / rel if rel else None
        if path is None or not path.is_file():
            continue
        kind = "note" if unit.kind == "notes" else "body"
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            visible = _dest_text(line)
            norm = _norm(visible)
            if not norm:
                continue
            items.append(
                {
                    "unit": unit.id,
                    "kind": kind,
                    "line": line_no,
                    "text": visible,
                    "norm": norm,
                }
            )
    return items


def _noise_texts(store: RunStore) -> set[str]:
    """只有 catalog 明确 excluded/absent 且写明理由的文本才算已批准噪声。"""
    rows = read_catalog(store) or []
    return {
        _norm(str(row.get("item") or ""))
        for row in rows
        if row.get("status") in ("excluded", "absent") and str(row.get("note") or "").strip()
    }


def collect_partition(store: RunStore) -> dict[str, Any]:
    """逐行分区账本（只读）。每行身份可独立复核，重复文本按出现次序对位。"""
    source, digests, reason = _source_lines(store.structured_dir / "raw")
    destinations = _destination_lines(store)
    noise = _noise_texts(store)
    if reason is not None:
        return {
            "status": "unknown",
            "reason": reason,
            "source_lines": len(source),
            "pages": digests,
            "entries": [],
            "destination_extra": [],
            "duplicates": [],
            "counts": {},
            "complete": False,
        }

    # 同文多次出现：按目标出现次序先进先出对位（不合并成集合，也不取第一次猜）。
    queues: dict[str, deque[int]] = defaultdict(deque)
    for index, item in enumerate(destinations):
        queues[item["norm"]].append(index)
    claimed: set[int] = set()
    entries: list[dict[str, Any]] = []
    counts = {"body": 0, "note": 0, "noise": 0, "unresolved": 0}
    for item in source:
        destination: dict[str, Any] | None = None
        queue = queues.get(item["norm"])
        if queue:
            index = queue.popleft()
            destination = destinations[index]
            claimed.add(index)
            counts[destination["kind"]] += 1
        elif item["norm"] in noise:
            counts["noise"] += 1
        else:
            counts["unresolved"] += 1
        entries.append(
            {
                "raw_file": item["raw_file"],
                "raw_digest": item["raw_digest"],
                "page": item["page"],
                "block": item["block"],
                "span": item["span"],
                "text": item["text"],
                "destination": (
                    destination["kind"]
                    if destination
                    else ("noise" if item["norm"] in noise else "unresolved")
                ),
                **(
                    {"unit": destination["unit"], "line": destination["line"]}
                    if destination
                    else {}
                ),
            }
        )

    # 跨块拆合：按块给出「源行 → 目标行区间」，coverage 只统计有去向的行。
    by_block: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        by_block[(entry["raw_file"], entry["block"])].append(entry)
    blocks: list[dict[str, Any]] = []
    for (raw_file, block), rows in sorted(by_block.items()):
        matched = [row for row in rows if "unit" in row]
        parts: list[dict[str, Any]] = []
        for position, row in enumerate(rows, start=1):
            if "unit" not in row:
                continue
            last = parts[-1] if parts else None
            if (
                last is not None
                and last["unit"] == row["unit"]
                and row["line"] == last["end_line"] + 1
            ):
                last["end_line"] = row["line"]
                last["source_lines"].append(position)
            else:
                parts.append(
                    {
                        "unit": row["unit"],
                        "start_line": row["line"],
                        "end_line": row["line"],
                        "source_lines": [position],
                    }
                )
        blocks.append(
            {
                "raw_file": raw_file,
                "block": block,
                "lines": len(rows),
                "coverage": round(len(matched) / len(rows), 6) if rows else 0.0,
                "parts": parts,
                "unresolved": [
                    row["text"]
                    for row in rows
                    if "unit" not in row and row["destination"] != "noise"
                ],
            }
        )

    extras = [
        {
            "unit": item["unit"],
            "line": item["line"],
            "text": item["text"],
        }
        for index, item in enumerate(destinations)
        if index not in claimed
    ]

    seen: dict[str, int] = defaultdict(int)
    for item in source:
        seen[item["norm"]] += 1
    duplicates = [
        {
            "text": next(item["text"] for item in source if item["norm"] == norm),
            "occurrences": count,
            "destinations": [
                {"unit": row["unit"], "line": row["line"]}
                for row in entries
                if "unit" in row and _norm(row["text"]) == norm
            ],
        }
        for norm, count in seen.items()
        if count > 1
    ]

    return {
        "status": "ok",
        "reason": None,
        "source_lines": len(source),
        "pages": digests,
        "counts": counts,
        "blocks": blocks,
        "entries": entries,
        "destination_extra": extras,
        "duplicates": duplicates,
        "complete": counts["unresolved"] == 0,
    }
