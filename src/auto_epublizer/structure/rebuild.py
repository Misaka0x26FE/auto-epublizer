"""结构重建编排：把归一化单元清洗、归类并落盘到 structured/。"""

from __future__ import annotations

from auto_common.workspace import Publication, RunStore

from ..ingest.models import SourceDocument
from .classify import classify_units, clean_unit


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
