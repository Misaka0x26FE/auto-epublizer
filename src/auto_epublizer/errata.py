# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""源文实印疑误登记（errata）：只记录证据，不改写不可变 source。

每条登记绑定单元与定位（页/块或源串），给出「实印如此」的原文、建议读法与证据。
``status`` 区分 proposed/confirmed/rejected：proposed 只是待核，不自动当成已确认修复；
confirmed 才能作为译文采用建议读法的依据。产物 ``preprocessing/errata.jsonl`` 独立于
``structured/``，源文永远保持交付时的模样。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from auto_common.workspace import RunStore

SCHEMA_VERSION = 1
STATUSES = ("proposed", "confirmed", "rejected")


class ErrataError(ValueError):
    """errata 契约错误（用户可预期）。"""


@dataclass
class ErrataReport:
    entries: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    path: Path | None = None


def errata_path(store: RunStore) -> Path:
    return store.preprocessing_dir / "errata.jsonl"


def _validate(store: RunStore, raw: Any, index: int) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return None, [f"第 {index} 行不是对象"]
    unit = str(raw.get("unit") or "").strip()
    locator = str(raw.get("locator") or "").strip()
    source_text = str(raw.get("source_text") or "").strip()
    reading = str(raw.get("reading") or "").strip()
    evidence = str(raw.get("evidence") or "").strip()
    status = str(raw.get("status") or "proposed").strip()
    if not unit:
        errors.append(f"第 {index} 行缺 unit")
    elif unit not in {u.id for u in store.load_publication().units}:
        errors.append(f"第 {index} 行的单元不存在：{unit}")
    if not locator:
        errors.append(f"第 {index} 行缺 locator（页/块或源串定位）")
    if not source_text:
        errors.append(f"第 {index} 行缺 source_text")
    if not reading:
        errors.append(f"第 {index} 行缺 reading（建议读法）")
    if not evidence:
        errors.append(f"第 {index} 行缺 evidence（原页/扫描/校勘依据）")
    if status not in STATUSES:
        errors.append(f"第 {index} 行 status 必须是 {STATUSES} 之一")
    if errors:
        return None, errors
    return {
        "unit": unit,
        "locator": locator,
        "source_text": source_text,
        "reading": reading,
        "evidence": evidence,
        "status": status,
        "source_sha256": store.load_publication().meta.source_sha256,
        "note": str(raw.get("note") or ""),
    }, []


def register_errata(store: RunStore, rows: list[Any], *, apply: bool = False) -> ErrataReport:
    """校验并（可选）合并写入 errata.jsonl；默认只预检。

    按 ``(unit, locator)`` 合并：本批同键重复报错；已有条目保留，同键以本批覆盖。
    空批次不覆盖既有台账。
    """
    report = ErrataReport(path=errata_path(store))
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(rows, start=1):
        entry, errors = _validate(store, raw, index)
        report.errors.extend(errors)
        if entry is not None:
            key = (entry["unit"], entry["locator"])
            if key in seen:
                report.errors.append(f"第 {index} 行与同批条目重复：{key[0]} / {key[1]}")
                continue
            seen.add(key)
            report.entries.append(entry)
    if report.errors or not apply:
        return report
    if not rows:
        report.errors.append("空批次拒绝覆盖既有 errata（确需清空请手工处理）")
        return report
    existing, _digest = read_errata(store)
    merged: dict[tuple[str, str], dict[str, Any]] = {
        (str(e.get("unit") or ""), str(e.get("locator") or "")): e for e in existing
    }
    for entry in report.entries:
        key = (entry["unit"], entry["locator"])
        prior = merged.get(key)
        if prior and prior.get("status") == "confirmed" and entry["status"] == "proposed":
            # 已确认条目不得被新批次的 proposed 静默降级；要降级先显式改旧行。
            continue
        merged[key] = entry
    path = errata_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
        for entry in sorted(merged.values(), key=lambda e: (e["unit"], e["locator"]))
    ).encode("utf-8")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)
    report.entries = sorted(merged.values(), key=lambda e: (e["unit"], e["locator"]))
    report.path = path
    store.log_event("errata_registered", entries=len(report.entries))
    return report


def read_errata(store: RunStore) -> tuple[list[dict[str, Any]], str | None]:
    path = errata_path(store)
    if not path.is_file():
        return [], None
    payload = path.read_bytes()
    rows: list[dict[str, Any]] = []
    for line in payload.decode("utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows, hashlib.sha256(payload).hexdigest()
