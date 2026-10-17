#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""真实 ledger 负责机器列；本工具只按唯一 slug 保留人工列。"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MANUAL = ("批次", "领域", "摘要", "最后修改")


def cells(line: str) -> list[str]:
    """保留单元格原字节，包括转义 pipe 与空白；只切未转义的分隔符。"""
    text = line.strip()
    if not text.startswith("|") or not text.endswith("|"):
        raise ValueError("台账行必须以 | 开始及结束")
    parts: list[str] = []
    start = 1
    for index in range(1, len(text)):
        if text[index] != "|":
            continue
        backslashes = 0
        previous = index - 1
        while previous >= 0 and text[previous] == "\\":
            backslashes += 1
            previous -= 1
        if backslashes % 2 == 0:
            parts.append(text[start:index])
            start = index + 1
    if start != len(text):
        raise ValueError("台账行结尾分隔符被转义")
    return parts


def table(text: str) -> tuple[list[str], int, int, list[list[str]]]:
    lines = text.splitlines()
    candidates = [
        i
        for i, line in enumerate(lines)
        if line.lstrip().startswith("|") and "slug" in [c.strip() for c in cells(line)]
    ]
    if len(candidates) != 1:
        raise ValueError("必须存在且仅存在一个带 slug 表头的台账表格")
    start = candidates[0]
    headers = [c.strip() for c in cells(lines[start])]
    if len(set(headers)) != len(headers):
        raise ValueError("台账表头重复")
    if start + 1 >= len(lines):
        raise ValueError("台账缺少分隔行")
    separator = cells(lines[start + 1])
    if len(separator) != len(headers) or not all(
        re.fullmatch(r"\s*:?-+:?\s*", c) for c in separator
    ):
        raise ValueError("台账分隔行/列数非法")
    rows = []
    end = start + 2
    seen = set()
    key_index = headers.index("slug")
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        row = cells(lines[end])
        if len(row) != len(headers):
            raise ValueError(f"台账第 {end + 1} 行列数不符，拒绝错搬人工列")
        key = row[key_index].strip()
        if not key or key in seen:
            raise ValueError(f"slug 空白或重复，无法稳定匹配工作区：{key!r}")
        seen.add(key)
        rows.append(row)
        end += 1
    return headers, start, end, rows


def merge(fresh: str, old: str | None) -> str:
    headers, start, end, rows = table(fresh)
    machine = [name for name in headers if name not in MANUAL]
    saved: dict[str, dict[str, str]] = {}
    if old is not None:
        previous, _, _, old_rows = table(old)
        if [name for name in previous if name not in MANUAL] != machine:
            raise ValueError("旧台账机器表头与真实 CLI 不同；请核证迁移，旧文件未改")
        for row in old_rows:
            saved[row[previous.index("slug")].strip()] = {
                name: row[previous.index(name)] for name in MANUAL if name in previous
            }
    output_headers = headers + [name for name in MANUAL if name not in headers]
    lines = fresh.splitlines()
    replacement = [
        "|" + "|".join(f" {name} " for name in output_headers) + "|",
        "|" + "|".join("---" for _ in output_headers) + "|",
    ]
    for row in rows:
        key = row[headers.index("slug")].strip()
        manual = saved.get(key, {})
        output = [
            manual.get(name, row[index]) if name in MANUAL else row[index]
            for index, name in enumerate(headers)
        ]
        output.extend(manual.get(name, "  ") for name in output_headers[len(headers) :])
        replacement.append("|" + "|".join(output) + "|")
    return "\n".join(lines[:start] + replacement + lines[end:]) + "\n"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="调用真实 ledger 重算机器列，按唯一 slug 原样保留四个人工列。"
    )
    parser.add_argument(
        "--workspace", type=Path, default=root / "workspaces", help="工作区集合根目录"
    )
    parser.add_argument(
        "--output", type=Path, default=root / "docs" / "工作台账.md", help="台账路径"
    )
    parser.add_argument("--cli", default="auto-epublizer", help="真实 auto-epublizer 可执行路径")
    args = parser.parse_args()
    temporary = None
    try:
        output = args.output.absolute()
        if output.is_symlink():
            raise ValueError("拒绝替换符号链接台账")
        before = output.read_bytes() if output.exists() else None
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=output.parent, prefix=".ledger-", suffix=".md", delete=False
        ) as stream:
            temporary = Path(stream.name)
        subprocess.run(
            [
                args.cli,
                "ledger",
                "--workspace",
                str(args.workspace.resolve()),
                "--output",
                str(temporary),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        result = merge(
            temporary.read_text(encoding="utf-8"),
            before.decode("utf-8") if before is not None else None,
        )
        temporary.write_text(result, encoding="utf-8")
        if (output.read_bytes() if output.exists() else None) != before:
            raise ValueError("台账在生成期间被修改，拒绝覆盖")
        temporary.replace(output)
        temporary = None
        print(f"台账已重算，机器列来自真实 CLI、人工列按 slug 保留：{output}")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        print(f"台账失败（旧文件未覆盖）：{detail}", file=sys.stderr)
        return 1
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
