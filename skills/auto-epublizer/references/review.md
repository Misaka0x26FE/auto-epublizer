<!-- i18n: source=review.zh.md sha256=4ca5f85b55cf7ca7280f7d97149c9f76bec06c5ba62260ff90782b2ee6878b9a -->
> **English** | [中文](review.zh.md)

# Review (six-gate QC operational guide)

> For a quick troubleshooting and release-interpretation reference (full error-code / condition sets), see `references/invariants.md`.

The six gates are layered by cost: G0/G4/G5 are CLI deterministic validation (zero token);
the **semantic review of G1–G3 is an agent task** (single-LLM principle) — you use your own
abilities to read the bilingual alignment, find problems, arbitrate and revise, and write
the artifacts into `reviews/review-<ts>/` per the contract; `qa` reads the g1/g2/g3 counts
and convergence state from `result.json`.

## Gate overview

| Gate | What it does | Who does it | Output |
|---|---|---|---|
| G0 | Zero-token static validation (alignment completeness / length ratio / terminology hit / marker conservation / footnote conservation / source fidelity) | CLI (`g0`/`import`) | static warning list |
| G1 | Segment-by-segment bilingual review (omission / addition / mistranslation / terminology / person) | agent | `issues` candidates |
| G2 | Evidence-gathering review (confirm against source text / context) | agent | `issues` confirmed / rejected |
| G3 | Arbitration + revision + convergence determination | agent | `patches` + `termination` |
| G4 | EPUB structural QA (epubcheck + unpack audit) | CLI (`qa`) | structural audit report |
| G5 | Delivery acceptance (aggregation + release checklist) | CLI (`qa`) | `report.json` |

## Review artifact contract (agent-written)

Produce `reviews/review-<ts>/`:

```text
reviews/review-<ts>/
├── metadata.json         # content summary + review-config fingerprint
├── issues.json           # issues found this round (after G1–G2 confirmation)
├── patches.json          # revision suggestions (G3)
├── summary.md            # review summary
└── result.json           # final: issue_count / termination / rounds (read by qa)
```

`result.json` keys (qa contract; default 0, `issue_count` is the legacy fallback key for
`g2_confirmed`):

```json
{
  "g1_candidates": 0,
  "g2_confirmed": 0,
  "g3_patched": 0,
  "termination": "clean_confirmed",
  "rounds": 2
}
```

After the review passes (`termination == "clean_confirmed"`), use
`auto-epublizer import --reviewed` to advance units in `aligned` to `reviewed`
(idempotent; units already reviewed/built skip re-import). If your revision changed
`translation/` + `align/`, first re-`import` (back to aligned) and then
`import --reviewed`.

## termination (convergence end state)

| Value | Meaning | Next step |
|---|---|---|
| `clean_confirmed` | N consecutive rounds with no issue | can proceed to build |
| `max_rounds` | max rounds reached without convergence | manually inspect leftover issues |
| `no_progress` | revision digest shows an A↔B cycle | oscillation, human arbitration required |
| `unresolved_fixes` | backlog of sentences that cannot be revised | handle manually |

## G1 sampling strategy

Small books (≤10 units) are fully reviewed. Large books use stratified sampling by
**chapter type × high-risk feature**; high-risk must be reviewed:
argument-dense/tables, footnotes, quotation-dense/multilingual material/OCR-suspect
segments (aligned with the risk annotations in `risks.md` and
`preprocessing/units/<id>.md`)/complex layout/**the first and last unit of each
chapter**; the rest are randomly spot-checked.

## G1 issue types (better to omit than to over-flag)

`missing` (omission) / `added` (addition) / `mistranslation` / `terminology` (terminology
violation) / `pronoun` (person/gender error). Reasonable word-order adjustment, natural
free translation and stylistic polish **do not count as issues**; when unsure, do not
report.

## Revision and blind re-review

- A revision first produces `patches.json` ("minimal-edit full-sentence replacement"),
  and only after confirmation edits `translation/` + `align/` (re-`import` after
  editing); do not hand-edit the official `translation/`, `glossary.csv` or
  `publication.json` directly, bypassing import.
- The next review round does not receive the previous issue descriptions and reads only
  the revised translation (blind review), preventing "checking the boxes against the
  spec".

## Terminology-conflict arbitration

When different segments give contradictory renderings for the same term/person/fixed
expression, externalize them to `analysis/glossary_conflicts.jsonl` and arbitrate at the
end; multiple renderings of the same word coexisting (e.g. 赤区/苏区) is "the most
insidious quality problem"; after arbitration write back to `analysis/glossary.csv`
(authoritative).

## G4 / G5 (see qa.md and build.md)

- G4: `auto-epublizer qa` runs epubcheck (zero error) + item-by-item unpack audit
  (mimetype first and uncompressed, container points to OPF, manifest/spine parseable,
  nav links resolvable, URL safe, correct lang, exactly one h1 per chapter).
- G5 release conditions: `g2_confirmed == 0` or all revised;
  `g0_terminology_open == 0` (terminology hits cleared);
  `g4_epubcheck_errors == 0` (and epubcheck actually ran); `g4_audit == "pass"`;
  complete provenance (`provenance_coverage ≈ 1.0`, zero missing in tri-lateral
  reconciliation / media provenance, TOC hierarchy not flat, no error-level provenance
  findings).
- **Release ≠ delivery**: `qa released` only means all known contracts are green; before
  delivery you must also complete the delivery audit per `references/delivery.md`
  (independent reconciliation + unpack sampling + manual checks → a
  `reviews/delivery-<ts>.md` record).

## Acceptance thresholds (defaults)

| Metric | Threshold |
|---|---|
| Length ratio | `0.30 ≤ len(tgt)/len(src) ≤ 3.0` (G0 warning, advisory) |
| **Insert marker conservation** | **`{fig:NNN}` etc. markers consistent in src/tgt unit-level totals (hard defect; if not cleared, G5 reports `structure_open`)** |
| **Footnote conservation** | **pandoc `[^label]` and sentence-final numeric note references consistent in total (hard defect, as above)** |
| **Terminology conflict** | **`glossary_conflicts_open == 0` (qa does not release before arbitration is written back to glossary.csv, `glossary_conflict_open`)** |
| **Terminology hit** | **0 (G0 `terminology` is a real defect, not advisory — the translation is missing a glossary source term; it must be verified and cleared item by item, otherwise G5 does not release, `released_reason=terminology_open`)** |
| Empty translation | forbidden (`import` blocks that unit) |
| Error rate | `confirmed_issues / total sentences ≤ 1e-4` (agent self-check reference, not a CLI hard gate) |
| epubcheck | 0 error (and it must actually run; missing jar → `epubcheck_not_run`) |

> Note: G0 can run independently — `auto-epublizer g0` validates immediately after
> translation/import.
> **G0 warnings fall into two categories with different handling**:
> - `terminology` (terminology hit): a **real defect**, the CLI marks it in red `✗`,
>   and `import` also counts it separately; you must check the translation/glossary item
>   by item and clear it (supplement the translation / fix the glossary / declare an
>   exception) before release. DouBao field lesson: terminology misses were once lumped
>   together with length false-positives and treated as all noise, missing the real
>   problem.
> - `length` (length ratio too low/too high): advisory, en→zh length ratios are naturally
>   low and produce many false positives, not a release hard condition; but **spot-check**
>   whether there is a real omission (especially paragraphs where an overly long sentence
>   ends with an ellipsis).
>
> G1–G3 are written to `result.json` after your review; the global-understanding context
> falls back to `preprocessing/global.md` when `analysis/` is missing. G4 is driven by the
> `qa` command; G5 is written by `qa`, aggregating G0–G4 into `report.json` (including
> `error_rate`/`released`/`released_reason`).

## In-process validation during translation (QC discipline, DouBao field lesson)

- **Build once every 3–5 units translated**: format-contract problems surface in that
  round (image segments missing an `<img>` line, blank-line breakage, escaping residue),
  avoiding contaminating multiple units at once and a big rework at the end.
- Write each unit and immediately `import --unit <id>` to register + `g0 --unit <id>` to
  validate; handle terminology warnings on the spot.
- Finalize headings once before starting work into `preprocessing/plan.md`; do not change
  them mid-translation.
