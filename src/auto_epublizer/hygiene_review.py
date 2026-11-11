# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""译文卫生候选的逐条处置（#93）：只读合并，不自动接受。

``hygiene`` 输出的是候选，不是缺陷；没有处置记录时「扫过了」无法审计。本模块读取
agent 手写的 ``preprocessing/hygiene-review.jsonl``，按
``unit + block + code + 文本摘要`` 绑定处置：文本一变，旧结论立即失效（stale），
不会继续为改后的内容背书。全部保持 advisory，不改译文、不进放行硬门。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from auto_common.workspace import RunStore

SCHEMA_VERSION = 1
RULE_VERSION = "hygiene-1"
DISPOSITIONS = ("accepted", "fixed", "false_positive")


def review_path(store: RunStore) -> Path:
    return store.preprocessing_dir / "hygiene-review.jsonl"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _sha(text: str) -> str:
    return hashlib.sha256(_norm(text).encode("utf-8")).hexdigest()


def load_review(store: RunStore) -> list[dict[str, Any]]:
    """读取并校验处置记录；坏行/缺字段显式报错，不静默跳过。"""
    path = review_path(store)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"hygiene-review 第 {number} 行不是合法 JSON：{exc}") from None
        if not isinstance(row, dict):
            raise ValueError(f"hygiene-review 第 {number} 行不是对象")
        if row.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"hygiene-review 第 {number} 行 schema_version 必须是 1")
        for field in ("unit", "code", "text_sha256", "disposition", "reason"):
            if not str(row.get(field) or "").strip():
                raise ValueError(f"hygiene-review 第 {number} 行缺 {field}")
        if row["disposition"] not in DISPOSITIONS:
            raise ValueError(
                f"hygiene-review 第 {number} 行 disposition 必须是 {DISPOSITIONS} 之一"
            )
        rows.append(row)
    return rows


def collect(store: RunStore, *, unit_id: str | None = None) -> dict[str, Any]:
    """合并当前候选与既有处置；不变式：文本摘要不符即 stale。"""
    from .hygiene import scan_workspace

    scan = scan_workspace(store, unit_id=unit_id)
    prior = [
        row
        for row in load_review(store)
        if unit_id is None or str(row.get("unit") or "") == unit_id
    ]
    by_key: dict[tuple[str, int | None, str], dict[str, Any]] = {}
    for row in prior:
        try:
            block = int(row["block"]) if row.get("block") is not None else None
        except (TypeError, ValueError):
            block = None
        by_key[(str(row["unit"]), block, str(row["code"]))] = row
    entries: list[dict[str, Any]] = []
    for finding in scan["findings"]:
        unit = str(finding.get("unit") or "")
        block = finding.get("block")
        code = str(finding.get("code") or "")
        text_sha = str(finding.get("block_sha256") or _sha(str(finding.get("context") or "")))
        entry: dict[str, Any] = {
            "unit": unit,
            "block": block,
            "code": code,
            "text_sha256": text_sha,
            "context": finding.get("context") or "",
            "disposition": None,
            "reason": "",
            "stale": False,
        }
        matched = by_key.get((unit, block if isinstance(block, int) else None, code))
        if matched is not None:
            if matched.get("text_sha256") == text_sha:
                entry["disposition"] = matched.get("disposition")
                entry["reason"] = matched.get("reason") or ""
            else:
                entry["stale"] = True
        entries.append(entry)
    current = {(e["unit"], e["block"], e["code"], e["text_sha256"]) for e in entries}
    stale_keys = {(e["unit"], e["block"], e["code"]) for e in entries if e["stale"]}
    # 候选已不再产生（文本改掉/扫描条件变化）：记 gone，不冒充「未处置」，
    # 也不当作通过——它只说明当前扫描没有这条候选。
    gone = [
        row
        for row in prior
        if (str(row["unit"]), row.get("block"), str(row["code"]), row.get("text_sha256"))
        not in current
        and (str(row["unit"]), row.get("block"), str(row["code"])) not in stale_keys
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "path": str(review_path(store)),
        "entries": entries,
        "gone": [
            {"unit": row["unit"], "block": row.get("block"), "code": row["code"]} for row in gone
        ],
    }


def summarize(store: RunStore, *, unit_id: str | None = None) -> dict[str, Any]:
    """处置视角：总数/未处置/已闭合/失效。坏文件显式 invalid，不当作通过。"""
    try:
        data = collect(store, unit_id=unit_id)
    except ValueError as exc:
        return {"status": "invalid", "reason": str(exc), "total": 0, "open": 0, "stale": 0}
    entries = data["entries"]
    open_ids = [e for e in entries if e["disposition"] not in DISPOSITIONS]
    stale = [e for e in entries if e["stale"]]
    return {
        "status": "ok" if not open_ids else "open",
        "rule_version": data["rule_version"],
        "total": len(entries),
        "open": len(open_ids),
        "stale": len(stale),
        "closed": len(entries) - len(open_ids),
        "gone": len(data["gone"]),
    }
