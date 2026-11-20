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
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from auto_common.workspace import RunStore
from auto_common.workspace.store import atomic_write_json, read_json, source_sha256

from .artifacts import read_catalog, read_repairs

_HEADING_RE = re.compile(r"^#{1,6}\s+")
_ANCHOR_RE = re.compile(r"\[\]\{#[^}]*\}")
_SPAN_ONLY_RE = re.compile(r"^:::\s*(\{[^}]*\})?\s*$")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_QUOTE_RE = re.compile(r"^>\s?")
_FOLIO_RE = re.compile(r"(?:[0-9]{1,5}|[ivxlcdm]{1,8})", re.I)
_TASK_FILE = "source-tasks.json"


def _optional_digest(path: Path) -> str | None:
    return source_sha256(path) if path.is_file() else None


def save_cleanup_tasks(store: RunStore, partition: dict[str, Any]) -> None:
    """保存供 status 读取的精简取证快照。"""
    units = store.load_publication().units
    structured = {}
    for unit in units:
        rel = (unit.meta or {}).get("rel_path")
        structured[unit.id] = _optional_digest(store.structured_dir / rel) if rel else None
    catalog = _optional_digest(store.preprocessing_dir / "catalog.csv")
    input_digest = hashlib.sha256(json.dumps([structured, catalog], sort_keys=True).encode())
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in partition["entries"]:
        by_page[entry["raw_file"]].append(entry)
    rows = []
    for candidate in partition["cleanup_candidates"]:
        row = dict(candidate["missing"])
        row["reason"] = candidate["reason"]
        identity = input_digest.copy()
        identity.update(json.dumps(row, sort_keys=True, ensure_ascii=False).encode())
        row["id"] = identity.hexdigest()
        page = by_page[row["raw_file"]]
        index = next(
            i
            for i, entry in enumerate(page)
            if (entry["block"], entry["span"]) == (row["block"], row["span"])
        )
        row["context"] = [
            {key: entry[key] for key in ("block", "text", "destination")}
            for entry in page[max(0, index - 2) : index + 3]
        ]
        rows.append(row)
    atomic_write_json(
        store.preprocessing_dir / _TASK_FILE,
        {
            "schema": 1,
            "status": partition["status"],
            "reason": partition["reason"],
            "structured": structured,
            "catalog": catalog,
            "rows": rows,
        },
    )


def next_cleanup_task(store: RunStore, structured: dict[str, str | None]) -> dict[str, Any] | None:
    """只读快照，按原页摘要核对候选及其处置。"""
    path = store.preprocessing_dir / _TASK_FILE
    if not path.is_file():
        return None
    try:
        data = read_json(path)
        if not isinstance(data, dict) or data.get("schema") != 1:
            raise ValueError
        rows = data["rows"]
        if not isinstance(rows, list):
            raise ValueError
    except (OSError, ValueError, KeyError):
        return {"status": "stale", "reason": "source_tasks_unreadable"}
    if data.get("status") != "ok":
        return {"status": "unknown", "reason": data.get("reason")}
    if data.get("structured") != structured or data.get("catalog") != _optional_digest(
        store.preprocessing_dir / "catalog.csv"
    ):
        return {"status": "stale", "reason": "partition_inputs_changed"}
    handled = {
        row["candidate_id"]
        for row in (read_repairs(store) or [])
        if isinstance(row.get("candidate_id"), str)
        and row.get("evidence")
        and not row.get("unit_missing")
    }
    digests: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            return {"status": "stale", "reason": "source_tasks_unreadable"}
        name = row.get("raw_file")
        if not isinstance(name, str) or not re.fullmatch(r"page-\d+\.json", name):
            return {"status": "stale", "reason": "source_tasks_unreadable"}
        page = store.structured_dir / "raw" / name
        try:
            if name not in digests:
                digests[name] = source_sha256(page)
        except OSError:
            return {"status": "stale", "reason": name}
        if digests[name] != row.get("raw_digest"):
            return {"status": "stale", "reason": name}
        if row.get("id") not in handled:
            return {"status": "manual", **row}
    return None


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
            for text in str(block.get("text") or "").splitlines(keepends=True):
                stripped = text.strip()
                start = offset + (len(text) - len(text.lstrip()))
                offset += len(text)
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
                        "font_size": block.get("font_size"),
                        "bbox": block.get("bbox"),
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


def _cleanup_candidates(
    entries: list[dict[str, Any]], destinations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """定位页首清洗附近的待核文本，以及字号突出的未匹配短块。"""
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in entries:
        by_page[row["raw_file"]].append(row)
    repeated_heads = Counter(_norm(rows[0]["text"]) for rows in by_page.values())
    destination_texts = {row["norm"] for row in destinations}
    out = []
    for rows in by_page.values():
        head = rows[0]
        head_removed = head["destination"] == "noise" or (
            head["destination"] == "unresolved" and repeated_heads[_norm(head["text"])] >= 2
        )
        sizes = Counter()
        block_sizes = Counter(row["block"] for row in rows)
        for row in rows:
            size = row["font_size"]
            if isinstance(size, (int, float)) and size > 0:
                sizes[round(size, 1)] += len(row["text"])
        body_size = sizes.most_common(1)[0][0] if sizes else None
        for index, row in enumerate(rows):
            if row["destination"] != "unresolved":
                continue
            size, text = row["font_size"], row["text"]
            after_head = index == 1 and head_removed and _norm(text) != _norm(head["text"])
            if after_head and row["block"] == head["block"] and _FOLIO_RE.fullmatch(text):
                continue
            heading = (
                body_size is not None
                and isinstance(size, (int, float))
                and size >= body_size * 1.15
                and block_sizes[row["block"]] == 1
                and 4 <= len(text) <= 120
                and any(char.isalpha() for char in text)
                and not (index == 0 and head_removed)
            )
            if not (after_head or heading):
                continue
            # 已接合的原始折行常不再逐行匹配。仅用相邻原行的精确拼接排除候选。
            if any(
                _norm("".join(item["text"] for item in rows[start:end])) in destination_texts
                for start in range(max(0, index - 3), index + 1)
                for end in range(index + 1, min(len(rows), start + 4) + 1)
                if end - start > 1
            ):
                continue
            out.append(
                {
                    "status": "manual",
                    "missing": row,
                    "head": head if after_head else None,
                    "reason": "after_page_head" if after_head else "prominent_short_block",
                    "body_font_size": body_size,
                }
            )
    return out


def collect_partition(store: RunStore) -> dict[str, Any]:
    """逐行分区账本；默认只读，任务快照由调用方显式保存。"""
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
            "cleanup_candidates": [],
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
                "font_size": item["font_size"],
                "bbox": item["bbox"],
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
        "cleanup_candidates": _cleanup_candidates(entries, destinations),
        "complete": counts["unresolved"] == 0,
    }
