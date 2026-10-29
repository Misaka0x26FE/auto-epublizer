# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""结构化校验报告不能因缺字段、损坏或非零退出而假绿。"""

import json
import subprocess

import pytest

from auto_epublizer.qa.epubcheck import run_epubcheck


def _run(tmp_path, monkeypatch, report, returncode=0):
    jar = tmp_path / "checker.jar"
    jar.touch()

    def execute(command, **kwargs):
        assert "--json" in command
        return subprocess.CompletedProcess(command, returncode, report, "")

    monkeypatch.setattr(subprocess, "run", execute)
    return run_epubcheck(tmp_path / "book.epub", jar)


def test_json_diagnostics_preserve_location(tmp_path, monkeypatch):
    data = {
        "messages": [
            {
                "ID": "RSC-005",
                "severity": "ERROR",
                "message": "Bad XML",
                "locations": [{"path": "ch01.xhtml", "line": 12, "column": 4}],
            }
        ]
    }
    result = _run(tmp_path, monkeypatch, json.dumps(data), 1)
    assert result.errors == 1
    assert result.diagnostics[0]["locations"][0]["line"] == 12
    assert "RSC-005" in " ".join(result.messages)


@pytest.mark.parametrize(
    "data", ["", "bad json", "{}", "[]", '{"messages": null}', '{"messages": [{}]}']
)
def test_invalid_report_fails_closed(tmp_path, monkeypatch, data):
    assert _run(tmp_path, monkeypatch, data).errors > 0


@pytest.mark.parametrize("code", [0, 1])
def test_empty_valid_report_requires_successful_exit(tmp_path, monkeypatch, code):
    result = _run(tmp_path, monkeypatch, '{"messages": []}', code)
    assert (result.errors == 0) == (code == 0)


def test_json_fatal_even_with_success_exit(tmp_path, monkeypatch):
    result = _run(
        tmp_path,
        monkeypatch,
        json.dumps(
            {
                "messages": [
                    {"ID": "PKG-008", "severity": "FATAL", "message": "bad", "locations": []}
                ]
            }
        ),
    )
    assert result.errors == 1
