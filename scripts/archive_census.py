# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""归档普查（A1）：只统计口径，不搬运书籍正文。

用法：
    python scripts/archive_census.py <translate-archive-root> [-o census.json]

读取 ``workspaces/*/report.json``、``translation/align/*.jsonl``、
``structured/notes.json`` 与 ``translation/notes.json``，输出：
- 报告句数 vs 实际 align 行数（差额不强行解释）；
- 注文 ID 契约问题（空/重复/源独有/目标独有）；
- 每本书的单元数、放行状态与注文计数。

输出只含 slug、计数、状态与文件相对路径，不含正文。缺文件或坏 JSON 记为错误，
不静默跳过。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _read_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{path}: 顶层不是对象")
        return None
    return data


def _note_ids(data: dict[str, Any] | None, key: str) -> list[str]:
    if not data:
        return []
    rows = data.get(key)
    if not isinstance(rows, list):
        return []
    return [str(r.get("note_id") or "") for r in rows if isinstance(r, dict)]


def census(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    workspaces = sorted((root / "workspaces").glob("*"))
    books: list[dict[str, Any]] = []
    totals = {
        "books": 0,
        "report_sentences": 0,
        "align_rows": 0,
        "notes": 0,
        "notes_missing_target": 0,
        "notes_extra_target": 0,
        "notes_duplicate": 0,
        "notes_empty_id": 0,
    }
    for workspace in workspaces:
        if not workspace.is_dir():
            continue
        report_path = workspace / "report.json"
        if not report_path.is_file():
            errors.append(f"{report_path}: 缺 report.json（工作区未完成 QA）")
            continue
        report = _read_json(report_path, errors) or {}
        align_rows = 0
        align_files = sorted((workspace / "translation" / "align").glob("*.jsonl"))
        for path in align_files:
            try:
                align_rows += sum(
                    1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
                )
            except OSError as exc:
                errors.append(f"{path}: {exc}")
        source_notes = _read_json(workspace / "structured" / "notes.json", errors)
        target_path = workspace / "translation" / "notes.json"
        target_notes = _read_json(target_path, errors)
        source_ids = _note_ids(source_notes, "notes")
        target_ids = _note_ids(target_notes, "notes")
        if source_notes is not None and _note_ids(source_notes, "notes") and target_notes is None:
            errors.append(f"{target_path}: 有源注文登记但缺译注文件")
        duplicates = len(source_ids) - len(set(source_ids))
        empty_ids = sum(1 for nid in source_ids + target_ids if not nid)
        missing_target = len(set(source_ids) - set(target_ids)) if source_notes else 0
        extra_target = len(set(target_ids) - set(source_ids)) if source_notes else 0
        books.append(
            {
                "slug": workspace.name,
                "released": bool(report.get("released")),
                "released_reason": str(report.get("released_reason") or ""),
                "units": int(report.get("units_total") or 0),
                "report_sentences": int(report.get("total_sentences") or 0),
                "align_rows": align_rows,
                "align_files": len(align_files),
                "notes": len(source_ids),
                "notes_duplicate": duplicates,
                "notes_empty_id": empty_ids,
                "notes_missing_target": missing_target,
                "notes_extra_target": extra_target,
            }
        )
        totals["books"] += 1
        totals["report_sentences"] += int(report.get("total_sentences") or 0)
        totals["align_rows"] += align_rows
        totals["notes"] += len(source_ids)
        totals["notes_missing_target"] += missing_target
        totals["notes_extra_target"] += extra_target
        totals["notes_duplicate"] += duplicates
        totals["notes_empty_id"] += empty_ids
    totals["sentence_delta"] = totals["report_sentences"] - totals["align_rows"]
    return {
        "schema_version": 1,
        "root": str(root),
        "source_sha256": None,
        "rule_version": "archive-census-1",
        "generated_by": "scripts/archive_census.py",
        "totals": totals,
        "books": books,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="translate 归档只读普查")
    parser.add_argument("root", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--source-sha256", default=None, help="原始 tar.gz 的 SHA-256")
    args = parser.parse_args(argv)
    data = census(args.root)
    if args.source_sha256:
        data["source_sha256"] = args.source_sha256
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 1 if data["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
