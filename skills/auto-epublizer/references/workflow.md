<!-- i18n: source=workflow.zh.md sha256=ed21023da2244f34a2439c3887491c1954d294b5c59209434bf79aad4951f99a -->
> **English** | [中文](workflow.zh.md)

# Workflow (stage routing + command overview)

## State routing

The workspace is `<workspaces_dir>/<book-slug>/`, and the authoritative index is
`publication.json`.

**Before starting**: `auto-epublizer doctor --json` self-checks the environment
(pandoc/pymupdf/OCR/epubcheck/MinerU/network), and self-reports multimodal / search
(whether you can see images and whether you have a search tool) — choose the ingest route
from the capability-routing decision table in `references/ingest.md`.

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

When you hit a **source-site / dirty-source / edge case** (e.g. Baka-Tsuki illustration
segments not rendering, installing the epubcheck jar offline, MediaWiki volume-navigation
junk mixed into structured), first check the `lessons/` directory — it contains the
"criterion + handling + verification" distilled from real work; if it matches, follow it;
if not, investigate on your own.

## Standard stages

```text
doctor (capability self-check: toolchain + self-reported multimodal/search)
  -> preprocess (CLI: sniff/metadata/TOC/health/size -> preprocessing/facts.*, zero-token)
  -> agent understanding (read facts.md and write capabilities/plan/global/units/terms/risks/report;
                 analysis/*.md is also written by the agent)
  -> semantic repair (optional/conditional: triggered by suspicious signals in facts; mandatory
                 for OCR/scanned paths — per references/repair.md, repair structured/ against
                 raw evidence and write preprocessing/repairs.jsonl as a trace)
  -> terminology seeding (knowledge export: same-language-pair confirmed terms -> preprocessing/terms.csv;
                 after agent review, import --terms into the workspace)
  -> translation (agent hand-writes translation/ + align/, then import to register)
  -> g0        (static validation: terminology hits = real defects that must be zeroed; length ratio = advisory)
  -> review    (QC G1–G3; after agent semantic review, write reviews/review-<ts>/result.json)
  -> unified store write-back (knowledge import: merge the workspace's confirmed terms into
                 the unified store and auto git commit; when possible knowledge push to a
                 hosting platform for cross-device sync)
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

## Delivery wrap-up: feedback contribution (optional)

After delivery is complete, ask the user: **Should the technical problems encountered in
this work and the proposed solutions be submitted as an issue to the project's GitHub
repository (`Misaka0x26FE/auto-epublizer`)?** If the user agrees:

1. **Check GitHub login status**: `gh auth status`. Logged in → continue under that account
   (i.e. the user's account); not logged in → ask the user to log in to their own GitHub
   account first (`gh auth login`, via the browser/device-code flow); do not ask the user
   for a password or token, and continue only after login succeeds.
2. **Prepare the content** (technical problems and solutions only, following the
   criterion/handling/verification three-part structure of `lessons/`):
   - Pure experience write-up → write `skills/auto-epublizer/lessons/<date>-<topic>.md` and
     update the `lessons/README.md` index;
   - If a code defect was fixed during the work → include the corresponding regression test
     and docs sync, follow the repository conventions
     (`uv run pytest -q` + `ruff check .` + `ruff format --check .`), and commit locally as
     a single-topic Conventional Commit (the issue flow does not require a fork/branch/push).
3. **File the issue in the user's name, with reference code attached**:
   - `gh issue create --repo Misaka0x26FE/auto-epublizer --title <topic>
     --body-file <temp-file>` (the body is long, use `--body-file` rather than `--body`);
   - issue body = problem symptoms + root cause + proposed solution + verification results
     (three parts) + **reference code** (i.e. the change that could have been a PR, for the
     maintainer to adopt directly):
     - Code fix → the complete patch from `git format-patch -<N> <commit>` (or `git diff`),
       pasted into a ```diff fenced code block (the maintainer can merge it directly with
       `git am` / `git apply`);
     - Pure experience write-up → paste the full lesson file into a ```markdown fenced code
       block.
4. **Privacy reminder (must say)**: the submission must not contain the user's book source
   files, translations, metadata, or any personal information; show the issue title/body/
   reference code to the user for confirmation before submitting.

## Command overview

```bash
# capability self-check (mandatory before starting; multimodal/search supplied by the agent's own report)
auto-epublizer doctor [--json] [--ping]

# preprocessing (new book: init + zero-token fact collection → preprocessing/facts.*; existing workspace: idempotent refresh)
auto-epublizer preprocess <input> [--reference <path...>] [--target zh-CN] [--workspace <dir>]
# (agent reads facts.md and writes capabilities/plan/global/units/terms/risks/report, see references/preprocessing.md)
# init <input> is equivalent to the workspace-creation subset of preprocess (produces no facts; still usable for split-only scenarios)

# registration entry after agent hand-writes translation (G0 structural validation + state advance + terminology-conflict externalization)
auto-epublizer meta [--translator X] [--publisher P] [--date D] [--rights R] [--workspace <dir>]
auto-epublizer import [--unit <id>] [--terms <csv>] [--reviewed] [--workspace <dir>]

# unified terminology/knowledge store (cross-workspace persistent + git-maintained; default ~/Documents/auto-epublizer)
auto-epublizer knowledge init [--remote <url>] [--push] [--dir <dir>]  # skeleton + git init
auto-epublizer knowledge export [--workspace <dir>] [--src-lang en]    # same-pair confirmed terms → preprocessing/terms.csv
auto-epublizer knowledge import [--workspace <dir>] [--src-lang en]    # workspace glossary.csv → store (merge + auto commit)
auto-epublizer knowledge status [--json] | push [--remote <name|url>] | path

# unit-boundary rebuild registration (after the agent re-splits/merges; preprocessing/structure.csv → publication.json)
auto-epublizer restructure [--workspace <dir>]

# G0 zero-token static validation (run immediately after translation/import; terminology hits are a hard release gate, length ratio advisory)
auto-epublizer g0 [--unit <id>] [--workspace <dir>]

# build (translation missing falls back to source; --bilingual produces -bi.epub; --theme selects the layout theme)
auto-epublizer build [--bilingual] [--theme standard|compact|spacious] [-o <out.epub>] [--workspace <dir>]

# QA (epubcheck zero errors + unpack audit + provenance audit + G5 release decision)
auto-epublizer qa [--epub <path>] [--workspace <dir>]

# conversion only, no translation
auto-epublizer convert <input> [--theme standard|compact|spacious] [-o <out.epub>] [--workspace <dir>]

# progress / state machine / artifact-state reconciliation
auto-epublizer status [--workspace <dir>] [--json]
```

## State machine and `status --json`

Unit state machine: `pending → split → analyzed → translated → aligned → reviewed → built`.

```bash
auto-epublizer status --workspace <dir> --json
# {"slug":"book","title":"...","target_language":"zh-CN","units_total":N,
#  "units":[{"id":"ch01","kind":"chapter","title":"...","status":"built",
#            "has_translation":true,"has_align":true}, ...],
#  "has_preprocessing":true,"preprocessing_complete":false,
#  "stale":[{"id":"preprocessing","status":"facts_written","reason":"preprocessing_plan_missing"}]}
```

- `stale`: the agent has handwritten translation/align but has not yet `import`-registered it,
  or the preprocessing facts are produced but the understanding artifacts
  (capabilities/global) are incomplete — a signal that the state machine and artifacts have
  fallen out of sync.
- Agent handwritten artifacts only advance state after `import` is run; `import` validates
  seq continuity / empty translations (blocking) and length ratio / terminology hits
  (warnings).

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
