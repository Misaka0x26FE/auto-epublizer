<!-- i18n: source=review-unit.zh.md sha256=f43c5a1ed0de6ff1dd171fe34641ea9fbb8d1fb76624c546169794b042d594fc -->
> **English** | [中文](review-unit.zh.md)

# Task card: review-unit

Stage reference: `references/review.md`.

**Scene (restate from disk)**: `next_tasks[0].kind=review` with a `unit` id; the unit is
`aligned` and not yet `reviewed`.

**Action**: perform the G1–G3 semantic review for that unit with your own judgement (missing /
added / mistranslation / terminology / pronoun), and write the review artifacts under
`reviews/review-<ts>/` (including `result.json`). Then register acceptance with
`auto-epublizer import --unit <unit> --reviewed`.

Read each source and target pair and sample adjacent paragraphs for misplaced text. Check negation,
numbers, proper names, quotations and verse. Complete source ranges and equal paragraph counts can
still contain misplaced translations. For a mismatch or omission, record the affected source range,
target location and source-page evidence.

**Done when**: `import --unit <unit> --reviewed` advances the unit to `reviewed`.

**If it fails**: record real issues in `result.json` and fix the shadow translation; do not
claim completion without the registration. If a unit oscillates, see the convergence rules in
`references/review.md`.
