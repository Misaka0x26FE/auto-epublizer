<!-- i18n: source=2026-09-05-agent-translation-workflow.zh.md sha256=a7c5081b0b1655066412cd4cceb8910cce076a0baac0d4250c3c93f803b27b11 -->
> **English** | [中文](2026-09-05-agent-translation-workflow.zh.md)

# Agent main-process translation workflow: lessons from three rounds of GT1/GT2/On Lisp measurement

> Date: 2026-09-05　Source: record of DouBao cloud agent main-process translation (A Certain
> Magical Index GT1/GT2, On Lisp 25 chapters) — no external LLM API was called throughout;
> the translation was completed segment by segment by the agent.
> Status: experience retained.

## Trigger scenario

Use path B — "the agent main process hand-writes translation/ + align/, then import
registers it" — to translate a whole book. This round is a summary of three real rounds of
pitfall-hitting on this workflow, directly guiding subsequent GT3 / other books.

## Lessons and handling

### 1. Build once every 3–5 units translated (verify the format contract)

- **Pitfall**: GT2 translated 47 units consecutively before the first build; while
  hand-writing the translation, the `<img src>` lines were missed, polluting 8 illustration
  units in one go, and finally requiring concentrated rework.
- **Handling**: during translation, build once every 3–5 units + spot-check the rendering;
  format-contract problems (image segments, blank lines, escaping) surface in that round.

### 2. Finalize headings once before starting

- **Pitfall**: GT2 ch06's title was changed midway, and ch46 accidentally mixed in `」」` —
  patched while writing.
- **Handling**: before translating, finalize all unit headings into `preprocessing/plan.md`
  or a terminology file; after import, check `publication.json.units[].title` uniformly.

### 3. Write translation data files with the Write tool, not heredoc-embedded Python

- **Pitfall**: repeatedly hit the syntax pitfalls of heredoc-embedded Python (Lisp
  parentheses, quotes, `'\'`), and flipped over repeatedly on JSON escaping.
- **Handling**: always write the translation list as a `.json`/`.py` data file with the
  Write tool, then run a deterministic writer to generate `translation/` + `align/`.

### 4. Do not end long sentences with an ellipsis "lazily"

- **Pitfall**: very long sentences were ended with the "she was…" ellipsis. Partly the
  Baka-Tsuki source text was itself truncated, partly laziness when compressing long
  sentences — the two were mixed in the finished product and indistinguishable.
- **Handling**: compressing a long sentence must preserve semantic completeness; prefer
  splitting the sentence; all ellipsis-ended paragraphs are marked in the align comparison
  for review spot-checks.

### 5. G0 warnings cannot all be treated as noise

- **Pitfall**: GT2's 1970 G0 advisory items were all ignored, but real problems were mixed
  in (e.g. the terminology hit `Academy City 译文缺失 学园都市` was missed); the length-ratio
  warnings mixed "omission" with "normal compression".
- **Handling**: go through the terminology warnings one by one (`g0 --unit <id>` to locate);
  for abnormal length ratios, pull the align bilingual to check whether there is an
  omission; produce a `--bilingual` version for manual spot-checking.

### 6. Structural/semantic judgement belongs to the agent; scripts only do deterministic transport

- **Pitfall**: to split MinerU output and remove table-of-contents-page garbage,
  "intelligent scripts" were written repeatedly, and the threshold was always slightly off.
- **Handling**: **semantic judgements** such as heading determination, chapter boundaries,
  and garbage removal are done directly by the agent reading the source text manually;
  scripts only do deterministic actions such as writing to disk / aligning / changing status
  (see `2026-09-05-scanned-pdf-operations.md` §3).

### 7. The terminology loop must actually be run

- GT1 → GT2 used `import --terms preprocessing/terms.csv` to inherit the term-name table +
  seed new words; at import time a csv_io empty-cell bug was reported (already fixed in the
  main repo, `1766e7a`).
- After conflicts are externalized to `glossary_conflicts.jsonl`, a human must arbitrate and
  write them back; do not leave them unattended.

## Related

- Translation flow: `references/translation.md`, `references/review.md`;
- G0 interpretation: `references/review.md`; build verification: `references/build.md`;
- DouBao GT2 upstream bug fix: `docs/plans/2026-09-05-scanned-pdf-mineru.md` and `1766e7a`.
