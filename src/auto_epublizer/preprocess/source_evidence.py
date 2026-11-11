# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""原始页/栏/块与源 TOC 证据：只读定位，不合并、不删页眉、不裁定注释。"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from auto_common.workspace import RunStore

from ..notes import extract_candidates, read_notes_json
from .evidence import collect_breaks
from .note_inventory import collect_note_inventory


def _same_bbox(left: Any, right: Any) -> bool:
    if (
        not isinstance(left, list)
        or not isinstance(right, list)
        or len(left) != 4
        or len(right) != 4
    ):
        return False
    try:
        return all(abs(float(a) - float(b)) <= 0.5 for a, b in zip(left, right, strict=True))
    except (TypeError, ValueError):
        return False


def _registered_note_evidence(
    store: RunStore,
    blocks: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    note_ids: list[str] | None,
) -> dict[str, Any]:
    """以注册 notes.json 的每条 source_locations 为全集，保留缺坐标与多页续注。"""
    path = store.structured_dir / "notes.json"
    if not path.is_file():
        return {"registered": False, "source": "structured/notes.json", "notes": []}
    payload = path.read_bytes()
    data = read_notes_json(path)
    notes = data.get("notes")
    if not isinstance(notes, list):
        raise ValueError("structured/notes.json 的 notes 必须是数组")
    by_candidate = {
        str(item.get("candidate_id")): item
        for item in candidates
        if isinstance(item, dict) and item.get("candidate_id")
    }
    block_by_page: dict[Any, list[dict[str, Any]]] = {}
    for block in blocks:
        block_by_page.setdefault(block.get("page"), []).append(block)
    evidence: list[dict[str, Any]] = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        locations: list[dict[str, Any]] = []
        raw_locations = note.get("source_locations")
        if not isinstance(raw_locations, list):
            raw_locations = []
        for order, location in enumerate(raw_locations, start=1):
            if not isinstance(location, dict):
                location = {}
            page = location.get("page")
            bbox = location.get("bbox")
            candidate = by_candidate.get(str(location.get("candidate_id") or ""))
            matches: list[dict[str, Any]] = []
            if isinstance(page, int):
                for block in block_by_page.get(page, []):
                    if _same_bbox(bbox, block.get("bbox")):
                        matches.append(
                            {
                                key: block[key]
                                for key in (
                                    "raw_file",
                                    "page",
                                    "block",
                                    "bbox",
                                    "font_size",
                                    "column",
                                )
                            }
                        )
            if not matches and candidate:
                matches = list(candidate.get("raw_matches") or [])
            if matches:
                status = "located" if len(matches) == 1 else "ambiguous"
            elif isinstance(page, int):
                status = "page_only" if not bbox else "unmatched"
            else:
                status = "unknown"
            locations.append(
                {
                    "order": order,
                    "page": page,
                    "bbox": bbox if isinstance(bbox, list) else None,
                    "candidate_id": location.get("candidate_id"),
                    "unit": location.get("unit"),
                    "line": location.get("line"),
                    "text_block": location.get("text_block"),
                    "status": status,
                    "raw_matches": matches,
                }
            )
        statuses = {item["status"] for item in locations}
        if not locations:
            overall = "unknown"
        elif statuses <= {"located"}:
            overall = "located"
        elif "located" in statuses or "ambiguous" in statuses:
            overall = "partial"
        elif statuses <= {"page_only"}:
            overall = "page_only"
        elif statuses <= {"unknown"}:
            overall = "unknown"
        else:
            overall = "unmatched"
        evidence.append(
            {
                "note_id": str(note.get("note_id") or ""),
                "source_label": note.get("source_label"),
                "note_type": note.get("note_type"),
                "status": note.get("status"),
                "evidence_status": overall,
                "location_count": len(locations),
                "locations": locations,
            }
        )
    requested = [str(item) for item in (note_ids or [])]
    present = {item["note_id"] for item in evidence}
    missing = [item for item in requested if item not in present]
    selected = [item for item in evidence if not requested or item["note_id"] in requested]
    selected.sort(
        key=lambda item: (
            min(
                (loc["page"] for loc in item["locations"] if isinstance(loc["page"], int)),
                default=10**9,
            ),
            item["note_id"],
        )
    )
    return {
        "registered": True,
        "source": "structured/notes.json",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "inventory": data.get("inventory"),
        "total": len(evidence),
        "selected": len(selected),
        "requested_note_ids": requested,
        "missing_note_ids": missing,
        "notes": selected,
    }


def collect_source_evidence(
    store: RunStore, *, note_ids: list[str] | None = None
) -> dict[str, Any]:
    """保留真实可得坐标/字体/栏号及全部匹配；缺失精度明确 null。"""
    raw = store.structured_dir / "raw"
    blocks: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for path in sorted(raw.glob("page-*.json")):
        if not path.resolve().is_relative_to(raw.resolve()):
            raise ValueError(f"raw 页证据越界：{path.name}")
        payload = path.read_bytes()
        hashes[path.name] = hashlib.sha256(payload).hexdigest()
        page = json.loads(payload)
        if not isinstance(page, dict) or not isinstance(page.get("blocks"), list):
            raise ValueError(f"raw 页缺 blocks 数组：{path.name}")
        for index, block in enumerate(page["blocks"], start=1):
            if not isinstance(block, dict):
                raise ValueError(f"raw 页块不是对象：{path.name}:{index}")
            blocks.append(
                {
                    "raw_file": path.name,
                    "page": page.get("page_idx"),
                    "block": index,
                    "type": block.get("type"),
                    "text": block.get("text", ""),
                    "bbox": block.get("bbox"),
                    "font_size": block.get("font_size"),
                    "column": block.get("column"),
                }
            )
    pub = store.load_publication()
    md_by_unit: dict[str, str] = {}
    roles = []
    for unit in pub.units:
        rel = str(unit.meta.get("rel_path") or "")
        path = store.structured_dir / rel
        roles.append(
            {
                "unit": unit.id,
                "kind": unit.kind,
                "region": unit.meta.get("region"),
                "nav": unit.meta.get("nav", True),
            }
        )
        if rel and path.is_file():
            payload = path.read_bytes()
            hashes[f"structured/{rel}"] = hashlib.sha256(payload).hexdigest()
            md_by_unit[unit.id] = payload.decode("utf-8")
    candidates = extract_candidates(md_by_unit)
    for candidate in candidates:
        text = re.sub(r"\s+", "", candidate["text"])
        matches = [
            block for block in blocks if text and text in re.sub(r"\s+", "", str(block["text"]))
        ]
        candidate["raw_matches"] = [
            {k: b[k] for k in ("raw_file", "page", "block", "bbox", "font_size", "column")}
            for b in matches
        ]
        candidate["location_status"] = (
            "ambiguous" if len(matches) > 1 else ("unique" if matches else "unmatched")
        )
    facts_path = store.preprocessing_dir / "facts.json"
    toc = None
    if facts_path.is_file():
        payload = facts_path.read_bytes()
        hashes["preprocessing/facts.json"] = hashlib.sha256(payload).hexdigest()
        facts = json.loads(payload)
        if not isinstance(facts, dict):
            raise ValueError("facts.json 顶层不是对象")
        toc = (facts.get("source") or {}).get("toc")
    inventory = collect_note_inventory(store)
    result = {
        "schema_version": "1",
        "rule_version": "source-evidence-1",
        "source_sha256": pub.meta.source_sha256,
        "raw_hashes": hashes,
        "blocks": blocks,
        "source_toc": toc,
        "unit_roles": roles,
        "boundaries": collect_breaks(store),
        "note_candidates": candidates,
        "note_evidence": _registered_note_evidence(store, blocks, candidates, note_ids),
        # 独立于 notes.json 的源注候选清点；跨页注尾只在两端都像注文时配对。
        "note_inventory": inventory,
        "note_tail_pairs": inventory["continued_tails"],
        "source_inventory_status": "manual",
    }
    result["input_digest"] = hashlib.sha256(
        json.dumps(result, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return result
