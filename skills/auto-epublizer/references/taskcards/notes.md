<!-- i18n: source=notes.zh.md sha256=407a83abd27e28d4bd0e03d942841d012bae87c770a0256d25d349c630901034 -->
> **English** | [中文](notes.zh.md)

# Task card: notes (verify / register)

Stage document: `references/notes.md`.

**Situation (restated from disk)**: `next_tasks[0].kind` is `notes_verify` or
`notes_register` — the book really does carry note candidates:
`preprocessing/note_candidates.jsonl` has pending entries, or `structured/notes.json` is not
registered yet / has gone stale because the source or structure changed.

**Action (`notes_verify`)**: go back to the source (page-bottom / margin / facing-page
evidence) and verify the candidates one by one, writing `disposition=note|not_note` back into
`preprocessing/note_candidates.jsonl`; write the ones judged as notes into
`structured/notes.json` (note content + source reference position/evidence) and keep the
`[^ref-…]` in-place marker at the **original reference position** in the body (the source JSON
maps ref_id → note_id).

**Action (`notes_register`)**: run `auto-epublizer notes register` to register
`structured/notes.json` — the separation-registration gate performs contract validation,
two-way marker reconciliation and writes the digest into `publication.json`.

**Done criterion**: the `notes` section of `status --json` shows the registration and the
digest matches what is on disk; during translation, write the complete translated note under
the same `note_id` into `translation/notes.json`, which `import`'s translation gate validates
(marker conservation + all translations present + digest binding).

**Failure handling**: fix contract errors one by one following the messages (**never**
hand-edit `publication.json`); do not skip pending candidates — a book with notes that yields
zero semantic nodes, partial omission, wrong target/content or broken backlinks is blocked at
the product gate with `notes_open` (`E_NOTES_*` points at the concrete ref/file).
