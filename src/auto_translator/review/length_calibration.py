# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""长度比规则的离线校准（E1）：只评估，不自动改阈值。

真实语料上「长度比低」既可能是正常压缩（拉丁/西里尔 → 汉字），也可能是整段漏译。
没有人工标注的对照集时，任何阈值调整都只是把噪声挪走，不能证明召回率。本模块提供
固定输入格式的评估器：调用方给 ``label``（``ok``/``missing``），它报告误报、漏报与
新旧规则差异；阈值是否启用由人依据独立验证集决定。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

LABELS = ("ok", "missing")


@dataclass(frozen=True)
class CalibrationRow:
    src: str
    tgt: str
    label: str  # ok | missing


def _ratio(src: str, tgt: str) -> float:
    source = len((src or "").strip())
    return len((tgt or "").strip()) / source if source else 0.0


def evaluate(
    rows: Iterable[CalibrationRow | dict[str, Any]],
    *,
    too_short: float = 0.30,
    too_long: float = 3.0,
    min_src_chars: int = 20,
) -> dict[str, Any]:
    """按给定阈值评估告警质量；返回计数与可复现的分母。"""
    parsed: list[CalibrationRow] = []
    for row in rows:
        item = (
            row
            if isinstance(row, CalibrationRow)
            else CalibrationRow(
                str(row.get("src") or ""), str(row.get("tgt") or ""), str(row.get("label") or "")
            )
        )
        if item.label not in LABELS:
            raise ValueError(f"label 必须是 {LABELS} 之一：{item.label!r}")
        parsed.append(item)
    tp = fp = fn = tn = 0
    alerts = 0
    for item in parsed:
        src_len = len(item.src.strip())
        ratio = _ratio(item.src, item.tgt)
        alerted = not item.tgt.strip() or (
            src_len >= min_src_chars and (ratio < too_short or ratio > too_long)
        )
        alerts += int(alerted)
        if alerted and item.label == "missing":
            tp += 1
        elif alerted:
            fp += 1
        elif item.label == "missing":
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {
        "rows": len(parsed),
        "labels": {label: sum(1 for r in parsed if r.label == label) for label in LABELS},
        "thresholds": {
            "too_short": too_short,
            "too_long": too_long,
            "min_src_chars": min_src_chars,
        },
        "alerts": alerts,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
    }
