# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""issue #68 回归：审校账本（跨审校有效问题集合）与放行失效链。

现场错误：全书 24 项未结后跑一次局部审校（clean），qa 只读目录名最新的
``result.json`` → 24 项凭空归零、成品放行。本文件按「血缘/范围/证据」三件事
分别给出正负例，并验证报告失效链覆盖**全部**审校记录而非最新一份。
"""

from __future__ import annotations

import json
from pathlib import Path

from auto_common.config import Config
from auto_epublizer import orchestrator as orch
from auto_epublizer.qa import (
    AuditResult,
    EpubcheckResult,
    artifacts_digest,
    generate_report,
    review_ledger,
)
from auto_translator.review.ledger import (
    STATUS_DISMISSED,
    STATUS_OPEN,
    STATUS_PATCHED,
    STATUS_UNKNOWN,
    build_ledger,
    load_record,
)


def _ok_audit() -> AuditResult:
    return AuditResult(ok=True)


def _ok_epubcheck() -> EpubcheckResult:
    return EpubcheckResult(available=True, ran=True, errors=0, warnings=0, returncode=0)


def _ledger(records: list[tuple[str, dict]]) -> object:
    return build_ledger([load_record(review_id, payload) for review_id, payload in records])


def _full(review_id: str, **kw) -> dict:
    payload = {
        "schema_version": 2,
        "review_id": review_id,
        "scope": "full",
        "parent_reviews": [],
        "g2_confirmed": 0,
        "g3_patched": 0,
        "termination": "clean_confirmed",
    }
    payload.update(kw)
    return payload


def _issue(issue_id: str, unit: str = "ch01", **kw) -> dict:
    payload = {"issue_id": issue_id, "unit": unit, "status": "open"}
    payload.update(kw)
    return payload


def _closure(issue_id: str, **kw) -> dict:
    payload = {
        "issue_id": issue_id,
        "status": STATUS_PATCHED,
        "closed_by": "patch-0001",
        "evidence": "align/ch01.jsonl#seq=3",
    }
    payload.update(kw)
    return payload


# ── 旧格式：逐项重登之前一律未结 ────────────────────────────────────────


def test_single_legacy_record_counts_unresolved_as_open() -> None:
    ledger = _ledger([("review-a", {"g1_candidates": 5, "g2_confirmed": 2, "g3_patched": 0})])
    assert ledger.contract == "legacy"
    assert ledger.open == 2 and ledger.blocking is True


def test_legacy_records_are_not_summed_nor_latest_only() -> None:
    """多份旧格式：不能相加（重复计数）也不能只取最新，记一条 unknown 要求重登。"""
    ledger = _ledger(
        [
            ("review-a", {"g2_confirmed": 3, "g3_patched": 0}),
            ("review-b", {"g2_confirmed": 0, "g3_patched": 0}),
        ]
    )
    assert ledger.legacy_unknown is True
    assert ledger.unknown == 1
    assert all(issue.status == STATUS_UNKNOWN for issue in ledger.issues)
    assert ledger.blocking is True


def test_local_clean_does_not_close_book_level_legacy_issues() -> None:
    """现场主症：24 项未结 + 一次局部 clean → 仍 24 项未结。"""
    ledger = _ledger(
        [
            ("review-full", {"g2_confirmed": 24, "g3_patched": 0}),
            ("review-local", _full("review-local", scope="units", units=["ch01"])),
        ]
    )
    assert ledger.open == 24
    assert ledger.blocking is True


# ── v2 契约：血缘 / 范围 / 证据 ─────────────────────────────────────────


def test_full_review_with_evidence_closes_issue() -> None:
    ledger = _ledger(
        [
            ("review-a", _full("review-a", issues=[_issue("i-1")], g2_confirmed=1)),
            (
                "review-b",
                _full(
                    "review-b",
                    parent_reviews=["review-a"],
                    dispositions=[_closure("i-1")],
                    g2_confirmed=1,
                    g3_patched=1,
                ),
            ),
        ]
    )
    assert ledger.open == 0 and ledger.unknown == 0 and not ledger.inconsistent
    assert ledger.closed == 1 and ledger.blocking is False
    assert ledger.issues[0].status == STATUS_PATCHED
    assert ledger.issues[0].closed_in_review == "review-b"


def test_disposition_without_lineage_does_not_close() -> None:
    """目录名字典序在后 ≠ 血缘：独立根不能悄悄关闭别人的问题。"""
    ledger = _ledger(
        [
            ("review-a", _full("review-a", issues=[_issue("i-1")], g2_confirmed=1)),
            ("review-b", _full("review-b", dispositions=[_closure("i-1")], g3_patched=1)),
        ]
    )
    assert ledger.open == 1
    assert any(reason.startswith("closure_without_lineage") for reason in ledger.inconsistent)
    assert ledger.blocking is True


def test_covered_but_undisposed_issue_becomes_unknown() -> None:
    ledger = _ledger(
        [
            ("review-a", _full("review-a", issues=[_issue("i-1")], g2_confirmed=1)),
            ("review-b", _full("review-b", parent_reviews=["review-a"])),
        ]
    )
    assert ledger.open == 0 and ledger.unknown == 1
    assert ledger.issues[0].status == STATUS_UNKNOWN
    assert ledger.blocking is True


def test_local_clean_leaves_other_units_untouched() -> None:
    ledger = _ledger(
        [
            (
                "review-a",
                _full(
                    "review-a",
                    issues=[_issue("i-1", unit="ch01"), _issue("i-2", unit="ch02")],
                    g2_confirmed=2,
                ),
            ),
            (
                "review-b",
                _full(
                    "review-b",
                    scope="units",
                    units=["ch01"],
                    parent_reviews=["review-a"],
                    dispositions=[_closure("i-1")],
                    g2_confirmed=1,
                    g3_patched=1,
                ),
            ),
        ]
    )
    assert ledger.open == 1
    assert {issue.issue_id: issue.status for issue in ledger.issues} == {
        "i-1": STATUS_PATCHED,
        "i-2": STATUS_OPEN,
    }
    assert ledger.blocking is True


def test_closure_requires_closed_by_and_evidence() -> None:
    ledger = _ledger(
        [
            ("review-a", _full("review-a", issues=[_issue("i-1")], g2_confirmed=1)),
            (
                "review-b",
                _full(
                    "review-b",
                    parent_reviews=["review-a"],
                    dispositions=[_closure("i-1", closed_by="", evidence="")],
                    g3_patched=1,
                ),
            ),
        ]
    )
    assert ledger.open == 1
    assert any(reason.startswith("closure_evidence_missing") for reason in ledger.inconsistent)


def test_inflated_patched_count_is_inconsistent() -> None:
    ledger = _ledger(
        [
            ("review-a", _full("review-a", issues=[_issue("i-1")], g2_confirmed=1)),
            (
                "review-b",
                _full(
                    "review-b",
                    parent_reviews=["review-a"],
                    dispositions=[_closure("i-1")],
                    g3_patched=4,
                ),
            ),
        ]
    )
    assert any(reason.startswith("patched_without_items") for reason in ledger.inconsistent)
    assert ledger.blocking is True


def test_missing_parent_is_inconsistent() -> None:
    ledger = _ledger([("review-b", _full("review-b", parent_reviews=["review-gone"]))])
    assert any(reason.startswith("missing_parent") for reason in ledger.inconsistent)


def test_review_cycle_is_inconsistent() -> None:
    records = [
        ("review-a", _full("review-a", parent_reviews=["review-b"])),
        ("review-b", _full("review-b", parent_reviews=["review-a"])),
    ]
    ledger = _ledger(sorted(records, key=lambda item: item[0]))
    assert any(reason.startswith("review_cycle") for reason in ledger.inconsistent)


def test_parent_not_earlier_is_inconsistent() -> None:
    """父记录在目录序里更晚 → 关系无法证明（不能靠时间戳猜测）。"""
    ledger = _ledger(
        [
            ("review-a", _full("review-a", parent_reviews=["review-z"])),
            ("review-z", _full("review-z")),
        ]
    )
    assert any(reason.startswith("parent_not_earlier") for reason in ledger.inconsistent)


def test_inputs_digest_mismatch_downgrades_closure() -> None:
    ledger = _ledger(
        [
            (
                "review-a",
                _full(
                    "review-a",
                    issues=[_issue("i-1")],
                    inputs_digest={"ch01": "aaa"},
                    g2_confirmed=1,
                ),
            ),
            (
                "review-b",
                _full(
                    "review-b",
                    parent_reviews=["review-a"],
                    dispositions=[_closure("i-1")],
                    inputs_digest={"ch01": "bbb"},
                    g3_patched=1,
                ),
            ),
        ]
    )
    assert ledger.unknown == 1
    assert any(reason.startswith("inputs_digest_mismatch") for reason in ledger.inconsistent)


def test_unknown_can_be_resolved_by_later_lineage_review() -> None:
    ledger = _ledger(
        [
            ("review-a", _full("review-a", issues=[_issue("i-1")], g2_confirmed=1)),
            ("review-b", _full("review-b", parent_reviews=["review-a"])),
            (
                "review-c",
                _full(
                    "review-c",
                    parent_reviews=["review-b"],
                    dispositions=[_closure("i-1", status=STATUS_DISMISSED)],
                    g3_patched=1,
                ),
            ),
        ]
    )
    assert ledger.unknown == 0 and ledger.open == 0
    assert ledger.issues[0].status == STATUS_DISMISSED


def test_legacy_opaque_issue_can_be_closed_explicitly() -> None:
    ledger = _ledger(
        [
            ("review-a", {"g2_confirmed": 1, "g3_patched": 0}),
            (
                "review-b",
                _full(
                    "review-b",
                    dispositions=[_closure("opaque:review-a:1")],
                    g3_patched=1,
                ),
            ),
        ]
    )
    assert ledger.open == 0 and ledger.unknown == 0
    assert ledger.blocking is False


# ── 放行判定与报告失效链 ───────────────────────────────────────────────


def test_report_blocks_on_effective_open_issues() -> None:
    ledger = _ledger(
        [
            ("review-full", {"g2_confirmed": 24, "g3_patched": 0}),
            ("review-local", _full("review-local", scope="units", units=["ch01"])),
        ]
    )
    report = generate_report(
        "book",
        _ok_audit(),
        _ok_epubcheck(),
        review={"g1_candidates": 0, "g2_confirmed": 0, "g3_patched": 0},
        review_ledger=ledger.to_dict(),
    )
    assert report.released is False
    assert report.released_reason == "unresolved_confirmed"
    assert report.review_contract == "v2"
    assert report.review_effective_open == 24


def test_report_blocks_on_unknown_and_inconsistent() -> None:
    ledger = _ledger(
        [
            ("review-a", _full("review-a", issues=[_issue("i-1")], g2_confirmed=1)),
            ("review-b", _full("review-b", parent_reviews=["review-a"])),
        ]
    )
    report = generate_report("book", _ok_audit(), _ok_epubcheck(), review_ledger=ledger.to_dict())
    assert report.released is False and report.released_reason == "review_unknown"
    assert report.review_unknown == 1

    bad = generate_report(
        "book",
        _ok_audit(),
        _ok_epubcheck(),
        review_ledger={
            "contract": "v2",
            "open": 0,
            "unknown": 0,
            "inconsistent": ["missing_parent"],
        },
    )
    assert bad.released is False and bad.released_reason == "review_inconsistent"


def test_report_releases_when_ledger_is_clean() -> None:
    ledger = _ledger([("review-a", _full("review-a", termination="clean_confirmed"))])
    report = generate_report("book", _ok_audit(), _ok_epubcheck(), review_ledger=ledger.to_dict())
    assert report.released is True and report.released_reason == "ok"


def test_digest_covers_every_review_record(tmp_path: Path) -> None:
    """改动**非最新**的审校记录也必须使报告过期（旧问题不能被静默改写）。"""
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    older = store.reviews_dir / "review-20260101T000000"
    newer = store.reviews_dir / "review-20260102T000000"
    for directory, count in ((older, 1), (newer, 0)):
        directory.mkdir(parents=True)
        (directory / "result.json").write_text(
            json.dumps({"g2_confirmed": count, "g3_patched": 0}), encoding="utf-8"
        )
    before = artifacts_digest(store)
    (older / "result.json").write_text('{"g2_confirmed": 2, "g3_patched": 0}', encoding="utf-8")
    assert artifacts_digest(store) != before
    ledger = review_ledger(store)
    assert ledger.records == 2
    assert ledger.legacy_unknown is True and ledger.blocking is True


def test_status_exposes_review_ledger(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    directory = store.reviews_dir / "review-20260101T000000"
    directory.mkdir(parents=True)
    (directory / "result.json").write_text('{"g2_confirmed": 2, "g3_patched": 0}', encoding="utf-8")
    data = orch.status(store, as_json=True)
    assert data["review"]["contract"] == "legacy"
    assert data["review"]["open"] == 2
    assert any(item["id"] == "review" for item in data["stale"])
    assert Config()  # 配置对象可正常构造（无隐藏全局状态）
