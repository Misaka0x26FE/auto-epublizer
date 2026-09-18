<!-- i18n: source=development-plan.zh.md sha256=7899a205ed96e81ca531e6341c3bde2971531b1ae13fcc8d018c97957054cfc4 -->
> **English** | [中文](development-plan.zh.md)

# auto-epublizer Project Development Plan

> ⚠️ **Historical planning (largely completed)**: the LLM abstraction modules within it (`llm/`, `agents/`,
> the `analyze`/`translate`/`review` commands) have been removed per the **single-LLM principle** (the CLI
> makes zero LLM calls; semantic work is done by the agent operating the CLI). This file is kept as the
> original design record of the architecture's evolution.

This file is the **task document** for completing the project development next. It converges all the
designs finalized in the session (workspace, pipeline, translation, QC, genre, PDF, license) into two
executable modules + other items, and gives an index of existing reference materials.

---

## I. Project positioning

A Python CLI, two capabilities, one shared pipeline:

1. **Translation**: foreign-language documents → any configurable target language.
2. **Convert to EPUB**: heterogeneous sources (PDF/scanned PDF/EPUB/DOCX/HTML/TXT/Markdown) → standard EPUB 3.

**External contract**: the user sends the repository address to an agent with **only basic capabilities**
(read files, run shell, write files, no MCP, no sub-agents); with only the repository's `AGENTS.md` +
`skills/` + `docs/`, the agent can complete a full high-quality processing of a book. All intelligent
stages are completed by the CLI internally calling an OpenAI-compatible API.

**License**: own code AGPL-3.0; third-party dependencies retain their own licenses and are registered.

---

## II. Two modules

### Module one: `skills/` —— agent-facing guidance

- Responsibility: **teach the agent how to use this project to complete tasks, and how to do quality control**.
- Form: one Skill (`SKILL.md` entry + `references/` topic documents), installable into opencode and other agents.
- Reference: wenyi's `traditional-translation` Skill, epub-builder's `skills/epub-builder/`.

### Module two: `src/auto_epublizer/` —— Python code

- Responsibility: file parsing, cleaning, intermediate-file processing, quality control, EPUB writing.
- Form: Python 3.12 CLI, managed with `uv`, `typer` + `pydantic` + `rich`.
- Reference: epub-builder (stable IDs, content tree, validation gates, original-image first, staged validation) + wenyi (RunStore, LLM abstraction, glossary, paragraph-level alignment, Review system).

---

## III. Repository structure (target form)

```text
auto-epublizer/
├── skills/                        # module one: agent guidance
│   └── auto-epublizer/
│       ├── SKILL.md               # agent entry: route to each references by state
│       └── references/
│           ├── workflow.md        # stage routing + command overview
│           ├── ingest.md          # file parsing (pandoc / PDF / OCR)
│           ├── structure.md       # cleaning + restructure + provenance
│           ├── analysis.md        # layered understanding (overview/global/units/keypoints/glossary)
│           ├── translation.md     # chunked translation + sentence alignment + glossary
│           ├── review.md          # six-gate QC operational guide
│           ├── build.md           # EPUB packaging
│           ├── qa.md              # epubcheck + unpack audit
│           └── style.md           # genre profile application
│
├── src/auto_epublizer/            # module two: Python code
│   ├── __init__.py
│   ├── cli.py                     # typer CLI + stage entry
│   ├── config.py                  # pydantic config + default config.yaml
│   ├── workspace/                 # publication.json + RunStore (atomic write/lock/sha256/snapshot)
│   ├── ingest/                    # file parsing → structured/ (pandoc/pymupdf/RapidOCR/vision LLM)
│   ├── structure/                 # cleaning + four-layer restructure + insert extraction + provenance
│   ├── analysis/                  # layered understanding (LLM): overview/global/units/keypoints + terminology seeding
│   ├── translation/               # chunked translation + sentence-level alignment + align/ alignment
│   ├── review/                    # six-gate QC: g0 pure functions + g1 review + g2 evidence + g3 arbitration/shadow revision
│   ├── build/                     # EPUB 3 direct write (opf/nav/ncx/cover/DC metadata/epub:type)
│   ├── qa/                        # structure audit + epubcheck integration
│   ├── glossary/                  # glossary three states (CSV authoritative + conflicts + optional SQLite)
│   ├── llm/                       # LLM abstraction (complete/complete_json + tiers + retry + usage)
│   └── genre/                     # genre profiles (declarative genre profile)
│
├── docs/                          # design documents (reference materials finalized in the session)
├── template/                      # workspace template (one directory per book)
├── tests/                         # offline tests (FakeClient + tempfile fixture)
├── pyproject.toml                 # uv + Ruff + pytest
├── config.example.yaml            # configuration example
├── AGENTS.md                      # agent entry contract
├── README.md
├── LICENSE                        # AGPL-3.0
└── THIRD_PARTY_LICENSES.md        # third-party dependency license registry
```

---

## IV. Module one development tasks: `skills/`

| # | Task | Content | Acceptance |
|---|---|---|---|
| S1 | `SKILL.md` entry | Route by workspace state (no publication.json → fresh flow; present → resume); list stage commands | agent can advance following the route |
| S2 | `references/workflow.md` | Stage routing table + `status --json` usage + troubleshooting | covers all subcommands |
| S3 | `references/ingest.md` | Selection rules for each format → pandoc/PDF/OCR; "non-PDF goes pandoc, what cannot be handled converts to PDF, hard pages convert to images" | agent can decide the route |
| S4 | `references/structure.md` | Four-layer structure + insert extraction + provenance (source_page) convention | aligned with workspace contract |
| S5 | `references/analysis.md` | overview/global/units/keypoints + glossary/characters seeding | aligned with analysis/ contract |
| S6 | `references/translation.md` | Chunking + layered context + sentence alignment + glossary three states | aligned with translation/ + align/ |
| S7 | `references/review.md` | **Six-gate QC operational guide** (when to run G0-G5, how to read reports, how to fix) | covers quality-control.md |
| S8 | `references/build.md` + `qa.md` | Packaging + epubcheck zero errors + unpack audit | aligned with build/qa |
| S9 | `references/style.md` | Genre profile selection + genre-specific optimizations | aligned with genres/ |
| S10 | Install script | `scripts/install-skills.sh --target opencode` | installable |

> skills is **pure documentation**, writes no business logic; it translates the designs in docs/ into steps that "the agent can do by copying".

---

## V. Module two development tasks: `src/auto_epublizer/`

In dependency order (lower layers first):

| # | Domain service | Task | Borrowed from | Acceptance |
|---|---|---|---|---|
| C1 | `workspace/` | publication.json schema (DC metadata + content tree + state machine + config snapshot); RunStore: tmp+`os.replace` atomic write, `source_sha256` binding, multi-level flock, export snapshot, `events.jsonl`/`usage.json` ledger | wenyi runstore | schema unit-test coverage |
| C2 | `llm/` | `complete`/`complete_json` + tiers (strong/cheap/fast) + unified retry + usage ledger + lenient JSON parsing + FakeClient | wenyi llm | offline testable |
| C3 | `ingest/` | pandoc normalization (non-PDF) + PDF page slicing (pymupdf) + OCR (RapidOCR) + page-to-image vision LLM fallback | epub-builder + pdf-parsing.md | sample files extract correct structure |
| C4 | `structure/` | four-layer structure classification, heading levels, running head/footer/page number removal, column reading order, footnote pairing, table shape preservation, insert extraction, source_page provenance | publication specifications + epub-builder | complex PDF samples |
| C5 | `analysis/` | layered-understanding generation (overview/global/units/keypoints) + terminology seeding + source language detection + web search writing references/web/ | wenyi preparation + synopsis | generated file contract correct |
| C6 | `translation/` | chunking (paragraph→batch) + layered context assembly + paragraph translation returning sentence pairs + sentence-level align/ alignment + terminology injection/proposal | wenyi translator + segmenter | sentence alignment 1:1 |
| C7 | `glossary/` | three states: CSV authoritative + `glossary_conflicts.jsonl` + worker read-only/single-threaded merge + optional SQLite index | wenyi glossary | conflict tracking correct |
| C8 | `review/` | six gates: G0 pure functions (marker conservation/paragraph 1:1/length ratio/leftovers/punctuation/terminology hits/URL safety) + G1 per-batch review + G2 evidence + G3 arbitration/shadow revision/blind re-review convergence | wenyi review + quality-control.md | convergence state machine correct |
| C9 | `build/` | EPUB 3 direct write: opf/nav.xhtml/NCX/cover/DC metadata/epub:type/lang/landmarks/two-way footnote jumps/original-image first + supplement layer | epub-builder | deterministic build + epubcheck zero errors |
| C10 | `qa/` | unpack item-by-item audit + epubcheck integration + release four-required-component gate + quality report | epub-builder + epub-qa | zero-error release |
| C11 | `genre/` | declarative genre profile loading (novel/academic/paper/poetry/newspaper) + langprofile | wenyi langprofile + genres/ | each genre injected correctly |
| C12 | `cli.py` | subcommands init/analyze/translate/review/convert/build/qa/status + `--json` + exit code + Chinese error messages | wenyi cli | `--help` + status query runnable |

**Implementation order**: C1→C2 (foundation) → C3/C4 (parsing) → C5/C11 (understanding + genre) → C6/C7 (translation + terminology) →
C8 (QC) → C9/C10 (packaging + audit) → C12 (CLI threading through).

---

## VI. Other required content

| # | Item | Description |
|---|---|---|
| O1 | `pyproject.toml` | uv-managed; dependencies: typer/pydantic/rich/httpx/pymupdf/rapidocr-onnxruntime/lxml/pyyaml; dev: pytest/ruff |
| O2 | Ruff rules | target Python 3.12; line width, E/W/F/I; ignore E501 for Chinese prompts |
| O3 | `config.example.yaml` | aligned with the complete schema of docs/configuration.md |
| O4 | Testing strategy | all offline: FakeClient/mock, no real LLM/network calls; data written to tempfile; `test_architecture_boundaries.py` fixes the dependency boundaries |
| O5 | `THIRD_PARTY_LICENSES.md` | register the licenses of PyMuPDF(AGPL)/pymupdf4llm/RapidOCR/MinerU(if used)/pandoc etc. |
| O6 | Workspace template | already have `template/`; after implementation `init` generates from it, kept in sync |
| O7 | `.gitignore` | exclude output/, glossary.db, OCR page images, __pycache__ |
| O8 | Environment-neutral | no absolute paths/user paths; secrets read from environment variables only |
| O9 | Packaging & release | `uv build` installable; EPUB products via GitHub Releases |

---

## VII. Milestones (after update)

| # | Milestone | Covered tasks | Acceptance |
|---|---|---|---|
| M1 | Scaffold + config + LLM foundation | C1(workspace) + C2(llm) + O1/O2/O3 | `--help` runnable, FakeClient usable |
| M2 | Workspace model | C1 complete + O6/O7 | schema unit-test coverage |
| M3 | Normalization + restructure | C3 + C4 | each format's samples extract correct structure |
| M4 | Understanding + genre | C5 + C11 | analysis/ + style contract correct |
| M5 | Translation + terminology + alignment | C6 + C7 | sentence alignment 1:1 + terminology conflicts |
| M6 | Quality control | C8 | G0-G3 convergence correct |
| M7 | EPUB packaging + QA | C9 + C10 | epubcheck zero errors + determinism |
| M8 | CLI threading + tests | C12 + O4/O5 | pytest all green + ruff |
| M9 | skills + documentation | S1-S10 + O8/O9 | agent runs end-to-end following skills |

---

## VIII. Reference material index (valid content saved in this session)

All design documents are persisted in `docs/`; use them as authoritative during implementation:

| Document | Content |
|---|---|
| `README.md` | General outline: decisions/pipeline/directory/modules/QC/milestones/commands |
| `AGENTS.md` | agent entry contract |
| `docs/configuration.md` | complete configuration schema |
| `docs/translation-flow.md` | chunked translation flow (layered understanding + sentence alignment + terminology closed loop) |
| `docs/quality-control.md` | six-gate QC specification (data contract/thresholds/convergence/configuration) |
| `docs/quality-lessons.md` | positive goals + negative constraints distilled from historical practice |
| `docs/publishing-workflow.md` | traditional three-review-three-proofread mapping |
| `docs/pdf-parsing.md` | PDF approach (page slicing + provenance + page-to-image) |
| `docs/genre-style.md` + `docs/genres/*.md` | genre optimization (novel/academic/paper/poetry/newspaper) |
| `template/` | workspace directory template |
| `LICENSE` | AGPL-3.0 |

**Reference external projects**: `~/github/epub-builder` (stable ID / content tree / validation gates / original-image first),
`~/github/wenyi` (RunStore / LLM abstraction / glossary / Review system), `~/work/translate` (11-book real-world specification).
