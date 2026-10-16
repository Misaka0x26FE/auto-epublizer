# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""源文件路径与成品 URL 的独立身份域；不读取资源字节、不参与渲染。"""

from __future__ import annotations

import posixpath
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urlsplit


def resolve_media_path(ref: str, media_root: Path) -> Path | None:
    """按原路径、重复根前缀、basename 顺序定位根内真实文件。"""
    root = media_root.resolve()
    rel = ref.strip().lstrip("/")
    candidates = [rel]
    parts = Path(rel).parts
    for size in range(1, len(parts)):
        if parts[:size] == root.parts[-size:]:
            candidates.append(str(Path(*parts[size:])))
            break
    candidates.append(Path(rel).name)
    for candidate in candidates:
        try:
            resolved = (root / candidate).resolve()
            if resolved.is_relative_to(root) and resolved.is_file():
                return resolved
        except (OSError, ValueError):
            continue
    return None


def epub_member_path(document: str, href: str) -> str | None:
    """把文档内 URL 解码一次为 ZIP 字面成员；不接受外链或包外路径。"""
    try:
        url = urlsplit(unescape(href))
        path = unquote(url.path)
    except ValueError:
        return None
    if url.scheme or url.netloc or path.startswith("/"):
        return None
    member = (
        posixpath.normpath(posixpath.join(posixpath.dirname(document), path)) if path else document
    )
    return None if member == ".." or member.startswith("../") else member
