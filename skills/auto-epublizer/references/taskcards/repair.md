<!-- i18n: source=repair.zh.md sha256=efdc74ce9ba13863170597dfd7920bf5b7e31f2e32c48d41f547a68d65f4b43a -->
> **English** | [中文](repair.zh.md)

# Task card: repair

Stage reference: `references/repair.md`.

**Scene (restate from disk)**: An input-repair task with `kind=repair` names the unit and
its suspicious signals. Verification is mandatory for OCR and scanned inputs. When the
task reports a QA failure, find the corresponding diagnostics in `report.json` first.

For PDF source-page candidates, run `auto-epublizer evidence partition --save-tasks`.
When `source_evidence` appears, refresh the snapshot as directed. In `evidence source --json`,
use `page_routes` to locate multicolumn, OCR and coordinate-free pages, and `boundaries` to see
both sides of page breaks. Check single-column reading order against the page and verify
cross-column entries in indexes and bibliographies. Record missing evidence if you cannot inspect a page.
Tasks with a `candidate_id` include the raw page file, block number, text span and nearby
blocks. After checking the page, record that ID, the affected unit and an existing
workspace-relative evidence path in `repairs.jsonl`. Use `unresolved` and name the
missing evidence if you cannot finish the check. After an edit to the structured source,
rerun partition evidence and verify that the content appears in the correct place.

**Action**: per `references/repair.md`, verify `structured/` against raw evidence
(`structured/raw/`, page images) and fix parse defects (line joins, hyphenation, OCR chars,
mojibake, headers/footers, footnote markers, ordering). Write one JSON line per fix to
`preprocessing/repairs.jsonl` with `status` `done` or `unresolved`.

**Done when**: You have checked the unit against the raw evidence and recorded a valid
entry for this unit in `preprocessing/repairs.jsonl`.

**If it fails**: anything you cannot confirm must be recorded as `unresolved` (with
`evidence`), never silently dropped; `qa` will surface unresolved items as a warning.
