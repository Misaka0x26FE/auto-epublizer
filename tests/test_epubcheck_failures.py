# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""校验进程失败或 fatal 诊断不得被当作零错误放行。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_epublizer.qa import AuditResult, generate_report
from auto_epublizer.qa.epubcheck import run_epubcheck


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr"),
    [
        (1, "", "Exception in thread main java.lang.NoClassDefFoundError: validator/dependency"),
        (0, "FATAL(PKG-008): Invalid EPUB container.\n", ""),
    ],
    ids=["unrecognized-process-failure", "fatal-diagnostic"],
)
def test_validator_failure_cannot_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    stdout: str,
    stderr: str,
) -> None:
    """仅替换外部进程边界；实际结果解析与发布判定必须拒绝失败。"""
    jar = tmp_path / "checker.jar"
    jar.write_bytes(b"external-tool-boundary")
    completed = subprocess.CompletedProcess([], returncode, stdout, stderr)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)
    checked = run_epubcheck(tmp_path / "book.epub", jar_path=jar)
    report = generate_report("book", AuditResult(ok=True), checked)
    assert report.released is False
    assert report.released_reason == "epubcheck_errors"


def test_old_release_without_exit_evidence_is_stale(tmp_path: Path) -> None:
    """其他产物不变也不能沿用缺进程退出证据的旧放行记录。"""
    import json

    from auto_common.workspace import atomic_write_json
    from auto_epublizer import orchestrator as orch
    from auto_epublizer.qa import EpubcheckResult
    from auto_epublizer.qa.artifacts import artifacts_digest, report_state

    source = tmp_path / "book.md"
    source.write_text("# Chapter I\n\nSource paragraph.\n", encoding="utf-8")
    store = orch.init(str(source), workspace_dir=str(tmp_path / "work"))
    epub = orch.convert(store)
    digest = artifacts_digest(store, epub_path=epub)
    report = generate_report(
        "book",
        AuditResult(ok=True),
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0, returncode=0),
    ).to_dict()
    report.update(artifacts_digest=digest, artifacts_epub=str(epub))
    atomic_write_json(store.report_path, report)
    assert report_state(store)["stale"] is False
    legacy = json.loads(store.report_path.read_text(encoding="utf-8"))
    del legacy["epubcheck"]["returncode"]
    atomic_write_json(store.report_path, legacy)
    assert artifacts_digest(store, epub_path=epub) == digest
    state = report_state(store)
    assert state["stale"] is True
    assert state["reason"] == "epubcheck_unverified"


@pytest.mark.parametrize("returncode", [None, 1], ids=["unknown-exit", "nonzero-exit"])
def test_release_requires_successful_exit_even_when_error_count_is_zero(
    returncode: int | None,
) -> None:
    """聚合器自身守住退出证据，不依赖外部包装器已修正错误计数。"""
    from auto_epublizer.qa import EpubcheckResult

    report = generate_report(
        "book",
        AuditResult(ok=True),
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0, returncode=returncode),
    )
    assert report.passed is False
    assert report.released is False
