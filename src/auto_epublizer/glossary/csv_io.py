"""术语表 CSV 读写与三态合并（单线程裁决）。

权威 CSV 列序（与 template/analysis/glossary.csv 一致）：
``source,target,type,aliases,gender,reading,status,note``。

aliases 用 ``|`` 分隔。同 source 出现多个不同 target 时记冲突，不自动覆盖已确认译法。
"""

from __future__ import annotations

import csv
import io
import unicodedata
from pathlib import Path

from .models import (
    GENDERS,
    STATUS_CONFIRMED,
    STATUS_CONFLICT,
    STATUS_SEED,
    TERM_STATUSES,
    TERM_TYPES,
    GlossaryConflict,
    GlossaryEntry,
)

_HEADER = ["source", "target", "type", "aliases", "gender", "reading", "status", "note"]


def normalize(text: str) -> str:
    """NFKC 归一化 + 去首尾空白，用于术语匹配。"""
    return unicodedata.normalize("NFKC", (text or "").strip())


def _parse_aliases(raw: str) -> list[str]:
    return [a.strip() for a in (raw or "").split("|") if a.strip()]


def _coerce_type(value: str) -> str:
    value = (value or "").strip()
    return value if value in TERM_TYPES else "term"


def _coerce_status(value: str) -> str:
    value = (value or "").strip()
    return value if value in TERM_STATUSES else STATUS_SEED


def _coerce_gender(value: str) -> str:
    value = (value or "").strip()
    return value if value in GENDERS else ""


def row_to_entry(row: dict[str, str]) -> GlossaryEntry:
    return GlossaryEntry(
        source=row.get("source", "").strip(),
        target=row.get("target", "").strip(),
        type=_coerce_type(row.get("type", "")),
        aliases=_parse_aliases(row.get("aliases", "")),
        gender=_coerce_gender(row.get("gender", "")),
        reading=row.get("reading", "").strip(),
        status=_coerce_status(row.get("status", "")),
        note=row.get("note", "").strip(),
    )


def entry_to_row(entry: GlossaryEntry) -> dict[str, str]:
    return {
        "source": entry.source,
        "target": entry.target,
        "type": entry.type,
        "aliases": "|".join(entry.aliases),
        "gender": entry.gender,
        "reading": entry.reading,
        "status": entry.status,
        "note": entry.note,
    }


def load_glossary_csv(path: str | Path) -> list[GlossaryEntry]:
    """读取权威 CSV，容忍缺列（旧案例用 ``category,source,target,note`` 时由调用方先转换）。"""
    p = Path(path)
    if not p.is_file():
        return []
    text = p.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    entries: list[GlossaryEntry] = []
    for row in reader:
        source = (row.get("source") or "").strip()
        if not source:
            continue
        entries.append(row_to_entry(row))
    return entries


def save_glossary_csv(path: str | Path, entries: list[GlossaryEntry]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_HEADER)
    writer.writeheader()
    for entry in entries:
        writer.writerow(entry_to_row(entry))
    p.write_text(buf.getvalue(), encoding="utf-8")


# 旧真实案例的类别列 → 标准 type 映射
_CATEGORY_TO_TYPE = {
    "人物": "person",
    "person": "person",
    "地名": "place",
    "place": "place",
    "关键术语": "term",
    "term": "term",
    "政党": "org",
    "组织": "org",
    "organization": "org",
    "org": "org",
    "事件": "event",
    "event": "event",
    "历史时期": "period",
    "period": "period",
    "作品": "work",
    "work": "work",
    "固定表达": "fixed_expr",
}


def load_legacy_category_csv(path: str | Path) -> list[GlossaryEntry]:
    """读旧真实案例的 ``category,source,target,note`` 格式术语表，映射为标准 schema。"""
    p = Path(path)
    if not p.is_file():
        return []
    reader = csv.DictReader(io.StringIO(p.read_text(encoding="utf-8")))
    entries: list[GlossaryEntry] = []
    for row in reader:
        source = (row.get("source") or "").strip()
        if not source:
            continue
        category = (row.get("category") or "").strip()
        entries.append(
            GlossaryEntry(
                source=source,
                target=(row.get("target") or "").strip(),
                type=_CATEGORY_TO_TYPE.get(category, "term"),
                status=STATUS_CONFIRMED if (row.get("target") or "").strip() else STATUS_SEED,
                note=(row.get("note") or "").strip(),
            )
        )
    return entries


class Glossary:
    """术语表内存索引：按归一化 source 查表、提案、单线程合并与冲突检测。"""

    def __init__(self, entries: list[GlossaryEntry] | None = None) -> None:
        self._entries: dict[str, list[GlossaryEntry]] = {}
        for e in entries or []:
            self.add(e)

    def add(self, entry: GlossaryEntry) -> None:
        key = normalize(entry.source)
        self._entries.setdefault(key, []).append(entry)

    def entries(self) -> list[GlossaryEntry]:
        out: list[GlossaryEntry] = []
        for group in self._entries.values():
            out.extend(group)
        return out

    def lookup(self, source: str) -> list[GlossaryEntry]:
        key = normalize(source)
        return list(self._entries.get(key, []))

    def confirmed_target(self, source: str) -> str | None:
        """返回确认态译法；无确认态时返回第一个非空 target。"""
        entries = self.lookup(source)
        for e in entries:
            if e.status == STATUS_CONFIRMED and e.target:
                return e.target
        for e in entries:
            if e.target:
                return e.target
        return None

    def propose(self, source: str, target: str, *, type: str = "term", note: str = "") -> None:
        """worker 追加提案：不覆盖既有 target，若与确认态不同则标记冲突。"""
        entries = self.lookup(source)
        existing_targets = {e.target for e in entries if e.target}
        if not entries:
            self.add(
                GlossaryEntry(
                    source=source, target=target, type=type, status=STATUS_SEED, note=note
                )
            )
            return
        if target in existing_targets:
            return
        confirmed = [e for e in entries if e.status == STATUS_CONFIRMED and e.target]
        status = (
            STATUS_CONFLICT
            if confirmed and target not in {e.target for e in confirmed}
            else STATUS_SEED
        )
        self.add(GlossaryEntry(source=source, target=target, type=type, status=status, note=note))

    def detect_conflicts(self) -> list[GlossaryConflict]:
        conflicts: list[GlossaryConflict] = []
        for _key, entries in self._entries.items():
            targets = sorted({e.target for e in entries if e.target})
            if len(targets) <= 1:
                continue
            confirmed = [e for e in entries if e.status == STATUS_CONFIRMED and e.target]
            existing = confirmed[0].target if confirmed else (entries[0].target or "")
            for e in entries:
                if e.status != STATUS_CONFIRMED and e.target and e.target != existing:
                    conflicts.append(
                        GlossaryConflict(
                            source=entries[0].source,
                            targets=targets,
                            existing_target=existing,
                            proposed_target=e.target,
                            type=entries[0].type,
                        )
                    )
        return conflicts
