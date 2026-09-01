"""QA 报告汇总：G4 审计 + epubcheck → report.json。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .audit import AuditResult
from .epubcheck import EpubcheckResult


@dataclass
class QaResult:
    slug: str
    epub_path: str = ""
    audit: dict[str, Any] = field(default_factory=dict)
    epubcheck: dict[str, Any] = field(default_factory=dict)
    g4_audit: str = "pending"
    g4_epubcheck_errors: int = -1
    passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_report(
    slug: str,
    audit: AuditResult,
    epubcheck: EpubcheckResult,
    *,
    epub_path: str = "",
) -> QaResult:
    errors = [f for f in audit.findings if f.level == "error"]
    g4_audit = "pass" if audit.ok else "fail"
    # 未实际运行 epubcheck（jar 缺失）不算通过，只能算「未验证」。
    passed = audit.ok and epubcheck.ran and epubcheck.errors == 0
    return QaResult(
        slug=slug,
        epub_path=epub_path,
        audit={
            "ok": audit.ok,
            "errors": len(errors),
            "findings": [
                {"level": f.level, "code": f.code, "message": f.message} for f in audit.findings
            ],
        },
        epubcheck={
            "available": epubcheck.available,
            "ran": epubcheck.ran,
            "errors": epubcheck.errors,
            "warnings": epubcheck.warnings,
            "messages": epubcheck.messages or [],
        },
        g4_audit=g4_audit,
        g4_epubcheck_errors=epubcheck.errors if epubcheck.ran else -1,
        passed=passed,
    )
