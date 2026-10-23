# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""原始页/栏/块与源 TOC 证据：只读定位，不合并、不删页眉、不裁定注释。"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from auto_common.workspace import RunStore

from ..notes import extract_candidates
from .evidence import collect_breaks


def collect_source_evidence(store: RunStore) -> dict[str, Any]:
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
        "source_inventory_status": "manual",
    }
    result["input_digest"] = hashlib.sha256(
        json.dumps(result, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return result
