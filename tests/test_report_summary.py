"""E2：G0 摘要与完整明细（计数不因明细文件而丢失）。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from auto_common.workspace import RunStore
from auto_epublizer.orchestrator import _write_g0_details
from auto_epublizer.qa import AuditResult, EpubcheckResult, generate_report, summarize_g0


def _report(flags):
    return generate_report(
        "book",
        AuditResult(ok=True),
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0, returncode=0),
        g0_flags=flags,
    )


def test_summary_keeps_total_and_blocking_split() -> None:
    flags = [
        {"unit": "ch01", "check": "length", "message": "low", "blocking": False},
        {"unit": "ch01", "check": "length", "message": "empty", "blocking": True},
        {"unit": "ch02", "check": "terminology", "message": "miss", "blocking": True},
    ]
    summary = summarize_g0(flags)
    assert summary["length"] == {"total": 2, "blocking": 1, "advisory": 1}
    assert summary["terminology"]["blocking"] == 1

    report = _report(flags)
    assert report.g0_total == 3
    assert report.g0_summary == summary


def test_details_file_is_sorted_and_digest_bound(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "ws")
    store.ensure_skeleton()
    flags = [
        {"unit": "ch02", "check": "length", "message": "b", "blocking": False},
        {"unit": "ch01", "check": "terminology", "message": "a", "blocking": True},
    ]
    report = _report(flags)
    _write_g0_details(store, report, flags)

    path = store.output_dir / "g0-details.jsonl"
    payload = path.read_bytes()
    assert report.g0_detail_sha256 == hashlib.sha256(payload).hexdigest()
    assert report.g0_detail_path == str(path.relative_to(store.dir))
    lines = [json.loads(line) for line in payload.decode().splitlines()]
    assert [row["check"] for row in lines] == ["length", "terminology"]  # 稳定排序（按序列化键）
    assert len(lines) == report.g0_total

    # 无 flags 时不写文件（也不产生空摘要文件）
    other = RunStore(tmp_path / "ws2")
    other.ensure_skeleton()
    empty = _report([])
    _write_g0_details(other, empty, [])
    assert not (other.output_dir / "g0-details.jsonl").exists()


def test_report_records_software_detail_and_rights_presence() -> None:
    """#72-5：rights 详略与权利字段是否存在必须可被机器消费。"""
    report = generate_report(
        "book",
        AuditResult(ok=True),
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0, returncode=0),
        software_detail="rights",
        rights_present=False,
    )
    assert report.software_detail == "rights"
    assert report.rights_present is False


def test_report_records_hygiene_candidate_counts() -> None:
    """#85：卫生候选数进入报告，但仍是 advisory。"""
    report = generate_report(
        "book",
        AuditResult(ok=True),
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0, returncode=0),
        hygiene={"candidates": 4, "cross_page": 2},
    )
    assert (report.hygiene_candidates, report.hygiene_cross_page) == (4, 2)
    assert report.released is True
