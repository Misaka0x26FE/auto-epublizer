# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""报告失效证据链（B2）：产物摘要与「旧报告不再代表当前产物」的判定。

``report.json`` 记录生成时刻的 ``artifacts_digest``（源哈希 + 每单元
structured/translation/align 内容 + 注释文件 + 最新审校 result.json + 成品 EPUB 字节）
与 ``artifacts_epub``（实际被审计的成品路径，兼容 ``-bi.epub``）。

任何一处产物变化 → 摘要不再匹配 → ``status``/``status_all``/``ledger`` 把旧报告的
放行结论视为**过期**（降级为 ``built_not_released``，附 ``report_stale``），须重跑
``build``/``qa`` 才恢复；不靠用户记忆「qa 后别再改文件」。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest_review_result_path(store: Any) -> Path | None:
    """最新一次审校的 result.json（目录名时间戳可排序；无则 None）。"""
    reviews = store.reviews_dir
    if not reviews.is_dir():
        return None
    candidates = sorted(reviews.glob("review-*/result.json"))
    return candidates[-1] if candidates else None


def artifacts_digest(store: Any, *, epub_path: str | Path | None = None) -> str:
    """当前产物集合的内容摘要（确定性；与 report.json 里记录的值比对判定过期）。"""
    pub = store.load_publication()
    h = hashlib.sha256()
    h.update(f"src:{pub.meta.source_sha256}\n".encode())
    for unit in sorted(pub.units, key=lambda u: u.id):
        rel = (unit.meta or {}).get("rel_path") or ""
        pairs: list[tuple[str, Path | None]] = [
            ("structured", store.structured_dir / rel if rel else None),
            ("translation", store.translation_dir / rel if rel else None),
            ("align", store.unit_align_path(unit.id)),
        ]
        for kind, path in pairs:
            h.update(f"{unit.id}:{kind}:".encode())
            if path is not None and path.is_file():
                h.update(_file_sha256(path).encode())
            h.update(b"\n")
    for extra in ("structured/notes.json", "translation/notes.json"):
        path = store.dir / extra
        h.update(f"{extra}:".encode())
        if path.is_file():
            h.update(_file_sha256(path).encode())
        h.update(b"\n")
    review_path = latest_review_result_path(store)
    h.update(b"review:")
    if review_path is not None:
        h.update(_file_sha256(review_path).encode())
    h.update(b"\n")
    epub = Path(epub_path) if epub_path else store.output_dir / f"{pub.slug}.epub"
    h.update(b"epub:")
    if epub.is_file():
        h.update(_file_sha256(epub).encode())
    h.update(b"\n")
    return h.hexdigest()


def report_state(store: Any) -> dict[str, Any]:
    """读取现有 report.json 并判定是否过期（只读；无报告返回 released=None）。"""
    path = store.report_path
    if not path.is_file():
        return {"exists": False, "released": None, "stale": False, "reason": None}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"exists": True, "released": None, "stale": True, "reason": "report_unreadable"}
    released = report.get("released")
    recorded = str(report.get("artifacts_digest") or "")
    if not released:
        return {
            "exists": True,
            "released": released,
            "stale": False,
            "reason": report.get("released_reason"),
        }
    if not recorded:
        # 旧格式报告（无摘要）：无法证明仍对应当前产物 → 视为过期（保守）
        return {"exists": True, "released": released, "stale": True, "reason": "digest_missing"}
    epub = report.get("artifacts_epub") or None
    current = artifacts_digest(store, epub_path=epub)
    if current != recorded:
        return {"exists": True, "released": released, "stale": True, "reason": "artifacts_changed"}
    return {
        "exists": True,
        "released": released,
        "stale": False,
        "reason": report.get("released_reason"),
    }
