"""pandoc 统一处理非 PDF 格式（HTML / DOCX / EPUB）→ Markdown 纯文本 + 媒体抽取。"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .models import KIND_HEADING, KIND_TEXT, SourceDocument, SourceSegment, SourceUnit


class PandocError(RuntimeError):
    """pandoc 调用失败。"""


def pandoc_available() -> bool:
    return shutil.which("pandoc") is not None


def run_pandoc(
    path: str | Path,
    *,
    media_dir: str | Path | None = None,
) -> str:
    """调用 pandoc 把文件转为 Markdown 纯文本并返回内容。"""
    if not pandoc_available():
        raise PandocError("未找到 pandoc；请安装 pandoc 或先把文件转为 PDF/TXT/Markdown")
    cmd = ["pandoc", str(path), "-t", "markdown", "--wrap=none"]
    if media_dir is not None:
        media_dir = Path(media_dir)
        media_dir.mkdir(parents=True, exist_ok=True)
        cmd.append(f"--extract-media={media_dir}")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as e:
        raise PandocError(f"pandoc 执行失败：{e}") from e
    if proc.returncode != 0:
        raise PandocError(f"pandoc 处理失败：{proc.stderr.strip()[:300]}")
    return proc.stdout


def parse_markdown_units(content: str) -> list[SourceUnit]:
    """把 pandoc 产出的 Markdown 按标题拆成单元。"""
    lines = content.splitlines()
    raw_units: list[tuple[str, int, list[str]]] = []
    current_title = "正文"
    current_level = 1
    current_body: list[str] = []
    for line in lines:
        m = _match_md_heading(line)
        if m:
            if current_body:
                raw_units.append((current_title, current_level, current_body))
            current_title, current_level = m
            current_body = []
        else:
            current_body.append(line)
    if current_body:
        raw_units.append((current_title, current_level, current_body))

    units: list[SourceUnit] = []
    for ui, (title, level, body_lines) in enumerate(raw_units):
        segments: list[SourceSegment] = []
        idx = 0
        segments.append(SourceSegment(index=idx, source=title, kind=KIND_HEADING))
        idx += 1
        for para in _split_md_paragraphs("\n".join(body_lines)):
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
    return units


def _match_md_heading(line: str) -> tuple[str, int] | None:
    line = line.rstrip()
    if not line.startswith("#"):
        return None
    text = line.lstrip("#").strip()
    if not text:
        return None
    return text, len(line) - len(line.lstrip("#"))


def _split_md_paragraphs(block: str) -> list[str]:
    import re

    parts = re.split(r"\n\s*\n", block)
    return [p.strip("\n") for p in parts if p.strip()]


def read_pandoc(
    path: str | Path,
    *,
    fmt: str,
    media_dir: str | Path | None = None,
) -> SourceDocument:
    """用 pandoc 读取 HTML/DOCX/EPUB，返回结构化的 Document。"""
    content = run_pandoc(path, media_dir=media_dir)
    units = parse_markdown_units(content)
    return SourceDocument(
        title=os.path.splitext(os.path.basename(str(path)))[0],
        source_path=os.path.abspath(str(path)),
        fmt=fmt,
        units=units,
        meta={"via": "pandoc"},
    )
