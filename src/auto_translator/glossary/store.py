"""统一术语库（跨工作区）领域逻辑：CSV 超集 schema + 语言对键 + 合并/导出 + 冲突账本。

与工作区权威 ``analysis/glossary.csv`` 的区别：

- 追加溯源列 ``src_lang,tgt_lang,book``；
- **键** = ``(src_lang, tgt_lang, NFKC(source))``——术语决策只在同一语言对内有效；
- 跨书同一键出现不同已确认译法时外置到 ``conflicts.jsonl`` 待 agent 裁决（不自动覆盖）。

本模块只做确定性计算（合并/去重/计数/CSV 读写），**不含 git、不含路径策略、不做裁决**；
git 维护与目录解析在 ``auto_epublizer.knowledge``，裁决由 agent 完成（单 LLM 原则）。
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from .csv_io import (
    entry_to_row,
    normalize,
    row_to_entry,
    save_glossary_csv,
)
from .models import (
    STATUS_CANDIDATE,
    STATUS_CONFIRMED,
    STATUS_CONFLICT,
    STATUS_SEED,
    GlossaryEntry,
)

# 统一库列序 = 工作区权威列序 + 溯源列
STORE_HEADER = [
    "source",
    "target",
    "type",
    "aliases",
    "gender",
    "reading",
    "status",
    "note",
    "src_lang",
    "tgt_lang",
    "book",
]

# 导出到工作区 terms.csv 时接受的态（confirmed 为默认；include_pending 追加 seed/candidate）
_EXPORTABLE_CONFIRMED = (STATUS_CONFIRMED,)
_EXPORTABLE_PENDING = (STATUS_SEED, STATUS_CANDIDATE)


class StoreEntry(GlossaryEntry):
    """统一库条目：工作区术语 + 语言对与来源书溯源。"""

    src_lang: str = ""
    tgt_lang: str = ""
    book: str = ""


class StoreConflict(BaseModel):
    """跨书冲突记录（append-only 账本）。"""

    source: str
    src_lang: str = ""
    tgt_lang: str = ""
    existing_target: str = ""
    proposed_target: str = ""
    targets: list[str] = Field(default_factory=list)
    type: str = "term"
    books: list[str] = Field(default_factory=list)
    status: str = "open"

    def as_jsonl(self) -> dict:
        return self.model_dump(mode="json")


@dataclass
class MergeResult:
    """合并结果：合并后的完整条目表 + 计数 + 新增冲突。"""

    entries: list[StoreEntry]
    added: int = 0
    updated: int = 0
    conflicts: list[StoreConflict] = field(default_factory=list)


def store_key(src_lang: str, tgt_lang: str, source: str) -> tuple[str, str, str]:
    """统一库键：语言对 + NFKC 归一化 source。"""
    return (src_lang or "", tgt_lang or "", normalize(source))


def _entry_key(entry: StoreEntry) -> tuple[str, str, str]:
    return store_key(entry.src_lang, entry.tgt_lang, entry.source)


def _row_to_store_entry(row: dict[str, str | None]) -> StoreEntry:
    base = row_to_entry(row)
    return StoreEntry(
        **base.model_dump(),
        src_lang=(row.get("src_lang") or "").strip(),
        tgt_lang=(row.get("tgt_lang") or "").strip(),
        book=(row.get("book") or "").strip(),
    )


def _store_entry_to_row(entry: StoreEntry) -> dict[str, str]:
    row = entry_to_row(entry)
    row.update(
        {
            "src_lang": entry.src_lang,
            "tgt_lang": entry.tgt_lang,
            "book": entry.book,
        }
    )
    return row


def load_store_csv(path: str | Path) -> list[StoreEntry]:
    """读取统一库 CSV；文件不存在返回空表。"""
    p = Path(path)
    if not p.is_file():
        return []
    reader = csv.DictReader(io.StringIO(p.read_text(encoding="utf-8")))
    entries: list[StoreEntry] = []
    for row in reader:
        if not (row.get("source") or "").strip():
            continue
        entries.append(_row_to_store_entry(row))
    return entries


def save_store_csv(path: str | Path, entries: list[StoreEntry]) -> None:
    """写统一库 CSV（同目录临时文件 + os.replace 原子替换）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=STORE_HEADER)
    writer.writeheader()
    for entry in entries:
        writer.writerow(_store_entry_to_row(entry))
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8")
    tmp.replace(p)


def to_workspace_entry(entry: StoreEntry) -> GlossaryEntry:
    """统一库条目 → 工作区 schema（丢溯源列）。"""
    return GlossaryEntry(
        source=entry.source,
        target=entry.target,
        type=entry.type,
        aliases=list(entry.aliases),
        gender=entry.gender,
        reading=entry.reading,
        status=entry.status,
        note=entry.note,
    )


def merge_workspace_glossary(
    store_entries: list[StoreEntry],
    ws_entries: list[GlossaryEntry],
    *,
    src_lang: str,
    tgt_lang: str,
    book: str,
) -> MergeResult:
    """把工作区术语合并进统一库（幂等；不同已确认译法记冲突，不覆盖）。

    - 新键 → 新增（保留工作区态，默认 seed）；
    - 同键同 target → 幂等，仅补强 aliases/note/status（不把冲突态自动升为 confirmed）；
    - 同键不同 target：已有 confirmed → 新条目落 ``conflict`` 态并记冲突；无 confirmed → 新增。
    """
    entries = list(store_entries)
    by_key: dict[tuple[str, str, str], list[StoreEntry]] = {}
    for e in entries:
        by_key.setdefault(_entry_key(e), []).append(e)

    result = MergeResult(entries=entries)

    for ws in ws_entries:
        if not ws.source or not ws.target:
            continue
        key = store_key(src_lang, tgt_lang, ws.source)
        group = by_key.setdefault(key, [])
        same = [e for e in group if normalize(e.target) == normalize(ws.target)]
        if same:
            tgt_entry = same[0]
            changed = False
            other_confirmed = [
                e for e in group if e.status == STATUS_CONFIRMED and e.target and e is not tgt_entry
            ]
            if (
                ws.status == STATUS_CONFIRMED
                and tgt_entry.status not in (STATUS_CONFIRMED, STATUS_CONFLICT)
                and not other_confirmed
            ):
                tgt_entry.status = STATUS_CONFIRMED
                changed = True
            for alias in ws.aliases:
                if alias and alias not in tgt_entry.aliases:
                    tgt_entry.aliases.append(alias)
                    changed = True
            if ws.note and not tgt_entry.note:
                tgt_entry.note = ws.note
                changed = True
            if changed:
                result.updated += 1
            continue

        confirmed = [e for e in group if e.status == STATUS_CONFIRMED and e.target]
        if confirmed:
            new = StoreEntry(
                source=ws.source,
                target=ws.target,
                type=ws.type,
                aliases=list(ws.aliases),
                gender=ws.gender,
                reading=ws.reading,
                status=STATUS_CONFLICT,
                note=ws.note,
                src_lang=src_lang,
                tgt_lang=tgt_lang,
                book=book,
            )
            entries.append(new)
            group.append(new)
            result.added += 1
            result.conflicts.append(
                StoreConflict(
                    source=ws.source,
                    src_lang=src_lang,
                    tgt_lang=tgt_lang,
                    existing_target=confirmed[0].target,
                    proposed_target=ws.target,
                    targets=sorted({e.target for e in group if e.target}),
                    type=ws.type,
                    books=sorted({e.book for e in group if e.book} | ({book} if book else set())),
                )
            )
        else:
            new = StoreEntry(
                source=ws.source,
                target=ws.target,
                type=ws.type,
                aliases=list(ws.aliases),
                gender=ws.gender,
                reading=ws.reading,
                status=ws.status or STATUS_SEED,
                note=ws.note,
                src_lang=src_lang,
                tgt_lang=tgt_lang,
                book=book,
            )
            entries.append(new)
            group.append(new)
            result.added += 1

    return result


def export_for_workspace(
    store_entries: list[StoreEntry],
    *,
    src_lang: str,
    tgt_lang: str,
    include_pending: bool = False,
) -> list[GlossaryEntry]:
    """导出同语对条目为工作区 schema：默认仅 confirmed；``include_pending`` 追加 seed/candidate。

    同一 source 多条目（冲突）时优先取 confirmed，避免导出歧义；冲突态不导出。
    """
    allowed = set(_EXPORTABLE_CONFIRMED)
    if include_pending:
        allowed |= set(_EXPORTABLE_PENDING)

    by_src: dict[str, StoreEntry] = {}
    order: list[str] = []
    for e in store_entries:
        if e.src_lang != src_lang or e.tgt_lang != tgt_lang:
            continue
        if not e.target or e.status not in allowed:
            continue
        key = normalize(e.source)
        if key not in by_src:
            by_src[key] = e
            order.append(key)
            continue
        cur = by_src[key]
        if e.status == STATUS_CONFIRMED and cur.status != STATUS_CONFIRMED:
            by_src[key] = e
    return [to_workspace_entry(by_src[k]) for k in order]


def unresolved_keys(store_entries: list[StoreEntry]) -> list[tuple[str, str, str]]:
    """未裁决键：同一键仍有 >1 个不同非空 target（agent 裁决后自动归零）。"""
    groups: dict[tuple[str, str, str], set[str]] = {}
    for e in store_entries:
        if not e.target:
            continue
        groups.setdefault(_entry_key(e), set()).add(normalize(e.target))
    return sorted(k for k, targets in groups.items() if len(targets) > 1)


def store_stats(store_entries: list[StoreEntry]) -> dict:
    """统一库统计：总数 / 按语对 / 按态 / 涉及书籍 / 未裁决键。"""
    by_lang: dict[str, int] = {}
    by_status: dict[str, int] = {}
    books: set[str] = set()
    for e in store_entries:
        pair = f"{e.src_lang or '?'}->{e.tgt_lang or '?'}"
        by_lang[pair] = by_lang.get(pair, 0) + 1
        by_status[e.status] = by_status.get(e.status, 0) + 1
        if e.book:
            books.add(e.book)
    return {
        "total": len(store_entries),
        "by_lang": by_lang,
        "by_status": by_status,
        "books": sorted(books),
        "unresolved": len(unresolved_keys(store_entries)),
    }


def write_store_conflicts(path: str | Path, conflicts: list[StoreConflict]) -> int:
    """追加跨书冲突账本（按 语对+source+proposed_target 去重）；返回实际写入条数。"""
    if not conflicts:
        return 0
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = {
        (c.get("src_lang"), c.get("tgt_lang"), c.get("source"), c.get("proposed_target"))
        for c in read_store_conflicts(p)
    }
    written = 0
    with open(p, "a", encoding="utf-8") as f:
        for c in conflicts:
            key = (c.src_lang, c.tgt_lang, c.source, c.proposed_target)
            if key in existing:
                continue
            existing.add(key)
            f.write(json.dumps(c.as_jsonl(), ensure_ascii=False, sort_keys=True) + "\n")
            written += 1
    return written


def read_store_conflicts(path: str | Path) -> list[dict]:
    """读取跨书冲突账本（按 语对+source+proposed_target 去重，保留首次出现顺序）。"""
    p = Path(path)
    if not p.is_file():
        return []
    seen: set[tuple] = set()
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = (
            row.get("src_lang"),
            row.get("tgt_lang"),
            row.get("source"),
            row.get("proposed_target"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def write_workspace_terms(path: str | Path, entries: list[GlossaryEntry]) -> None:
    """把导出条目写成工作区 terms.csv（列序与 glossary.csv 一致）。"""
    save_glossary_csv(path, entries)


__all__ = [
    "STORE_HEADER",
    "MergeResult",
    "StoreConflict",
    "StoreEntry",
    "export_for_workspace",
    "load_store_csv",
    "merge_workspace_glossary",
    "read_store_conflicts",
    "save_store_csv",
    "store_key",
    "store_stats",
    "to_workspace_entry",
    "unresolved_keys",
    "write_store_conflicts",
    "write_workspace_terms",
]
