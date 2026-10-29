# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""epubcheck 集成：本地 jar 校验，读取结构化 JSON 诊断，零 error 才放行。"""

from __future__ import annotations

import json
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
    diagnostics: list[dict] = field(default_factory=list)


def _parse_epubcheck_json(text: str) -> tuple[int, int, list[str], list[dict]]:
    """严格读取官方 JSON；缺失/未知严重程度不能被解释为零错误。"""
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
        raise ValueError("缺少 messages 数组")
    errors = warnings = 0
    messages: list[str] = []
    diagnostics: list[dict] = []
    for item in data["messages"]:
        if not isinstance(item, dict):
            raise ValueError("无效诊断条目")
        severity = item.get("severity")
        if severity not in {"FATAL", "ERROR", "WARNING", "INFO", "USAGE", "SUPPRESSED"}:
            raise ValueError("无效诊断严重程度")
        if not isinstance(item.get("ID"), str) or not isinstance(item.get("message"), str):
            raise ValueError("缺少诊断代码或消息")
        locations = item.get("locations", [])
        if not isinstance(locations, list) or any(not isinstance(loc, dict) for loc in locations):
            raise ValueError("无效诊断位置")
        errors += severity in {"FATAL", "ERROR"}
        warnings += severity == "WARNING"
        diagnostics.append(item)
        messages.append(f"{severity}({item['ID']}): {item['message']}")
    # 官方计数可能大于展示条数（重复消息默认有截断），不能仅数数组长度。
    if "checker" in data:
        checker = data["checker"]
        if not isinstance(checker, dict):
            raise ValueError("无效 checker 统计")
        counts = [checker.get(key) for key in ("nFatal", "nError", "nWarning")]
        if any(type(n) is not int or n < 0 for n in counts):
            raise ValueError("无效 checker 错误计数")
        errors = max(errors, counts[0] + counts[1])
        warnings = max(warnings, counts[2])
    return errors, warnings, messages[:50], diagnostics


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
            ["java", "-jar", str(jar), str(epub_path), "--locale", "en", "--quiet", "--json", "-"],
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
    diagnostics: list[dict] = []
    try:
        errors, warnings, messages, diagnostics = _parse_epubcheck_json(proc.stdout)
    except (ValueError, TypeError) as e:
        errors, warnings = 1, 0
        messages = [f"epubcheck JSON 报告无效：{e}", *proc.stderr.strip().splitlines()[:49]]
    if proc.returncode != 0:
        errors = max(errors, 1)
        if not messages:
            messages = proc.stderr.strip().splitlines()[:49]
        messages = [f"epubcheck 进程退出码：{proc.returncode}", *messages][:50]
    return EpubcheckResult(
        available=True,
        ran=True,
        errors=errors,
        warnings=warnings,
        returncode=proc.returncode,
        messages=messages,
        diagnostics=diagnostics,
    )
