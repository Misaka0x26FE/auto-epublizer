<!-- i18n: source=write-preprocessing.zh.md sha256=4c41289000a25cdc4ade0e0b58b81d1b0d3978eda73706c0055e23347c23ca3f -->
> **English** | [中文](write-preprocessing.zh.md)

# Task card: write-preprocessing

Stage reference: `references/preprocessing.md`.

**Scene (restate from disk)**: `has_preprocessing=true` but `preprocessing_complete=false`;
`next_tasks[0].done_when.file` names the missing artifact (e.g. `preprocessing/capabilities.md`).

**Action**: read `preprocessing/facts.md` and write the named file, following the structure in
`references/preprocessing.md`. Write it from the facts plus your own reading — never invent
content. Repeat for each listed file (order: `capabilities.md` → `global.md` → `todo.md`).

**Done when**: the named file exists and `status --json` advances to the next missing file.

**If it fails**: if a fact is genuinely missing, record the gap in `risks.md` rather than
inventing; if the source is unreadable, go back to the `preprocess` card.
