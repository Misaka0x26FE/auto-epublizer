"""结构重建编排：把归一化单元清洗、归类并落盘到 structured/。"""

from __future__ import annotations

import re

from auto_common.workspace import Publication, RunStore

from ..ingest.models import SourceDocument
from .classify import classify_units, clean_unit

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def unit_heading(md_text: str) -> str | None:
    """提取单元 markdown 第一个 ATX 标题（无则返回 None）。"""
    for line in md_text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            return m.group(2).strip()
    return None


def skip_empty_unit(md_text: str, fallback_title: str) -> bool:
    """判断是否应跳过该单元：无正文段落且标题为占位（空 / 「正文」）。

    有正文段落、或标题为真实章节标题（如「第一章：…」）的单元都保留——
    后者即使没有正文，也作为目录导航锚点生成一个标题页。
    只跳过 init 拆分产生的空壳单元（MediaWiki 容器 div：标题为「正文」占位、
    内容仅容器标记 :::）。
    """
    title = (unit_heading(md_text) or fallback_title or "").strip()
    for line in md_text.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith(":::"):
            return False  # 有正文段落
    return title in ("", "正文")


def count_empty_units(md_texts: list[str], fallback_titles: list[str]) -> int:
    """统计空壳单元数量（体检用；确定性纯函数）。"""
    return sum(
        1 for md, t in zip(md_texts, fallback_titles, strict=False) if skip_empty_unit(md, t)
    )


class StructureError(RuntimeError):
    """结构重建失败。"""


def _render_markdown(title: str, segments) -> str:
    lines = [f"# {title}", ""]
    for s in segments:
        if s.kind == "heading":
            if s.source.strip() == title.strip():
                # 单元标题已在 # 行呈现，heading segment 不重复写入
                continue
            lines.append(f"## {s.source}")
            lines.append("")
        else:
            lines.append(s.source)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def rebuild_structure(doc: SourceDocument, pub: Publication) -> list[dict]:
    """清洗并归类单元，返回结构化单元清单（region/kind/unit_id/rel_path）。"""
    classified = classify_units(doc)
    entries: list[dict] = []
    for index, cls in enumerate(classified):
        cleaned = clean_unit(cls.unit)
        entries.append(
            {
                "_index": index,
                "id": cls.unit_id,
                "kind": cls.kind,
                "region": cls.region,
                "title": cleaned.title,
                "rel_path": cls.rel_path,
            }
        )
    return entries


def write_structured(store: RunStore, doc: SourceDocument, entries: list[dict]) -> None:
    """把结构化单元写为 structured/<rel_path> 的 Markdown 文件。"""
    structured = store.structured_dir
    units = doc.units
    for entry in entries:
        index = entry.get("_index")
        if not isinstance(index, int) or index >= len(units):
            continue
        unit = units[index]
        target = structured / entry["rel_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_render_markdown(unit.title, unit.segments), encoding="utf-8")
