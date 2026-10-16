# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""epubcheck 集成：本地 jar 校验，零 error 放行（测试中跳过）。"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EpubcheckResult:
    available: bool  # jar 是否存在
    ran: bool  # 是否实际执行
    errors: int
    warnings: int
    returncode: int | None  # 实际进程退出值；未执行时未知，不能推断为 0。
    messages: list[str] = field(default_factory=list)


def _parse_epubcheck_output(text: str) -> tuple[int, int, list[str]]:
    errors = len(re.findall(r"(?m)^(?:ERROR|FATAL)\b", text))
    warnings = len(re.findall(r"(?m)^WARNING", text))
    messages = [
        line for line in text.splitlines() if line.startswith(("ERROR", "FATAL", "WARNING"))
    ]
    return errors, warnings, messages[:50]


def run_epubcheck(epub_path: str | Path, jar_path: str | Path | None = None) -> EpubcheckResult:
    """运行本地校验器；非零退出或 fatal 诊断均不得视为零错误。"""
    jar = Path(jar_path).expanduser() if jar_path else Path.home() / ".cache" / "epubcheck.jar"
    if not jar.is_file():
        return EpubcheckResult(
            available=False,
            ran=False,
            errors=-1,
            warnings=-1,
            returncode=None,
            messages=["epubcheck jar 未安装；跳过"],
        )

    try:
        proc = subprocess.run(
            ["java", "-jar", str(jar), str(epub_path), "--locale", "en"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return EpubcheckResult(
            available=True,
            ran=False,
            errors=-1,
            warnings=-1,
            returncode=None,
            messages=[f"epubcheck 执行失败：{e}"],
        )
    output = "\n".join((proc.stdout, proc.stderr))
    errors, warnings, messages = _parse_epubcheck_output(output)
    if proc.returncode != 0:
        errors = max(errors, 1)
        if not messages:
            messages = output.strip().splitlines()[:49]
        messages = [f"epubcheck 进程退出码：{proc.returncode}", *messages][:50]
    return EpubcheckResult(
        available=True,
        ran=True,
        errors=errors,
        warnings=warnings,
        returncode=proc.returncode,
        messages=messages,
    )
