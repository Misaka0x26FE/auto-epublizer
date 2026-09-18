<!-- i18n: source=quality-control.zh.md sha256=0bb972ef8dd274c0d10d90774155a24d55dbc08830572b9ace12d2f354e96d86 -->
> **English** | [中文](quality-control.zh.md)

# Quality-Control Process Design (auto-epublizer)

This document turns the "six gates" in the README into an implementable specification:
each gate's **trigger timing, inputs, outputs, failure actions, cost, data contract,
acceptance thresholds and convergence conditions**. The scope boundary is unchanged: it is
responsible only for **delivery quality** (accurate / complete / consistent / compliant /
structurally correct / reproducible) and makes no value, political or ideological
judgements.

## 0. Design Principles

1. **Cost layering**: zero-token first, then the cheap tier, then the strong tier, upgrading as needed — never burn strong-tier money on errors the cheap tier can catch.
2. **Role separation**: translation / review / evidence-gathering / revision / arbitration are independent; review does not directly edit the translation, and revision goes through a shadow overlay.
3. **Evidence-driven, not voting**: candidate issues are evidenced before they are adjudicated; the glossary, references and shadow revisions are all "material pending verification".
4. **Deterministic + resumable + auditable**: results are merged in stable source order; each gate has checkpoints; all artifacts are persisted to disk for review.

## 1. Overview of the Six Gates

```text
translator(strong tier)          G0 zero-token static validation ── if fail, send back for retranslation/flag
      │                                     │
      ▼                                     ▼
  align/ sentence-level alignment    G1 per-batch bilingual review(cheap) ── reports issues, no direct edits
                                            │
                                            ▼
                                G2 evidence-gathering re-check(strong) ── confirm/dismiss candidates
                                            │
                                            ▼
                                G3 conflict arbitration + shadow revision + blind re-review(convergence state machine)
                                            │
                                            ▼
                                      build → EPUB
                                            │
                                            ▼
                                G4 EPUB structural QA(epubcheck + unpack audit)
                                            │
                                            ▼
                                G5 delivery acceptance(quality report + release checklist)
                                            │
                                            ▼
                          delivery audit(agent gate: independent reconciliation + sampling → delivery record)
```

| Gate | Name | Timing | Cost | Skippable | Output |
|---|---|---|---|---|---|
| G0 | Zero-token static validation | immediately after each unit is translated | 0 | No | static warning list |
| G1 | Per-batch bilingual review | after the whole book is translated | cheap | No (default) | `issues` (candidates) |
| G2 | Evidence-gathering re-check | after G1 reports issues | strong, on demand | Yes | `issues` (confirmed/dismissed) |
| G3 | Conflict arbitration + shadow revision + blind re-review | loop after G2 | strong | Yes | `patches` + convergence determination |
| G4 | EPUB structural QA | after `build` | 0 (epubcheck local) | No | structural audit report |
| G5 | Delivery acceptance | before release | 0 | No | `report.json` + release checklist |
| (additional) | Delivery audit | after `qa released`, before delivery | low (reconciliation + sampling) | No | `reviews/delivery-<ts>.md` |

## 2. Detailed Gate Specifications

### G0 Zero-Token Static Validation (pure function, immediately after translation)

Input: `translation/align/<id>.jsonl` + `structured/<id>.md` + `analysis/glossary.csv`.

| Check | Rule | Failure action |
|---|---|---|
| Alignment-table completeness | every source sentence has a `src↔tgt` mapping, `seq` is continuous 1..N with no gaps and no duplicates, no empty source/empty translation | block that unit's import (error list), rerun after correction |
| Insert-marker conservation | markers such as `{fig:NNN}` have consistent src/tgt **unit-level totals** (sentence split/merge shifting position does not false-positive) | warning (hard defect); not cleared blocks G5 (`structure_open`) |
| Footnote-marker conservation | the two representations — pandoc `[^label]` (reference + definition) and sentence-final digit note references — have consistent src/tgt totals | same as above |
| Table-shape conservation | md pipe tables in structured vs translation: same table count, same row/column count per table (fences skipped, escaped pipes not counted as columns) | block that unit's import (a bad table goes straight into the build product) |
| Source fidelity | each align line's normalized src string must be among all non-empty lines of structured (reverse = hard, import blocked); structured body blocks must be in the concatenation of align src (forward = advisory; legitimate removals such as leftover copyright sentences do not block) | reverse mismatch blocks; forward missing blocks warn |
| md↔align consistency | translation md (build input) and align tgt (validation baseline) are identical after normalization (strip headings/footnote definitions/markers/whitespace; tolerance conventions see g0) | mismatch = one side is missing content → block that unit's import (delivery audit S1.1) |
| Length ratio | `len(tgt)/len(src)` falls within `[0.30, 3.0]`; translation non-empty | warning, handed to G1 for re-check |
| Terminology hit | when the body contains a glossary `source`, the translation contains the corresponding `target` (NFKC normalization + word boundary) | warning, handed to G1 for attribution |
| Erratum traceability | a sentence src hits a known typographic-error precedent (IDG→IDF etc.) → align `note` prefixed with `corr:` | trace, no warning |

> Implementation status: the five items above are wired up (`g0_unit_flags` /
> `annotate_correction_notes`). The "punctuation normalization" (`normalize_punctuation`)
> and "residue artifacts" (HTML comments / placeholders / running heads and page numbers)
> in the spec are deterministic pure functions, handled respectively by build-time style
> cleanup and the G4 unpack audit (`E_RESIDUE`/`W_RESIDUE`); source-language character
> residue is a semantic judgement and belongs to G1 (agent task).

G0 burns no tokens and issues no "verdict", only **deterministic warnings**, serving as input leads for G1.

### G1 Per-Batch Bilingual Review (cheap-tier Reviewer)

Input: source sentence + translated sentence (from the `align/` alignment table), the relevant terminology subset, G0 warnings.

- Issue types: `missing` (omission) / `added` (addition) / `mistranslation` / `terminology` (terminology violation) / `pronoun` (person/gender error).
- **Better to omit than to over-flag**: reasonable word-order adjustment, natural free translation and stylistic polishing are not problems; when unsure, do not report.
- **Strict JSON protocol**: the object must end with, in order, `reviewed_segments` (= the number of sentences in this batch) and `complete:true`; a violation retries the whole batch (with a narrower input), preventing bad fields from being silently treated as "no issues".
- Output: an `issues` candidate list (`verdict` undecided), handed to G2.

### G2 Evidence-Gathering Re-Check (strong-tier Agent Loop)

Input: G1 candidate issues.

- Read-only tools: `glossary_term` (look up a term in the store), `term_occurrences` (locations of a term across the book), `segment_context` (context near a paragraph), `book_context` (style/overview/chapter synopsis).
- At most 4 requests per round and at most `max_evidence_rounds` rounds of evidence gathering; **assuming un-obtained context is forbidden**.
- Each candidate is judged `confirmed` / `dismissed`, with `evidence_refs`.
- The glossary, references and shadow revisions are **material pending verification**; when they contradict each other, dismiss the candidate or keep the baseline.

### G3 Conflict Arbitration + Shadow Revision + Blind Re-Review (convergence state machine)

For issues confirmed by G2, a three-step loop:

1. **Conflict arbitration**: when cross-block suggestions for the same term/person/fixed expression contradict each other, the Arbiter makes a final ruling of `suggested` (pick one) or `unresolved` (insufficient evidence).
2. **Shadow revision**: the Fixer generates on an in-memory overlay a "minimal-change full single-sentence replacement" (echoing `segment_ref`, `before_hash`, all `issue_ids`, ending with `complete:true`). The official `translation/`, `glossary` and `publication.json` are read-only throughout.
3. **Blind re-review**: the next review round is **not given the old issue descriptions** and reads only the revised shadow translation, preventing "ticking boxes against the instructions".

Convergence determination (see §5):

- `clean_confirmations` consecutive rounds with no issue → `clean_confirmed`;
- exceeding the round limit → `max_rounds`;
- the overall shadow-translation digest (SHA-256) shows an A↔B cycle → `no_progress`;
- Fixer failures pile up and review no longer reports → `unresolved_fixes`.

Autofix (optional): first write a recoverable index `reviews/<ts>/autofix/index.json`, then update the `tgt` of the official `align/`; the rest of the history is kept in the Review directory.

### G4 EPUB Structural QA (after build, local)

- `epubcheck` zero errors (jar cached in `~/.cache`).
- Item-by-item unpack audit (`qa/audit.py`, already implemented):
  - `mimetype` first, uncompressed, content exactly `application/epub+zip`;
  - `META-INF/container.xml` well-formed, pointing to the OPF;
  - every href in the manifest resolvable, every idref in the spine present;
  - all references in nav / NCX / landmarks / content-document img src resolvable (dangling detection);
  - dangerous URL (javascript:/data:) injection interception;
  - theme-layer boundary: style.css has no specific font name/size (`E_THEME_FONT`), no color (`E_THEME_COLOR`);
  - cover meta mutual corroboration: `properties="cover-image"` ↔ `<meta name="cover">` (`E_COVER_META`);
  - each content document has a correct `xml:lang`, exactly one `h1`, no skipped levels (`E_HEADING_SKIP`);
  - residue: HTML comments (`E_RESIDUE`), markdown/pandoc markers (`W_RESIDUE`);
  - internal anchors resolvable (`E_ANCHOR`, including footnote noteref→footnote) + footnote backlinks (`E_FN_BACKLINK`);
  - bilingual src/tgt paragraph counts paired (`E_BI_PAIRS`);
  - media: empty alt (`W_IMG_NO_ALT`), format compatibility (`W_IMG_FORMAT`), oversized/overwide/overtall/uncompressed (`W_IMG_LARGE`/`W_IMG_RATIO`/`W_IMG_UNCOMPRESSED`), total EPUB size (`W_EPUB_SIZE`);
  - DC metadata missing hints (`W_META_INCOMPLETE`).
- Provenance audit (`qa/provenance.py`, postprocessing-spec §2): tri-lateral reconciliation, media provenance, per-segment coverage, TOC hierarchy — see G5.
- **Finished-product presentation reconciliation** (delivery audit S1.2, `qa/provenance.py`): md image references ↔ product `<img>` (`E_MEDIA_EPUB_LOST`, closing off silent build drops), md footnote-definition count ↔ product `<aside>` count (`E_FN_EPUB_LOST`), full body-paragraph probe (`E_EPUB_PARA_LOST` + `epub_coverage`, reusing the same renderer as build); md↔align consistency fallback (`E_ALIGN_MD_DRIFT`). A reference dropped at build time is traced by writing a `media_dropped` event to `events.jsonl`.

### G5 Delivery Acceptance (before release)

- Aggregate G0–G4 + the provenance audit into `report.json`:
  ```json
  {
    "slug": "…", "epub_path": "…",
    "g0_flags": [], "g0_terminology_open": 0, "g1_candidates": 0, "g2_confirmed": 0,
    "g3_patched": 0, "g3_termination": "clean_confirmed", "g3_rounds": 2,
    "total_sentences": 0, "error_rate": 0.0,
    "g4_epubcheck_errors": 0, "g4_audit": "pass", "passed": true,
    "audit": {"ok": true, "errors": 0, "findings": []},
    "epubcheck": {"available": true, "ran": true, "errors": 0, "warnings": 0, "messages": []},
    "provenance_coverage": 1.0, "units_missing": 0, "units_order_ok": true,
    "media_lost": 0, "toc_missing": [], "toc_flat": false,
    "inserts_missing_files": 0, "provenance_findings": [],
    "released": true, "released_reason": "ok"
  }
  ```
- Release checklist verification: product naming (`<slug>.epub` / `<slug>-bi.epub`, `W_NAMING`), metadata (all DC items present), cover, copyright attribution, license.
- **Release conditions** (aligned with docs/postprocessing-spec.md §5 and `qa/report.py::generate_report`):
  `g2_confirmed == 0` or all revised (`g3_patched`);
  **`g0_terminology_open == 0`** (a G0 terminology hit is a real defect — the translation is missing a glossary source term and must be verified and cleared one by one, otherwise `released_reason=terminology_open`);
  **`g0_structure_open == 0`** (marker/footnote conservation violations; `structure_open`);
  **`glossary_conflicts_open == 0`** (undecided terminology conflicts; `glossary_conflict_open` — no release before the arbitration is written back to glossary.csv);
  `g4_epubcheck_errors == 0`; `g4_audit == "pass"`; complete provenance
  (`provenance_coverage ≈ 1.0` (null when there is no translation artifact), zero missing
  in tri-lateral reconciliation/media provenance, `toc_flat == false`, no error-level
  provenance findings);
  finished-product presentation reconciliation cleared (**`align_md_drift == 0`,
  `epub_media_missing == 0`, `epub_footnotes_missing == 0`, `epub_coverage ≈ 1.0`**,
  delivery audit S1).
  The G0 **length-ratio** warning is advisory and does not block (English→Chinese length
  ratios are naturally low, with many observed false positives); epubcheck not run (jar
  missing) counts as unverified and does not release.

### Delivery Audit (agent gate, mandatory after qa released)

`qa released=True` only means the **known contracts** are all green. Before delivery, per
`skills/auto-epublizer/references/delivery.md`, perform an independent full validation and
write `reviews/delivery-<ts>.md`: tool reconciliation re-check → unpack sampling
(first/middle/last + high-risk chapters: body probe / image viewing / footnote content) →
manual check of TOC/cover/metadata → handling of inserts descriptions and open items →
byte-level artifact-sync verification. Defects found go through the repair loop
(fix → import → build → qa → re-audit). Once every unit is built, qa reminds you with
`W_DELIVERY_AUDIT_MISSING` when the record is missing (warning, non-blocking).

> Basis: a real delivery case — *The History of Russian Railways* passed all tool QA, yet
> the finished product included only 34 of 72 referenced images (the translated body
> dropped image segments; the tool's conservation check only inspects the alignment
> table). Finished-product validation must independently reconcile "source references ↔
> product inclusion" and must not rely solely on tool QA.

## 3. Data Contracts (written to `reviews/`)

### Issue (produced by G1, adjudicated by G2)

```json
{
  "issue_id": "r1-ch01-0003",
  "chapter": "ch01",
  "index": 3,
  "seq": [12, 13],
  "type": "terminology",
  "detail": "old sport does not use the confirmed rendering 「老兄」",
  "suggestion": "change to 「老兄」",
  "evidence_refs": ["glossary:old sport"],
  "consistency": null,
  "verdict": "confirmed",
  "status": "open"
}
```

`seq` locates the exact sentence in `align/<id>.jsonl` and is the anchor for bilingual
location, repair write-back and error-rate statistics.

### Patch (G3 shadow revision)

```json
{
  "patch_id": "p-ch01-0003-1",
  "chapter": "ch01",
  "index": 3,
  "before_hash": "sha256 current translation",
  "after": "complete revised translated sentence",
  "issue_ids": ["r1-ch01-0003"],
  "review_round": 1,
  "status": "provisional"
}
```

### Review Run Directory

```text
reviews/review-<ts>/     # agent hand-written review records (G1–G3 executed by the agent itself)
├── issues/               # review findings
├── patches/              # revision patches
├── summary               # summary explanation
└── result.json           # final outcome (qa reads from here): g1_candidates / g2_confirmed /
                         # g3_patched / termination / rounds (issue_count is the legacy fallback key)
```

## 4. Acceptance Thresholds (default, configurable)

| Metric | Threshold | Meaning |
|---|---|---|
| Length ratio | `0.30 ≤ ratio ≤ 3.0` (advisory) | too small suggests omission, too large suggests runaway; G1 re-check |
| Empty translation | forbidden | import blocks the unit |
| Terminology hit | `g0_terminology_open == 0` (hard release gate) | whole-book consistency; real defects must be cleared |
| Error rate | `confirmed / total_sentences ≤ 1e-4` (agent self-check reference, not a CLI hard gate) | aligned with publishing error-rate conventions |
| epubcheck | 0 error (and must actually run) | structural validity |

## 5. Convergence State Machine (G3)

```text
start ──▶ R1 review ──▶ no issue ──▶ clean_streak++ ──▶ reach clean_confirmations ──▶ clean_confirmed
   │                        │
   │                        └─▶ has issue ──▶ arbitration + shadow revision ──▶ R2 blind review (repeat, and clean_streak=0)
   │
   └─▶ round count exceeded ──▶ max_rounds
   └─▶ digest SHA-256 cycle ──▶ no_progress
   └─▶ Fixer failures pile up and review no longer reports ──▶ unresolved_fixes
```

Round limit = `(fix_max_rounds + 1) × clean_confirmations` (default `3 × 2 = 6`).

## 6. Configuration Items (the qc section of config)

The `qc` section of `config.yaml` **actually has only two items** (see `auto_common/config.py`):

```yaml
qc:
  length_ratio: { too_short: 0.30, too_long: 3.0 }   # G0 length-ratio warning thresholds
  epubcheck: { jar: "~/.cache/epubcheck.jar", strict: true }
```

The following parameters are **reference values for the agent's review operations**
(G1–G3 are executed by the agent itself; the CLI does not wire them):

| Parameter | Reference value | Description |
|---|---|---|
| `error_rate_threshold` | 0.0001 | error-rate self-check threshold (`g2_confirmed / total_sentences`) |
| `review.output_retries` | 2 | number of retries for review JSON protocol violations |
| `evidence.max_rounds` | 2 | maximum number of evidence-gathering rounds |
| `fix_loop.max_rounds` | 2 | maximum number of repair rounds (convergence state machine: `(max_rounds+1)×clean_confirmations`) |
| `fix_loop.clean_confirmations` | 2 | number of consecutive clean confirmations |

## 7. Correspondence with the Workspace Directories

| QC artifact | Landing point |
|---|---|
| Sentence-level alignment | `translation/align/<id>.jsonl` |
| Static warnings | G0 outputs them in the current round of the `import`/`g0` commands; at `qa` time they are recomputed and aggregated into `report.json`'s `g0_flags` (not persisted separately) |
| Review issues/patches/arbitration | `reviews/review-<ts>/` (agent hand-written, `result.json` required) |
| Quality report | `report.json` (workspace root) |
| Behavior ledger | `events.jsonl` (append-only; the usage ledger has been removed along with the internal LLM) |

## 8. Correspondence with the Traditional Three Reviews and Three Proofreads

| Traditional | Our project's gate |
|---|---|
| Checking similarities and differences (校异同) | G0 (deterministic collation + alignment-table completeness) |
| Checking right and wrong (校是非) | G1 + G2 (report issues, evidence-based adjudication, no direct edits) |
| First review | G1 (basic errors) |
| Second review | G2 + G3 arbitration (consistency + doubts) |
| Editorial processing | G3 shadow revision (read-only, traceable, escalate difficult cases) |
| Checking red marks (核红) | G3 blind re-review + oscillation detection |
| Three proofreads and one read | G3 consecutive clean confirmations + G4 structural audit |
| Press proof (付印清样) | G4 + G5 (zero errors to release) |
