# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""生成式目录页（D2）：从单元树渲染可点击层级目录。

目录页是**结构视图**，不是译文段落：条目来自已译单元标题与单元内子标题锚点，
允许按单元树重排；原版目录文本只作来源证据（D1）。页码只读取显式
``preprocessing/toc_pages.csv`` 的 ``unit,page`` 映射，缺省不显示，不猜页码。
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from auto_common.workspace import RunStore

from . import toc_depths
from .html import plain_label, render_toc_document, slug_file, subheading_anchors


def read_toc_pages(store: RunStore) -> dict[str, str]:
    """读取目录页码映射（可选）：``unit,page``；非法/重复/未知单元报错。"""
    path = store.preprocessing_dir / "toc_pages.csv"
    if not path.is_file():
        return {}
    known = {unit.id for unit in store.load_publication().units}
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig")))
    missing = [field for field in ("unit", "page") if field not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"目录页码表缺少必需列：{', '.join(missing)}")
    pages: dict[str, str] = {}
    for lineno, row in enumerate(reader, start=2):
        unit = (row.get("unit") or "").strip()
        page = (row.get("page") or "").strip()
        if not unit and not page:
            continue
        if unit not in known:
            raise ValueError(f"目录页码表第 {lineno} 行 unit 不在 publication.json：{unit!r}")
        if not page:
            raise ValueError(f"目录页码表第 {lineno} 行 page 不能为空")
        if unit in pages:
            raise ValueError(f"目录页码表第 {lineno} 行 unit 重复：{unit}")
        pages[unit] = page
    return pages


def _md_for(store: RunStore, entry: dict[str, Any], *, prefer_translation: bool) -> str:
    rel = str(entry.get("rel_path") or "")
    if not rel:
        return ""
    candidates = []
    if prefer_translation:
        candidates.append(store.translation_dir / rel)
    candidates.append(store.structured_dir / rel)
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return ""


_LEADER_RE = re.compile(r"[.…·。．\s]+")
_TRAILING_PAGE_RE = re.compile(r"\d+$")


def normalize_toc_label(text: str) -> str:
    """目录条目归一化：去掉引导点/空白/末尾页码，用于「是否已收录」的对比。"""
    value = _LEADER_RE.sub("", str(text or ""))
    value = _TRAILING_PAGE_RE.sub("", value)
    return value.strip()


def source_toc_lines(
    store: RunStore, entry: dict[str, Any], *, prefer_translation: bool
) -> list[str]:
    """原目录单元里可读的条目行（去 markdown 标记与空行），保留源文顺序。"""
    text = _md_for(store, entry, prefer_translation=prefer_translation)
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("#").strip()
        if not line or set(line) <= set(".…·。．-— "):
            continue
        label = normalize_toc_label(line)
        if label:
            lines.append(label)
    return lines


def _tree_labels(tree: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    for node in tree:
        labels.append(normalize_toc_label(node["label"]))
        labels.extend(_tree_labels(node.get("children") or []))
    return labels


def preserved_source_nodes(
    store: RunStore,
    toc_entry: dict[str, Any],
    tree: list[dict[str, Any]],
    *,
    prefer_translation: bool,
) -> list[dict[str, Any]]:
    """原目录中未被结构树覆盖的条目，作为无链接条目保留（不丢内容）。"""
    labels = _tree_labels(tree)
    joined = "\n".join(labels)
    nodes: list[dict[str, Any]] = []
    for line in source_toc_lines(store, toc_entry, prefer_translation=prefer_translation):
        if line in joined:
            continue
        nodes.append({"unit": "", "label": line, "href": "", "children": []})
    return nodes


def build_toc_tree(
    store: RunStore,
    entries: list[dict[str, Any]],
    *,
    nav_depth: int,
    prefer_translation: bool = True,
) -> list[dict[str, Any]]:
    """按单元树 + 单元内锚点构建目录树（生成器）。"""
    visible = [
        entry for entry in entries if entry.get("kind") != "cover" and entry.get("nav") is not False
    ]
    depths = toc_depths(visible)
    tree: list[dict[str, Any]] = []
    stack: list[tuple[int, list[dict[str, Any]]]] = [(0, tree)]
    for entry, depth in zip(visible, depths, strict=False):
        if depth > nav_depth:
            continue
        href = f"{slug_file(entry['id'])}.xhtml"
        node = {
            "unit": entry["id"],
            "label": plain_label(str(entry.get("title") or entry["id"])),
            "href": href,
            "children": [],
        }
        while stack and stack[-1][0] >= depth:
            stack.pop()
        stack[-1][1].append(node)
        stack.append((depth, node["children"]))
        anchors = subheading_anchors(
            _md_for(store, entry, prefer_translation=prefer_translation), entry["id"]
        )
        relative = toc_depths([{"level": anchor["level"]} for anchor in anchors])
        anchor_stack: list[tuple[int, list[dict[str, Any]]]] = [(0, node["children"])]
        for anchor, rel in zip(anchors, relative, strict=False):
            if depth + rel > nav_depth:
                continue
            child = {
                "unit": entry["id"],
                "label": anchor["title"],
                "href": f"{href}#{anchor['anchor']}",
                "children": [],
            }
            while anchor_stack and anchor_stack[-1][0] >= rel:
                anchor_stack.pop()
            anchor_stack[-1][1].append(child)
            anchor_stack.append((rel, child["children"]))
    return tree


def generated_toc_document(
    store: RunStore,
    entries: list[dict[str, Any]],
    *,
    lang: str,
    nav_depth: int,
    prefer_translation: bool,
) -> dict[str, Any] | None:
    """生成目录页 XHTML；没有 toc 单元时返回 None。"""
    toc_entries = [entry for entry in entries if entry.get("kind") == "toc"]
    if not toc_entries:
        return None
    toc_unit = toc_entries[0]
    tree = build_toc_tree(
        store, entries, nav_depth=nav_depth, prefer_translation=prefer_translation
    )
    pages = read_toc_pages(store)
    title = str(toc_unit.get("title") or "目录")
    tree = [
        *tree,
        *preserved_source_nodes(store, toc_unit, tree, prefer_translation=prefer_translation),
    ]
    html = render_toc_document(title, tree, lang=lang, pages=pages)
    return {
        "unit": toc_unit["id"],
        "name": f"{slug_file(toc_unit['id'])}.xhtml",
        "html": html,
        "tree": tree,
        "pages": pages,
    }
