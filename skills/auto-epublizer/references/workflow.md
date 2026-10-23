<!-- i18n: source=workflow.zh.md sha256=3073869712a30d5ed01db6156e7fbabfd549812cadd76cb79d6a0384f94dac21 -->
> **English** | [中文](workflow.zh.md)

# Workflow (stage routing + command overview)

## State routing

The workspace is `<workspaces_dir>/<book-slug>/`, and the authoritative index is
`publication.json`.

**Before any CLI**: complete the user-selected work root, official GitHub main checkout,
project `uv` environment, and non-overwriting skeleton generation in `references/work-root.md`.
Installing the skill does not install the engine. Execute all `auto-epublizer …` examples
on this page as `"$AEP_CLI" …` (exported by bootstrap). Relative book paths assume the work
root is the current directory; never put books in the source checkout.
Then compare `"$AEP_CLI" version` with the skill manifest's minimum and stop if incompatible.
`"$AEP_CLI" doctor --json` self-checks pandoc/pymupdf/OCR/epubcheck/MinerU/network; self-report
multimodal/search and select the ingest route from `references/ingest.md`.

```text
No publication.json              -> fresh flow: first preprocess <input> (= init + fact collection)
publication.json present         -> resume: status --json to see the state machine and reconciliation (stale / preprocessing)
  preprocessing_complete=false   -> complete the agent understanding artifacts per the facts.md to-do (todo.md detailed checklist + capabilities/plan/global/...)
  all unit status = built        -> done, skip the corresponding stages
  has structured/ no analysis/ and no preprocessing/global.md -> agent writes global.md (understanding layer)
  has translation/ but status not advanced (stale) -> run import to register
  has translation/ no reviews/   -> agent writes review artifacts reviews/review-<ts>/
  has output/*.epub              -> already built; qa or rebuild
```

### Machine next-task pointer (weak-model path)

`status --json` also returns `next_tasks: [{kind, unit?, hint, done_when}]`, derived from
the existing state machine (no second state source). Execute **only the first entry**, then
re-run `status --json` to refresh — do not plan the whole flow yourself. `done_when` is the
machine form of the completion criterion (a CLI command or a workspace file), so it can be
checked without trusting a model's self-assessment.

When you hit a **source-site / dirty-source / edge case** (e.g. Baka-Tsuki illustration
segments not rendering, installing the epubcheck jar offline, MediaWiki volume-navigation
junk mixed into structured), first check the `lessons/` directory — it contains the
"criterion + handling + verification" distilled from real work; if it matches, follow it;
if not, investigate on your own.

## Standard stages

```text
bootstrap (work root + official main + uv + non-overwriting skeleton) -> version (compatibility gate)
doctor (capability self-check: toolchain + self-reported multimodal/search)
  -> preprocess (CLI: sniff/metadata/TOC/health/size -> preprocessing/facts.*, zero-token)
  -> agent understanding (read facts.md and write capabilities/plan/global/units/terms/risks/report;
                 analysis/*.md is also written by the agent)
  -> semantic repair (optional/conditional: triggered by suspicious signals in facts; mandatory
                 for OCR/scanned paths — per references/repair.md, repair structured/ against
                 raw evidence and write preprocessing/repairs.jsonl as a trace)
  -> note structuring (mandatory for books with notes: notes candidates exports candidates →
                 the agent verifies each one as disposition=note|not_note → write
                 structured/notes.json + in-place body markers [^ref-…] → notes register;
                 see references/notes.md)
  -> terminology seeding (knowledge export: same-language-pair confirmed terms -> preprocessing/terms.csv;
                 after agent review, import --terms into the workspace)
  -> translation (agent hand-writes translation/ + align/; for books with notes, keep the same
                 ref_id at the corresponding semantic position and write translation/notes.json,
                 then import to register)
  -> g0        (static validation: terminology hits = real defects that must be zeroed; length ratio = advisory;
                 the note-number set difference footnote_suspect = advisory for item-by-item verification)
  -> review    (QC G1–G3; after agent semantic review, write reviews/review-<ts>/result.json)
  -> unified store write-back (knowledge import: merge the workspace's confirmed terms into
                 the unified store and auto git commit; knowledge push syncs across devices;
                 the remote is built in as the public store auto-epublizer-knowledge, so
                 init needs no --remote)
  -> build     (EPUB build -> output/)
  -> qa        (epubcheck + unpack audit + G5 release -> report.json)
  -> delivery  (delivery audit: full validation per references/delivery.md + write
                 reviews/delivery-<ts>.md; mandatory, and after all units are built qa
                 will remind with W_DELIVERY_AUDIT_MISSING)
```

Conversion only, no translation:

```text
convert <input>   -> normalize + structure + EPUB + QA
```

## At delivery or when problems arise: feedback contribution (optional, issue + PR)

Ask whether the user wants to contribute: **issues report symptoms and minimal synthetic
reproduction; PRs carry actual repairs, regression tests, or documentation improvements**.
They may choose either or both, linking the issue and PR. Do not replace a PR by dumping
the complete repair patch into an issue. Book delivery and problem handling do not depend
on public contribution.

### Default: sanitized local drafts only

1. Write drafts in the work root's `docs/feedback-issue.md` and/or `docs/feedback-pr.md`
   as needed; do not automatically commit them anywhere. An issue draft contains generic
   symptoms, minimal fictitious input, exact commands, expected/actual results, and public-safe
   tool versions. Mark an unknown cause unknown. A PR draft states the reason, exact change
   scope, synthetic regression fixtures, and checks actually run with their results; explicitly
   label unexecuted checks.
2. **Never transmit** real book titles/authors, file/workspace names, original/translated
   text or quotations, real paths, credentials, sensitive report metadata, or user/book Git
   history (including logs, patch context, attachments, branch names, and commit messages).
   Recreate a minimum example with entirely fictitious `sample.md`, `sample-workspace`, and
   self-written sentences. Do not excerpt "harmless-looking" real book content or paste raw
   facts/report/events or format-patch output. Preserve the public project's name, URL,
   and author attribution; do not disguise private material as a public fixture.
3. Show the user the **complete sanitized title, body, every proposed attachment/patch,
   and destination repository**. Obtain explicit approval for the planned issue, fork, push,
   and PR network writes; one approval may explicitly cover them all. General willingness
   to receive feedback is not authorization. Without approval, keep only local drafts:
   **never execute** issue create, fork, push, or pr create. If content/action scope changes
   after approval, show it again and obtain renewed consent.
4. After approval, use `gh auth status` to confirm **the user's own account**. Missing login
   or permissions means stop at the draft. The user can resolve this themselves with
   `gh auth login` via browser/device code. Never solicit passwords or tokens, borrow the
   maintainer/agent identity, or redirect the submission elsewhere to bypass permissions.

### Approved issue

This template is for manual execution **only after the approval and authentication above**.
Replace the title with the approved sanitized title first:

```bash
gh issue create --repo Misaka0x26FE/auto-epublizer \
  --title 'Synthetic input: concise symptom' \
  --body-file "$AEP_ROOT/docs/feedback-issue.md"
```

Keep the issue to symptoms/reproduction/suggestions; use a PR below for an actual repair.
Link the confirmed public URLs in the drafts if both are created. Do not automatically
create Releases, upload book artifacts, or mutate existing online issues/PRs.

### PR for actual repair or documentation improvement

Use a **fresh, separate contribution checkout cloned from official main**, for example
`$AEP_ROOT/docs/contribution-source`. Do not switch the book-running engine checkout to a
contribution branch, and never fork/push a book repository, user Git history, or task history.
Preserve official public history and author attribution. Create a single-topic branch in
the fresh checkout and recreate only the sanitized actual repair/docs and synthetic regression
fixtures. Follow repository maintenance checks and record actual evidence in the draft.
Review content and diffs file by file; **only `git add -- <explicit-reviewed-files...>`,
never blindly `git add -A`**. Inspect the staged diff and commit message for privacy, then
make a local Conventional Commit. Show the final patch and PR draft and obtain the approval
above. Without an actual change, do not manufacture an empty PR.

These network-write templates apply **only to an approved actual commit**; the branch name
must match the reviewed local branch, and the contribution checkout must have official
`origin` and no existing `fork` remote:

```bash
contribution="$AEP_ROOT/docs/contribution-source"
account=$(gh api user --jq .login)
gh repo fork Misaka0x26FE/auto-epublizer --clone=false --remote=false
git -C "$contribution" remote add fork "https://github.com/$account/auto-epublizer.git"
git -C "$contribution" push fork HEAD:refs/heads/fix/synthetic-example
gh pr create --repo Misaka0x26FE/auto-epublizer --base main \
  --head "$account:fix/synthetic-example" \
  --title 'fix: concise synthetic regression repair' \
  --body-file "$AEP_ROOT/docs/feedback-pr.md"
```

Stop on authentication/permission failure or any failed step, preserving the draft without
automatically retrying writes. Report a real URL only after the tool confirms creation.
If unsubmitted, explicitly say "local draft only", not that feedback was sent upstream.

## Command overview

```bash
# capability self-check (mandatory before starting; multimodal/search supplied by the agent's own report)
auto-epublizer doctor [--json] [--ping]

# preprocessing (new book: init + zero-token fact collection → preprocessing/facts.*; existing workspace: idempotent refresh)
auto-epublizer preprocess <input> [--reference <path...>] [--original <path>] [--progress] [--target zh-CN] [--workspace <dir>]
#   --force (input omitted): rebuild structured/ + facts in place from source/ (recovery after an interrupted preprocess; unit status resets to split)
#   --original <path>: archive the unmodified delivered original into references/user/ (issue #30 §4.6)
#   --progress: per-page progress to stderr for long tasks (PDF slicing, issue #30 §4.4)
# (agent reads facts.md and writes capabilities/plan/global/units/terms/risks/report, see references/preprocessing.md)
# init <input> is equivalent to the workspace-creation subset of preprocess (produces no facts; still usable for split-only scenarios)

# registration entry after agent hand-writes translation (G0 structural validation + state advance + terminology-conflict externalization)
auto-epublizer meta [--translator X] [--publisher P] [--date D] [--rights R] [--workspace <dir>]
auto-epublizer import [--unit <id>] [--terms <csv>] [--reviewed] [--force] [--workspace <dir>]
#   --force: re-run the full blocking validation on reviewed/built units (post-delivery revision re-registration, issue #13);
#            pass keeps the original status, failure rolls the unit back to aligned

# unified terminology/knowledge store (cross-workspace persistent + git-maintained; default ~/Documents/auto-epublizer)
#   the remote is built in as the public store
#   https://github.com/Misaka0x26FE/auto-epublizer-knowledge (content CC BY-SA 4.0);
#   init needs no --remote; override for a self-hosted store/fork via --remote,
#   AUTO_EPUBLIZER_REMOTE or paths.knowledge_remote
auto-epublizer knowledge init [--remote <url>] [--push] [--dir <dir>]  # skeleton + git init (writes the CC BY-SA 4.0 LICENSE)
auto-epublizer knowledge export [--workspace <dir>] [--src-lang en]    # same-pair confirmed terms → preprocessing/terms.csv
auto-epublizer knowledge import [--workspace <dir>] [--src-lang en]    # workspace glossary.csv → store (merge + auto commit)
auto-epublizer knowledge status [--json] | push [--remote <name|url>] | path
auto-epublizer knowledge import-csv <csv> --src-lang en --book <slug>  # historical/arbitrary term CSV (legacy format auto-detected)

# unit-boundary rebuild registration (after the agent re-splits/merges; preprocessing/structure.csv → publication.json)
auto-epublizer restructure [--workspace <dir>]

# G0 zero-token static validation (run immediately after translation/import; terminology hits are a hard release gate, length ratio advisory)
auto-epublizer g0 [--unit <id>] [--workspace <dir>]

# note structuring and binding (books with notes; phase N: candidates → registration → product gate; see references/notes.md)
auto-epublizer notes candidates [-o <jsonl>] [--workspace <dir>]  # export candidates (zero-token; re-runs keep dispositions)
auto-epublizer notes register [--workspace <dir>]                 # separation-registration gate: validate and write publication.json.notes
auto-epublizer notes status [--json] [--workspace <dir>]          # summary / stale / candidate disposition progress

# build (translation missing falls back to source; --theme selects the layout theme)
auto-epublizer build [--theme standard|compact|spacious] [-o <out.epub>] [--workspace <dir>]

# QA (epubcheck zero errors + unpack audit + provenance audit + G5 release decision)
auto-epublizer qa [--epub <path>] [--workspace <dir>]

# conversion only, no translation
auto-epublizer convert <input> [--theme standard|compact|spacious] [-o <out.epub>] [--workspace <dir>]

# progress / state machine / artifact-state reconciliation
auto-epublizer status [--workspace <dir>] [--json]
#   --all: overview of every workspace under the base dir (multi-book summary; issue #32)
auto-epublizer status --all [--json] [--workspace <work-root>]

# cross-book ledger (markdown): machine-recomputable columns + blank domain/summary to fill
auto-epublizer ledger [-o <ledger.md>] [--workspace <work-root>]
```

## Machine-interface boundaries (#50)

Not every command supports `--json`; do not append it mechanically to arbitrary commands:

| Command | Machine-readable interface |
|---|---|
| `doctor`, `status` (including `--all`), `notes status`, `knowledge status` | Explicit `--json`; parse stdout as JSON |
| `qa` | Read workspace `report.json`, then check freshness with `status --json`; exit 0 means execution finished, not released |
| `build`, `import`, `g0`, `meta` | Follow actual help, reject nonzero exits, then read applicable state through `status --json` / `report.json`; rerun QA after later edits |
| `ledger` | Markdown; use `-o` for a file and `status --all --json` for progress decisions, not colored summaries |

`publication.json` is read-only state evidence for agents, not a manual state-advancement
interface. `report.json` establishes machine contracts only for its bound inputs; verify
freshness and scope. Successful execution does not prove semantic acceptance.

## State machine and `status --json`

Unit state machine: `pending → split → analyzed → translated → aligned → reviewed → built`.

```bash
auto-epublizer status --workspace <dir> --json
# {"slug":"book","title":"...","target_language":"zh-CN","units_total":N,
#  "units":[{"id":"ch01","kind":"chapter","title":"...","status":"built",
#            "has_translation":true,"has_align":true}, ...],
#  "has_preprocessing":true,"preprocessing_complete":false,
#  "stale":[{"id":"preprocessing","status":"facts_written","reason":"preprocessing_plan_missing"}],
#  "next_tasks":[{"kind":"translate","unit":"ch01","hint":"...","done_when":{"cmd":"import","unit":"ch01"}}]}
```

- `stale`: the agent has handwritten translation/align but has not yet `import`-registered it,
  or the preprocessing facts are produced but the understanding artifacts
  (capabilities/global) are incomplete — a signal that the state machine and artifacts have
  fallen out of sync.
- Agent handwritten artifacts only advance state after `import` is run; `import` validates
  seq continuity / empty translations (blocking) and length ratio / terminology hits
  (warnings).

## Multi-workspace work root (long-running projects)

For one book or many, first follow the safe bootstrap in `references/work-root.md`.
The existing `"$AEP_CLI" work-root "$AEP_ROOT"` generates the skeleton without `--force`.
Keep one separate workspace per book; `status --all` and `ledger` are the cross-book index.

```text
<work-root>/
├── auto-epublizer/    # official main source and .venv; no books or contribution branches
├── AGENTS.md          # how this directory works (keep the root to a single .md)
├── config.yaml        # workspaces_dir / qc.epubcheck.jar / pdf.*
├── inbox/ sources/    # inbox: not-yet-started sources; sources: staging copies named <slug>.<ext>
├── workspaces/<slug>/ # one workspace per book (the standard 11 top-level entries)
├── docs/              # process docs (plans / specs / audits)
└── references/        # cross-book shared baselines (read-only)
```

- Source identity is always `publication.json.meta.source_sha256`, never the file name;
- When the source was pre-processed (bookmarks injected, format converted), keep the
  **unmodified original** in `references/user/` (`preprocess --original`) alongside the
  `source/` ingest copy;
- `status --all --json` recomputes per-book `progress` (`released` / `built_not_released` /
  `preprocessing`), unit counts and words; `ledger` renders them as a table whose
  domain/summary columns the agent fills. **Never hand-maintain the numbers** — recompute.

## Troubleshooting

| Symptom | Handling |
|---|---|
| `工作区尚未初始化` | run `init` first; or `--workspace` points to the wrong directory |
| `输入文件内容与工作区不一致` | the source file was replaced; use the original source file or re-`init` |
| `成品不存在：...请先 build/convert` | run `build` before `qa` |
| `epubcheck errors: -1` | the epubcheck jar is not installed (`~/.cache/epubcheck.jar`); the G4 audit can still run, with `released_reason=epubcheck_not_run` |
| `导入失败` (import blocked) | fix align per the error list output by `--unit` (sequence gaps/empty translations/missing files) and retry |
| `pandoc` missing | `doctor` already flags it; install pandoc or first convert the file to PDF/TXT/MD |
| Scanned PDF cannot be processed | follow the OCR route (`doctor` + multimodal self-report): **MinerU external API first** (ask the user first when there is no key) → traditional OCR (tesseract/ocrmypdf)/rapidocr + agent page-by-page reading as fallback |
| Unit status stuck in an intermediate state / stale | locate with `status --json` and resume from the corresponding stage (run `import` for handwritten artifacts) |
