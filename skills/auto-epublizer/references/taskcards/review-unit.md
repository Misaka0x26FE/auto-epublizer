<!-- i18n: source=review-unit.zh.md sha256=e8a8b8cff355df06d785aaf5a86b76c1503afec22f8b22fb8f45899b9dd416a0 -->
> **English** | [中文](review-unit.zh.md)

# Task card: review-unit

Stage reference: `references/review.md`.

**Scene (restate from disk)**: `next_tasks[0].kind=review` with a `unit` id; the unit is
`aligned` and not yet `reviewed`.

**Action**: perform the G1–G3 semantic review for that unit with your own judgement (missing /
added / mistranslation / terminology / pronoun), and write the review artifacts under
`reviews/review-<ts>/` (including `result.json`). Then register acceptance with
`auto-epublizer import --unit <unit> --reviewed`.

**Done when**: `import --unit <unit> --reviewed` advances the unit to `reviewed`.

**If it fails**: record real issues in `result.json` and fix the shadow translation; do not
claim completion without the registration. If a unit oscillates, see the convergence rules in
`references/review.md`.
