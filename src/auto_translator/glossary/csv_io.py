# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""术语表 CSV 读写与三态合并（单线程裁决）。

权威 CSV 列序（与 template/analysis/glossary.csv 一致）：
``source,target,type,aliases,gender,reading,status,note``。

aliases 用 ``|`` 分隔。同 source 出现多个不同 target 时记冲突，不自动覆盖已确认译法。
"""

from __future__ import annotations

import csv
import io
import json
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


def row_to_entry(row: dict[str, str | None]) -> GlossaryEntry:
    return GlossaryEntry(
        source=(row.get("source") or "").strip(),
        target=(row.get("target") or "").strip(),
        type=_coerce_type(row.get("type") or ""),
        aliases=_parse_aliases(row.get("aliases") or ""),
        gender=_coerce_gender(row.get("gender") or ""),
        reading=(row.get("reading") or "").strip(),
        status=_coerce_status(row.get("status") or ""),
        note=(row.get("note") or "").strip(),
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
    """读取权威 CSV，容忍缺列（旧案例用 ``category,source,target,note`` 时由调用方先转换）。

    ``utf-8-sig``：Excel 另存的 CSV 常带 BOM；用 ``utf-8`` 读会让首列名变成
    ``\\ufeffsource``，``DictReader`` 取不到 ``source`` 而**整表静默丢光**
    （issue #36）。与 ``structure.csv`` 的读取口径保持一致。
    """
    p = Path(path)
    if not p.is_file():
        return []
    text = p.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    entries: list[GlossaryEntry] = []
    for row in reader:
        source = (row.get("source") or "").strip()
        if not source:
            continue
        entries.append(row_to_entry(row))
    return entries


def load_terminology_exemptions(path: str | Path) -> dict[str, dict[str, str]]:
    """读取**按单元**的术语门豁免表，返回 ``{单元 id: {术语 source: 理由}}``。

    CSV 列：``unit,source,reason``。文件不存在即无豁免（不报错）。

    为什么需要（2026-10-07 于 forced-labour 的 back-notes）：
    G0 术语判据是「源行出现术语 source，译文行必须含 target」，但**文献著录
    体例天然违反它**——注文里的书名/丛书名/档案题名按体例保留德文，Kurztiitel
    （`Tuchei, Konzentrationslager, S. 243`）也保留拉丁。这类行里术语出现
    而中文译名按体例**不该**出现，判据报出的 227 条全是**改译文也放行不了**
    的假阳性：一刀切改译文会把正确体例改坏。

    与「把词条从 glossary.csv 删掉」的区别：删词条会让该术语**全书失去检查**
    （`Konzentrationslager → 集中营` 在正文译了几百处，正文必须继续查）。
    本表只豁免**指定单元**，其余单元照常受检；且每条豁免必须写 ``reason``，
    命中时以 advisory 形式**照样报出**（check=``terminology_exempt``），
    不阻断放行也不从报告里消失——审计可见、可回溯、可撤销。
    """
    p = Path(path)
    if not p.is_file():
        return {}
    out: dict[str, dict[str, str]] = {}
    for row in csv.DictReader(io.StringIO(p.read_text(encoding="utf-8-sig"))):
        unit = (row.get("unit") or "").strip()
        source = (row.get("source") or "").strip()
        if not unit or not source:
            continue
        out.setdefault(unit, {})[source] = (row.get("reason") or "").strip()
    return out


def save_glossary_csv(path: str | Path, entries: list[GlossaryEntry]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_HEADER)
    writer.writeheader()
    for entry in entries:
        writer.writerow(entry_to_row(entry))
    p.write_text(buf.getvalue(), encoding="utf-8")


def write_conflicts_jsonl(path: str | Path, conflicts: list[GlossaryConflict]) -> int:
    """把术语冲突外置到 glossary_conflicts.jsonl（追加式、按身份去重）；返回**本次新增**条数。

    去重键 ``(source, existing_target, proposed_target)``：同一冲突重复检出不再追加，
    重复 ``import`` 幂等（issue #35）；已有行（含已裁决的 ``resolved``）不被改写、不删除。
    """
    if not conflicts:
        return 0
    p = Path(path)
    seen: set[tuple[str, str, str]] = set()
    if p.is_file():
        for row in read_conflicts_jsonl(p):
            seen.add(
                (
                    str(row.get("source", "")),
                    str(row.get("existing_target", "")),
                    str(row.get("proposed_target", "")),
                )
            )
    fresh: list[GlossaryConflict] = []
    for c in conflicts:
        key = (c.source, c.existing_target, c.proposed_target)
        if key in seen:  # 含同批内重复（防御）
            continue
        seen.add(key)
        fresh.append(c)
    if not fresh:
        return 0
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        for c in fresh:
            f.write(json.dumps(c.as_jsonl(), ensure_ascii=False, sort_keys=True) + "\n")
    return len(fresh)


def read_conflicts_jsonl(path: str | Path) -> list[dict]:
    """读取冲突记录（去重按 source+proposed_target，保留首次出现顺序）。"""
    p = Path(path)
    if not p.is_file():
        return []
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = (str(row.get("source", "")), str(row.get("proposed_target", "")))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


# 旧真实案例的类别列 → 标准 type 映射
_CATEGORY_TO_TYPE = {
    "人物": "person",
    "person": "person",
    "地名": "place",
    "place": "place",
    "关键术语": "term",
    "term": "term",
    "概念": "term",
    "专名": "term",
    "职衔": "term",
    "政党": "org",
    "组织": "org",
    "组织机构": "org",
    "机构": "org",
    "政治派系": "org",
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
    reader = csv.DictReader(io.StringIO(p.read_text(encoding="utf-8-sig")))
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

    def propose(
        self,
        source: str,
        target: str,
        *,
        type: str = "term",
        note: str = "",
        aliases: str | list[str] | None = None,
        gender: str = "",
        reading: str = "",
    ) -> None:
        """worker 追加提案：不覆盖既有 target，若与确认态不同则标记冲突。

        ``aliases`` 接受 ``|`` 分隔的字符串（与 CSV 列格式一致）或已切好的列表；
        其它列（gender/reading）同 proposal 落盘，否则 ``import --terms`` 会把它们丢掉。
        """
        alias_text = aliases if isinstance(aliases, str) else "|".join(aliases or [])
        entries = self.lookup(source)
        existing_targets = {e.target for e in entries if e.target}
        if not entries:
            self.add(
                GlossaryEntry(
                    source=source,
                    target=target,
                    type=type,
                    aliases=_parse_aliases(alias_text),
                    gender=gender or "",
                    reading=reading or "",
                    status=STATUS_SEED,
                    note=note,
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
        self.add(
            GlossaryEntry(
                source=source,
                target=target,
                type=type,
                aliases=_parse_aliases(alias_text),
                gender=gender or "",
                reading=reading or "",
                status=status,
                note=note,
            )
        )

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
