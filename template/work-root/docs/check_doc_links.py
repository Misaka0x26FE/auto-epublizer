#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""离线检查工作根 AGENTS.md 与 docs/*.md；不读取书籍内容。"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


def visible_lines(text: str) -> list[tuple[int, str]]:
    lines = []
    fence = None
    in_comment = False
    for number, original in enumerate(text.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", original)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is not None or original.startswith(("    ", "\t")):
            continue
        # HTML comments are not rendered references.
        line = original
        if in_comment:
            if "-->" not in line:
                continue
            line = line.split("-->", 1)[1]
            in_comment = False
        while "<!--" in line:
            before, after = line.split("<!--", 1)
            if "-->" in after:
                line = before + after.split("-->", 1)[1]
            else:
                line = before
                in_comment = True
                break
        lines.append((number, line))
    return lines


def destination(text: str) -> str:
    text = text.strip()
    if text.startswith("<") and ">" in text:
        return text[1:text.index(">")]
    # Markdown allows escaped whitespace and nested parentheses in bare destinations.
    match = re.match(r"(?:\\.|[^\s])+", text)
    return match.group(0) if match else ""


def references(lines: list[tuple[int, str]]) -> tuple[list[tuple[int, str]], list[str]]:
    definitions = {}
    found = []
    errors = []
    for number, line in lines:
        match = re.match(r"^\s{0,3}\[([^\]]+)\]:\s*(.+)$", line)
        if match:
            key = " ".join(match.group(1).lower().split())
            target = destination(match.group(2))
            definitions[key] = target
            found.append((number, target))
    for number, line in lines:
        if re.match(r"^\s{0,3}\[[^\]]+\]:", line):
            continue
        # Mask code spans when scanning Markdown links; path-only code spans are
        # checked separately, whereas commands and example placeholders are skipped.
        for code in re.finditer(r"(`+)(.+?)\1", line):
            token = code.group(2).strip()
            if not re.search(r"\s", token) and (
                token.endswith((".md", ".py", "/")) or "/" in token and not Path(token).suffix
            ):
                found.append((number, token))
        plain = re.sub(r"(`+)(.+?)\1", lambda m: " " * len(m.group(0)), line)
        pattern = re.compile(r"!?\[([^\]]+)\]")
        position = 0
        while match := pattern.search(plain, position):
            end = match.end()
            label = match.group(1)
            if end < len(plain) and plain[end] == "(":
                depth = 1
                cursor = end + 1
                escaped = False
                while cursor < len(plain):
                    char = plain[cursor]
                    if not escaped:
                        if char == "(":
                            depth += 1
                        elif char == ")":
                            depth -= 1
                            if depth == 0:
                                break
                    escaped = char == "\\" and not escaped
                    cursor += 1
                if depth == 0:
                    found.append((number, destination(plain[end + 1:cursor])))
                    end = cursor + 1
                else:
                    errors.append(f"{number}: Markdown 链接括号未闭合")
            else:
                explicit = re.match(r"\[([^\]]*)\]", plain[end:])
                key = (explicit.group(1) or label) if explicit else label
                key = " ".join(key.lower().split())
                if key in definitions:
                    found.append((number, definitions[key]))
                elif explicit:
                    errors.append(f"{number}: 未定义引用链接 [{key}]")
                if explicit:
                    end += explicit.end()
            position = end
    return found, errors


def local_path(target: str) -> str | None:
    if not target or target.startswith(("#", "//")):
        return None
    # Explicit placeholders/globs are examples, not a request to guess a book.
    if re.search(r"<[^>]+>|\{[^}]+\}|\*|\$\w|\$\(", target):
        return None
    target = re.sub(r"\\([\\ ()\[\]#])", r"\1", target)
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    path = unquote(parsed.path)
    if not path or Path(path).is_absolute():
        return None
    # EPUB-internal members belong to EPUB QA, not work-root documentation.
    if Path(path).suffix.lower() in {".xhtml", ".html", ".opf", ".ncx", ".css"}:
        return None
    if any(part in {"OEBPS", "EPUB", "META-INF"} for part in Path(path).parts):
        return None
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="离线检查 AGENTS.md + docs/*.md 的相对文档、脚本及目录引用。")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="工作根")
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        agents = root / "AGENTS.md"
        if not agents.is_file() or not (root / "docs").is_dir():
            raise ValueError("工作根必须含 AGENTS.md 与 docs/ 目录")
        documents = [agents, *sorted((root / "docs").glob("*.md"))]
        failures = 0
        for doc in documents:
            found, errors = references(visible_lines(doc.read_text(encoding="utf-8")))
            for error in errors:
                print(f"{doc.relative_to(root)}:{error}")
                failures += 1
            for number, target in sorted(set(found)):
                relative = local_path(target)
                if relative is not None and not (doc.parent / relative).exists():
                    print(f"{doc.relative_to(root)}:{number}: 断链 {target!r} → {doc.parent / relative}")
                    failures += 1
        print(f"已检查 {len(documents)} 份文档；断链/语法问题 {failures} 项。")
        return 1 if failures else 0
    except (OSError, ValueError) as exc:
        print(f"文档检查失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
