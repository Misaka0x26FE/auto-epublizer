<!-- i18n: source=translation.zh.md sha256=01ffe46010734f820a54233da3f4cf542632c3192fc85161be4b1e887cb97f16 -->
> **English** | [中文](translation.zh.md)

# Translation (chunk translation + sentence alignment + terminology loop)

Translation is an **agent task** (single-LLM principle): the agent reads
`structured/<rel_path>.md`, translates paragraph by paragraph with its own abilities,
writes `translation/<rel_path>.md` (mirrored structure) + `translation/align/<unit-id>.jsonl`
(`{seq, src, tgt, note}`), and then **must** run `auto-epublizer import` to register — G0
structural validation (broken seq numbers / empty translations block) + state advance
(translated→aligned) + terminology-conflict externalization. Before import, the unit state
stays at `analyzed`, and `status --json` reports stale.

## Output

```text
translation/
├── body/ch01.md ...      # translation (mirrors the structured relative path)
└── align/ch01.jsonl      # sentence-level alignment
```

## Reference context while translating (reading priority)

Read the understanding-layer artifacts before translating to ensure consistency:

| Layer | Source (falls back to `preprocessing/` when `analysis/` is missing) |
|---|---|
| Whole-book overview | `analysis/overview.md` or `preprocessing/global.md` |
| Style/global | `analysis/global.md` or `preprocessing/global.md` |
| Chapter summary | `analysis/units/<id>.md` or `preprocessing/units/<id>.md` |
| Key points | `analysis/keypoints.md` |
| Terminology subset | the ones actually appearing in this batch of body text in `glossary.csv` (filtered by `terms_in_text`) |
| Previous translation | the `tgt` of completed `align/` (maintain terminology/style continuity) |

When both exist, `analysis/` takes priority; the pure-agent preprocessing path uses
`preprocessing/`.

## Sentence-level alignment

`translation/align/<id>.jsonl`, one sentence per line:

```jsonl
{"seq": 1, "src": "source sentence", "tgt": "translated sentence", "note": null}
```

- `seq` is the anchor for translation validation, fidelity review, QA location and resume, starting from 1 and consecutive.
- Paragraph-level equal length: one source paragraph usually corresponds to one sentence
  (or several); splits/merges are declared in `note`; `note` records splits/merges/
  omissions/doubts (the prefix `corr:wrong→right` records source-erratum precedents).

Empty align is allowed only when **both existing, nonempty** `structured/` and
`translation/` documents contain only canonical ATX heading lines and blanks. Missing/empty
source, body immediately after a heading without a blank, or extra target body is not exempt.
Import and G0/QA share this test; per-level `heading` conservation still applies.

### Block identity (paragraph ↔ contiguous seq range)

Paragraph identity is **not a column in align**: every row is still a sentence. Blocks come
from `content_blocks` (headings and pure comments skipped, fenced code its own block, block
numbers from 1, the same split used by coverage and source fidelity). One block maps to a
**contiguous** `seq` range; several sentences per block are normal, and splitting/merging
sentences changes the count, not the block identity.

- Allowed: one block with many sentences; one sentence split across rows (`note=split`);
  duplicated text taking one row each in order; newline/indent-only changes.
- Structural change: merging/splitting blocks, adding/removing blocks, reordering, or putting
  one sentence into two blocks — import must register a new baseline.
- When derivation fails (missing sentence, wrong order) report an issue instead of guessing
  boundaries; a historical workspace without a baseline is `unknown`.
- The baseline is a hash over block number/kind/seq range/block-text digest
  (`review/blocks.py:structure_digest`), written to `meta.align_structure` on the unit in
  `publication.json` by a successful import. Newlines inside a block do not invalidate it.
  `qa`/delivery audit re-derive and compare: a mismatch with a baseline is a block-boundary
  defect (`E_ALIGN_MD_DRIFT`); a missing baseline or ambiguous mapping is
  `align_structure_unknown` and does not block migrating historical books.
  `import --force` re-registers it.
- **Source and target blocks are numbered independently and need not match in count**: source
  blocks serve fidelity/coverage, target blocks serve md↔align drift, and the two connect only
  through each align row's `src`. "Rows = paragraphs" or "normalized full text is equal" never
  substitutes for checking block boundaries.

### Read-only rebuild proposal

`auto-epublizer align-propose --workspace <dir> [--unit ch01]` prints JSON and writes no formal
file: `mappings[]` carries `status` (`exact` / `merge` / `split` / `propose` / `unmatched`),
`source_blocks`, `seq_range`, reused verified `rows`, `uncovered` source blocks and `issues`.

- Correspondence comes from overlapping block and seq ranges, not cross-language text
  similarity; duplication, OCR gaps and heavy rewriting are never auto-accepted.
- `propose` means no align row covers that target block: candidates only, no rows; sentence
  ownership after splitting is confirmed by the agent before align is written.
- A proposal is not an applied result; writing goes through the explicit B4 transaction
  (the `repair apply --apply` family).

### Explicit apply and recovery

```bash
auto-epublizer align-apply plan.json --workspace <dir>          # read-only precheck (default)
auto-epublizer align-apply plan.json --workspace <dir> --apply  # explicit write
```

The plan binds SHA-256 values for the source, `translation/` and `align/`; a failed precheck
or a file changed after the precheck is rejected. Before writing, a journal persists the old
bytes, statuses and unit meta; any failure restores both files and registrations. On success
the baseline and import digests are re-registered, and `reviewed`/`built` fall back to
`aligned`. `already_applied` means the current align bytes *and* baseline already equal the
plan result, so retrying the same successful plan is idempotent.

- **Interruption and recovery**: while a `pending` / `rollback_incomplete` journal exists,
  ordinary commands (including `status`) stop with "存在未决重对齐事务"; use
  `align-apply --recover` (or `repair recover`) to restore files and unit state from the
  journal. Only a fully successful restore writes `rolled_back`; otherwise the journal stays
  `rollback_incomplete` and the command exits non-zero, so it can be retried after fixing the
  fault.
- A failed state restore is never swallowed: any failing step reports "回滚未完成" instead
  of claiming a rollback.

### Read-only hygiene scan

`auto-epublizer hygiene --workspace <dir> [--unit ch01]` prints JSON (`writes: false`) with
`unit`, `block`, `seq_range`, `context` and candidate types: residual source-language words,
unbalanced quotes/brackets, adjacent duplicated words, half sentences, overlong blocks and
suspected tail loss. `translation/notes.json` is scanned too (with `note_id`).

- Everything is **advisory**: candidates are located, never judged semantically, rewritten or
  treated as a substitute for agent review.
- Negative controls: fenced/inline code is ignored; bibliography/index/glossary units are
  skipped; abbreviation dots do not raise half sentences; a colon lead-in followed by a block
  does not raise tail loss; quotes pair across the whole unit, so cross-paragraph quotations
  are allowed.
- Candidates need human verification; confirmed defects go through `repair apply`/rebuild,
  never bulk edits from scanner output.

## Handling special segments (PDF content-extraction artifacts)

PDF ingest produces three kinds of non-plain-text segments (for the source see
`references/ingest.md`; description files are in `structured/raw/inserts/`). Handle them by
type when translating:

| Segment form | Handling |
|---|---|
| Image-reference segment: `![p012-img01](raw/media/…)` | **Keep as-is**; do not translate alt (alt is an inserts id, not content); the translated segment just needs to match the source segment to pass G0 |
| Formula segment: `$$raw extracted text$$` | Keep the `$$…$$` wrapping; the formula text inside is **not translated** (mostly garbled symbols, keep the translation as-is; real LaTeX goes into the inserts `latex`, see next section) |
| markdown table segment: `\| a \| b \|…` | Translate the **cell text**, keep the pipe characters / separator rows / alignment structure; do not add blank lines at either end of the table to merge it |

## inserts completion (agent task: semantic fields)

The deterministic fields (id/type/source/file) of `raw/inserts/<id>.json` are generated by
the CLI; **the semantic fields are completed by you** — timing: after that unit's
translation is done and before running `qa`. The provenance audit takes the single
`<id>.json` file as authoritative (`index.jsonl` is only a snapshot and need not be
changed):

1. **Mandatory · all records**: go back to the source page by `source.page` (turn to that
   page in a PDF viewer) and verify the content, then write `content_desc` — **what this
   illustration/table/formula is about and why it appears here** (one or two sentences is
   enough);
2. **formula records**: hand-write `latex` (locate the formula on the page by
   `source.bbox`; the raw extracted text inside `$$…$$` is for reference only, the image is
   authoritative);
3. Optional: confirm the file is on disk (`source.file` corresponds to
   `structured/raw/<file>`) — if missing it reports `E_INSERT_MISSING_FILE`, see
   `references/qa.md`.

Not completing them does not block the build (W-level warning), but `content_desc` goes
into the EPUB's image alt/caption position, and an empty description directly affects
product quality — **treat it as mandatory**.

## Three-state terminology loop

```text
seed ── agent writes glossary.csv + references/user import (preprocessing/terms.csv pre-extraction)
    │
inject ── inject filtered by terms_in_text (confirmed translations must be followed)
    │
import ── terminology-conflict detection; same source with a different target is recorded as a conflict
    │
record ── conflicts are appended to analysis/glossary_conflicts.jsonl (done automatically by import)
    │
resolve ── agent reads the conflict file and makes the final arbitration, writing back to glossary.csv (authoritative)
    │
store ── knowledge import: merge the workspace's confirmed terms into the unified store (cross-book reuse + auto git commit)
```

**After the arbitration is written back to glossary.csv, re-run `g0` on all translated
units** — old-translation violations (`terminology`) are cleared on the spot; do not only
check the newly translated units; before unresolved conflicts are written back, `qa` will
not release (`glossary_conflict_open`).

- **Cross-book reuse**: seed `preprocessing/terms.csv` from the unified store with
  `knowledge export` before starting; after this workspace's terminology is finalized, write
  it back with `knowledge import` (default `~/Documents/auto-epublizer/`, a private git
  repository; `knowledge push` syncs across devices); the same key with a different target
  across books is externalized to the store's `conflicts.jsonl` pending your arbitration.

- Conflicts do not automatically override confirmed translations; the candidate is kept
  pending arbitration (corresponding to "unified translated names + established usage").
- `import --terms <csv>` can batch-import new terminology proposals extracted by the agent
  (three states auto-determined: new source→seed, a different translation from
  confirmed→conflict).
- Appellations/honorifics/speech tics/fixed expressions (source-only types) are
  classification annotations of the genre profile; the terminology hit check uniformly
  matches all types by literal/word boundary.
- For evidence-backed retention of original titles/quotations, use the optional
  `preprocessing/terminology_exemptions.csv` with required columns `unit,source,reason`.
  Match the exact unit and canonical glossary source; record source-verification evidence
  in `reason`, never blanket-waive real mistranslations. Fully blank rows are skipped;
  partial rows or whitespace-only reasons fail; an absent file means no exemptions.
  A hit is `terminology_exempt` (`blocking=false`, `data.reason`), visible in import
  warnings, standalone `g0`, and QA `g0_flags`. Other terminology violations still block.
  See `qa.md` for report invalidation.
- **Excerpt `src` verbatim**: each line's `src` in align must be taken verbatim from
  `structured/` (a heading line can also serve as src) — import performs source-fidelity
  validation; a rewritten/truncated/fabricated src blocks registration (for source errata
  change only `tgt` and leave a trace with the `corr:` note; do not change src in passing).
- **Table shape must match the source**: the number of md pipe tables and the row/column
  count of each table in the translation must be the same as in `structured/` (cell content
  is translated normally, the structure does not move) — import hard validation, a
  violation blocks registration (`table`).
- **Not a single marker may be lost**: `{fig:NNN}` insert markers and footnote markers
  (`[^label]`/sentence-final digits) must total the same in the translation as in the
  source (splits/merges may move them, but they must not be lost) — G0 unit-level
  conservation validation; loss is a hard defect (`marker`/`footnote`) that blocks G5
  release.

## Copied prose and severely short translation gates

Normalized identical `src`/`tgt` prose emits blocking `language` as a **review signal**,
not proof of a semantic omission. Only standalone headings, images, link-only locators,
anchors and literal code are outside scope; an inline note marker never exempts a whole
paragraph. Unicode letters are supported. Explicit same-source/target-language conversion
does not require translation; Chinese source copied to an English target is not exempt.
The signal examines prose after removing headings/furniture and code: Chinese headings
cannot hide copied foreign prose. For a Chinese target, a few embedded CJK characters do
not exempt identical prose when CJK accounts for less than half of its alphabetic characters.
This heuristic requests review, not a language or mistranslation verdict. Literal code is
excluded from the severe-short rule's source and target character counts.

Optional `preprocessing/style_exemptions.csv` requires `unit,pattern,style_ref,reason`.
`pattern` is a regex (empty means the whole unit for the copying check); `style_ref` must
be nonempty and resolve to a real entry in `analysis/style.md` (`§5` matches `## 5.`).
Matches remain visible as advisory `language_exempt`. Example (exempt the bibliography
block only, never copied body prose in the same unit):

```csv
unit,pattern,style_ref,reason
ch07,^Müller, Hans\.,§5,§5 bibliographic style: retain the German entry verbatim
```

A same-unit `This copied body sentence…` still emits blocking `language`; an empty
translation stays blocking and cannot be exempted by a style regex. `language_exempt`
carries the matched `seq` and source `head` as block-level evidence, and changing the
translation or the evidence files invalidates the report digest. Do not exempt an entire
index when the user has explicitly required localized headwords. The agent must verify the
actual reason, not merely fill fields.

The separate severe-short gate emits blocking `length_review` when source prose contains
at least 80 alphabetic characters and a nonempty translation retains at most four, after
excluding standalone furniture/code. Existing 0.30/3.0 ratio advisories are unchanged.
Repair against the source, or provide a **nonempty source-specific regex** and written
style evidence; accepted cases remain advisory `length_review_exempt`. An empty translation
always blocks and cannot be exempted. These deterministic signals cannot detect all omissions.

## State machine and resume

Unit: `split → analyzed → translated → aligned → reviewed → built`. `import` sets a
completed unit to `aligned`; repeated import is harmless (idempotent). After review passes,
`import --reviewed` can advance newly validated units to `reviewed` in the same call
(idempotent); import normally skips `reviewed`/`built` units. Failed forced revalidation
must not promote a unit back to reviewed.
Successful imports register byte digests for structured/translation/align. If a completed unit's bytes change, ordinary import reports `E_STATE_DRIFT` instead of silently skipping it. In `status --json`, each unit exposes `content_state` (`current/changed/unknown`) and current `content_digests`. Verify source changes and run `restructure` first; for translation/align revisions use `import --unit ID --force`. Legacy workspaces without import digests remain unknown, with an explicit revalidation hint in skip details; unchanged units still skip idempotently. `--force` validates existing translation/align artifacts; it does not assemble private intermediate files such as `.work`.

## Chunk scratch workflow (optional)

Long units may be translated in chunks, but **chunks are not a translation authority**:
the official artifacts remain `translation/<rel>.md` and
`translation/align/<id>.jsonl`.

```bash
auto-epublizer chunk export --workspace <ws> [--unit ch01]   # preprocessing/chunks/<unit>/
# translate <unit>/0001.zh.md … (same block count as index.json)
auto-epublizer chunk assemble ch01 --workspace <ws>          # preflight only
auto-epublizer chunk assemble ch01 --apply --workspace <ws>  # transactional write
auto-epublizer chunk recover --workspace <ws>                # restore a pending transaction
auto-epublizer chunk reset ch01 --apply --workspace <ws>     # archive chunks after source change
auto-epublizer chunk import-tr --source <old/.tr> --apply    # explicit legacy import
```

- Block identity = unit + seq + source digest; after a source change `export` refuses to
  rewrite the index silently — run `reset` first.
- `assemble` checks source digest, block count and heading; it refuses to overwrite a
  hand-edited official translation unless `--force`.
- `.tr` import accepts only directories whose file count matches the index; missing blocks
  are never guessed.
- Block-level align is paragraph-level and still validated by import/G0/delivery, but it
  changes the `total_sentences` denominator.
