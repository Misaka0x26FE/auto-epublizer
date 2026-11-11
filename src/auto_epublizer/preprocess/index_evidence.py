# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""索引证据（#58/#57，只读）：条目、页码引用、源页定位与孤页候选。

只做确定性抽取，不判断索引语义、不改索引文本、不自动补页码。真实书里索引页
可能是双栏、OCR 合并或缺失文字层；证据不足显式记 ``unknown``/``missing_page``，
供 agent 回原页核证。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from auto_common.workspace import RunStore

_PAGE_SPEC = re.compile(r"^\d{1,4}(?:\s*[-–—]\s*\d{1,4})?$")
_ENTRY_PREFIX = re.compile(r"^\s*(?:[-*+•]\s*)?")
_LABEL_NORM = re.compile(r"[\W_]+", re.UNICODE)


def _normalize(text: str) -> str:
    return _LABEL_NORM.sub("", text.casefold())


def _looks_year(token: str) -> bool:
    first = re.match(r"\d+", token)
    return bool(first and len(first.group()) == 4 and int(first.group()) >= 1000)


def parse_index_line(raw: str) -> dict[str, Any] | None:
    """把一行索引拆成 ``label + page refs``；无页码引用也保留为 unresolved。

    不用“整行后缀正则”：索引行可能很长（数千字符、上百个页码），带嵌套可选的
    正则会产生灾难性回溯。这里按逗号/空白从右往左消费页码 token。
    """
    text = _ENTRY_PREFIX.sub("", raw.strip())
    if not text or text.startswith("#"):
        return None
    text = re.sub(r"\s*([-–—])\s*", r"\1", text)
    parts = [part.strip() for part in text.split(",") if part.strip()]
    refs: list[str] = []
    while parts:
        tokens = parts[-1].split()
        if (
            tokens
            and all(_PAGE_SPEC.match(token) for token in tokens)
            and not any(_looks_year(token) for token in tokens)
        ):
            refs = tokens + refs
            parts.pop()
            continue
        break
    if parts:
        tokens = parts[-1].split()
        while tokens and _PAGE_SPEC.match(tokens[-1]):
            token = tokens[-1]
            if _looks_year(token):
                break  # 年份属于条目标题
            refs.insert(0, token)
            tokens.pop()
        parts[-1] = " ".join(tokens).strip()
        if not parts[-1]:
            parts.pop()
    label = ", ".join(parts).strip(" ,;")
    if not label:
        return None
    return {
        "label": label,
        "page_refs": refs,
        "page_ranges": [_expand_range(ref) for ref in refs],
    }


def _expand_range(ref: str) -> list[int]:
    parts = [int(x) for x in re.split(r"\s*[-–—]\s*", ref)]
    if len(parts) == 2 and parts[1] < parts[0] and len(str(parts[1])) < len(str(parts[0])):
        # 索引缩写：98-9 → 99，105-6 → 106，212-13 → 213
        parts[1] = int(str(parts[0])[: -len(str(parts[1]))] + str(parts[1]))
    return parts


def _parse_entries(md: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line_no, raw in enumerate(md.splitlines(), start=1):
        item = parse_index_line(raw)
        if item is None:
            continue
        item["line"] = line_no
        entries.append(item)
    return entries


def _index_entry_lines(text: str) -> int:
    """一行本身像“标签 + 页码引用”的条目数；用于判断索引页密度。"""
    return sum(
        1
        for line in text.splitlines()
        if line.strip() and (parsed := parse_index_line(line)) and parsed["page_refs"]
    )


def _looks_index_page(text: str, titles: Sequence[str]) -> bool:
    """索引页须在版头位置出现标题行，不能只靠正文里的 “index” 字样。"""
    names = {"index", "索引", "register", "namenregister"}
    names.update(_normalize(title) for title in titles)
    names.discard("")
    head_lines = [line for line in text.splitlines() if line.strip()][:4]
    return any(_normalize(line) in names for line in head_lines)


def _is_index_page(text: str, titles: Sequence[str]) -> bool:
    # 版头标题是决定性的；正文页即使出现 “index” 字样也不会是独立标题行。
    return _looks_index_page(text, titles) and _index_entry_lines(text) >= 1


def _pdf_lines(page: Any, width: float) -> list[dict[str, Any]]:
    """逐行文本 + 几何框 + 左右栏；只在索引页调用（dict 抽取较慢）。"""
    blocks = []
    for block in page.get_text("dict").get("blocks", []):
        lines = []
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if not text:
                continue
            bbox = line.get("bbox")
            side = None
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                side = "left" if (float(bbox[0]) + float(bbox[2])) / 2 < width / 2 else "right"
            lines.append({"text": text, "bbox": list(bbox) if bbox else None, "side": side})
        if lines:
            blocks.append({"lines": lines})
    return blocks


def _pdf_pages(
    path: Path, *, titles: Sequence[str]
) -> tuple[int, list[tuple[int, str, list[dict[str, Any]]]]]:
    """返回页数 + 每页文本/行框；只对索引页做昂贵的 dict 抽取。

    真实书 300+ 页、每页 dict 约 0.3 秒；先取纯文本判页，再只对索引页取行框。
    """
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - 依赖缺失由调用方降级
        return 0, []
    with pymupdf.open(path) as doc:
        pages = []
        for page in doc:
            text = page.get_text()
            width = float(page.rect.width) or 1.0
            blocks = _pdf_lines(page, width) if _is_index_page(text, titles) else []
            pages.append((page.number + 1, text, blocks))
        return doc.page_count, pages


def _raw_pages(store: RunStore) -> tuple[int, list[tuple[int, str, list[dict[str, Any]]]]]:
    raw = store.structured_dir / "raw"
    pages = []
    maximum = 0
    for path in sorted(raw.glob("page-*.json")):
        payload = path.read_bytes()
        data = json.loads(payload)
        page = int(data.get("page_idx") or 0)
        maximum = max(maximum, page)
        blocks = []
        for block in data.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            text = str(block.get("text") or "").strip()
            if not text:
                continue
            side = (
                "left"
                if block.get("column") == 0
                else "right"
                if block.get("column") == 1
                else None
            )
            # raw 的 block 常是多行文本；拆成行才能对上索引条目。
            blocks.append(
                {
                    "lines": [
                        {"text": line, "bbox": block.get("bbox"), "side": side}
                        for line in text.splitlines()
                        if line.strip()
                    ]
                }
            )
        page_text = "\n".join(
            str(line.get("text") or "") for block in blocks for line in block.get("lines") or []
        )
        pages.append((page, page_text, blocks))
    return maximum, pages


def _page_locations(
    entries: list[dict[str, Any]],
    pages: list[tuple[int, str, list[dict[str, Any]]]],
    *,
    titles: Sequence[str],
) -> tuple[list[int], dict[str, list[dict[str, Any]]]]:
    """按“行本身像索引条目”的密度识别索引页，再记录每条目的源行定位。

    不能用“命中标签数”判页：正文提到同一术语的页会被误判成索引页。
    """
    index_pages = []
    page_entries: dict[int, list[tuple[str, dict[str, Any]]]] = {}
    for page, text, _blocks in pages:
        parsed_lines = [
            (line, parse_index_line(line)) for line in text.splitlines() if line.strip()
        ]
        if _is_index_page(text, titles):
            index_pages.append(page)
            page_entries[page] = [
                (_normalize(parsed["label"]), parsed) for _, parsed in parsed_lines if parsed
            ]
    # 以“索引页上实际出现的行”为索引，避免 entry×page×line 的三重扫描。
    locations: dict[str, list[dict[str, Any]]] = {}
    for page, _text, blocks in pages:
        if page not in page_entries:
            continue
        for block in blocks:
            for line in block.get("lines") or []:
                parsed = parse_index_line(str(line.get("text") or ""))
                key = _normalize(parsed["label"]) if parsed else ""
                if key:
                    locations.setdefault(key, []).append(
                        {
                            "page": page,
                            "bbox": line.get("bbox"),
                            "side": line.get("side"),
                        }
                    )
    by_entry: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        by_entry[str(entry["line"])] = locations.get(_normalize(entry["label"]), [])
    return index_pages, by_entry


def collect_index_evidence(store: RunStore) -> dict[str, Any]:
    """逐条索引证据：真实书优先读源 PDF 文字层，缺失时退回 raw 页。"""
    pub = store.load_publication()
    source = store.dir / pub.meta.source
    page_count = 0
    pages: list[tuple[int, str, list[dict[str, Any]]]] = []
    source_kind = "none"
    if source.is_file() and source.suffix.lower() == ".pdf":
        index_titles = [u.title for u in pub.units if u.kind == "index"]
        page_count, pages = _pdf_pages(source, titles=index_titles)
        source_kind = "pdf"
    if not pages:
        page_count, pages = _raw_pages(store)
        source_kind = "raw"
    raw_pages = {page for page, _text, _blocks in pages}
    units: list[dict[str, Any]] = []
    for unit in pub.units:
        if unit.kind != "index":
            continue
        rel = str(unit.meta.get("rel_path") or "")
        path = store.structured_dir / rel if rel else None
        if path is None or not path.is_file():
            units.append(
                {"unit": unit.id, "rel_path": rel, "status": "missing_markdown", "entries": []}
            )
            continue
        payload = path.read_bytes()
        entries = _parse_entries(payload.decode("utf-8", "replace"))
        index_pages, locations = _page_locations(entries, pages, titles=[unit.title])
        seen: dict[str, dict[str, Any]] = {}
        unresolved: list[int] = []
        orphan: list[dict[str, Any]] = []
        missing_evidence: list[dict[str, Any]] = []
        for entry in entries:
            key = _normalize(entry["label"])
            record = seen.setdefault(key, {"label": entry["label"], "lines": []})
            record["lines"].append(entry["line"])
            refs: list[int] = []
            for group in entry["page_ranges"]:
                refs.extend(group)
            if not entry["page_refs"]:
                unresolved.append(entry["line"])
            for ref in refs:
                if page_count and (ref < 1 or ref > page_count):
                    orphan.append({"line": entry["line"], "label": entry["label"], "page": ref})
                elif ref not in raw_pages and source_kind == "raw":
                    missing_evidence.append(
                        {"line": entry["line"], "label": entry["label"], "page": ref}
                    )
            entry["locations"] = locations.get(str(entry["line"]), [])
            entry["located"] = bool(entry["locations"])
        duplicates = [
            {"label": record["label"], "lines": record["lines"]}
            for label, record in sorted(seen.items())
            if label and len(record["lines"]) > 1
        ]
        sides = {
            loc.get("side") for entry in entries for loc in entry["locations"] if loc.get("side")
        }
        units.append(
            {
                "unit": unit.id,
                "rel_path": rel,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "status": "ok",
                "entries": entries,
                "entry_count": len(entries),
                "located_entries": sum(1 for entry in entries if entry["located"]),
                "unresolved_lines": unresolved,
                "orphan_page_refs": orphan,
                "missing_page_evidence": missing_evidence,
                "duplicate_labels": duplicates,
                "index_pages": index_pages,
                "two_column_index": len(sides) > 1,
            }
        )
    return {
        "schema_version": "1",
        "rule_version": "index-evidence-1",
        "source_sha256": pub.meta.source_sha256,
        "source_kind": source_kind,
        "page_count": page_count,
        "units": units,
        "note": "索引页码只作候选；孤页/缺页证据须回原页核证，工具不自动改索引",
    }
