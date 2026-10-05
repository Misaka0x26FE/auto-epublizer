<!-- i18n: source=repair.zh.md sha256=6b700c30ad7d8b6ff6646898915896ffae606dae81bb6e9317fb2f2e26f4eec9 -->
> **English** | [中文](repair.zh.md)

# Task card: repair

Stage reference: `references/repair.md`.

**Scene (restate from disk)**: `next_tasks[0].kind=repair` — `facts` flagged
`repair_signals.units > 0` and `preprocessing/repairs.jsonl` does not exist. Mandatory for
OCR / scanned paths.

**Action**: per `references/repair.md`, verify `structured/` against raw evidence
(`structured/raw/`, page images) and fix parse defects (line joins, hyphenation, OCR chars,
mojibake, headers/footers, footnote markers, ordering). Write one JSON line per fix to
`preprocessing/repairs.jsonl` with `status` `done` or `unresolved`.

**Done when**: `preprocessing/repairs.jsonl` exists.

**If it fails**: anything you cannot confirm must be recorded as `unresolved` (with
`evidence`), never silently dropped; `qa` will surface unresolved items as a warning.
