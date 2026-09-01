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
    messages: list[str] = field(default_factory=list)


def _parse_epubcheck_output(text: str) -> tuple[int, int, list[str]]:
    errors = len(re.findall(r"(?m)^ERROR", text))
    warnings = len(re.findall(r"(?m)^WARNING", text))
    messages = [line for line in text.splitlines() if line.startswith(("ERROR", "WARNING"))]
    return errors, warnings, messages[:50]


def run_epubcheck(epub_path: str | Path, jar_path: str | Path | None = None) -> EpubcheckResult:
    """用 epubcheck jar 校验 EPUB；jar 缺失时返回 available=False。"""
    jar = Path(jar_path) if jar_path else Path.home() / ".cache" / "epubcheck.jar"
    if not jar.is_file():
        return EpubcheckResult(
            available=False,
            ran=False,
            errors=-1,
            warnings=-1,
            messages=["epubcheck jar 未安装；跳过"],
        )

    try:
        proc = subprocess.run(
            ["java", "-jar", str(jar), str(epub_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return EpubcheckResult(
            available=True, ran=False, errors=-1, warnings=-1, messages=[f"epubcheck 执行失败：{e}"]
        )
    errors, warnings, messages = _parse_epubcheck_output(proc.stdout + proc.stderr)
    return EpubcheckResult(
        available=True, ran=True, errors=errors, warnings=warnings, messages=messages
    )
