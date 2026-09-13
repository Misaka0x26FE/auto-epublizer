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
    g0_terminology_open: int = 0  # 术语命中告警数：真实缺陷，必须清零才能放行
    g0_structure_open: int = 0  # 标记/脚注守恒等结构违例数：真实缺陷，必须清零才能放行
    glossary_conflicts_open: int = 0  # 术语冲突未裁决数：真实缺陷，必须清零才能放行
    catalog_unresolved_open: int = 0  # 源盘点未决项数（catalog.csv 存在时才检查）
    g1_candidates: int = 0
    g2_confirmed: int = 0
    g3_patched: int = 0
    g3_termination: str = ""
    g3_rounds: int = 0
    total_sentences: int = 0
    error_rate: float = 0.0
    released: bool = False
    released_reason: str = ""  # ok | epubcheck_not_run | epubcheck_errors | audit_failed | unresolved_confirmed | provenance_incomplete
    # 溯源审计（postprocessing-spec §3.2）
    provenance_coverage: float | None = None
    units_missing: int = 0
    units_order_ok: bool = True
    media_lost: int = 0
    toc_missing: list[str] = field(default_factory=list)
    toc_flat: bool = False
    inserts_missing_files: int = 0
    # 交付审计 S1：md↔align 一致性 + EPUB 呈现对账（error 级发现已在 provenance_findings）
    align_md_drift: int = 0
    epub_media_missing: int = 0
    epub_footnotes_missing: int = 0
    epub_coverage: float | None = None
    provenance_findings: list[dict[str, Any]] = field(default_factory=list)

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
    provenance: dict[str, Any] | None = None,
    toc_missing: list[str] | None = None,
    glossary_conflicts_open: int = 0,
    catalog_unresolved_open: int = 0,
) -> QaResult:
    """聚合 G0–G4 + 溯源审计生成放行报告。

    ``review`` 是最新一次审校的 result.json（g1_candidates/g2_confirmed/g3_patched/
    termination/rounds）；``g0_flags`` 是 G0 静态校验告警；``total_sentences`` 是全部
    align 句数（用于差错率分母）；``provenance`` 是溯源审计结果
    （qa/provenance.py）；``toc_missing`` 是 facts 源 TOC 对账缺失标题；
    ``glossary_conflicts_open`` 是术语冲突未裁决条数（glossary_conflicts.jsonl
    中 status=open）。
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
    g0_terminology_open = sum(1 for f in flags if f.get("check") == "terminology")
    # 结构违例：标记/脚注守恒（S1.2）+ 表格形状/源保真（S4.1/S4.2 预留）
    g0_structure_open = sum(
        1 for f in flags if f.get("check") in ("marker", "footnote", "table", "fidelity")
    )
    error_rate = (g2_confirmed / total_sentences) if total_sentences else 0.0

    # 溯源审计结果映射（postprocessing-spec §5 放行扩展）
    prov = provenance or {}
    coverage = prov.get("coverage")
    units_missing = len(prov.get("units_missing") or [])
    units_order_ok = bool(prov.get("units_order_ok", True))
    media_lost = len(prov.get("media_lost") or [])
    toc_flat = bool(prov.get("toc_flat"))
    prov_findings = list(prov.get("findings") or [])
    inserts_missing_files = int(prov.get("inserts_missing_files") or 0)
    # 交付审计 S1：md↔align 一致性 + EPUB 媒体/脚注/段落呈现对账
    align_md_drift = len(prov.get("align_md_drift") or [])
    epub_media_missing = len(prov.get("epub_media_missing") or [])
    epub_footnotes_missing = len(prov.get("epub_footnotes_missing") or [])
    epub_coverage = prov.get("epub_coverage")
    # error 级溯源发现必须清零：E_UNIT_ORDER（spine 含未知文档）、E_MEDIA_ORDER
    # （图片相对顺序错乱）、E_INSERT_BAD_SOURCE 等均为真实缺陷（与 provenance.ok 一致）
    prov_error_findings = [f for f in prov_findings if f.get("level") == "error"]
    prov_ok = (
        (coverage is None or coverage >= 0.9999)
        and units_missing == 0
        and units_order_ok
        and media_lost == 0
        and not toc_flat
        and inserts_missing_files == 0
        and align_md_drift == 0
        and epub_media_missing == 0
        and epub_footnotes_missing == 0
        and not prov_error_findings
    )

    # 放行条件（对齐 AGENTS.md G5 + postprocessing-spec §5）：确认问题为零或全部已修订；
    # epubcheck 零 error；审计通过；溯源完整（覆盖率≈1.0、三边对账/媒体溯源零缺失、
    # 目录层级不扁平）。G0 长度比告警是 advisory，不作为放行硬条件——英→中等语言对
    # 长度比天然偏低，实测会产生大量误报（豆包实测 994 条均为误报）。
    # **G0 术语命中（terminology）是真实缺陷**：译文中缺失了术语表的源词，
    # 必须逐条核验清零才可放行（豆包实测曾把术语未命中与长度误报混为一谈而漏检）。
    # **G0 结构违例（marker/footnote/table/fidelity）与未决术语冲突同属硬门**：
    # 标记丢失=插图/脚注在成品中丢失；冲突未裁决=同一术语两种译法并存到成品。
    confirmed_resolved = g2_confirmed == 0 or g2_confirmed <= g3_patched
    released = (
        confirmed_resolved
        and g0_terminology_open == 0
        and g0_structure_open == 0
        and glossary_conflicts_open == 0
        and catalog_unresolved_open == 0
        and epubcheck.ran
        and epubcheck.errors == 0
        and audit.ok
        and prov_ok
    )
    if released:
        reason = "ok"
    elif g0_terminology_open:
        reason = "terminology_open"
    elif glossary_conflicts_open:
        reason = "glossary_conflict_open"
    elif g0_structure_open:
        reason = "structure_open"
    elif not confirmed_resolved:
        reason = "unresolved_confirmed"
    elif not audit.ok:
        reason = "audit_failed"
    elif catalog_unresolved_open:
        reason = "catalog_open"
    elif not prov_ok:
        reason = "provenance_incomplete"
    elif not epubcheck.ran:
        reason = "epubcheck_not_run"
    else:
        reason = "epubcheck_errors"

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
        g0_terminology_open=g0_terminology_open,
        g0_structure_open=g0_structure_open,
        glossary_conflicts_open=glossary_conflicts_open,
        catalog_unresolved_open=catalog_unresolved_open,
        g1_candidates=g1_candidates,
        g2_confirmed=g2_confirmed,
        g3_patched=g3_patched,
        g3_termination=g3_termination,
        g3_rounds=g3_rounds,
        total_sentences=total_sentences,
        error_rate=round(error_rate, 6),
        released=released,
        released_reason=reason,
        provenance_coverage=round(coverage, 6) if coverage is not None else None,
        units_missing=units_missing,
        units_order_ok=units_order_ok,
        media_lost=media_lost,
        toc_missing=list(toc_missing or []),
        toc_flat=toc_flat,
        inserts_missing_files=inserts_missing_files,
        align_md_drift=align_md_drift,
        epub_media_missing=epub_media_missing,
        epub_footnotes_missing=epub_footnotes_missing,
        epub_coverage=round(epub_coverage, 6) if epub_coverage is not None else None,
        provenance_findings=prov_findings,
    )
