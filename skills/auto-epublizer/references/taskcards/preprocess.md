<!-- i18n: source=preprocess.zh.md sha256=a50ddda6b5f7203a7a748bc318a8984709a5aa0b0fe3c7efe2ad9c3257ba4b51 -->
> **English** | [中文](preprocess.zh.md)

# Task card: preprocess

Stage reference: `references/preprocessing.md`, `references/ingest.md`.

**Scene (restate from disk)**: `status --json` reports `has_preprocessing=false`; the
workspace may or may not have `publication.json` yet.

**Action**: run `auto-epublizer preprocess <input> [--reference <path>...] [--target <lang>]`
for a new book, or `auto-epublizer preprocess` in an existing workspace to refresh facts.
This is zero-token fact collection only — do **not** start writing understanding artifacts.

**Done when**: `status --json` reports `has_preprocessing=true`.

**If it fails**: run `auto-epublizer doctor --json` first (toolchain / MinerU / network), then
read the Chinese error; an unsupported or encrypted source is a real stop — see
`references/ingest.md`.
