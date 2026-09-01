"""纯文本 / Markdown 读取器：识别章节标题、按空行切段。"""

from __future__ import annotations

import os
import re

from .models import KIND_HEADING, KIND_TEXT, SourceDocument, SourceSegment, SourceUnit

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_CHAPTER_MARK = re.compile(
    r"^\s*(?:"
    r"第[0-9０-９一二三四五六七八九十百千]+[章話话节節回部巻卷]"
    r"|序章|終章|終幕|序幕|プロローグ|エピローグ|あとがき|まえがき"
    r"|Chapter\s+\d+|CHAPTER\s+\d+"
    r")"
)


def _is_heading(line: str) -> tuple[str, int] | None:
    m = _MD_HEADING.match(line)
    if m:
        return m.group(2).strip(), len(m.group(1))
    if _CHAPTER_MARK.match(line):
        return line.strip(), 1
    return None


def _split_paragraphs(block: str) -> list[str]:
    parts = re.split(r"\n\s*\n", block)
    return [p.strip("\n") for p in parts if p.strip()]


def read_text(path: str) -> SourceDocument:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    lines = content.splitlines()
    book_title = os.path.splitext(os.path.basename(path))[0]

    raw_units: list[tuple[str | None, int, list[str]]] = []
    current_title: str | None = None
    current_level = 1
    current_body: list[str] = []
    for line in lines:
        info = _is_heading(line)
        if info is not None:
            if current_title is not None or current_body:
                raw_units.append((current_title, current_level, current_body))
            current_title, current_level = info
            current_body = []
        else:
            current_body.append(line)
    if current_title is not None or current_body:
        raw_units.append((current_title, current_level, current_body))

    units: list[SourceUnit] = []
    for ui, (explicit_title, level, body_lines) in enumerate(raw_units):
        title = explicit_title or book_title
        segments: list[SourceSegment] = []
        idx = 0
        if explicit_title:
            segments.append(SourceSegment(index=idx, source=explicit_title, kind=KIND_HEADING))
            idx += 1
        body = "\n".join(body_lines)
        for para in _split_paragraphs(body):
            segments.append(SourceSegment(index=idx, source=para, kind=KIND_TEXT))
            idx += 1
        units.append(
            SourceUnit(
                id=f"u{ui + 1:03d}",
                kind="chapter",
                title=title,
                segments=segments,
                meta={"heading_level": level},
            )
        )

    return SourceDocument(
        title=book_title,
        source_path=os.path.abspath(path),
        fmt="text",
        units=units,
    )
