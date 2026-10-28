# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""扫描件封面候选与确认（issue #63）：发现归发现，登记归登记。

问题：扫描 PDF 的封面通常只是第 1 页的整页位图，不是 ``cover`` 单元里的
``![…]`` 引用——build 因此没有 ``properties="cover-image"``，EPUB 在书架/锁屏
上是空白，现场只能手工 ``pdfimages`` 抽图再改包。

本模块只做两件事：

1. **只读发现** ``collect_cover_candidates``：前 3 页的 image 块，带页号、块号、
   bbox、魔数判定的真实格式与字节摘要。书名页同样是候选——「第一张图」不等于封面，
   最终由 agent 核证。
2. **确认登记** ``read_confirmed_cover``：读 ``preprocessing/cover.json``
   （``{"file": "structured/raw/media/p001-page.png", "evidence": "…"}``，两项必填、
   路径必须在 ``structured/raw`` 内且真实存在）。确认后 build 复用既有 cover-image
   路径；未确认时绝不自动把首页图当封面。

格式只按文件魔数判定，不看扩展名：OCR/渲染产物常把 JPX 存成 ``.png``。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from auto_common.workspace import RunStore

COVER_FILE = "preprocessing/cover.json"
_MAX_CANDIDATE_PAGES = 3
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")


def _magic_format(data: bytes) -> str:
    """按魔数判定位图格式；未知返回 ``unknown``（不猜扩展名）。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"\x00\x00\x00\x0cjP  ") or data.startswith(b"\xff\x4f\xff\x51"):
        return "jpeg2000"
    if data.startswith(b"\x97JB2\r\n\x1a\n"):
        return "jbig2"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if data.startswith(b"BM"):
        return "bmp"
    return "unknown"


def _media_root(store: RunStore) -> Path:
    return store.structured_dir / "raw"


def _resolve_media(store: RunStore, rel: str) -> Path | None:
    """把 raw 页里的 ``media/…`` 引用解析到 ``structured/raw`` 内；越界/缺失 → None。"""
    root = _media_root(store).resolve()
    candidate = (root / rel).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


def collect_cover_candidates(store: RunStore) -> list[dict[str, Any]]:
    """前 3 页的整页/大幅位图候选（只读；书名页与插图同样只是候选）。"""
    raw = _media_root(store)
    candidates: list[dict[str, Any]] = []
    for path in sorted(raw.glob("page-*.json"))[:_MAX_CANDIDATE_PAGES]:
        try:
            page = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(page, dict) or not isinstance(page.get("blocks"), list):
            continue
        for index, block in enumerate(page["blocks"], start=1):
            if not isinstance(block, dict) or block.get("type") != "image":
                continue
            rel = str(block.get("file") or "")
            resolved = _resolve_media(store, rel) if rel else None
            if resolved is None:
                continue
            data = resolved.read_bytes()
            candidates.append(
                {
                    "page": page.get("page_idx"),
                    "block": index,
                    "file": resolved.relative_to(store.dir.resolve()).as_posix(),
                    "insert_id": block.get("insert_id"),
                    "bbox": block.get("bbox"),
                    "method": block.get("method"),
                    "format": _magic_format(data),
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
    return candidates


def read_confirmed_cover(store: RunStore) -> dict[str, Any] | None:
    """读确认记录；未确认返回 None，记录不合格 → ``ValueError``（可预期输入错误）。"""
    path = store.dir / COVER_FILE
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{COVER_FILE} 不可读：{exc}") from None
    if not isinstance(payload, dict):
        raise ValueError(f"{COVER_FILE} 必须是对象")
    rel = str(payload.get("file") or "").strip()
    evidence = str(payload.get("evidence") or "").strip()
    if not rel or not evidence:
        raise ValueError(f"{COVER_FILE} 需要 file 与 evidence（两者必填）")
    root = _media_root(store).resolve()
    candidate = (store.dir / rel).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"封面路径越界（必须在 structured/raw 内）：{rel}")
    if not candidate.is_file():
        raise ValueError(f"封面文件不存在：{rel}")
    data = candidate.read_bytes()
    return {
        "file": rel,
        "epub_path": candidate.relative_to(root).as_posix(),
        "evidence": evidence,
        "format": _magic_format(data),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "data": data,
    }


def cover_status(store: RunStore) -> dict[str, Any]:
    """封面三态：declared / confirmed / missing / candidates / error（只读）。"""
    pub = store.load_publication()
    declared = [unit.id for unit in pub.units if unit.kind == "cover"]
    has_image = False
    for unit in pub.units:
        if unit.kind != "cover":
            continue
        rel = str((unit.meta or {}).get("rel_path") or "")
        for root in (store.structured_dir, store.translation_dir):
            path = root / rel if rel else None
            if path is None or not path.is_file():
                continue
            for match in _MD_IMAGE_RE.finditer(path.read_text(encoding="utf-8")):
                if _resolve_media(store, match.group(1)) is not None:
                    has_image = True
    status: dict[str, Any] = {
        "declared": declared,
        "has_image": has_image,
        "confirmed": None,
        "candidates": [],
        "missing": False,
        "error": None,
    }
    try:
        status["candidates"] = collect_cover_candidates(store)
        confirmed = read_confirmed_cover(store)
    except ValueError as exc:
        status["error"] = str(exc)
        status["missing"] = True
        return status
    if confirmed is not None:
        status["confirmed"] = {key: value for key, value in confirmed.items() if key != "data"}
    # 声明了 cover 单元但没有可解析图片 → 明确 missing（build 同时写 cover_without_image）
    status["missing"] = confirmed is None and (not declared or not has_image)
    return status
