# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""生成式目录页的独立对账（D2）：不复用生成器的树，只读成品与源登记。

期望树从 ``publication.json`` 单元与各单元 md 子标题锚点独立重算；成品侧解析
``nav[data-aep=generated-toc]`` 的实际 ``<ol>/<li>/<a>``，逐条核对顺序、层级、标签、
目标（含 fragment）。findings 为 advisory：目录页缺陷可见，但不单独阻断放行；
``<br/>`` 压缩、零链接、缺页码作为 lint 候选。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from auto_common.workspace import RunStore

from ..build.html import plain_label, slug_file, subheading_anchors

_XHTML = "{http://www.w3.org/1999/xhtml}"
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_BR_IN_P = re.compile(r"<p\b[^>]*>(?:(?!</p>).)*<br\s*/?>(?:(?!</p>).)*<br\s*/?>", re.I | re.S)


def _depths(levels: list[int]) -> list[int]:
    """与目录深度定义一致的独立实现（不调用生成器）。"""
    depths: list[int] = []
    stack: list[int] = []
    for level in levels:
        while stack and stack[-1] >= level:
            stack.pop()
        depths.append(len(stack) + 1)
        stack.append(level)
    return depths


def _md(store: RunStore, entry: dict[str, Any], prefer_translation: bool) -> str:
    rel = str(entry.get("rel_path") or "")
    paths = []
    if prefer_translation and rel:
        paths.append(store.translation_dir / rel)
    if rel:
        paths.append(store.structured_dir / rel)
    for path in paths:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return ""


def expected_toc(
    store: RunStore,
    entries: list[dict[str, Any]],
    *,
    nav_depth: int,
    prefer_translation: bool = True,
) -> list[dict[str, Any]]:
    visible = [
        entry for entry in entries if entry.get("kind") != "cover" and entry.get("nav") is not False
    ]
    depths = _depths([int(entry.get("level") or 1) for entry in visible])
    flat: list[dict[str, Any]] = []
    for entry, depth in zip(visible, depths, strict=False):
        if depth > nav_depth:
            continue
        href = f"{slug_file(entry['id'])}.xhtml"
        flat.append(
            {
                "depth": depth,
                "unit": entry["id"],
                "label": plain_label(str(entry.get("title") or entry["id"])),
                "href": href,
            }
        )
        anchors = subheading_anchors(_md(store, entry, prefer_translation), entry["id"])
        relative = _depths([int(anchor["level"]) for anchor in anchors])
        for anchor, rel in zip(anchors, relative, strict=False):
            if depth + rel > nav_depth:
                continue
            flat.append(
                {
                    "depth": depth + rel,
                    "unit": entry["id"],
                    "label": anchor["title"],
                    "href": f"{href}#{anchor['anchor']}",
                }
            )
    toc_entries = [entry for entry in visible if entry.get("kind") == "toc"]
    if toc_entries:
        labels = "\n".join(_norm(item["label"]) for item in flat)
        for label, key in _source_lines(store, toc_entries[0], prefer_translation):
            if key in labels:
                continue
            flat.append({"depth": 1, "unit": "", "label": label, "href": ""})
    return flat


def _norm(text: str) -> str:
    """独立归一化：去引导点/空白/末尾页码（与生成器算法分开实现）。"""
    value = "".join(ch for ch in str(text or "") if ch not in ".…·。．" and not ch.isspace())
    while value and value[-1].isdigit():
        value = value[:-1]
    return value


def _source_lines(store: RunStore, entry: dict[str, Any], prefer: bool) -> list[tuple[str, str]]:
    """原目录条目行：``(显示文本, 比较键)``；独立实现，避免与生成器互相背书。"""
    text = _md(store, entry, prefer)
    lines: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("#").strip()
        if not line or all(ch in ".…·。．-— " for ch in line):
            continue
        display = re.sub(r"[.…·。．]{2,}\s*\d*\s*$", "", line).strip()
        key = _norm(display)
        if key:
            lines.append((display, key))
    return lines


def _actual_toc(html: str) -> list[dict[str, Any]] | None:
    try:
        root = ET.fromstring(html)
    except ET.ParseError:
        return None
    nav = next(
        (
            node
            for node in root.iter()
            if node.tag.endswith("}nav") and node.get("data-aep") == "generated-toc"
        ),
        None,
    )
    if nav is None:
        return None
    flat: list[dict[str, Any]] = []

    def walk(ol: ET.Element, depth: int) -> None:
        for li in ol.findall(f"{_XHTML}li"):
            link = next((node for node in li.iter() if node.tag.endswith("}a")), None)
            plain = next((node for node in li.iter() if node.get("class") == "toc-plain"), None)
            if link is not None or plain is not None:
                node = link if link is not None else plain
                flat.append(
                    {
                        "depth": depth,
                        "label": "".join(node.itertext()).strip(),
                        "href": (link.get("href") or "") if link is not None else "",
                    }
                )
            child = li.find(f"{_XHTML}ol")
            if child is not None:
                walk(child, depth + 1)

    top = nav.find(f"{_XHTML}ol")
    if top is not None:
        walk(top, 1)
    return flat


def normalize_label(text: str) -> str:
    """公开的条目归一化（去引导点/空白/末尾页码）。"""
    return _norm(text)


def actual_toc(html: str) -> list[dict[str, Any]]:
    """成品目录页的公开读取口（供发布门校验链接目标）。"""
    return _actual_toc(html) or []


def check_generated_toc(
    html: str,
    expected: list[dict[str, Any]],
    *,
    pages: dict[str, str] | None = None,
) -> list[str]:
    """对账成品目录页；返回可读 findings（空 = 一致）。"""
    findings: list[str] = []
    if _BR_IN_P.search(html):
        findings.append("toc_compressed：目录被压进单个段落（<p> 内含 ≥2 个 <br/>）")
    actual = _actual_toc(html)
    if pages:
        missing = sorted({item["unit"] for item in expected if item["unit"] not in pages})
        if missing:
            findings.append(
                f"toc_missing_pages：{len(missing)}/{len({item['unit'] for item in expected})} "
                f"个条目没有页码（{'、'.join(missing[:5])}）"
            )
    if actual is None:
        findings.append("toc_generated_missing：成品没有 data-aep=generated-toc 的目录 nav")
        return findings
    if not actual and len(expected) > 10:
        findings.append(f"toc_no_links：期望 {len(expected)} 条但目录页没有内部链接")
    if len(actual) != len(expected):
        findings.append(f"toc_count：成品 {len(actual)} 条 / 期望 {len(expected)} 条")
    for index, (got, want) in enumerate(zip(actual, expected, strict=False), start=1):
        for key in ("depth", "label", "href"):
            if got[key] != want[key]:
                findings.append(f"toc_entry_{key}：第 {index} 条 {got[key]!r} ≠ 期望 {want[key]!r}")
                break
    return findings
