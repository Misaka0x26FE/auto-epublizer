<!-- i18n: source=import-unit.zh.md sha256=15c0c7f13578f78fb7fe1705390a853153d143b472e5377ed076743920a79439 -->
> **English** | [中文](import-unit.zh.md)

# Task card: import-unit

Stage reference: `references/translation.md`, `references/review.md`.

**Scene (restate from disk)**: `next_tasks[0].kind=import` with a `unit` id — the translation
and/or alignment are on disk but the status was not advanced (stale).

**Action**: run `auto-epublizer import --unit <unit>` (add `--terms preprocessing/terms.csv`
if you have a workspace term file). This registers the artifacts and runs the G0 structural
validation.

**Done when**: the command exits 0 and `status --json` no longer lists the unit as stale.

**If it fails**: read the G0 error code / message, fix `translation/` + `align/`, re-run
`import --unit <unit>`. Never hand-edit `publication.json`.
