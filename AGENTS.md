<!-- i18n: source=AGENTS.zh.md sha256=fc9b2c2a292d213479af649d9cf8dc5e92b1af35e50ff52bfd58982965d40da1 -->
> **English** | [中文](AGENTS.zh.md)

# auto-epublizer repository guide (for coding agents developing/maintaining this project)

This file is the entry contract for agents that **maintain this repository's code**: it
explains what the project is, how it is implemented, and how to verify it.

> If your task is to **process a book with this CLI** (translate / convert to EPUB), read
> `skills/auto-epublizer/` instead — those are installable instructions that turn the
> design into "copy and go" steps (see the "skills/ directory" section).

> This file is also the "what must be implemented" contract; if a subdirectory contains a
> more specific `AGENTS.md`, the deeper file wins.

## Project positioning

`auto-epublizer` (a Python CLI, three-package monorepo) provides two capabilities over one
shared pipeline:

1. **Translation**: foreign-language documents → any configurable target language.
2. **EPUB conversion**: heterogeneous sources (PDF / scanned PDF / EPUB / DOCX / HTML /
   TXT / Markdown) → standard EPUB 3.

- Python 3.12; package management with `uv`.
- **Single-LLM principle (hard constraint)**: the **only LLM in this project is the agent
  operating the CLI itself** — the CLI performs only deterministic, zero-token computation
  (parsing / splitting / detection / validation / building / auditing); all semantic work
  (understanding, translation, review judgement, terminology arbitration, formula LaTeX,
  content descriptions) is done by the agent with its own capabilities. **Adding any LLM
  API call is forbidden** (no new dependency, endpoint, or package extension); the legacy
  internal LLM paths (`auto_common/llm/`, the `agents/` package, the translate/analyze/
  review commands) **have been removed**, see
  [docs/plans/2026-09-04-remove-internal-llm.md](docs/plans/2026-09-04-remove-internal-llm.md),
  enforced by `test_no_llm_api_calls_anywhere` in `test_architecture_boundaries.py`. The
  criterion is unchanged: "same input must yield same output → Python; needs
  understanding/weighing/judgement → agent"; the full version is in
  [docs/agent-vs-code.md](docs/agent-vs-code.md).
- The workspace is a `publication.json` authoritative index plus a workspace directory
  (below); the old `split/` flow is not used.
- Six quality gates (G0–G5), drawing heavily on wenyi's (`trans_novel`) Review system.
- **Responsible for delivery quality only** (accurate / complete / consistent / compliant /
  structurally correct / reproducible); it **makes no value, political or ideological
  judgements about the content**.
- **Copyright and publishing responsibility**: the project **does not review whether the
  processed object (source files, illustrations, etc.) carries copyright risk** — rights
  are the user's responsibility. The working directory produced during processing
  (including `source/`) is **fully tracked in git** and by default is uploaded as a
  **private repository** to the configured git hosting platform (default GitHub); making
  it public requires the user to handle it themselves or to make an explicit declaration.
- **Division of labour**: the CLI does deterministic computation and validation/release;
  **content understanding, semantic judgement, quality gating, terminology arbitration and
  repair decisions** are done by the agent using this project with its own abilities
  (read files, judge, write files). The agent needs only basic capabilities — no MCP or
  sub-agents.
- **Artifact specs**: the EPUB form spec (unstyled template / limited themes / standard
  popup notes) is in [docs/epub-template-spec.md](docs/epub-template-spec.md); the
  post-processing acceptance and implementation plan (content provenance / media / TOC
  hierarchy) is in [docs/postprocessing-spec.md](docs/postprocessing-spec.md).
- **License**: the project's own code is **AGPL-3.0**; third-party dependencies keep their
  own licenses and are registered in `THIRD_PARTY_LICENSES.md` (AGPL dependencies may be
  used directly, as they are compatible with the project license).

## Standard workflow for processing a work

```bash
# 0. Capability self-check (the agent must do this before starting: its own capability
#    boundary + the environment toolchain)
auto-epublizer doctor [--ping]   # toolchain/deps/MinerU/network probe; multimodal/search self-reported by the agent

# 1. Install
uv sync

# 2. Configure (no secret section; the optional external parsing API's MINERU_API_KEY is
#    read from the environment only, see "Configuration, secrets and providers")

# 3. Preprocessing (zero-token fact collection + agent understanding):
auto-epublizer preprocess <input>   # new book: init + sniff/metadata/TOC/health/size → preprocessing/facts.*
#    The agent reads facts.md and writes, per the to-do list: todo.md (detailed task list,
#    checked off throughout) / capabilities.md (self-reported five dimensions) / plan.md
#    (approach decisions) / global.md (global understanding) / units/<id>.md /
#    terms.csv / risks.md / report.md
auto-epublizer preprocess           # existing workspace: idempotent refresh of facts

# 3.5 Metadata verification and translator credit (agent task): verify the sniffed facts
#     against the source copyright page and write back via the meta command; translator
#     credit defaults to the agent framework name (OpenCode/DouBao/...)
auto-epublizer meta [--translator OpenCode] [--publisher ...] [--date ...] [--rights ...]

# 4. Analysis (agent task): analysis/*.md and the glossary are written by the agent itself
#    (overview/global/per-unit/key points; context may also come from preprocessing/)

# 4.5 Unified terminology/knowledge store (cross-workspace persistent, maintained by the
#     agent itself; default ~/Documents/auto-epublizer, a private git repository, pushable
#     across devices via knowledge push): run knowledge path/init first, then seed the
#     same-language-pair confirmed terms (add --src-lang <code> when the source is auto)
auto-epublizer knowledge export --workspace .   # → preprocessing/terms.csv (agent reviews, then import --terms)
auto-epublizer knowledge status                 # statistics + git state (--json for machine decisions)

# 5. Translation (agent task): the agent reads structured/ and translates, writing
#    translation/ + align/, then "import" registers it: G0 validation + state advance +
#    terminology-conflict externalization (terms.csv may be imported via --terms)
auto-epublizer import [--unit <id>] [--terms preprocessing/terms.csv] [--reviewed]
                                 # register agent-written translation artifacts; --reviewed advances
                                 # aligned units to reviewed (explicit registration of review
                                 # acceptance; reviewed/built skip re-import)
auto-epublizer g0                # run static validation right after translating/importing (terminology hits are real defects to verify one by one; length ratio is only advisory)

# 5.5 Semantic repair (agent task, conditionally triggered): when facts carry suspicious
#     signals, or the OCR/scanned path was used, follow references/repair.md to repair
#     structured/ against raw evidence and write preprocessing/repairs.jsonl; for unit
#     boundary re-splits/merges also write preprocessing/structure.csv and register it (S3)
auto-epublizer restructure [--workspace <dir>]   # register rebuilt unit structure (unchanged ids keep state)

# 6. Review (agent task): the agent performs G1–G3 semantic review itself and writes
#    reviews/review-<ts>/ (issues/patches/summary/result.json; qa reads g1/g2/g3 counts
#    from result.json)

# 6.5 Unified store write-back (after terminology is finalized): merge the workspace
#     glossary.csv into the unified store (auto git commit; knowledge push syncs across
#     devices when possible)
auto-epublizer knowledge import --workspace .   # cross-book same-key different-target is externalized to the store's conflicts.jsonl pending agent arbitration

# 7. Package output
auto-epublizer build          # translation-only / bilingual EPUB → output/ (--theme selects the layout theme)

# 8. QA (G0 static validation + G4 audit + G5 release summary → report.json)
auto-epublizer qa             # structure audit + epubcheck
auto-epublizer status --json  # inspect progress/state machine/artifact-state reconciliation

# 9. Delivery audit (agent task, mandatory): follow
#    skills/auto-epublizer/references/delivery.md for full independent reconciliation +
#    sampling + manual checks → write reviews/delivery-<ts>.md
```

Conversion only, no translation: `auto-epublizer convert <input> -o output/book.epub`.

**State invariants**: semantic artifacts are hand-written by the agent; `publication.json`
state advances only through CLI commands (`import` registers translation artifacts and
`restructure` registers unit-boundary rebuilds — the two entries through which
agent-written artifacts enter the CLI; review artifacts `result.json` are hand-written by
the agent and state advances per their contract). The agent never edits state by hand; all
artifacts flow into the same G0 validation, state machine, terminology loop, build and QA.

## skills/ directory (installable instructions for downstream agents)

`skills/auto-epublizer/` is **module one**: it turns the design in `docs/` into steps a
downstream agent can follow to finish a book. It divides labour with this file
(`AGENTS.md`) as follows:

| Document | Audience | Question it answers |
|---|---|---|
| `AGENTS.md` (this file) | Agents developing/maintaining this project | What the project is, how it is implemented, how to verify it |
| `skills/auto-epublizer/` | Agents processing a book with this CLI | What to do at each step, how to read the results, how to fix |

`skills/` structure (pure documentation, no business logic):

```text
skills/auto-epublizer/
├── SKILL.md               # entry: route by workspace state (no publication.json → fresh flow; present → resume)
├── manifest.json          # metadata + references list
└── references/            # per-topic operational guides (read only the current stage on demand)
    ├── workflow.md        # stage routing + command overview + status --json reading + troubleshooting
    ├── preprocessing.md   # preprocessing: read facts → agent writes plan/global/units/terms/risks/report
    ├── ingest.md          # file parsing (pandoc / PDF page slicing / OCR fallback)
    ├── repair.md          # semantic repair: parse defects / OCR fixes / structural re-split (signal→fix→trace)
    ├── structure.md       # four-layer structure classification + cleaning + provenance
    ├── analysis.md        # layered understanding (overview/global/units/keypoints) + terminology seeding
    ├── translation.md     # chunk translation + sentence alignment + three-state terminology loop
    ├── review.md          # six-gate QC operational guide (when to run G0–G5, how to read reports, how to fix)
    ├── build.md           # EPUB packaging + determinism
    ├── qa.md              # epubcheck + unpack audit
    ├── delivery.md        # delivery audit: mandatory full validation after qa (independent reconciliation + sampling + delivery record)
    └── style.md           # genre profiles (novel/academic/paper/poetry/newspaper) + langprofile
```

- Each reference covers exactly one stage; SKILL.md's "Route Before Acting" table makes the
  agent read only one file for the current stage instead of loading everything at once.
- Documentation follows **actual CLI capability**: unimplemented items (e.g. automatic G0
  wiring, web search) are explicitly marked "future extension" so agents do not act on
  features that do not exist.
- Install: `scripts/install-skills.sh --target opencode` copies it into the agent's skills
  directory.

> When maintaining this repository, if you change a CLI command, the workspace contract or
> QC behaviour, you must update the corresponding reference and the SKILL.md routing table.

## Documentation map (each of the four doc types has its place)

| Directory | Role | Content | When to add/update |
|---|---|---|---|
| `docs/` root | **Specs / handover / reference / testing guides** | Design specs (`pdf-content-spec` / `epub-template-spec` / `postprocessing-spec` / `semantic-repair`), cross-cutting docs (`agent-vs-code` / `quality-control` / the `quality-lessons` spec table / `configuration` / `translation-flow` / `publishing-workflow`), reference projects (`reference-projects`), handover (`workstate`, historical progress snapshot `progress-snapshot-2026-09-01`), DouBao environment testing guide (`testing-doubao`) | When design/handover flow changes |
| `docs/plans/` | **Plan documents, one per task** | `YYYY-MM-DD-<topic>.md`, drafted → implemented → status written back (completion marked with commit hash); README index | When each development task is planned |
| `skills/auto-epublizer/references/` | **Routine operational guidance for book-processing agents** | One per stage (workflow/preprocessing/ingest/.../style) | When CLI commands / workspace contract / QC behaviour change |
| `skills/auto-epublizer/lessons/` | **Situation-specific experience from real work** | Criterion / handling / verification, one topic per file; index includes source and destination | When a specific source site, dirty source or edge case is encountered and solved |

**Where lessons belong**: a plan document's verification record (e.g. §6 of
`pdf-dogfooding`) is the **source** of reusable experience, but the experience itself is
**deposited in `lessons/`** (the plan keeps the verification context; the lesson offers
"how to judge/fix the same kind of situation"); spec tables (e.g. the positive
goals/negative constraints in `quality-lessons.md`) stay in `docs/` as QC design
rationale. New lessons always go to `lessons/`; never stuff lesson prose into plans.

**Documentation i18n (bilingual)**: docs use the "English default `X.md` + Chinese
`X.zh.md`" convention, with **Chinese as the authoritative source** and English as the
derived translation; when you change a Chinese source you must update the English version
and run `python scripts/i18n.py --finalize X.md` (`--check`/`--links` are enforced by
`tests/test_i18n.py`); naming, scope and the glossary are in `docs/i18n.md`. Historical
plans (`docs/plans/`), `template/`, `THIRD_PARTY_LICENSES.md`, CLI output and code comments
stay Chinese-only.

## Workspace directory contract

```text
<book-slug>/
├── source/           ① file to process (untouched, never modified)
├── output/           ② finished EPUB (<slug>.epub / <slug>-bi.epub)
├── structured/       ③ source split by the four-layer publication structure (frontmatter/body/backmatter/media)
│                     + raw/ (intermediates from processing the source: OCR page images, PDF→HTML,
│                     pages/ (rendered scanned pages), mineru/ (MinerU artifacts), persisted for review)
├── analysis/         ④ layered understanding (agent artifacts: overview/global/units/keypoints/glossary, etc.)
├── translation/      ⑤ translation (mirrors the structured tree) + align/<unit-id>.jsonl sentence-level alignment
├── reviews/          ⑥ review-run records review-<ts>/ (issues/patches/summary/result.json)
├── references/       ⑦ references: user/ (user uploads) + web/ (agent web retrieval) + index.jsonl
├── preprocessing/    ⑧ preprocessing layer: facts.json/facts.md (CLI zero-token facts) +
│                       agent-written todo.md (detailed task list) / plan/global/units/terms/risks/report
│                       + catalog.csv (optional source inventory: included/physical/excluded/unresolved)
│                       + repairs.jsonl (optional semantic-repair trace: done/unresolved)
│                       + structure.csv (optional structural-rebuild list, used by restructure)
├── publication.json  authoritative index (DC metadata + content tree + state machine + config snapshot)
├── .progress.json    (reserved) batch-level checkpoint; not written today, so resume = unit-level skip
├── glossary.db       terminology-store internal index (optional, SQLite)
└── events.jsonl      append-only behavior ledger
```

Unit state machine: `pending → split → analyzed → translated → aligned → reviewed → built`
(`reviewed` = passed review, `built` = packaged; the `convert` path skips analysis /
translation / review and goes split → built directly).

Directory lifecycle: `source/` and `references/user/` are immutable; `structured/`
(including `raw/` intermediates) is persisted for review and can be rebuilt from the
source; `preprocessing/facts.*` is generated idempotently by the CLI, while the rest of
`preprocessing/`, `analysis/`, `translation/`, `reviews/` and `output/` are intelligent
artifacts; `events.jsonl` is an append-only ledger; `.progress.json` is a reserved
checkpoint file (not written today — resume is actually done by skipping completed units
per `publication.json`); `publication.json` and `glossary.db` are the authoritative truth.

**Unified terminology/knowledge store (outside the workspace)**: default
`~/Documents/auto-epublizer/` (configurable via `paths.knowledge_dir`), persistent across
workspaces, maintained by the agent itself, and itself a **private git repository**
(`knowledge push` syncs across devices); it flows both ways with the workspace's
`analysis/glossary.csv` via `knowledge export` (seed) / `knowledge import` (write-back)
(see "Standard workflow" 4.5 / 6.5).

**Preprocessing division of labour**: the `preprocess` command produces only zero-token
facts (sniff/metadata/TOC/health/size); **approach decisions and layered understanding are
the agent's job** — read facts.md and the docs decision tables to write `plan.md`, and use
your own abilities for global understanding / per-chapter understanding / terminology
pre-extraction / risk annotation. Reading priority for analysis context: `analysis/`
(agent-written) → `preprocessing/` (agent preprocessing artifacts).

Terminology three states: `seed → candidate → conflict → confirmed`.
`analysis/glossary.csv` is authoritative (human/agent readable); conflicts are externalized
to `glossary_conflicts.jsonl`; translation workers read a snapshot and append proposals
only, and a single-threaded merger arbitrates and writes back to the CSV.
**Cross-book reuse** is handled by the unified store outside the workspace
(`knowledge export/import`, see above).

Sentence-level alignment `translation/align/<unit-id>.jsonl`, one sentence per line:

```jsonl
{"seq": 1, "src": "source sentence", "tgt": "translated sentence", "note": null}
```

`seq` anchors bilingual layout, QA location and resume; `note` records splits/merges/
omissions/doubts, and the `corr:wrong→right` prefix records source-erratum precedents
(written automatically by both the translate and import paths).

## Architecture boundaries

Three-package monorepo; the dependency direction must hold (fixed by
`test_architecture_boundaries.py`):

```text
auto_common (infrastructure: config/workspace)
      ▲
auto_translator (deterministic domain logic: glossary/genre/analysis(detect)/translation(align)/review(g0/models/convergence))
      ▲
auto_epublizer (EPUB conversion + orchestration: ingest/structure/build/qa + orchestrator/cli)
```

Logical layering (invariant across packages):

```text
CLI → Orchestrator (thin façade) → domain services → glossary / align / g0 / workspace(RunStore)
```

- `auto_common` is the leaf and must not depend on `auto_translator` / `auto_epublizer`.
- `auto_translator` depends only on `auto_common`, never on `auto_epublizer`.
- `orchestrator.py` only assembles and routes; it does not call domain functions directly
  and holds no thread pool.
- Lower layers must not import orchestrator in reverse.
- The whole repository must contain no LLM module/call (single-LLM principle, enforced by
  the architecture-boundary tests).
- Concurrency belongs to concrete domain services; results must be merged in stable source
  order and thread completion order must never change the output.
- Third-party dependencies keep their own licenses and are registered in
  `THIRD_PARTY_LICENSES.md`; AGPL dependencies may be used directly (the project itself is
  AGPL).

**Division of labour**: the CLI only does deterministic computation and
validation/release — parsing/splitting/detection (language & genre heuristics, PDF
illustrations/tables/formulas), G0 static validation, import registration, build, QA audit.
**All semantic judgement is done by the agent itself**: the analysis layer (`analysis/` and
`preprocessing/`), translation (`translation/` + `align/`), review (G1–G3, writing
`reviews/review-<ts>/result.json`), final terminology-conflict arbitration
(`glossary_conflicts.jsonl` → write back to `glossary.csv`), inserts semantics
(content_desc/latex), handling of non-converged cases (`max_rounds` / `no_progress` /
`unresolved_fixes`), source errata, complex structural judgement, repair and release
decisions. The agent needs only three basic abilities — **read files, run shell, write
files** — and **no MCP, sub-agents or special tools**.

**Capability self-check first**: before starting, the agent runs
`auto-epublizer doctor` to assess the environment toolchain (pandoc/pymupdf/OCR
(tesseract/ocrmypdf/rapidocr)/epubcheck/MinerU/network) and **self-reports its multimodal
and search** abilities (can it see images, does it have a search tool — the CLI cannot probe
these). Based on that, choose the ingest route from the skills capability-routing table
(pandoc / page slicing / scanned path: **MinerU external API first (ask the user first when
there is no key) → traditional OCR + agent page-by-page reading fallback**; "looking" is the
agent's own ability). The PDF content-extraction spec (illustrations/tables/formulas/
multi-column/bookmark chaptering) is in
[docs/pdf-content-spec.md](docs/pdf-content-spec.md).

## State and resume invariants

- `publication.json` is the final marker of a successful init: derived state is persisted
  first and committed atomically last.
- JSON state is written atomically via a same-directory temp file + `os.replace`; direct
  overwrite is forbidden.
- State is bound to content via the source file's `source_sha256`; never silently reuse
  different content under the same name.
- Completed units must be safely skippable; when changing translation/terminology/parsing/
  review caches, resume after interruption must still work.
- Export reads from a consistent snapshot; review may change only the shadow translation,
  and official segments may change only through an explicit Autofix.
- Usage ledger is append-only; one review increment is merged exactly once, and
  retries/resumes must not double-count.

## Quality-check flow (G0–G5 + delivery audit)

1. **Zero-token cheap validation**: alignment completeness, abnormal length ratio
   (<0.30 / >3.0 / empty, advisory), terminology hits (hard), insert-marker/footnote-marker
   conservation (hard, unit-level total comparison, covering both pandoc `[^N]` and
   sentence-final digit forms), source fidelity (align src ↔ structured bidirectional
   block-level binding; reverse mismatch = src was rewritten/fabricated, blocks import;
   forward missing block = advisory).
2. **Batch review agent (cheap)**: missing/added/mistranslation/terminology/pronoun; better
   to omit than to over-flag; the JSON protocol must end with `reviewed_segments` +
   `complete:true`, otherwise the whole batch is retried.
3. **Evidence-gathering agent loop (strong)**: candidates are evidenced before being
   judged; assuming un-obtained context is forbidden; both the glossary and the shadow
   revision are unverified material.
4. **Conflict arbitration + shadow revision + blind re-review**: cross-block contradictions
   are finally arbitrated; the Fixer edits only the shadow overlay; the next blind round
   does not receive the previous explanation; consecutive clean confirmations or max_rounds
   convergence; oscillation detection (digest SHA-256 cycle).
5. **EPUB structure QA**: epubcheck zero errors + item-by-item unpack audit (mimetype
   first, manifest/spine/nav parse, cover, lang, one h1 per chapter, bidirectional footnote
   links, no leftovers).
6. **Delivery acceptance**: aggregate G0–G4 + provenance audit into `report.json`
   (g0_flags/g1_issues/g2_confirmed/g3_termination/error_rate/provenance_coverage/
   units_missing/media_lost/released/released_reason); the release conditions are
   **G0 terminology hits cleared** (`terminology` is a real defect, not advisory),
   **G0 structural violations cleared** (`marker`/`footnote` conservation;
   `g0_structure_open`), **unresolved terminology conflicts cleared**
   (`glossary_conflicts_open`: no release before arbitration is written back to
   glossary.csv), **unresolved source inventory cleared** (`catalog_unresolved_open`, only
   checked when catalog.csv exists), `g2_confirmed == 0` or all revised,
   `g4_epubcheck_errors == 0`, `g4_audit == "pass"`, complete provenance
   (`provenance_coverage ≈ 1.0` (null when there is no translation artifact), zero missing
   in tri-lateral reconciliation/media provenance, TOC hierarchy not flat; see
   docs/postprocessing-spec.md §5). Finished-product presentation reconciliation must also
   be zero: `epub_media_missing`/`epub_footnotes_missing`/`align_md_drift` = 0 and
   `epub_coverage ≈ 1.0` (delivery audit S1; md is the build input and align is the
   validation baseline, and both are reconciled independently against the product).
7. **Delivery audit (agent gate, mandatory after qa released)**: per
   `skills/auto-epublizer/references/delivery.md`, perform independent reconciliation +
   unpack sampling (first/middle/last + high-risk chapters: body probes / image viewing /
   footnote content) + manual checks (TOC/cover/metadata) + inserts-description handling +
   byte-level artifact-sync verification, and write `reviews/delivery-<ts>.md`; defects go
   through the repair loop (fix → import → build → qa → re-audit). Once every unit is
   built, qa reminds you with `W_DELIVERY_AUDIT_MISSING` when the record is missing
   (warning, non-blocking).

> In-process validation during translation (QC discipline, a DouBao field lesson): build
> once every 3–5 units so format-contract problems surface in that round (missing `<img>`
> lines in image segments, blank-line breakage); after each unit run `import --unit <id>` +
> `g0 --unit <id>` to handle terminology warnings on the spot; finalize headings once,
> before starting, in plan.md.

## Configuration, secrets and providers

- Configuration has **no LLM/secret section** (single-LLM principle); the optional external
  parsing API's `MINERU_API_KEY` is read from the environment only and must never be written
  to source, tests, documentation examples or commits.
- All tests are deterministic and offline: no LLM calls, no external network.
- User-predictable errors → explicit exception + concise Chinese message; the CLI does not
  print tracebacks.

## Development and verification commands

```bash
uv sync                      # install
uv run pytest -q             # full test suite (offline, deterministic, fast; no real books)
uv run ruff check .
uv run ruff format --check .
```

When fixing a defect, first add the smallest failing regression test; test data goes in
`tempfile` and must not depend on real books outside the repository.

## Code and delivery style

- Chinese domain naming and prompts; public code has type hints and short docstrings.
- Follow the Ruff rules in pyproject (target Python 3.12).
- Commit messages use Conventional Commits; stage only the files changed by the current
  task; never commit secrets or user-local data.
- Before delivery, run the affected tests + ruff check + ruff format --check.
