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


def _resolve_epub_path(store: Any, epub_path: str | Path | None) -> Path:
    """成品路径归一（P2：相对路径相对 ``store.dir`` 解析，外部路径存绝对）。

    评审复现：QA 保存相对 EPUB 路径后，切换 cwd 会让**未变的产物**被误判 stale。
    规则：工作区内的路径一律用相对 ``store.dir`` 的规范形式参与摘要；工作区外的
    成品用规范化绝对路径（摘要只吃内容，路径字符串仅用于定位文件）。
    """
    if not epub_path:
        return store.output_dir / f"{store.load_publication().slug}.epub"
    p = Path(epub_path)
    if not p.is_absolute():
        p = store.dir / p
    return p


def artifacts_digest(store: Any, *, epub_path: str | Path | None = None) -> str:
    """当前产物集合的内容摘要（确定性；与 report.json 里记录的值比对判定过期）。

    覆盖**全部放行输入**（P1 漏门修复）：按 publication **发布顺序**（不再按 id 排序，
    排序会抹去单元顺序）编码单元发布描述 + structured/translation/align 内容 + 注释
    文件 + 放行输入的预处理产物（`catalog.csv`/`repairs.jsonl`）+ 最新审校 result.json
    + 实际源件字节 + 成品字节。
    """
    pub = store.load_publication()
    h = hashlib.sha256()
    h.update(f"src:{pub.meta.source_sha256}\n".encode())
    # 实际源身份：文件字节哈希（meta 声明与磁盘不一致时摘要必然不同）
    src_rel = str(getattr(pub.meta, "source", "") or "")
    src_path = store.dir / src_rel if src_rel else None
    h.update(b"srcfile:")
    if src_path is not None and src_path.is_file():
        h.update(_file_sha256(src_path).encode())
    h.update(b"\n")
    for unit in pub.units:  # 发布顺序，不排序
        meta = unit.meta or {}
        rel = meta.get("rel_path") or ""
        h.update(
            f"unit:{unit.id}:{meta.get('region', '')}:{unit.kind}:"
            f"{meta.get('level', '')}:{rel}:{unit.title}\n".encode()
        )
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
    # 放行硬门输入（F2）：注释契约、源盘点/整备、术语表与冲突账本——
    # 漏一项就会出现「摘要未变但重跑 qa 变 released=False」的假有效报告。
    for extra in (
        "structured/notes.json",
        "translation/notes.json",
        "preprocessing/catalog.csv",
        "preprocessing/repairs.jsonl",
        "preprocessing/facts.json",
        "analysis/glossary.csv",
        "analysis/glossary_conflicts.jsonl",
    ):
        path = store.dir / extra
        h.update(f"{extra}:".encode())
        if path.is_file():
            h.update(_file_sha256(path).encode())
        h.update(b"\n")
    # 注释登记绑定状态（登记摘要决定成品注释门与译注要求，F2）
    h.update(b"notes_summary:")
    h.update(json.dumps(getattr(pub, "notes", None), ensure_ascii=False, sort_keys=True).encode())
    h.update(b"\n")
    # inserts：单文件内容 + 引用资源存在性（E_INSERT_MISSING_FILE 的真实输入，F2）
    inserts_dir = store.structured_dir / "raw" / "inserts"
    if inserts_dir.is_dir():
        raw_dir = store.structured_dir / "raw"
        for ins in sorted(inserts_dir.glob("*.json")):
            h.update(f"insert:{ins.name}:".encode())
            h.update(_file_sha256(ins).encode())
            try:
                record = json.loads(ins.read_text(encoding="utf-8"))
                ref = str((record or {}).get("file") or "")
            except (OSError, json.JSONDecodeError):
                ref = ""
            if ref:
                exists = (raw_dir / ref).is_file()
                h.update(b":file:" + (b"1" if exists else b"0"))
            h.update(b"\n")
    review_path = latest_review_result_path(store)
    h.update(b"review:")
    if review_path is not None:
        h.update(_file_sha256(review_path).encode())
    h.update(b"\n")
    epub = _resolve_epub_path(store, epub_path)
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
