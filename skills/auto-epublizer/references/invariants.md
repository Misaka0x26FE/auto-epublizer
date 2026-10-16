<!-- i18n: source=invariants.zh.md sha256=a3f7cd0ded72b1dca88488e286a2bf6d9cd66a4615da2c7baeeb8ce7ea89e7db -->
> **English** | [中文](invariants.zh.md)

# Invariants quick-reference card (invariants)

> **Positioning**: the single reference for all machine-verifiable contracts — read this
> before troubleshooting, interpreting qa reports, or making release decisions. Detailed
> interpretation and repair methods are in the per-stage docs (review/qa/build); this card
> is only a quick reference for the full set; where the two conflict, the code and
> docs/quality-control.md prevail.

## 1. Overview of the six gates

| Gate | What it does | Who does it | Hard gate | advisory |
|---|---|---|---|---|
| G0 | static validation (align/length/terminology/marker conservation/footnote conservation) | CLI (`g0`/`import`) | terminology/marker/footnote | length |
| G1 | paragraph-by-paragraph bilingual review | agent | — | — |
| G2 | evidence-gathering re-check | agent | — | — |
| G3 | arbitration+revision+convergence | agent | — | — |
| G4 | epubcheck + unpack audit | CLI (`qa`) | all E_* | W_* |
| G5 | release summary (report.json) | CLI (`qa`) | see §2 | — |

## 2. Full set of G5 release conditions (`qa/report.py::generate_report`)

`released=true` if and only if all of the following are satisfied:

| Condition | `released_reason` when it fails |
|---|---|
| `g2_confirmed == 0` or all revised (`g2_confirmed <= g3_patched`) | `unresolved_confirmed` |
| `g0_terminology_open == 0` (terminology hit = real defect) | `terminology_open` |
| `glossary_conflicts_open == 0` (terminology conflict unresolved; no release before the arbitration is written back to glossary.csv) | `glossary_conflict_open` |
| `g0_structure_open == 0` (**blocking** align/marker/footnote/heading/table/fidelity violations) | `structure_open` |
| `notes_ok` (books with notes: product note gate has no findings; zero-to-zero for none) | `notes_open` |
| `catalog_unresolved_open == 0` (unresolved source-inventory items; only checked when catalog.csv exists) | `catalog_open` |
| `audit.ok` (G4 unpack audit zero error) | `audit_failed` |
| `prov_ok` (coverage≈1.0 or null, units_missing/media_lost/inserts_missing_files/toc_flat, no error-level findings) | `provenance_incomplete` |
| `epubcheck.ran == true` (missing jar or no execution = unverified, no release) | `epubcheck_not_run` |
| `epubcheck.returncode == 0` and `epubcheck.errors == 0` (actual process success, no errors) | `epubcheck_errors` |

reason determination priority = top to bottom of the table above (first g0 hard defects →
conflict → structure → notes → review → audit → provenance → epubcheck).

**Report freshness (B2)**: `report.json` records the `artifacts_digest` taken at generation
time (source hash + each unit's structured/translation/align + note files + latest review
result + product bytes) and the audited `artifacts_epub`. After any artifact changes,
`status`/`status_all`/`ledger` treat that report as stale (`report_stale`, progress
downgraded to `built_not_released`); re-running `qa` also rejects the old product against
the new artifacts (coverage/drift/note-content reconciliation). The old "don't touch files
after review" verbal convention is no longer the only safeguard.

**EPUBCheck process evidence**: `report.epubcheck.returncode` is the actual process exit value, or `null` when not executed; never guess 0 for an unknown result. Jar presence, Java startup, and a legacy `ran` field do not prove success; process failure/FATAL must not count as zero errors. Keep the complete distribution's `lib` beside the jar; headless Java is sufficient. For legacy released reports missing the field or reliable `returncode == 0` evidence, `status`/`status_all`/`ledger` treat them as stale with reason `epubcheck_unverified` (existing `digest_missing` takes priority). Rerun `qa`, never hand-edit the old `released` value or infer that missing evidence means the historical product necessarily passed or failed.

## 3. G0 checks (`auto_translator/review/g0.py::g0_unit_flags`)

Each flag carries a `blocking` field (default True): import blocking, G5 release counting
and CLI red/yellow rendering **all read that field** instead of guessing the level from the
check name or message text (B2 truth-table correction).

| check | semantics | level (`blocking`) |
|---|---|---|
| `align` | seq continuous 1..N, no empty src/tgt; an empty/missing alignment for a unit with a registered translation is a hard gate in qa too | hard |
| `terminology` | glossary source appears but the translation lacks the target | hard |
| `marker` | `{fig:NNN}` etc. markers **unit-level total** src/tgt consistent | hard |
| `footnote` | pandoc `[^label]` + sentence-final numeric note-reference total consistent | hard |
| `heading` | structured↔translation h1–h6 per-level counts (issue #12) | hard |
| `table` | table shape conservation (table count/per-table row-column counts) | hard |
| `fidelity` | forward missing block (may be a legitimate removal) **advisory**; reverse src not in source (rewritten/fabricated) hard | forward `False` / reverse `True` |
| `length` | length ratio (with short-source protection `qc.length_ratio.min_src_chars`) | advisory (`False`) |
| `footnote_suspect` | note-number set difference present on the source side but absent from the translation | advisory (`False`) |

Conservation classes compare **unit-level totals**: splitting/joining sentences so that a
marker moves to an adjacent line does not false-report; loss always reports.

## 4. G4 error-code quick reference (`qa/audit.py` + `qa/provenance.py`)

### Structure and packaging (audit)

| Code | Level | One-line handling |
|---|---|---|
| E_NOT_EPUB | E | illegal zip / provenance failed to read the package |
| E_ZIP_DUPLICATE | E | duplicate zip entry name (hand-modified package corrupted) → re-build from the translation |
| E_MIMETYPE_FIRST/STORED/CONTENT | E | mimetype not first/uncompressed/content wrong → re-build |
| E_NO_CONTAINER / E_CONTAINER_OPF / E_OPF_MISSING | E | container or OPF missing → re-build |
| E_SPINE_REF / E_MANIFEST_HREF | E | manifest↔spine inconsistent → re-build |
| E_NAV_HREF / E_NCX_HREF / E_LANDMARKS_HREF | E | navigation link dangling → check whether the corresponding document exists |
| E_TOC_COVERAGE | E | spine↔nav bidirectional coverage gap → check the chapter heading levels (units too deep that are pruned by the `output.nav_depth` projection are expected exemptions) |
| E_IMG_SRC | E | local image dangling → add it under raw/media/ then re-build |
| E_IMG_REMOTE | E | remote image link → download into the package and change to a local reference |
| E_UNSAFE_URL | E | javascript:/data: injection → inspect the translation HTML |
| E_THEME_FONT / E_THEME_COLOR | E | concrete font name/font size/color → switch theme, do not edit style |
| E_RESIDUE | E | HTML comment leftover → clean the translation |
| E_HEADING_SKIP | E | heading level skip (h1→h3) → add the intermediate level |
| E_COVER_META | E | cover properties and meta fail mutual verification → re-build |
| E_ANCHOR / E_FN_BACKLINK | E | internal anchor/footnote backlink dangling → check noteref/footnote |
| W_META_INCOMPLETE | W | DC item missing **or blank** → should already have been filled by `meta` during preprocessing |
| W_NO_LANG / W_H1_COUNT | W | missing lang / h1 count ≠ 1 |
| W_RESIDUE | W | markdown/pandoc marker leftover (`![` `**` `[^` etc.) |
| W_IMG_NO_ALT / W_IMG_FORMAT / W_IMG_LARGE / W_IMG_RATIO / W_IMG_UNCOMPRESSED | W | accessibility/compatibility/size |
| W_EPUB_SIZE | W | total size >50MB |

### Provenance (provenance)

| Code | Level | One-line handling |
|---|---|---|
| E_UNIT_MISSING / E_UNIT_ORDER | E | structured↔translation↔spine three-way gap/out-of-order → add the missing translation or re-build |
| E_MEDIA_LOST / E_MEDIA_ORDER | E | translation lost images/image order changed → align with the source image references |
| E_MEDIA_EPUB_LOST | E | image referenced by the translation did not enter the product (silently dropped at build) → check raw/media and the `media_dropped` event |
| E_FN_EPUB_LOST | E | product footnote count differs from the translation → check `[^label]:` definitions then re-build |
| E_EPUB_PARA_LOST | E | product missing translation paragraphs (`epub_coverage` < 1.0) → locate by `unit:paragraph` and re-build |
| E_ALIGN_MD_DRIFT | E | translation body and alignment table inconsistent (one side missing content) → fix md with align as authority then re-import |
| E_TOC_FLAT | E | nav flat for a source that has hierarchy → check unit level and headings |
| E_INSERT_MISSING_FILE | E | media pointed to by inserts missing → re-run that unit's ingest |
| E_INSERT_BAD_SOURCE | E | inserts source illegal → fix that `<id>.json` |
| W_INSERT_NO_DESC / W_INSERT_NO_LATEX | W | content description/formula LaTeX not filled → agent completes and re-runs |
| W_NO_COVER | W | no cover (acceptable when ownership is unclear, see publishing.md §2) |
| W_STRUCT_MISSING | W | structured source file missing → re-ingest |
| W_TOC_DEPTH | W | nav depth sequence inconsistent with source (reconciled after projection by `output.nav_depth`) |
| W_TOC_MISSING / W_NAMING | W | facts source TOC entries not mapped to any `unit` / `unit#anchor` after normalized title matching (real coverage gap) / product naming does not match slug |
| W_DELIVERY_AUDIT_MISSING | W | all units built but no delivery record → run the delivery audit per references/delivery.md |
| W_REPAIR_UNRESOLVED | W | semantic repair has unresolved fixes (repairs.jsonl unresolved) → fix what can be fixed, record doubtful ones in the delivery record |
| W_REPAIR_STALE_UNIT | W | repairs.jsonl rows reference a unit removed by a structure rebuild → historical rows can be ignored; re-attach `unresolved` rows to a surviving unit (issue #23) |

## 5. Condensed workspace contract

- State machine: `pending → split → analyzed → translated → aligned → reviewed → built`
  (`import` advances translated→aligned; `import --reviewed` advances aligned→reviewed;
  `build` advances to built; reviewed/built skip re-import).
- Authoritative truth: `publication.json` (not hand-edited; metadata is written via the
  `meta` command), glossary.csv.
- import blocks (errors): missing file, align broken sequence/empty translation,
  **alignment-table src not in the source text**, **table shape not conserved**. import
  warnings: terminology/marker/footnote/fidelity forward missing blocks/length (hard-defect
  classes shown in red; misses are caught by G5).
- Terminology three states: seed→candidate→conflict→confirmed; conflicts are externalized
  to `analysis/glossary_conflicts.jsonl`, and **qa does not release before the arbitration
  is written back**.
- After the terminology arbitration is written back: re-run `g0` on **all translated
  units** (old-translation violations are cleared on the spot).

## 6. Build constraints

- Three themes: `standard` (default)/`compact`/`spacious`; layout fine-tuning only,
  concrete font names/font sizes/colors forbidden.
- Deterministic build: `dcterms:modified` frozen as a constant; the same input always
  yields the same EPUB.
- EPUB 3: nav+NCX, exactly one h1 per chapter, standard note semantics and bidirectional jumps, cover cover-image + `linear="no"`. Note content/resources/current registration binding must pass independent offline acceptance; GUI reader compatibility is conditional and never a universal popup guarantee (see `references/delivery.md`).
- Translator credit: `dc:creator(creator-trl)` + `role=trl` (written by
  `meta --translator`).
