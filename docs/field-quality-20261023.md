# 2026-10-23 field-quality inventory (sanitized)

This is a scope/ownership register, **not acceptance of any book**. Baseline: official
`08a8b1a`; unpublished field commits were reviewed in an isolated worktree. No manuscript,
workspace, credential or source-page image is included. Issues distinguish upstream defects
from defects in the operator's local scripts and agent judgement.

| Problem observed during this run | Owner / evidence / tracking |
|---|---|
| Raw copying accepted; footnote/heading bypass; ASCII-only detection | CLI G0; synthetic regressions; [#54](https://github.com/Misaka0x26FE/auto-epublizer/issues/54) |
| Empty translation and nonempty severely short translation conflated with advisory ratios | CLI import/G5; keep 0.30/3.0 advisory, separate severe-short review gate; #54 and existing #39 |
| G0 flags added but ignored by import and G5 check allowlists | CLI orchestration/report, end-to-end regressions; #54 |
| Empty/unresolvable style references; whole-index exemptions contradict requested style | Schema validation + agent responsibility; #54/#57; do not infer that a matching exemption is semantically legitimate |
| Style CSV/style.md/nav switch missing from report digest | CLI artifacts digest; synthetic mutation tests; #54 |
| Missing note registration silently skips QA; malformed notes swallowed | CLI notes gate; #56; absence of machine evidence is not proof that a source has no notes |
| Original note labels, orphan-note host and renderer/audit normalization disagree | CLI build/notes audit; previously unpublished four field commits, synthetic tests; #56 |
| NCX labels leak Pandoc attributes; dedication cannot remain in spine but leave TOC | CLI plain-label + explicit nav switch; #56 |
| Filename/placeholder captions unchecked; non-ASCII numeric captions misclassified | CLI audit, positive/negative synthetic samples; #55 |
| Missing alt hides image repetition; wrong figure caption reused; single quotes ignored | CLI audit uses parsed XHTML independently for references/captions; #55 |
| Same bytes/different path; different bytes/same relative spelling | ZIP member identity + image digest warning, never auto-delete; #55 |
| PDF page headers/OCR fragments become TOC; source NCX collapsed | Ingest evidence + manual structure review; #58, existing #31/#16; counts alone are not semantic evidence |
| Two-column index order/page continuation wrong; false bibliography tables | Source layout/manual repair; #58; do not auto-delete a table or translate scattered row heads |
| Cross-page note tail omitted; two notes absent despite registered count=aside count | Source inventory/manual repair; #58/#37/#46; do not fabricate missing numbers |
| OCR residue census misses notes/backmatter | Full-product census with separately identified regions; #58 |
| Bibliography vs index vs body metadata and language census conflated | Source classification/agent style; #57/#58; explicitly separate scopes and denominators |
| Empty or truncated note accepted by substring audit | Local delivery generator, not upstream file; generic verification contract #57 |
| Tautological body coverage, H1-only check, nav path comparison skipped | Local generator, not upstream file; #57; actual md/align/product probes required |
| Source hashes copied or first candidate chosen; missing sources called three-way match | Local generator; #57; missing/ambiguous identity is unknown/fail, not pass |
| Reuse vs redo, sampling vs full inspection, fixed all-green conclusions | Delivery skill/local generator; #57; unexecuted checks remain unknown/manual |
| Default copy audit absent; missing directory/file skipped; manifest skip called verification | Local batch gate/packager; #57; verify every expected artifact and current report binding |
| PDF extractor difference/repeated sentence/token presence auto-explained; stale verdicts reused | Local adjudicator/agent; #57; positive scoped evidence and input/rule binding required |
| Garbled text layer claimed to prove invisible/unreadable page image | Agent evidence error; #57/#58; render/read the actual page; never certify an unperformed visual inspection |
| Index parser consumes page-number tails, misses Unicode initials/quotation styles | Local index scripts; #57; test grammar/column order before mapping, no silent heuristic acceptance |
| Harvest overwrites manual mapping; swaps/double wrapping/aliases lose original spelling | Local repair scripts; #57; stable source identity, reviewed mapping, idempotence and conflict tests |
| Apply writes before validation, partial failure, dry-run or rerun unsafe | Local repair scripts; #57; preflight and baseline-bound transactional plan required |
| Names harvested with surrounding verbs/job titles; wrong entities and invented transliterations | Agent semantic error, NOT repairable by a CJK-presence gate; #57; per-entry source/body verification remains a local task |
| Destructive git clean/checkout deletes untracked work; unrelated dirty files staged | Operator discipline; #57; narrow staging, preserve concurrent work, no broad cleanup |
| English docs stamped but not actually translated; i18n failure called pre-existing | Field patch defect: clean official baseline i18n tests **12 passed**; #57. Finalize updates stamps only, not prose |
| Unsafe bulk transfer of books because census counts differ | Agent evidence error; #57/#58; align exact scope before comparing counts; do not upload/alter user books in this PR |

## Verification boundary

The added `length_review` rule is deliberately narrower than the existing ratio advisory:
at least 80 alphabetic source prose characters and at most four alphabetic target characters,
with a nonempty target. It asks for source review, not a machine assertion of mistranslation.
Only an explicit nonempty source pattern plus a real style reference can waive that signal;
empty translations cannot be waived. Short-source protection and ordinary ratio advisories
remain unchanged. This heuristic does **not** detect all semantic omissions.

Index transliteration, source-column restoration and legitimate bibliographic retention
remain agent tasks. A CLI cannot verify a Chinese personal name merely because it contains
Chinese characters. The old field workspace is intentionally not changed here.

## Reproduction discipline

Use `PYTHONPATH=src python -m pytest ...` when reusing another worktree's environment:
an editable install may otherwise import the original checkout, producing misleading results.
All field regression fixtures are synthetic. Test failures must name the actual checkout;
successful unit tests do not establish end-to-end import/G5 behaviour without separate tests.
