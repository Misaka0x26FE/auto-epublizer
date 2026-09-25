<!-- i18n: source=SKILL.zh.md sha256=14766b0e8387b227a665f76da30302ca3b7066b3e640c0040f6a3d3c0e9535de -->
> **English** | [中文](SKILL.zh.md)

---
name: auto-epublizer
description: Orchestrates the auto-epublizer translation and EPUB workflow. Use for publication.json workspaces, init/preprocess/import/g0/build/qa/status/convert stage routing, glossary.csv three-state terminology, translation/align/ sentence tables, structured/ four-layer content, or EPUB output. The only LLM is the agent using the CLI (no internal LLM calls).
compatibility: opencode
metadata:
  suite: auto-epublizer
  workspace_model: publication.json
---

# auto-epublizer

`auto-epublizer` is a Python CLI that provides two capabilities over one shared pipeline:
**translation** (foreign-language documents → any target language) and **EPUB conversion**
(heterogeneous sources → standard EPUB 3). The workspace uses `publication.json` as its
authoritative index.

**Single-LLM principle**: the **only LLM in this project is the agent operating this CLI
itself**. The CLI performs only deterministic, zero-token computation (parsing / slicing /
detection / validation / building / auditing); **content understanding, translation, review
judgement, final terminology arbitration, formula LaTeX, content description, and
repair/release decisions** are all done by the agent using this Skill with its own
abilities (read files, judge, write files). The agent needs only basic capabilities and no
MCP/sub-agents.

## Non-negotiable red lines

1. **Do not hand-edit `publication.json`** — state advances only through CLI commands
   (import/g0/qa/meta).
2. **`source/` and `references/user/` must never be modified**.
3. **Structure (chapter splitting / heading hierarchy) is finalized before translation**;
   mid-course changes require re-running the affected units (re-ingest + re-translate), and
   old translations do not count.
4. **G0 terminology hits / marker conservation / footnote conservation / source fidelity /
   table shape are defects, not suggestions**, and must be zeroed before release; only the
   length ratio is advisory.
5. **EPUB is not the source of truth** — when a problem is found in the finished product,
   fix `translation/` + `align/` and rebuild; do not hand-patch the product files.
6. **`qa` released ≠ ready to publish**: before publishing you must pass the
   rights + privacy gate in `references/publishing.md`.
7. **Single-LLM principle**: the CLI is zero-token; all semantic judgement is done by you,
   and introducing any LLM API call is forbidden.
8. **Translator credit defaults to your agent framework name** (OpenCode/DouBao…); a
   user-specified name takes priority (written via `meta --translator`).

## Route Before Acting

First run `auto-epublizer version`; if it is lower than this directory's `manifest.json`
`minimum_cli_version`, stop and ask the user to upgrade the CLI (the skill and CLI contract
are incompatible). Then run `auto-epublizer doctor --json` for the capability self-check
(toolchain/dependencies/MinerU/network), and **self-report multimodal / search** (whether
you can see images and whether you have a search tool — the CLI cannot probe these) —
choose the ingest route accordingly (see the capability-routing decision table in
`references/ingest.md`). Then read this Skill directory's `manifest.json`, and read only
the reference needed for the current stage.

| Scenario | Read |
|---|---|
| Fresh task / state routing / multi-stage request / command overview | `references/workflow.md` |
| Preprocessing: read facts → write todo/capabilities/plan/global/units/terms/risks/report | `references/preprocessing.md` |
| File parsing: PDF / scanned PDF / EPUB / DOCX / HTML / TXT / MD / OCR | `references/ingest.md` |
| Semantic repair: parse-defect repair / OCR fixes / structural re-split (signal-triggered; mandatory for OCR) | `references/repair.md` |
| Four-layer structure classification, cleaning, running head/footer and page-number removal, provenance | `references/structure.md` |
| Layered understanding, terminology seeding, language/genre detection | `references/analysis.md` |
| Chunk translation, sentence-level alignment, three-state terminology loop, agent handwritten-translation path | `references/translation.md` |
| Six-gate QC (G0–G5) operational guide | `references/review.md` |
| Pre-delivery full validation (after qa, before delivery; mandatory) | `references/delivery.md` |
| EPUB build, deterministic packaging | `references/build.md` |
| epubcheck + unpack audit, quality report | `references/qa.md` |
| Genre profile (novel/academic/paper/poetry/newspaper) application | `references/style.md` |
| Complete release-conditions set / error-code quick reference / troubleshooting interpretation | `references/invariants.md` |
| Publishing/distributing the product (GitHub release / private distribution), rights and privacy | `references/publishing.md` |
| Field experience with source sites / dirty sources / edge cases (Baka-Tsuki illustration segments, offline epubcheck, etc.) | `lessons/` (match by topic; read only when it hits) |

> **Legacy workspace fingerprint**: if the directory contains `split/`,
> `split_translated/`, `.progress`, a root `GLOSSARY.csv`, `_analysis.md`,
> `_understanding.md`, etc. → **stop**: this is a file-based workspace from the
> traditional-translation skill; switch to that skill to continue, or confirm with the
> user about migration. Migration = a **semantic redo** by re-`init`/`preprocess` from the
> original `source/` files; legacy translations serve only as cross-reference evidence and
> **must not** be copied into this workspace or used as canonical IDs.

## Boundary (non-violable)

1. `source/` and `references/user/` are read-only and must never be modified; source file
   content is bound via `publication.json.meta.source_sha256`.
2. `publication.json` is the only source of truth and **hand-editing is forbidden**; all
   state changes go through CLI commands.
3. `structured/` (including `raw/` intermediates) is persisted for review and can be
   rebuilt from the source files; `analysis/`, `translation/`, `reviews/`, `output/` are
   intelligent artifacts.
4. Review artifacts are written only to `reviews/review-<ts>/` (shadow translation,
   result.json); the official `translation/` is overwritten only after an explicit agent fix.
5. This project **does not review the copyright risk of the processed object** (rights are
   the user's responsibility); the workspace (including `source/` and all processing
   artifacts) is **fully tracked in git** and by default is uploaded as a **private
   repository** to the configured hosting platform (default GitHub); making it public
   requires an explicit user declaration or the user handling it themselves.

## Command Discipline

- Use `status --json` or `--json` output for machine decisions; do not parse colored
  terminal text.
- On command failure, read the error code and Chinese message, fix the workspace/input, and
  retry; completed units can be safely skipped.
- Run only one long pipeline command per workspace at a time to avoid concurrent writes to
  `publication.json`.
- After changing the glossary/understanding/parsing, re-run the subsequent stages for the
  affected units (state machine `split → analyzed → translated → aligned → reviewed →
  built`).

## Standard workflow

```bash
auto-epublizer doctor --json                              # capability self-check (before starting; multimodal/search self-reported)
auto-epublizer preprocess <input>                         # preprocessing: init + zero-token facts → preprocessing/facts.*
#   agent reads facts.md and writes todo/capabilities/plan/global/units/terms/risks/report (see references/preprocessing.md)
#   the understanding layer analysis/*.md is likewise written by the agent (see references/analysis.md)
auto-epublizer meta --translator OpenCode                             # metadata verification write-back + translator credit (default = agent framework name)
auto-epublizer import [--unit <id>] [--terms preprocessing/terms.csv]  # register agent-written translation artifacts
auto-epublizer import --reviewed                                    # after review passes: aligned → reviewed
auto-epublizer knowledge export --workspace .             # seed same-pair confirmed terms from the unified store → preprocessing/terms.csv
auto-epublizer knowledge import --workspace .             # write workspace terms back to the unified store (cross-book reuse + auto git commit)
auto-epublizer knowledge import-csv <csv> --src-lang en --book <slug>  # import historical/arbitrary term CSV
#   unified store defaults to ~/Documents/auto-epublizer (a private git repository); see references/workflow.md for init/path/status/push
auto-epublizer g0                                         # static validation (terminology hits = real defects that must be zeroed; length ratio = advisory)
#   agent writes review artifacts reviews/review-<ts>/ (including result.json, see references/review.md)
auto-epublizer build [--bilingual] [--theme standard|compact|spacious]  # build EPUB → output/
auto-epublizer qa                                         # epubcheck + unpack audit
auto-epublizer status --json                              # view progress/state machine/artifact-state reconciliation
```

Conversion only, no translation: `auto-epublizer convert <input> -o output/book.epub`.
