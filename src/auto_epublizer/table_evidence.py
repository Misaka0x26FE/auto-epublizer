# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""逐格比较人工核过的 XHTML 表格与成品表格。"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _text(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())


def _grid(table: ET.Element) -> dict[tuple[int, int], dict]:
    grid = {}
    occupied: dict[int, int] = {}
    row_number = 0
    for child in table:
        section = _tag(child)
        rows = [child] if section == "tr" else list(child)
        for row in rows:
            if _tag(row) != "tr" or section not in {"tr", "thead", "tbody", "tfoot"}:
                continue
            row_number += 1
            column = 1
            for cell in row:
                role = _tag(cell)
                if role not in {"td", "th"}:
                    continue
                while occupied.get(column, 0) >= row_number:
                    column += 1
                width = int(cell.get("colspan", "1"))
                height = int(cell.get("rowspan", "1"))
                if not 1 <= width <= 1000 or not 1 <= height <= 65534:
                    raise ValueError("表格合并范围超出支持范围")
                for covered in range(column, column + width):
                    if occupied.get(covered, 0) >= row_number:
                        raise ValueError(f"表格合并重叠：第 {row_number} 行，第 {covered} 列")
                    occupied[covered] = row_number + height - 1
                grid[row_number, column] = {
                    "text": _text(cell),
                    "role": role,
                    "section": "tbody" if section == "tr" else section,
                    "rowspan": height,
                    "colspan": width,
                }
                column += width
    if not grid or max(occupied.values()) > row_number:
        raise ValueError("表格为空或纵向合并超出末行")
    return grid


def _tables(payload: bytes) -> list[ET.Element]:
    root = ET.fromstring(payload)
    return [node for node in root.iter() if _tag(node) == "table"]


def compare_table(expected: Path, epub: Path, member: str, number: int) -> dict:
    """基准文件含一张表，成品按明确的成员路径与一基序号定位。"""
    baseline = expected.read_bytes()
    source = _tables(baseline)
    if len(source) != 1:
        raise ValueError("核对基准必须恰有一张表")
    with ZipFile(epub) as archive:
        if archive.namelist().count(member) != 1:
            raise ValueError("成品成员不存在或重复")
        actual = archive.read(member)
    tables = _tables(actual)
    if not 1 <= number <= len(tables):
        raise ValueError(f"成品成员中没有第 {number} 张表")
    left, right = _grid(source[0]), _grid(tables[number - 1])
    findings = [
        {
            "row": row,
            "column": col,
            "expected": left.get((row, col)),
            "actual": right.get((row, col)),
        }
        for row, col in sorted(left.keys() | right.keys())
        if left.get((row, col)) != right.get((row, col))
    ]
    captions = [
        [_text(node) for node in table if _tag(node) == "caption"]
        for table in (source[0], tables[number - 1])
    ]
    if captions[0] != captions[1]:
        findings.append(
            {"row": None, "column": None, "expected": captions[0], "actual": captions[1]}
        )
    return {
        "status": "fail" if findings else "pass",
        "member": member,
        "table": number,
        "baseline_sha256": hashlib.sha256(baseline).hexdigest(),
        "member_sha256": hashlib.sha256(actual).hexdigest(),
        "expected_cells": len(left),
        "actual_cells": len(right),
        "findings": findings,
    }
