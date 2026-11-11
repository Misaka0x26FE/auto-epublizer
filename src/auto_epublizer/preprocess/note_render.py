# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""按需源页裁剪图与审阅状态（#72-1，显式写入）。

只在用户显式请求时渲染注文所在页的局部图，默认不生成全页/全书画像；默认单次
最多 200 张（``max_crops``），可调低不可无限增长。账本
``preprocessing/notes-render.json`` 记录页/框/图摘要/审阅状态：

- 同一注文、同一图摘要重跑 → 复用图片并保留 ``reviewed``；
- 重新渲染导致图摘要变化 → ``reviewed`` 归零（旧审阅不再代表新图）；
- 无 PDF、无 bbox、页码缺失分别记 ``source_missing``/``page_only``/``missing_page``。

模块不判断注文语义，也不改写 ``structured/notes.json``。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from auto_common.workspace import RunStore

RULE_VERSION = "notes-render-1"
DEFAULT_MAX_CROPS = 200


def ledger_path(store: RunStore) -> Path:
    return store.preprocessing_dir / "notes-render.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _source_pdf(store: RunStore) -> Path | None:
    source = store.dir / store.load_publication().meta.source
    return source if source.is_file() and source.suffix.lower() == ".pdf" else None


def _notes(store: RunStore) -> list[dict[str, Any]]:
    path = store.structured_dir / "notes.json"
    if not path.is_file():
        raise ValueError("structured/notes.json 不存在（先运行 notes register）")
    data = _read_json(path)
    notes = data.get("notes")
    if not isinstance(notes, list):
        raise ValueError("structured/notes.json 的 notes 必须是数组")
    return [note for note in notes if isinstance(note, dict)]


def _first_box(note: dict[str, Any]) -> tuple[int | None, list[float] | None]:
    best_page: int | None = None
    best_box: list[float] | None = None
    for location in note.get("source_locations") or []:
        if not isinstance(location, dict):
            continue
        page = location.get("page")
        box = location.get("bbox")
        if best_page is None and isinstance(page, int):
            best_page = page
        if best_box is None and isinstance(page, int) and isinstance(box, list) and len(box) == 4:
            try:
                best_box = [float(value) for value in box]
                best_page = page
            except (TypeError, ValueError):
                best_box = None
    return best_page, best_box


def _previous_entries(store: RunStore) -> dict[str, dict[str, Any]]:
    data = _read_json(ledger_path(store))
    rows = data.get("notes")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("note_id")): row for row in rows if isinstance(row, dict) and row.get("note_id")
    }


def _render_one(
    doc: Any,
    *,
    root: Path,
    note_id: str,
    page: int,
    box: list[float],
    dpi: int,
) -> dict[str, Any]:
    import pymupdf

    if page < 1 or page > doc.page_count:
        return {"status": "missing_page"}
    page_obj = doc[page - 1]
    rect = pymupdf.Rect(box)
    clip = rect & page_obj.rect
    if clip.is_empty:
        return {"status": "missing_page", "reason": "bbox_outside_page"}
    pixmap = page_obj.get_pixmap(clip=clip, dpi=dpi)
    relative = Path("preprocessing") / "notes-render" / f"{note_id}-p{page:04d}.png"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(target))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return {
        "status": "rendered",
        "image": relative.as_posix(),
        "sha256": digest,
        "width": pixmap.width,
        "height": pixmap.height,
    }


def render_note_crops(
    store: RunStore,
    *,
    note_ids: list[str] | None = None,
    dpi: int = 150,
    max_crops: int = DEFAULT_MAX_CROPS,
) -> dict[str, Any]:
    """按需渲染注文裁剪图；幂等复用同摘要图片，保留审阅状态。"""
    if dpi < 36 or dpi > 600:
        raise ValueError("dpi 必须在 36–600 之间（默认 150）")
    if max_crops < 1:
        raise ValueError("max_crops 必须 ≥ 1（默认 200）")
    requested = [str(item) for item in (note_ids or [])]
    notes = _notes(store)
    present = {str(note.get("note_id")) for note in notes}
    missing = [item for item in requested if item not in present]
    previous = _previous_entries(store)
    pdf = _source_pdf(store)

    selected = set(requested)
    rows: list[dict[str, Any]] = [
        prior for note_id, prior in previous.items() if requested and note_id not in selected
    ]
    rendered = reused = page_only = missing_page = source_missing = deferred = 0
    doc = None
    try:
        if pdf is not None:
            import pymupdf

            doc = pymupdf.open(pdf)
        for note in notes:
            note_id = str(note.get("note_id") or "")
            if not note_id or (requested and note_id not in requested):
                continue
            page, box = _first_box(note)
            prior = previous.get(note_id) or {}
            row: dict[str, Any] = {
                "note_id": note_id,
                "page": page,
                "bbox": box,
                "status": "unknown",
                "image": None,
                "sha256": None,
                "reviewed": bool(prior.get("reviewed")) if prior.get("sha256") else False,
            }
            if pdf is None:
                row["status"] = "source_missing"
                source_missing += 1
            elif page is None:
                row["status"] = "missing_page"
                missing_page += 1
            elif box is None:
                row["status"] = "page_only"
                page_only += 1
            elif rendered + reused >= max_crops:
                row["status"] = "deferred"
                deferred += 1
            else:
                result = _render_one(
                    doc, root=store.dir, note_id=note_id, page=page, box=box, dpi=dpi
                )
                row.update(result)
                if result["status"] == "rendered":
                    if (
                        prior.get("sha256") == result["sha256"]
                        and prior.get("image") == result["image"]
                    ):
                        reused += 1
                    else:
                        rendered += 1
                        row["reviewed"] = False
            rows.append(row)
    finally:
        if doc is not None:
            doc.close()

    payload = {
        "schema_version": "1",
        "rule_version": RULE_VERSION,
        "source_sha256": store.load_publication().meta.source_sha256,
        "dpi": dpi,
        "max_crops": max_crops,
        "requested_note_ids": requested,
        "missing_note_ids": missing,
        "counts": {
            "selected": len(rows),
            "rendered": rendered,
            "reused": reused,
            "page_only": page_only,
            "missing_page": missing_page,
            "source_missing": source_missing,
            "deferred": deferred,
            "reviewed": sum(1 for row in rows if row["reviewed"]),
        },
        "notes": sorted(rows, key=lambda row: str(row.get("note_id") or "")),
        "limits": "只渲染被选中注文的局部图；deferred 表示达到单次上限，未生成不等于注文缺失",
    }
    _write_json(ledger_path(store), payload)
    store.log_event(
        "notes_render_written",
        rendered=rendered,
        reused=reused,
        deferred=deferred,
    )
    return payload


def mark_reviewed(store: RunStore, note_ids: list[str], *, reviewed: bool = True) -> dict[str, Any]:
    """登记人工审阅结论；只改账本，不改注文或图片。"""
    path = ledger_path(store)
    data = _read_json(path)
    rows = data.get("notes")
    if not isinstance(rows, list) or not rows:
        raise ValueError("尚无裁剪账本；先运行 evidence notes --render")
    by_id = {
        str(row.get("note_id")): row for row in rows if isinstance(row, dict) and row.get("note_id")
    }
    missing = [str(item) for item in note_ids if str(item) not in by_id]
    changed = 0
    for note_id in note_ids:
        row = by_id.get(str(note_id))
        if row is None or row.get("status") != "rendered":
            continue
        if bool(row.get("reviewed")) != reviewed:
            row["reviewed"] = reviewed
            changed += 1
    data["notes"] = rows
    data["counts"] = {
        **(data.get("counts") or {}),
        "reviewed": sum(1 for row in rows if isinstance(row, dict) and row.get("reviewed")),
    }
    _write_json(path, data)
    store.log_event("notes_review_marked", changed=changed, reviewed=reviewed)
    return {
        "path": str(path),
        "changed": changed,
        "missing_note_ids": missing,
        "reviewed": data["counts"]["reviewed"],
        "total": len(rows),
    }
