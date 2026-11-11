# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""源目录 ↔ EPUB nav 逐项 diff（#58d，只读）。

只做确定性对账：把印刷目录条目与最终 EPUB 的 ``nav.xhtml`` 条目按**规范化标签**
对齐，输出 matched / printed_only / nav_only / ambiguous / href 缺失，供 agent 判断
“目录文字与导航目标是否同一套”。不按条数或标题子串猜页码，也不改写任何文件。

译文工作区优先用 ``translation/`` 的目录（目标语言），没有译文时才退回
``structured/``；两种来源都在输出里标注，避免把源语言目录和译文 nav 混为一谈。
"""

from __future__ import annotations

import hashlib
import posixpath
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from auto_common.workspace import RunStore

from ..toc_model import _PAGE_LINE

_NUMBERING = re.compile(r"^\s*(?:\d{1,3}[.．、)]|[①-⑳])\s*")
_PAGE_ONLY = re.compile(r"^\s*(?P<page>[0-9]{1,4}|[ivxlcdm]{1,8})\s*$", re.IGNORECASE)
_TRAILING = " .…·•—–-"
_QUOTES = str.maketrans("", "", "「」『』\u201c\u201d\u2018\u2019\"'")


def normalize_toc_label(text: str) -> str:
    """目录对齐口径：NFKC、去编号、去空白与尾部点线，大小写不敏感。"""
    value = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    value = _NUMBERING.sub("", value)
    value = value.strip().rstrip(_TRAILING)
    return "".join(value.split()).casefold()


def parse_printed_entries(md: str) -> list[dict[str, Any]]:
    """印刷目录逐行解析：标签、页码候选、行号；不猜层级、不补页码。"""
    entries: list[dict[str, Any]] = []
    for line_no, raw in enumerate(md.splitlines(), start=1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        match = _PAGE_LINE.match(text)
        if match is None:
            # 印刷目录常把页码单独排一行；挂到上一条，不造“条目”。
            page_only = _PAGE_ONLY.match(text)
            if page_only:
                if entries and entries[-1]["page"] is None:
                    page = page_only.group("page")
                    entries[-1]["page"] = page
                    entries[-1]["page_kind"] = "arabic" if page.isdigit() else "roman"
                continue
            label, page = text, None
        else:
            label = match.group("label").strip()
            page = match.group("page")
        if not label:
            continue
        entries.append(
            {
                "line": line_no,
                "label": label,
                "page": page,
                "page_kind": ("arabic" if page.isdigit() else "roman") if page else None,
                "indent": len(raw) - len(raw.lstrip()),
            }
        )
    return entries


def _nav_member(zf: zipfile.ZipFile) -> str | None:
    names = zf.namelist()
    if "OEBPS/nav.xhtml" in names:
        return "OEBPS/nav.xhtml"
    return next((name for name in names if name.endswith("nav.xhtml")), None)


def parse_nav_entries(epub: Path) -> dict[str, Any]:
    """读 EPUB nav：有序条目、层级、href、重复标签与缺失成员。"""
    from lxml import etree

    with zipfile.ZipFile(epub) as zf:
        member = _nav_member(zf)
        if member is None:
            return {
                "epub": str(epub),
                "nav_member": None,
                "entries": [],
                "href_missing": [],
            }
        names = set(zf.namelist())
        payload = zf.read(member)
    root = etree.fromstring(payload)
    entries: list[dict[str, Any]] = []
    href_missing: list[str] = []
    for nav in root.iter():
        if etree.QName(nav).localname != "nav":
            continue
        if nav.get("{http://www.idpf.org/2007/ops}type") != "toc":
            continue
        for link in nav.iter():
            if etree.QName(link).localname != "a":
                continue
            href = link.get("href") or ""
            level = sum(
                1 for parent in link.iterancestors() if etree.QName(parent).localname == "ol"
            )
            label = "".join(link.itertext()).strip()
            target = unquote(urlsplit(href).path)
            file_member = posixpath.normpath(posixpath.join(posixpath.dirname(member), target))
            if target and file_member not in names:
                href_missing.append(href)
            entries.append(
                {
                    "index": len(entries) + 1,
                    "level": max(level, 1),
                    "label": label,
                    "href": href,
                    "file": file_member if target else member,
                    "file_present": (file_member in names) if target else True,
                }
            )
        break
    return {
        "epub": str(epub),
        "nav_member": member,
        "nav_sha256": hashlib.sha256(payload).hexdigest(),
        "entries": entries,
        "href_missing": href_missing,
    }


def _printed_path(store: RunStore) -> tuple[str, str] | None:
    """优先译文目录，其次结构化目录；返回 (kind, rel_path)。"""
    pub = store.load_publication()
    candidates: list[tuple[str, str]] = []
    for unit in pub.units:
        if unit.kind != "toc":
            continue
        rel = str((unit.meta or {}).get("rel_path") or "")
        if not rel:
            continue
        if (store.translation_dir / rel).is_file():
            candidates.append(("translation", rel))
        elif (store.structured_dir / rel).is_file():
            candidates.append(("structured", rel))
    return candidates[0] if candidates else None


def collect_toc_diff(store: RunStore, *, epub: str | Path | None = None) -> dict[str, Any]:
    """印刷目录 ↔ nav 逐项对账；只读，缺 epub/nav 时显式 unknown。"""
    pub = store.load_publication()
    printed_source = _printed_path(store)
    printed: list[dict[str, Any]] = []
    printed_md = ""
    printed_rel = None
    printed_kind = None
    if printed_source is not None:
        printed_kind, printed_rel = printed_source
        base = store.translation_dir if printed_kind == "translation" else store.structured_dir
        printed_md = (base / printed_rel).read_text(encoding="utf-8")
        printed = parse_printed_entries(printed_md)

    epub_path = Path(epub) if epub else store.dir / "output" / f"{pub.slug}.epub"
    nav = (
        parse_nav_entries(epub_path)
        if epub_path.is_file()
        else {"epub": str(epub_path), "nav_member": None, "entries": [], "href_missing": []}
    )
    nav_entries: list[dict[str, Any]] = nav["entries"]

    by_label: dict[str, list[int]] = {}
    for entry in nav_entries:
        key = normalize_toc_label(entry["label"])
        if key:
            by_label.setdefault(key, []).append(entry["index"])

    matched_nav: set[int] = set()
    duplicate_nav: list[dict[str, Any]] = []
    for key, indexes in sorted(by_label.items()):
        if len(indexes) > 1:
            duplicate_nav.append({"key": key, "nav_indexes": indexes})

    for entry in printed:
        key = normalize_toc_label(entry["label"])
        hits = by_label.get(key, [])
        entry["key"] = key
        if len(hits) == 1:
            entry["match"] = "matched"
            entry["nav_index"] = hits[0]
            matched_nav.add(hits[0])
        elif len(hits) > 1:
            entry["match"] = "ambiguous"
            entry["nav_indexes"] = hits
        else:
            entry["match"] = "printed_only"
            entry["nav_index"] = None

    nav_only = [entry for entry in nav_entries if entry["index"] not in matched_nav]
    counts = {
        "printed": len(printed),
        "nav": len(nav_entries),
        "matched": sum(1 for entry in printed if entry["match"] == "matched"),
        "printed_only": sum(1 for entry in printed if entry["match"] == "printed_only"),
        "ambiguous": sum(1 for entry in printed if entry["match"] == "ambiguous"),
        "nav_only": len(nav_only),
        "duplicate_nav_labels": len(duplicate_nav),
        "href_missing": len(nav.get("href_missing") or []),
    }
    status = "ok"
    reason = None
    if printed_rel is None:
        status, reason = "unknown", "printed_toc_missing"
    elif not nav_entries:
        status, reason = "unknown", "epub_nav_missing"
    return {
        "schema_version": "1",
        "rule_version": "toc-diff-1",
        "writes": False,
        "status": status,
        "reason": reason,
        "source_sha256": pub.meta.source_sha256,
        "printed": {
            "kind": printed_kind,
            "rel_path": printed_rel,
            "sha256": hashlib.sha256(printed_md.encode()).hexdigest() if printed_md else None,
            "entries": printed,
        },
        "nav": {
            "epub": nav.get("epub"),
            "member": nav.get("nav_member"),
            "sha256": nav.get("nav_sha256"),
            "entries": nav_entries,
            "href_missing": nav.get("href_missing") or [],
        },
        "nav_only": [
            {
                "index": entry["index"],
                "level": entry["level"],
                "label": entry["label"],
                "href": entry["href"],
            }
            for entry in nav_only
        ],
        "duplicates": duplicate_nav,
        "counts": counts,
        "note": "逐项对齐按规范化标签；nav 多出的结构项与标题改写都只报证据，不自动改目录",
    }
