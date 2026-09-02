"""QA 报告汇总：G5 交付验收 = G0 静态告警 + G1–G3 审校结果 + G4 结构审计 → report.json。"""

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
    # G5 交付验收（聚合 G0–G3）
    g0_flags: list[dict[str, Any]] = field(default_factory=list)
    g1_candidates: int = 0
    g2_confirmed: int = 0
    g3_patched: int = 0
    g3_termination: str = ""
    g3_rounds: int = 0
    total_sentences: int = 0
    error_rate: float = 0.0
    released: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_report(
    slug: str,
    audit: AuditResult,
    epubcheck: EpubcheckResult,
    *,
    epub_path: str = "",
    review: dict[str, Any] | None = None,
    g0_flags: list[dict[str, Any]] | None = None,
    total_sentences: int = 0,
) -> QaResult:
    """聚合 G0–G4 生成放行报告。

    ``review`` 是最新一次审校的 result.json（g1_candidates/g2_confirmed/g3_patched/
    termination/rounds）；``g0_flags`` 是 G0 静态校验告警；``total_sentences`` 是全部
    align 句数（用于差错率分母）。
    """
    errors = [f for f in audit.findings if f.level == "error"]
    g4_audit = "pass" if audit.ok else "fail"
    # 未实际运行 epubcheck（jar 缺失）不算通过，只能算「未验证」。
    passed = audit.ok and epubcheck.ran and epubcheck.errors == 0

    rev = review or {}
    g1_candidates = int(rev.get("g1_candidates", 0) or 0)
    g2_confirmed = int(rev.get("g2_confirmed", rev.get("issue_count", 0)) or 0)
    g3_patched = int(rev.get("g3_patched", 0) or 0)
    g3_termination = str(rev.get("termination", ""))
    g3_rounds = int(rev.get("rounds", 0) or 0)
    flags = list(g0_flags or [])
    error_rate = (g2_confirmed / total_sentences) if total_sentences else 0.0

    # 放行条件（对齐 AGENTS.md G5）：确认问题为零或全部已修订；epubcheck 零 error；审计通过。
    # G0 告警是给 G1 的确定性线索（advisory），不作为放行硬条件——英→中等语言对
    # 长度比天然偏低，实测会产生大量误报（豆包实测 994 条均为误报）。
    confirmed_resolved = g2_confirmed == 0 or g2_confirmed <= g3_patched
    released = confirmed_resolved and epubcheck.ran and epubcheck.errors == 0 and audit.ok

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
        g0_flags=[dict(f) for f in flags],
        g1_candidates=g1_candidates,
        g2_confirmed=g2_confirmed,
        g3_patched=g3_patched,
        g3_termination=g3_termination,
        g3_rounds=g3_rounds,
        total_sentences=total_sentences,
        error_rate=round(error_rate, 6),
        released=released,
    )
