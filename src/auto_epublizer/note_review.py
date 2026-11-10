# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""注文语言候选与逐条处置（C2/C3）。

机器只做确定性预筛：目标缺失、与源逐字相同、目标语言为中文但无汉字。
这些信号**不是**「未译」证明（纯著录、拉丁书名、URL/DOI、整段外文引文都可能合法），
必须由 agent 逐条给出 ``disposition`` 与理由；未闭合候选在交付门阻断放行。

处置绑定 ``note_id + 源文摘要 + 目标摘要``：任一摘要变化即失效重开，防止改了译文
仍沿用旧结论。产物是 ``preprocessing/note-review.json``，不写入 translation/notes.json。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from auto_common.workspace import RunStore

from .notes import read_notes_json

SCHEMA_VERSION = 1
RULE_VERSION = "notes-language-1"
DISPOSITIONS = ("translated", "retain_original")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def review_path(store: RunStore) -> Path:
    return store.preprocessing_dir / "note-review.json"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _sha(text: str) -> str:
    return hashlib.sha256(_norm(text).encode("utf-8")).hexdigest()


def _read_optional(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = read_notes_json(path)
    return data if isinstance(data, dict) else {}


def _signals(source_md: str, target_md: str, target_language: str) -> list[str]:
    signals: list[str] = []
    if source_md.strip() and not target_md.strip():
        signals.append("missing_target")
    if source_md.strip() and _norm(source_md) == _norm(target_md):
        signals.append("identical_to_source")
    if target_language.lower().startswith("zh") and target_md.strip():
        latin = sum(1 for char in target_md if char.isascii() and char.isalpha())
        cjk = len(_CJK.findall(target_md))
        if latin and not cjk:
            signals.append("no_target_script")
        elif latin >= 3 and cjk / (latin + cjk) < 0.5:
            # 照搬原文后补一两个汉字仍需核证：目标文字主体不是中文。
            signals.append("low_target_script")
    return signals


def _valid_disposition(entry: dict[str, Any]) -> bool:
    disposition = str(entry.get("disposition") or "")
    if disposition not in DISPOSITIONS:
        return False
    if not str(entry.get("reason") or "").strip():
        return False
    # 有风险信号却宣布「已译」是自相矛盾，必须给出保留/重译判断。
    return not (disposition == "translated" and entry.get("signals"))


def collect_review(store: RunStore) -> dict[str, Any]:
    """扫描登记注文并保留仍有效的处置；不修改 notes.json。"""
    source = _read_optional(store.structured_dir / "notes.json")
    target = _read_optional(store.translation_dir / "notes.json")
    target_language = str(store.load_publication().meta.target_language or "zh-CN")
    target_by_id = {
        str(n.get("note_id")): n
        for n in (target.get("notes") or [])
        if isinstance(n, dict) and n.get("note_id")
    }
    previous = _read_optional(review_path(store))
    previous_entries = {
        str(e.get("note_id")): e
        for e in (previous.get("entries") or [])
        if isinstance(e, dict) and e.get("note_id")
    }
    entries: list[dict[str, Any]] = []
    for note in source.get("notes") or []:
        if not isinstance(note, dict) or not note.get("note_id"):
            continue
        note_id = str(note["note_id"])
        source_md = str(note.get("source_markdown") or "")
        target_md = str((target_by_id.get(note_id) or {}).get("target_markdown") or "")
        signals = _signals(source_md, target_md, target_language)
        source_sha = _sha(source_md)
        target_sha = _sha(target_md)
        entry: dict[str, Any] = {
            "note_id": note_id,
            "rule_version": RULE_VERSION,
            "signals": signals,
            "source_sha256": source_sha,
            "target_sha256": target_sha,
            "disposition": None,
            "reason": "",
            "evidence": "",
            "stale": False,
        }
        prior = previous_entries.get(note_id)
        if prior is not None:
            same = (
                prior.get("source_sha256") == source_sha
                and prior.get("target_sha256") == target_sha
                and prior.get("rule_version") == RULE_VERSION
            )
            if same:
                entry["disposition"] = prior.get("disposition")
                entry["reason"] = prior.get("reason") or ""
                entry["evidence"] = prior.get("evidence") or ""
            elif prior.get("disposition"):
                entry["stale"] = True
        entries.append(entry)
    present = {e["note_id"] for e in entries}
    unknown = sorted(set(previous_entries) - present)
    return {
        "schema": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "target_language": target_language,
        "source_notes_sha256": hashlib.sha256(
            (store.structured_dir / "notes.json").read_bytes()
        ).hexdigest()
        if (store.structured_dir / "notes.json").is_file()
        else None,
        "target_notes_sha256": hashlib.sha256(
            (store.translation_dir / "notes.json").read_bytes()
        ).hexdigest()
        if (store.translation_dir / "notes.json").is_file()
        else None,
        "entries": entries,
        "unknown_note_ids": unknown,
    }


def write_review(store: RunStore) -> tuple[dict[str, Any], Path]:
    payload = collect_review(store)
    path = review_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return payload, path


def _detected_source_language(store: RunStore, pub: Any) -> str:
    lang = str(getattr(pub.meta, "language", "") or "").strip()
    if lang and lang.lower() != "auto":
        return lang
    for unit in pub.units:
        rel = str((unit.meta or {}).get("rel_path") or "")
        path = store.structured_dir / rel if rel else None
        if path is None or not path.is_file():
            continue
        try:
            sample = path.read_text(encoding="utf-8", errors="ignore")[:4000]
        except OSError:
            continue
        if sample.strip():
            from auto_translator.analysis.detect import detect_source_language

            return detect_source_language(sample)
    return ""


def summarize(store: RunStore) -> dict[str, Any]:
    """交付门视角：适用性、未闭合候选、过期处置与规则版本。"""
    source_path = store.structured_dir / "notes.json"
    if not source_path.is_file():
        return {"applicable": False, "status": "no_notes_registry", "total": 0, "open": 0}
    source = _read_optional(source_path)
    inventory = str(source.get("inventory") or "")
    notes = [n for n in (source.get("notes") or []) if isinstance(n, dict)]
    if not notes:
        return {"applicable": False, "status": "no_registered_notes", "total": 0, "open": 0}
    pub = store.load_publication()
    source_lang = _detected_source_language(store, pub).split("-")[0].lower()
    target_lang = str(pub.meta.target_language or "zh-CN").split("-")[0].lower()
    if source_lang and source_lang == target_lang:
        # 同语种无需翻译语言核验（校对仍由审校负责）
        return {"applicable": False, "status": "same_language", "total": len(notes), "open": 0}
    if inventory != "present":
        ids = [str(n.get("note_id")) for n in notes if n.get("note_id")]
        return {
            "applicable": True,
            "status": "inventory_unverified",
            "total": len(notes),
            "open": len(ids),
            "open_note_ids": ids,
            "reason": "structured/notes.json 的 inventory 不是 present，注文集合未核证",
        }
    path = review_path(store)
    if not path.is_file():
        ids = [str(n.get("note_id")) for n in notes if n.get("note_id")]
        return {
            "applicable": True,
            "status": "not_run",
            "total": len(notes),
            "open": len(notes),
            "open_note_ids": ids,
            "reason": "缺 preprocessing/note-review.json（先运行 notes review）",
        }
    try:
        review = _read_optional(path)
    except ValueError as exc:
        return {
            "applicable": True,
            "status": "invalid",
            "total": len(notes),
            "open": len(notes),
            "reason": str(exc),
        }
    if not isinstance(review, dict) or review.get("schema") != SCHEMA_VERSION:
        return {
            "applicable": True,
            "status": "invalid",
            "total": len(notes),
            "open": len(notes),
            "reason": "note-review.json schema 不是 1",
        }
    if review.get("rule_version") != RULE_VERSION:
        return {
            "applicable": True,
            "status": "stale_rule",
            "total": len(notes),
            "open": len(notes),
            "reason": f"规则版本 {review.get('rule_version')!r} 不是 {RULE_VERSION!r}，需重跑 notes review",
        }
    current = collect_review(store)
    open_ids: list[str] = []
    stale_ids: list[str] = []
    for entry in current["entries"]:
        if not entry["signals"]:
            continue
        if entry["stale"]:
            stale_ids.append(entry["note_id"])
        if not _valid_disposition(entry):
            open_ids.append(entry["note_id"])
    return {
        "applicable": True,
        "status": "ok" if not open_ids else "open",
        "rule_version": review.get("rule_version"),
        "total": len(notes),
        "candidates": sum(1 for e in current["entries"] if e["signals"]),
        "open": len(open_ids),
        "open_note_ids": open_ids,
        "stale": len(stale_ids),
        "stale_note_ids": stale_ids,
        "unknown_note_ids": current.get("unknown_note_ids") or [],
    }
