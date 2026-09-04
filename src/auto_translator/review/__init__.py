"""审校（QC G0–G3）：G0 零 token 校验 + agent 手写审校产物的 schema/常量契约。

G1–G3 的语义审校由操作 CLI 的 agent 完成：agent 按 G0–G3 语义自行审校，
写 ``reviews/review-<ts>/``（issues/patches/summary/result.json），qa 从 result.json
读 g1/g2/g3 计数与收敛状态。本包只提供：
- g0：确定性静态校验（import/g0 命令使用）；
- models：Issue/Patch schema（agent 产出物的数据契约）；
- convergence：TERMINATION_* 常量与收敛状态机（agent 判定收敛的参照）。
"""

from __future__ import annotations

from .convergence import ConvergenceResult, ConvergenceState, advance, summarize
from .g0 import (
    G0Flag,
    annotate_correction_notes,
    apply_corrections,
    check_alignment,
    count_footnote_refs,
    count_heading_levels,
    count_markers,
    count_paragraph_blocks,
    detect_corrections,
    g0_unit_flags,
    length_ratio,
    markers_conserved,
    normalize_punctuation,
    repair_missing_hyphens,
    strip_copyright_boilerplate,
)
from .models import Issue, Patch

__all__ = [
    "ConvergenceResult",
    "ConvergenceState",
    "G0Flag",
    "Issue",
    "Patch",
    "advance",
    "annotate_correction_notes",
    "apply_corrections",
    "check_alignment",
    "count_footnote_refs",
    "count_heading_levels",
    "count_markers",
    "count_paragraph_blocks",
    "detect_corrections",
    "g0_unit_flags",
    "length_ratio",
    "markers_conserved",
    "normalize_punctuation",
    "repair_missing_hyphens",
    "strip_copyright_boilerplate",
    "summarize",
]
