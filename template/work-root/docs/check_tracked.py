#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""独立允许规则与 Git/磁盘对账；只读，永不 git add。"""

from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

# 这不是 .gitignore 的副本；仅已知的工具缓存与交付 EPUB 默认可忽略。
DEFAULT_ALLOW = ("docs/__pycache__/**", "outbox/*/epub/**")


def allowed(path: str, pattern: str) -> bool:
    """按路径段匹配；* 不跨 /，** 才能匹配任意层。"""
    parts = path.split("/")
    rules = pattern.rstrip("/").split("/")
    if pattern.endswith("/"):
        rules.append("**")

    def match(p: list[str], r: list[str]) -> bool:
        if not r:
            return not p
        if r[0] == "**":
            return match(p, r[1:]) or bool(p) and match(p[1:], r)
        return bool(p) and fnmatch.fnmatchcase(p[0], r[0]) and match(p[1:], r[1:])

    return match(parts, rules)


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def paths(repo: Path, *args: str) -> set[str]:
    return {os.fsdecode(p) for p in git(repo, "ls-files", "-z", *args).split(b"\0") if p}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="只读核对跟踪/磁盘/忽略/未跟踪/缺失；意外忽略与未入库均失败。"
    )
    parser.add_argument("--repo", type=Path, default=root, help="明确 Git 仓库根；每本书独立检查")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        help="额外允许忽略的精确相对路径模式，可重复；* 不跨目录",
    )
    parser.add_argument(
        "--allow-file", type=Path, help="独立允许规则文件（一行一条，# 注释）；不得用 .gitignore"
    )
    args = parser.parse_args()
    try:
        repo = args.repo.resolve(strict=True)
        top = Path(os.fsdecode(git(repo, "rev-parse", "--show-toplevel")).strip()).resolve()
        if top != repo:
            raise ValueError(f"--repo 必须指定仓库根，实际为：{top}")
        rules = list(DEFAULT_ALLOW) + args.allow
        if args.allow_file:
            policy = args.allow_file.resolve(strict=True)
            if policy.name == ".gitignore" or policy == repo / ".git" / "info" / "exclude":
                raise ValueError("允许规则必须独立于 Git 忽略文件")
            rules.extend(
                line.strip()
                for line in policy.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
        for rule in rules:
            if rule.startswith(("/", "!")) or ".." in rule.split("/") or "\\" in rule:
                raise ValueError(f"允许规则必须为正向、仓库相对路径：{rule}")
        tracked = paths(repo, "--cached")
        ignored = paths(repo, "--others", "--ignored", "--exclude-standard")
        untracked = paths(repo, "--others", "--exclude-standard")
        disk: set[str] = set()
        for base, directories, files in os.walk(repo, followlinks=False):
            directories[:] = [name for name in directories if name != ".git"]
            for name in list(directories):
                path = Path(base) / name
                if path.is_symlink():
                    disk.add(path.relative_to(repo).as_posix())
                    directories.remove(name)
            for name in files:
                path = Path(base) / name
                if path == repo / ".git":  # worktree 的 .git 文件也属于 Git 元数据。
                    continue
                disk.add(path.relative_to(repo).as_posix())
        missing = tracked - disk
        unexpected = {p for p in ignored if not any(allowed(p, rule) for rule in rules)}
        unclassified = disk - tracked - ignored - untracked
        print(f"仓库：{repo}")
        print(
            f"跟踪 {len(tracked)}；磁盘 {len(disk)}；忽略 {len(ignored)}；未跟踪 {len(untracked)}；缺失 {len(missing)}"
        )
        print("忽略文件按顶层分组：")
        for group, count in sorted(Counter(p.split("/")[0] for p in ignored).items()):
            print(f"  {group}: {count}")
        for label, group in (
            ("意外忽略", unexpected),
            ("未跟踪", untracked),
            ("跟踪但缺失", missing),
            ("未归类磁盘文件（检查嵌套仓库）", unclassified),
        ):
            for path in sorted(group):
                print(f"{label}：{path}")
        if unexpected or untracked or missing or unclassified:
            print(
                "对账失败。先核证内容与保密边界；应忽略者添加精确独立允许规则，绝不要为消警把 secret 加入 Git。",
                file=sys.stderr,
            )
            return 1
        print("对账通过；没有修改索引、文件或忽略规则。")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        detail = (
            os.fsdecode(exc.stderr) if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        )
        print(f"对账失败：{detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
