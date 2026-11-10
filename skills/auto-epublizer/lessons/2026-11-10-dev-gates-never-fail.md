<!-- i18n: source=2026-11-10-dev-gates-never-fail.zh.md sha256=8777f003dc32f51975bcbe4868f802e99a2b66ec448c9a64f230420f5bae5a4a -->
> **English** | [中文](2026-11-10-dev-gates-never-fail.zh.md)

# Make the gate prove it can fail

## Criterion (when this applies)

- You just wrote or changed an audit criterion (`E_*` / `W_*`, one cell of the delivery audit, a
  `report.json` field).
- Its output is an all-green verdict such as "0 inconsistent units", "content matches ✅",
  "three-way identical ✅".
- You have **not** injected a real defect into a copy and watched it fail — until you do, the
  criterion is only an assertion.

Known failure shapes (all observed in real projects):

| Shape | How it fails |
|---|---|
| `if in_product and (n_blocks == 0 or n_blocks > 0) and present` | tautology: always true, always reports 0 |
| `want in got or got in want` | substring containment: a truncated product still "matches" |
| side keys disagree (`OEBPS/x.xhtml` vs `x.xhtml`) | always false: structurally cannot be non-zero, so always "clean" |
| sha256 checked on the **first file only** | other files can change unnoticed |
| missing data falls into the "pass" branch | absence read as "no difference" |

## Handling

1. **One criterion, one injection**: copy the workspace (or the minimal fixture) into a
   **throwaway copy**, inject one minimal defect matching the criterion's semantics, run the
   audit once, assert the **criterion fails**, and assert the **un-injected baseline reports zero
   blocking findings**. Delete the copy afterwards; never touch a real workspace.

   ```text
   inject: delete one body block from the translation layer (source layer and align untouched)
   expect: md↔align drift ≥ 1 unit; block-count difference "unattributed" ≥ 1
   also:   the clean baseline must report 0 blocking findings
   ```

2. **Commit the injection list as a table** (criterion → expected failure → "how the old
   criterion behaved"). That table *is* the criterion's documentation; anyone changing it must
   first check whether the table's expectations still hold.

3. **Put negative tests in `tests/`**: a gate tested only on clean input is untested. The
   fixtures must include **legitimate exceptions** (pure bibliography, foreign quotations,
   collation markers, filename-style captions), or the next "zero false positives" will have
   been bought by loosening the criterion.

4. **State the criterion's scope in the output**: `scope` (`not_run` / `sampled` / `full`),
   `candidate` / `confirmed` / `resolved`, the sampling denominator, and the rule/input digests.
   "Default 0" and "ran and confirmed 0" must look different in the report.

## Why the bar is this high

A gate's entire value comes from **daring to fail**. Once a criterion is a tautology, the report
stops being evidence and becomes the most dangerous kind of fake evidence: worse than no gate at
all — without one, people sample by hand; with a fake one, they ship with confidence.

## Reproduce / verify

```bash
# Shape (project-specific): a standalone script/test that reads a real or synthetic workspace
#   1) copy → temp dir (tempfile; deleted afterwards)
#   2) inject each defect → run the audit → assert the matching criterion is error/blocking
#   3) restore → run again → assert zero blocking findings
# return 0 only when every assertion passes

# Self-check: turn the criterion into a tautology (e.g. `if True:`) — the injections must stop
# failing, so the script must now exit non-zero. That step is the proof that it can fail.
```

- Relevant criteria: `src/auto_epublizer/qa/audit.py` (`_MD_RESIDUE` and similar residue checks),
  `src/auto_epublizer/qa/provenance.py` (three-way reconciliation / media / coverage),
  `src/auto_translator/review/g0.py` (conservation totals).
- Background: `docs/plans/2026-11-10-field-archive-gap-analysis.md` §6;
  `docs/quality-lessons.zh.md` "sample audit + repair loop".
