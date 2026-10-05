<!-- i18n: source=analyze.zh.md sha256=45653c1c7f48afe09d3a6a7a005614b9d48a804e612dba23e0f6e6801f929220 -->
> **English** | [中文](analyze.zh.md)

# Task card: analyze

Stage reference: `references/analysis.md`.

**Scene (restate from disk)**: `next_tasks[0].kind=analyze` with a `unit` id; the `analysis/`
layer has no `overview.md` / `global.md` yet.

**Action**: read `structured/<unit>` and `preprocessing/facts.md`, then write
`analysis/units/<unit>.md` (summary / characters appearing / terminology cautions). Do this
for the units listed (the pointer gives up to 5 per batch).

**Done when**: the named `analysis/units/<unit>.md` exists.

**If it fails**: keep it factual and short; if the unit's source is suspect, that is a
`repair` concern — do not fabricate understanding.
