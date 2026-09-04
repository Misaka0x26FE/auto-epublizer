"""QA：解包逐项审计 + epubcheck 集成 + 质量报告。

- 解包逐项审计：mimetype 首位未压缩、container 指向 OPF、manifest/spine 一致、
  nav 链接可解析、lang 正确、脚注双向跳转（占位）；
- epubcheck：本地 jar 校验，零 error 放行（测试中跳过/可配置）；
- 产出 report.json。
"""

from __future__ import annotations

from .audit import AuditFinding, AuditResult, audit_epub
from .epubcheck import EpubcheckResult, run_epubcheck
from .provenance import ProvenanceResult, audit_provenance
from .report import QaResult, generate_report

__all__ = [
    "AuditFinding",
    "AuditResult",
    "EpubcheckResult",
    "ProvenanceResult",
    "QaResult",
    "audit_epub",
    "audit_provenance",
    "generate_report",
    "run_epubcheck",
]
