"""审校（QC G0–G3）：零 token 校验 + 逐批审校 + 取证 + 仲裁/影子修订。"""

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
from .service import ReviewRun, review

__all__ = [
    "ConvergenceResult",
    "ConvergenceState",
    "G0Flag",
    "Issue",
    "Patch",
    "ReviewRun",
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
    "review",
    "strip_copyright_boilerplate",
    "summarize",
]
