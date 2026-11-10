# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""源文件路径与成品 URL 的独立身份域；不读取资源字节、不参与渲染。

路径解析分三级，且**调用方显式选择**：

- ``exact``：原相对路径与重复根前缀（可证明的身份）；
- ``basename``：旧工作区的兼容兜底（同名不同目录可能错配，**不得用于交付对账**）；
- 显式映射：``preprocessing/media-map.json`` 逐条声明 ref → 根内成员、理由与摘要，
  用于确实无法从字形路径还原的旧绝对路径。

交付对账（QA/注文门）只用 exact + 显式映射；构建期允许 basename 兼容，但错配风险
由交付门暴露，而不是被 basename 静默吸收。
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

MEDIA_MAP_REL = Path("preprocessing") / "media-map.json"
MEDIA_MAP_SCHEMA = 1
_SHA256_RE = r"^[0-9a-f]{64}$"


@dataclass(frozen=True)
class MediaResolution:
    """一次成功定位：文件、策略（exact/root-prefix/basename/mapped）与原引用。"""

    path: Path
    strategy: str
    ref: str

    def member(self, media_root: Path) -> str:
        root = media_root.resolve()
        return f"media/{self.path.resolve().relative_to(root).as_posix()}"


def _candidates(ref: str, root: Path) -> list[tuple[str, str]]:
    """按身份强度返回候选（相对路径，策略）。"""
    rel = ref.strip().lstrip("/")
    candidates: list[tuple[str, str]] = [(rel, "exact")]
    parts = Path(rel).parts
    for size in range(1, len(parts)):
        if parts[:size] == root.parts[-size:]:
            candidates.append((str(Path(*parts[size:])), "root-prefix"))
            break
    return candidates


def resolve_media(
    ref: str, media_root: Path, *, allow_basename: bool = False
) -> MediaResolution | None:
    """定位根内真实文件；``allow_basename`` 只给构建期兼容旧路径。"""
    root = media_root.resolve()
    for candidate, strategy in _candidates(ref, root):
        try:
            resolved = (root / candidate).resolve()
            if resolved.is_relative_to(root) and resolved.is_file():
                return MediaResolution(resolved, strategy, ref)
        except (OSError, ValueError):
            continue
    if allow_basename:
        name = Path(ref.strip().lstrip("/")).name
        if name:
            try:
                resolved = (root / name).resolve()
                if resolved.is_relative_to(root) and resolved.is_file():
                    return MediaResolution(resolved, "basename", ref)
            except (OSError, ValueError):
                return None
    return None


def resolve_media_path(ref: str, media_root: Path, *, allow_basename: bool = True) -> Path | None:
    """兼容入口：默认保留 basename 兜底（构建期旧路径）；对账请传 False。"""
    found = resolve_media(ref, media_root, allow_basename=allow_basename)
    return found.path if found else None


@dataclass(frozen=True)
class MediaMapEntry:
    ref: str
    member: str
    reason: str
    sha256: str | None = None


@dataclass
class MediaMap:
    """显式迁移映射；``findings`` 是契约/身份问题（不静默丢弃坏条目）。"""

    entries: dict[str, MediaMapEntry] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    path: Path | None = None

    def resolve(self, ref: str, media_root: Path) -> MediaResolution | None:
        entry = self.entries.get(ref)
        if entry is None:
            return None
        root = media_root.resolve()
        try:
            path = (root / entry.member).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                return None
        except (OSError, ValueError):
            return None
        if entry.sha256 and _file_sha256(path) != entry.sha256:
            return None
        return MediaResolution(path, "mapped", ref)


class MediaMapError(ValueError):
    """media-map.json 的契约错误（用户可预期，CLI 以中文提示）。"""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_media_map(store_dir: str | Path) -> MediaMap:
    """读取并校验 ``preprocessing/media-map.json``；缺失时返回空映射。"""
    path = Path(store_dir) / MEDIA_MAP_REL
    if not path.is_file():
        return MediaMap()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MediaMapError(f"无法读取媒体映射 {path}：{exc}") from None
    if not isinstance(data, dict) or data.get("schema") != MEDIA_MAP_SCHEMA:
        raise MediaMapError(f"媒体映射 {path} 的 schema 必须是 {MEDIA_MAP_SCHEMA}")
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        raise MediaMapError(f"媒体映射 {path} 缺少 entries 列表")
    media_root = (Path(store_dir) / "structured" / "raw" / "media").resolve()
    result = MediaMap(path=path)
    for position, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            result.findings.append(f"entries[{position}] 不是对象")
            continue
        ref = str(raw.get("ref") or "").strip()
        member = str(raw.get("member") or "").strip().replace("\\", "/")
        reason = str(raw.get("reason") or "").strip()
        sha = str(raw.get("sha256") or "").strip().lower() or None
        if not ref or not member:
            result.findings.append(f"entries[{position}] 缺 ref/member")
            continue
        if not reason:
            result.findings.append(f"entries[{position}]（{ref}）缺 reason")
            continue
        if sha is not None and not re.fullmatch(_SHA256_RE, sha):
            result.findings.append(f"entries[{position}]（{ref}）的 sha256 格式错误")
            continue
        pure = PurePosixPath(member)
        if pure.is_absolute() or any(part == ".." for part in pure.parts):
            result.findings.append(f"entries[{position}]（{ref}）的 member 越界")
            continue
        if ref in result.entries:
            result.findings.append(f"媒体映射 ref 重复：{ref}")
            continue
        entry = MediaMapEntry(ref, member, reason, sha)
        target = media_root / member
        if not target.is_file():
            result.findings.append(f"媒体映射目标不存在：{ref} → {member}")
        elif sha and _file_sha256(target) != sha:
            result.findings.append(f"媒体映射摘要不匹配：{ref} → {member}")
        else:
            result.entries[ref] = entry
    return result


def resolve_audit_media(
    ref: str, media_root: Path, media_map: MediaMap | None = None
) -> MediaResolution | None:
    """交付对账专用：exact/root-prefix，或显式映射；绝不 basename 兜底。"""
    found = resolve_media(ref, media_root, allow_basename=False)
    if found is not None:
        return found
    if media_map is not None:
        return media_map.resolve(ref, media_root)
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
