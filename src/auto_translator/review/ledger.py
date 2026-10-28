# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""审校账本（issue #68）：把「多次审校」还原成**有效问题集合**，而不是取最新一份。

背景：``reviews/review-<ts>/result.json`` 是 agent 手写的终局计数，qa 过去只读目录名
排序后的**最后一份**。于是「全书 24 项未结 + 之后一次局部 clean」会被读成 0 项，
放行结论凭空变绿；反过来，多次局部审校的计数也无法相加（会重复计数）。

本模块的契约（schema_version=2，写进 ``result.json`` 即可被 qa 识别）：

```json
{
  "schema_version": 2,
  "review_id": "review-2026-10-27T10-00-00",
  "scope": "full" | "units",
  "units": ["ch01", "ch02"],
  "parent_reviews": ["review-2026-10-26T10-00-00"],
  "inputs_digest": {"ch01": "<sha256>", "*": "<sha256>"},
  "issues": [
    {"issue_id": "...", "unit": "ch01", "detail": "...", "status": "open"}
  ],
  "dispositions": [
    {"issue_id": "...", "status": "patched", "closed_by": "patch-0007",
     "evidence": "align/ch01.jsonl#seq=42"}
  ],
  "g1_candidates": 3, "g2_confirmed": 1, "g3_patched": 1,
  "termination": "clean_confirmed", "rounds": 2
}
```

判定规则（全部保守，宁可 unknown 也不默认清零）：

1. 无 ``parent_reviews`` 的记录是**独立根**，不能关闭别人的问题（血缘不足 → 记
   ``closure_without_lineage``，问题保持未结）；
2. 记录范围覆盖某单元、但既未处置该单元的继承未结项、也未重列 → 该项转 ``unknown``
   （「没提」不等于「已核」）；
3. 结案必须给 ``closed_by`` + ``evidence``，缺一 → 不一致且问题保持未结；
4. ``g3_patched`` 大于逐项结案数 → 计数与逐项证据不一致（虚增 patched 不放行）；
5. 缺父记录 / 成环 / 父记录不在更早位置 / 输入摘要不符 → ``inconsistent``，不放行；
6. 旧格式（无 ``schema_version``）按 ``g2_confirmed - g3_patched`` 记为
   ``opaque:<review_id>:<n>`` 未结项，只能由 v2 记录逐项点名结清；同时存在多份旧格式
   且无 v2 记录时记一条 ``unknown``（不累加、不只取最新），要求重登 v2。

本模块只做确定性对账，不判断修复语义是否正确（那是 agent 的职责）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2

STATUS_OPEN = "open"
STATUS_PATCHED = "patched"
STATUS_DISMISSED = "dismissed"
STATUS_UNKNOWN = "unknown"

SCOPE_FULL = "full"
SCOPE_UNITS = "units"

CONTRACT_NONE = "none"
CONTRACT_LEGACY = "legacy"
CONTRACT_V2 = "v2"

_ISSUE_STATUS = (STATUS_OPEN, STATUS_PATCHED, STATUS_DISMISSED)
_DISPOSITION_STATUS = (STATUS_PATCHED, STATUS_DISMISSED)


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _as_str_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _as_digest_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items() if str(k).strip() and str(v).strip()}


@dataclass(frozen=True)
class LedgerIssue:
    """一条有效审校问题（跨多次审校的同一身份）。"""

    issue_id: str
    unit: str = ""
    status: str = STATUS_OPEN
    detail: str = ""
    origin_review: str = ""
    closed_in_review: str | None = None
    closed_by: str | None = None
    evidence: str | None = None
    note: str = ""
    opaque: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "unit": self.unit,
            "status": self.status,
            "detail": self.detail,
            "origin_review": self.origin_review,
            "closed_in_review": self.closed_in_review,
            "closed_by": self.closed_by,
            "evidence": self.evidence,
            **({"note": self.note} if self.note else {}),
        }


@dataclass(frozen=True)
class ReviewRecord:
    """一份 ``result.json`` 的结构化视图（新旧格式统一）。"""

    review_id: str
    schema_version: int
    scope: str
    units: tuple[str, ...]
    parent_reviews: tuple[str, ...]
    inputs_digest: dict[str, str]
    issues: tuple[LedgerIssue, ...]
    dispositions: dict[str, dict[str, Any]]
    g1_candidates: int
    g2_confirmed: int
    g3_patched: int
    termination: str
    rounds: int

    @property
    def legacy(self) -> bool:
        return self.schema_version < SCHEMA_VERSION

    def covers(self, unit: str) -> bool:
        if self.scope == SCOPE_FULL:
            return True
        return bool(unit) and unit in self.units


def load_record(review_id: str, payload: Any) -> ReviewRecord:
    """把一份 result.json 解析成记录；未知/畸形字段按缺省处理，不抛异常。"""
    data = payload if isinstance(payload, dict) else {}
    schema = _as_int(data.get("schema_version"))
    scope = str(data.get("scope") or (SCOPE_FULL if schema < SCHEMA_VERSION else SCOPE_UNITS))
    if scope not in (SCOPE_FULL, SCOPE_UNITS):
        scope = SCOPE_UNITS
    issues: list[LedgerIssue] = []
    for raw in data.get("issues") or []:
        if not isinstance(raw, dict):
            continue
        issue_id = str(raw.get("issue_id") or "").strip()
        if not issue_id:
            continue
        status = str(raw.get("status") or STATUS_OPEN)
        if status not in _ISSUE_STATUS:
            status = STATUS_OPEN
        issues.append(
            LedgerIssue(
                issue_id=issue_id,
                unit=str(raw.get("unit") or ""),
                status=status,
                detail=str(raw.get("detail") or ""),
                origin_review=review_id,
                closed_by=(
                    str(raw["closed_by"]) if raw.get("closed_by") not in (None, "") else None
                ),
                evidence=(str(raw["evidence"]) if raw.get("evidence") not in (None, "") else None),
            )
        )
    dispositions: dict[str, dict[str, Any]] = {}
    for raw in data.get("dispositions") or []:
        if not isinstance(raw, dict):
            continue
        issue_id = str(raw.get("issue_id") or "").strip()
        if not issue_id:
            continue
        dispositions[issue_id] = dict(raw)
    return ReviewRecord(
        review_id=review_id,
        schema_version=schema,
        scope=scope,
        units=_as_str_list(data.get("units")),
        parent_reviews=_as_str_list(data.get("parent_reviews")),
        inputs_digest=_as_digest_map(data.get("inputs_digest")),
        issues=tuple(issues),
        dispositions=dispositions,
        g1_candidates=_as_int(data.get("g1_candidates")),
        g2_confirmed=_as_int(data.get("g2_confirmed", data.get("issue_count"))),
        g3_patched=_as_int(data.get("g3_patched")),
        termination=str(data.get("termination") or ""),
        rounds=_as_int(data.get("rounds")),
    )


def load_review_records(reviews_dir: Path) -> list[ReviewRecord]:
    """读取 ``review-*/result.json``（按目录名排序；坏 JSON 记为无内容的旧格式记录）。"""
    if not reviews_dir.is_dir():
        return []
    records: list[ReviewRecord] = []
    for path in sorted(reviews_dir.glob("review-*/result.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        records.append(load_record(path.parent.name, payload))
    return records


@dataclass
class ReviewLedger:
    """跨审校的有效问题账本（qa/status/evidence 共用的唯一快照）。"""

    contract: str = CONTRACT_NONE
    records: int = 0
    review_id: str | None = None
    issues: list[LedgerIssue] = field(default_factory=list)
    inconsistent: list[str] = field(default_factory=list)
    legacy_unknown: bool = False

    @property
    def open(self) -> int:
        return sum(1 for issue in self.issues if issue.status == STATUS_OPEN)

    @property
    def unknown(self) -> int:
        count = sum(1 for issue in self.issues if issue.status == STATUS_UNKNOWN)
        return count + (1 if self.legacy_unknown else 0)

    @property
    def closed(self) -> int:
        return sum(1 for issue in self.issues if issue.status in _DISPOSITION_STATUS)

    @property
    def blocking(self) -> bool:
        """存在任何未结/未定/不一致 → 不得放行。"""
        return bool(self.open or self.unknown or self.inconsistent)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "records": self.records,
            "review_id": self.review_id,
            "open": self.open,
            "unknown": self.unknown,
            "closed": self.closed,
            "inconsistent": list(self.inconsistent),
            "blocking": self.blocking,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _ancestors(record: ReviewRecord, by_id: dict[str, ReviewRecord]) -> set[str]:
    """该记录的全部祖先（含父、祖父）；缺失父记录已由一致性检查报告。"""
    seen: set[str] = set()
    stack = [pid for pid in record.parent_reviews if pid in by_id]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(pid for pid in by_id[current].parent_reviews if pid in by_id)
    return seen


def build_ledger(records: list[ReviewRecord]) -> ReviewLedger:
    """按声明血缘与范围计算有效问题集合（确定性；输入按评审 id 排序）。"""
    ordered = sorted(records, key=lambda record: record.review_id)
    ledger = ReviewLedger(records=len(ordered))
    if not ordered:
        return ledger
    ledger.review_id = ordered[-1].review_id
    by_id: dict[str, ReviewRecord] = {}
    for record in ordered:
        if record.review_id in by_id:
            ledger.inconsistent.append(f"duplicate_review_id:{record.review_id}")
            continue
        by_id[record.review_id] = record
    v2_records = [r for r in ordered if not r.legacy]
    legacy_records = [r for r in ordered if r.legacy]
    ledger.contract = CONTRACT_V2 if v2_records else CONTRACT_LEGACY

    # 父记录存在性、位置与成环（环用 DFS 三色判定，父子皆缺一即报）。
    position = {record.review_id: index for index, record in enumerate(ordered)}
    for record in ordered:
        for parent in record.parent_reviews:
            if parent not in by_id:
                ledger.inconsistent.append(f"missing_parent:{record.review_id}:{parent}")
            elif position[parent] > position[record.review_id]:
                ledger.inconsistent.append(f"parent_not_earlier:{record.review_id}:{parent}")
    state_colors: dict[str, int] = {}

    def visit(node: str) -> None:
        color = state_colors.get(node, 0)
        if color == 1:
            ledger.inconsistent.append(f"review_cycle:{node}")
            return
        if color == 2:
            return
        state_colors[node] = 1
        for parent in by_id[node].parent_reviews:
            if parent in by_id:
                visit(parent)
        state_colors[node] = 2

    for record in ordered:
        visit(record.review_id)

    # 旧格式：多份且无 v2 → 不能相加、也不能只取最新，记一条 unknown 要求重登 v2。
    if legacy_records and not v2_records and len(legacy_records) > 1:
        # 不累加（重复计数）也不只取最新（会丢旧未结），记一条 unknown 要求重登 v2。
        ledger.legacy_unknown = True
        return ledger

    issues: dict[str, LedgerIssue] = {}
    ancestors: dict[str, set[str]] = {}
    for record in ordered:
        ancestors[record.review_id] = _ancestors(record, by_id)

    for record in ordered:
        if record.legacy:
            # 旧格式只给计数：g2-g3 记为不透明未结项，逐项重新登记才能结清。
            for index in range(_as_int(record.g2_confirmed - record.g3_patched)):
                issue_id = f"opaque:{record.review_id}:{index + 1}"
                issues[issue_id] = LedgerIssue(
                    issue_id=issue_id,
                    status=STATUS_OPEN,
                    origin_review=record.review_id,
                    note="legacy_count_only",
                    opaque=True,
                )
            continue
        # 1) 继承未结项：范围内未处置 → unknown；处置需血缘/覆盖/证据齐全。
        for issue_id, issue in list(issues.items()):
            if issue.status not in (STATUS_OPEN, STATUS_UNKNOWN) or not record.covers(issue.unit):
                continue
            disposition = record.dispositions.get(issue_id)
            if disposition is None:
                issues[issue_id] = LedgerIssue(
                    **{
                        **issue.__dict__,
                        "status": STATUS_UNKNOWN,
                        "note": f"undisposed:{record.review_id}",
                    }
                )
                continue
            status = str(disposition.get("status") or "")
            if status not in _DISPOSITION_STATUS:
                ledger.inconsistent.append(f"bad_disposition:{record.review_id}:{issue_id}")
                continue
            closed_by = str(disposition.get("closed_by") or "").strip()
            evidence = str(disposition.get("evidence") or "").strip()
            if not closed_by or not evidence:
                ledger.inconsistent.append(
                    f"closure_evidence_missing:{record.review_id}:{issue_id}"
                )
                continue
            lineage_ok = issue.origin_review in ancestors.get(record.review_id, set())
            if issue.opaque:
                # 旧格式逐项重登：id 已点名即为血缘证据。
                lineage_ok = True
            if not lineage_ok:
                ledger.inconsistent.append(f"closure_without_lineage:{record.review_id}:{issue_id}")
                continue
            origin = by_id.get(issue.origin_review)
            if origin is not None and origin.inputs_digest and record.inputs_digest:
                origin_digest = origin.inputs_digest.get(issue.unit) or origin.inputs_digest.get(
                    "*"
                )
                stated = record.inputs_digest.get(issue.unit) or record.inputs_digest.get("*")
                if origin_digest and stated and origin_digest != stated:
                    ledger.inconsistent.append(
                        f"inputs_digest_mismatch:{record.review_id}:{issue_id}"
                    )
                    issues[issue_id] = LedgerIssue(
                        **{
                            **issue.__dict__,
                            "status": STATUS_UNKNOWN,
                            "note": f"inputs_changed:{record.review_id}",
                        }
                    )
                    continue
            issues[issue_id] = LedgerIssue(
                issue_id=issue.issue_id,
                unit=issue.unit,
                status=status,
                detail=issue.detail,
                origin_review=issue.origin_review,
                closed_in_review=record.review_id,
                closed_by=closed_by,
                evidence=evidence,
                opaque=issue.opaque,
            )
        # 2) 本轮新问题（同 id 重列视为补充说明，不改变已结状态）。
        for issue in record.issues:
            if issue.issue_id in issues and issues[issue.issue_id].status != STATUS_OPEN:
                continue
            if issue.status in _DISPOSITION_STATUS and not (issue.closed_by and issue.evidence):
                ledger.inconsistent.append(
                    f"closure_evidence_missing:{record.review_id}:{issue.issue_id}"
                )
                issues[issue.issue_id] = LedgerIssue(**{**issue.__dict__, "status": STATUS_OPEN})
                continue
            issues[issue.issue_id] = issue
        # 3) 计数与逐项证据一致：虚增 patched 不放行。
        itemized = sum(1 for d in record.dispositions.values() if d.get("status") == STATUS_PATCHED)
        if record.g3_patched > itemized:
            ledger.inconsistent.append(
                f"patched_without_items:{record.review_id}:{record.g3_patched}>{itemized}"
            )
        if record.g2_confirmed > len(record.issues) + len(record.dispositions):
            ledger.inconsistent.append(
                f"confirmed_without_items:{record.review_id}:"
                f"{record.g2_confirmed}>{len(record.issues) + len(record.dispositions)}"
            )

    ledger.issues = sorted(
        issues.values(),
        key=lambda issue: (issue.status, issue.origin_review, issue.issue_id),
    )
    return ledger
