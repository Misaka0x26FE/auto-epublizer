"""术语表：三态生命周期 + CSV 权威 + 冲突外置 + 注入过滤。"""

from __future__ import annotations

from .csv_io import (
    Glossary,
    entry_to_row,
    load_glossary_csv,
    load_legacy_category_csv,
    normalize,
    read_conflicts_jsonl,
    row_to_entry,
    save_glossary_csv,
    write_conflicts_jsonl,
)
from .models import (
    GENDERS,
    STATUS_CANDIDATE,
    STATUS_CONFIRMED,
    STATUS_CONFLICT,
    STATUS_SEED,
    TERM_STATUSES,
    TERM_TYPES,
    GlossaryConflict,
    GlossaryEntry,
)
from .terms import TerminologyHit, terminology_hits, terms_in_text

__all__ = [
    "GENDERS",
    "Glossary",
    "GlossaryConflict",
    "GlossaryEntry",
    "STATUS_CANDIDATE",
    "STATUS_CONFIRMED",
    "STATUS_CONFLICT",
    "STATUS_SEED",
    "TERM_STATUSES",
    "TERM_TYPES",
    "TerminologyHit",
    "entry_to_row",
    "load_glossary_csv",
    "load_legacy_category_csv",
    "normalize",
    "read_conflicts_jsonl",
    "row_to_entry",
    "save_glossary_csv",
    "terminology_hits",
    "terms_in_text",
    "write_conflicts_jsonl",
]
