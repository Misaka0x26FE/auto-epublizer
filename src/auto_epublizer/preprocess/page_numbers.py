# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""目录/索引页码策略证据：只声明 original/product/none，不改源件、不猜页码。"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from auto_common.workspace import RunStore

from .artifacts import read_page_number_policies

_PAGE_LINE = re.compile(
    r"(?m)^\s*(?P<label>.{1,120}?)[\s.…·•—–-]+(?P<page>[0-9]+|[ivxlcdm]+)\s*$", re.I
)


def collect_page_number_evidence(store: RunStore) -> dict[str, Any]:
    """输出策略声明与页码候选；重复目录仅报候选，未声明不冒充 original。"""
    pub = store.load_publication()
    policies = read_page_number_policies(store)
    units: list[dict[str, Any]] = []
    groups: dict[str, list[str]] = {}
    source_hashes: dict[str, str] = {}
    for unit in pub.units:
        rel = str(unit.meta.get("rel_path") or "")
        if not rel:
            continue
        path = store.structured_dir / rel
        payload = path.read_bytes() if path.is_file() else b""
        digest = hashlib.sha256(payload).hexdigest()
        source_hashes[f"structured/{rel}"] = digest
        if unit.kind not in {"toc", "index"}:
            continue
        text = payload.decode("utf-8", "replace")
        candidates = [
            {"label": match.group("label").strip(), "page": match.group("page")}
            for match in _PAGE_LINE.finditer(text)
        ]
        normalized = re.sub(r"\s+", "", text)
        groups.setdefault(hashlib.sha256(normalized.encode("utf-8")).hexdigest(), []).append(
            unit.id
        )
        declared = policies.get(unit.id)
        units.append(
            {
                "unit": unit.id,
                "kind": unit.kind,
                "rel_path": rel,
                "sha256": digest,
                "declared_policy": declared["policy"] if declared else None,
                "reason": declared["reason"] if declared else "",
                "evidence": declared["evidence"] if declared else "",
                "number_candidates": candidates,
                "number_candidate_count": len(candidates),
                "applied": False,
            }
        )
    duplicates = [
        {"content_sha256": digest, "units": ids} for digest, ids in groups.items() if len(ids) > 1
    ]
    duplicates.sort(key=lambda item: item["units"])
    return {
        "schema_version": "1",
        "policy_source": "preprocessing/page_numbers.csv",
        "source_sha256": pub.meta.source_sha256,
        "source_hashes": source_hashes,
        "units": units,
        "duplicate_toc_candidates": duplicates,
        "note": "策略仅声明，不改源件；未声明不等于 original；重复目录仅供人工核证",
    }
