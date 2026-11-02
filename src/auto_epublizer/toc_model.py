# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""目录来源身份模型（D1，只读）：结构视图 + 原版目录行去向。

两个来源必须分开：

- **结构视图**（``nodes``）：由单元树与单元内子标题锚点生成，带父节点、顺序、标签和
  完整 ``href#fragment``；这是可点击目录的目标身份，不是原文段落。
- **原版目录文本**（``original``）：目录单元逐行的标签、页码候选、行号与源摘要；每条
  只做**完全同名**匹配（单元标题或子标题锚点），匹配不到/多义就记 unresolved/ambiguous，
  不按 ``§`` 字样自动造标题，也不猜页码。

页码策略只从 ``preprocessing/page_numbers.csv`` 读取并标注消费位置；未声明不等于
``original``。模块不写任何文件，生成目录页是 D2 的事。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from auto_common.workspace import RunStore

from .build.html import plain_label, slug_file, subheading_anchors
from .preprocess.artifacts import read_page_number_policies

_PAGE_LINE = re.compile(
    r"^\s*(?P<label>.{1,200}?)[\s.…·•—–-]+(?P<page>[0-9]{1,4}|[ivxlcdm]{1,8})\s*$",
    re.IGNORECASE,
)


def _page_kind(page: str) -> str:
    return "arabic" if page.isdigit() else "roman"


def _destination_index(nodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        key = plain_label(node["label"])
        if key:
            index.setdefault(key, []).append(
                {"kind": "unit", "unit": node["unit"], "href": node["href"]}
            )
        for anchor in node.get("anchors") or []:
            key = plain_label(anchor["label"])
            if key:
                index.setdefault(key, []).append(
                    {"kind": "anchor", "unit": node["unit"], "href": anchor["href"]}
                )
    return index


def _parse_original(lines: list[str], node_index: dict[str, list[dict[str, Any]]]) -> list[dict]:
    entries: list[dict[str, Any]] = []
    for line_no, raw in enumerate(lines, start=1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        match = _PAGE_LINE.match(text)
        label = (match.group("label") if match else text).strip()
        page = match.group("page") if match else None
        candidates = node_index.get(plain_label(label), [])
        entry: dict[str, Any] = {
            "line": line_no,
            "text": text,
            "label": label,
            "page": page,
            "page_kind": _page_kind(page) if page else None,
            "destination": None,
            "match": "unresolved",
            "candidates": candidates[:5],
        }
        if len(candidates) == 1:
            entry["destination"] = candidates[0]
            entry["match"] = "unit_exact" if candidates[0]["kind"] == "unit" else "anchor_exact"
        elif len(candidates) > 1:
            entry["match"] = "ambiguous"
        elif plain_label(label).startswith("§"):
            entry["match"] = "section_anchor_absent"
        entries.append(entry)
    return entries


def build_toc_model(store: RunStore) -> dict[str, Any]:
    """构建只读目录来源模型；不写文件、不改单元。"""
    pub = store.load_publication()
    policies = read_page_number_policies(store)
    nodes: list[dict[str, Any]] = []
    stack: list[tuple[int, str]] = []
    for order, unit in enumerate(pub.units, start=1):
        rel = str((unit.meta or {}).get("rel_path") or "")
        level = int((unit.meta or {}).get("level") or 1)
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else None
        stack.append((level, unit.id))
        md = ""
        path = store.structured_dir / rel if rel else None
        if path is not None and path.is_file():
            md = path.read_text(encoding="utf-8")
        href = f"{slug_file(unit.id)}.xhtml"
        anchors = [
            {"label": item["title"], "level": item["level"], "href": f"{href}#{item['anchor']}"}
            for item in subheading_anchors(md, unit.id)
        ]
        nodes.append(
            {
                "unit": unit.id,
                "kind": unit.kind,
                "region": (unit.meta or {}).get("region"),
                "order": order,
                "level": level,
                "parent": parent,
                "label": unit.title,
                "href": href,
                "anchors": anchors,
                "in_nav": bool((unit.meta or {}).get("nav", True)) and unit.kind != "cover",
            }
        )
    node_index = _destination_index(nodes)
    original: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for unit in pub.units:
        if unit.kind != "toc":
            continue
        rel = str((unit.meta or {}).get("rel_path") or "")
        path = store.structured_dir / rel if rel else None
        if path is None or not path.is_file():
            continue
        payload = path.read_bytes()
        entries = _parse_original(payload.decode("utf-8", "replace").splitlines(), node_index)
        digest = hashlib.sha256(payload).hexdigest()
        policy = policies.get(unit.id)
        for entry in entries:
            if entry["destination"] is None:
                unresolved.append(
                    {
                        "unit": unit.id,
                        "line": entry["line"],
                        "label": entry["label"],
                        "page": entry["page"],
                        "reason": entry["match"],
                    }
                )
        original.append(
            {
                "unit": unit.id,
                "rel_path": rel,
                "sha256": digest,
                "entries": entries,
                "page_policy": policy["policy"] if policy else None,
                "page_reason": policy["reason"] if policy else "",
                # 策略消费位置：original 才允许显示原书页码；product 需要映射证据；
                # none/未声明一律留空，不冒充 original。
                "page_display": "original" if policy and policy["policy"] == "original" else None,
            }
        )
    return {
        "schema_version": "1",
        "writes": False,
        "source_sha256": pub.meta.source_sha256,
        "nodes": nodes,
        "original": original,
        "unresolved": unresolved,
        "note": "结构视图与原版目录文本分开；只有完全同名才绑定目标，§ 不自动生成标题锚点",
    }
