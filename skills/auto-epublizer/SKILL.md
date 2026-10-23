---
name: auto-epublizer
description: Orchestrates the auto-epublizer translation and EPUB workflow. Use for publication.json workspaces, init/preprocess/import/g0/build/qa/status/convert stage routing, glossary.csv three-state terminology, translation/align/ sentence tables, structured/ four-layer content, or EPUB output. The only LLM is the agent using the CLI (no internal LLM calls).
license: AGPL-3.0-only
compatibility: Requires an agent with file read/write and shell execution, Git, uv, Python 3.12+, and network access to GitHub and Python package indexes.
metadata:
  suite: auto-epublizer
  workspace_model: publication.json
---
<!-- i18n: source=SKILL.zh.md sha256=10de612aacb9984c0f8f569def54ef76e4e59cb51b2d7e8d07db20a880a68240 -->
> **English** | [中文](SKILL.zh.md)

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
4. **Blocking G0 terminology / marker / footnote / source-fidelity / table-structure violations
   are defects, not suggestions**, and must be cleared before release. Length ratio, forward
   missing-block findings and evidence-registered `terminology_exempt` are advisory;
   see `references/translation.md` and `references/review.md`.
5. **EPUB is not the source of truth** — when a problem is found in the finished product,
   fix `translation/` + `align/` and rebuild; do not hand-patch the product files.
6. **`qa` released ≠ ready to publish**: before publishing you must pass the
   rights + privacy gate in `references/publishing.md`.
7. **Single-LLM principle**: the CLI is zero-token; all semantic judgement is done by you,
   and introducing any LLM API call is forbidden.
8. **Translator credit defaults to your agent framework name** (OpenCode/DouBao…); a
   user-specified name takes priority (written via `meta --translator`).
9. **Standard EPUB acceptance is desktop-independent**: note semantics/content/links/backlinks/resources/current registration binding, independent notes gate, epubcheck, independent delivery reconciliation and distribution byte checks are mandatory. Reader GUI testing is conditional compatibility sampling; without a desktop/reader record "reader not tested", do not block standard delivery or promise universal popups. See `references/delivery.md` and `references/publishing.md`.
10. **EPUBCheck requires real process success evidence**: release requires `report.epubcheck.ran == true`, the actual `returncode == 0`, and `errors == 0`. A jar's presence, Java startup, or a legacy `ran` field does not prove success; process failures/FATAL must not count as zero errors. Keep the complete distribution's `lib` beside the jar; headless Java is sufficient. An unexecuted check has `returncode: null`; never guess 0 for an unknown result. Status marks legacy released reports without this evidence stale: rerun `qa`, never hand-edit their old `released` value.

## Route Before Acting

**Bootstrap before calling any CLI**: installing the skill installs instructions, not the
Python engine. First read `references/work-root.md`, establish the user's chosen work root,
safely clone/fast-forward official GitHub **main** at `<work-root>/auto-epublizer/`,
prepare the CLI with the project's `uv` environment, and generate the skeleton using the
existing `work-root` command (no `--force`). Book workspaces stay outside the source checkout.
An existing checkout must pass repository-root/origin/main and tracked+untracked dirty guards.
Ahead/divergent history or a wrong branch/origin stops; never reset/stash/clean/overwrite.

After success, run its exported `"$AEP_CLI" version` and compare with this skill's
`manifest.json` `minimum_cli_version`; stop if incompatible. Then run
`"$AEP_CLI" doctor --json` for toolchain/dependency/MinerU/network checks, and **self-report
multimodal / search** (image and search access cannot be probed by the CLI). Select the
ingest route from `references/ingest.md`. Execute every `auto-epublizer …` example in this
skill and its references as `"$AEP_CLI" …`; in a new shell, first follow safe reuse in
work-root rather than accidentally calling a global namesake. Read only the current stage's reference.

| Scenario | Read |
|---|---|
| First use / safe reuse (mandatory before version/doctor) | `references/work-root.md` |
| Fresh task / state routing / multi-stage request / command overview | `references/workflow.md` |
| Weak-model path: machine next-task pointer (`status --json`) + atomic task cards | `references/taskcards/` |
| Long-running work root, batch SHA256 delivery, retained ledger manual cells, link/ignore guards | `references/work-root.md` |
| Preprocessing: read facts → write todo/capabilities/plan/global/units/terms/risks/report | `references/preprocessing.md` |
| File parsing: PDF / scanned PDF / EPUB / DOCX / HTML / TXT / MD / OCR | `references/ingest.md` |
| Semantic repair: parse-defect repair / OCR fixes / structural re-split (signal-triggered; mandatory for OCR) | `references/repair.md` |
| Four-layer structure classification, cleaning, running head/footer and page-number removal, provenance | `references/structure.md` |
| Layered understanding, terminology seeding, language/genre detection | `references/analysis.md` |
| Chunk translation, heading-only empty align, `unit,source,reason` exemptions and three-entry advisory visibility | `references/translation.md` |
| Note structuring/binding, stable refs, label collisions/orphan hosts, complete notes and code-literal boundaries | `references/notes.md` |
| Six-gate QC (G0–G5), blocking/advisory handling | `references/review.md` |
| Pre-delivery full validation (after qa, before delivery; mandatory) | `references/delivery.md` |
| Evidence scope, audit honesty, safe index/structure repair tools (read before writing your own audit or bulk-repair script) | `references/quality-evidence.md` |
| EPUB packaging, code/raw HTML, SVG/media identity, software fingerprint, production credits and nav/NCX entry | `references/build.md` |
| epubcheck + unpack audit, independent body/note reconciliation, segmentation advisory, report invalidation | `references/qa.md` |
| Genre profile (novel/academic/paper/poetry/newspaper) application | `references/style.md` |
| Complete release-conditions set / error-code quick reference / troubleshooting interpretation | `references/invariants.md` |
| Publishing/distributing the product (GitHub release / private distribution), rights and privacy | `references/publishing.md` |
| Delivery or problems: opt-in sanitized issue / repair PR (local draft by default) | `references/workflow.md`, feedback contribution |
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

Full command overview and stage list: `references/workflow.md` (not repeated here — this
entry stays lean on purpose).

```text
bootstrap → version → doctor → preprocess → agent understanding/analysis → (repair) → translate → import
       → g0 → review → build → qa → delivery → ask about sanitized issue / PR contribution
```

Drive it from the machine pointer: take `status --json` → `next_tasks[0]`, do that task
(see `references/taskcards/`), re-run `status --json`, repeat.

Conversion only, no translation: `"$AEP_CLI" convert <input> -o output/book.epub`.

## Feedback contribution (at delivery or when problems arise)

**Use an issue for symptoms/minimal synthetic reproduction, and a PR for actual repairs
or documentation changes; both are supported.** Keep a sanitized draft in the work root's
`docs/`, show the full title, body, and proposed patch to the user, and obtain explicit
consent before issue create / fork / push / pr create. Without consent, keep only the local draft.
Never contribute real book titles/authors, file or workspace names, original/translated
text, real paths, credentials, sensitive report metadata, or Git history. Use fictitious
fixtures; never blindly `git add -A`. Authenticate as the user without soliciting tokens;
missing authentication/permissions means stop at the draft. Full procedure: `references/workflow.md`.
