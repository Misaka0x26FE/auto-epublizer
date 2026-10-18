<!-- i18n: source=README.zh.md sha256=fe23daf840f98acab72b7fccab4c32e1a6fe4dd96875dbe23776d51834e12b37 -->
> **English** | [中文](README.zh.md)

# auto-epublizer

[![skills.sh](https://skills.sh/b/Misaka0x26FE/auto-epublizer)](https://skills.sh/Misaka0x26FE/auto-epublizer)

A Python CLI that **translates** documents from foreign languages into any configurable
target language and produces a **standard EPUB 3**.

- **Translation**: foreign-language documents → any configurable target language (the
  translation is done by the AI agent that drives this CLI; the CLI itself makes no LLM calls).
- **EPUB conversion**: PDF (including scanned) / EPUB / DOCX / HTML / TXT / Markdown →
  standard EPUB 3 with navigation, illustrations and a cover.

Both capabilities share one pipeline — "normalize → structure → translate → package" — so
there is no second parser.

The project has two modules: **`skills/`** (instructions that teach an AI agent to finish a
book with this project, plus quality control) and **`src/auto_epublizer/`** (the Python
code: parsing, cleaning, intermediate files, QC, EPUB writing).

---

## Usage (agent collaboration mode)

This project is **not aimed at human command-line users**; it is aimed at **AI coding
agents**. Give an execution-capable connected agent (OpenCode / DouBao / Cursor, etc.) the
repository URL and input, and choose a work root. Follow the copyable
[work-root bootstrap](skills/auto-epublizer/references/work-root.md) to clone the latest
official GitHub **main** at `<work-root>/auto-epublizer/`, prepare the Python CLI with the
project's `uv` environment, then generate the skeleton using the existing `work-root`
command without overwriting (`--force` is not used). **Installing the skill installs
documentation, not the Python engine.** Keep books, workspaces, and outputs separate
from the source checkout. For an existing checkout, validate root/origin/main and tracked
plus untracked dirt before fetch and fast-forward only. Wrong branch/origin or ahead/
divergent history stops: never reset/stash/clean/overwrite user content.

You only need to do three things:

1. Send the agent the address (or make the project reachable by any agent through a Git UI
   or the command line:
   `https://github.com/Misaka0x26FE/auto-epublizer.git`, Gitee mirror:
   `https://gitee.com/misaka0x26fe/auto-epublizer.git`).
2. Provide the file to process (book source PDF/EPUB/DOCX/HTML/TXT/MD, etc.).
3. Optionally provide the target language, metadata (title/author/copyright-page fields),
   reference material or notes.

> **Copyright & publishing**: this project **does not review whether the processed object
> (source files, illustrations, etc.) carries copyright risk** — rights are your
> responsibility. The working directory produced during processing (including `source/`)
> is **fully tracked in git** and by default is uploaded as a **private repository** to the
> configured git hosting platform (default GitHub); making it public requires you to handle
> it yourself or make an explicit declaration.

> **Scanned-PDF note**: if the source is a scanned PDF (no text layer), the agent will
> prefer the MinerU external parsing API (best layout/illustration recognition). In that
> case please provide a **MinerU API key** (`MINERU_API_KEY` environment variable, read at
> runtime only, never written to any file); without a key the agent falls back to
> traditional OCR plus page-by-page reading — slightly lower quality but workable.

### Prompt (copy-paste to your agent)

```text
You are a book-translation assistant. Follow these steps exactly:

1. Agree on a work root with me, even for one book. Read
   skills/auto-epublizer/references/work-root.md and execute its complete safe bootstrap:
   <work-root>/auto-epublizer is official GitHub latest main + the project uv environment;
   book inbox/sources/workspaces are siblings, not inside the source checkout.
   Use only the existing work-root command, without --force. Stop for a dirty checkout,
   wrong branch/origin, or ahead/divergent history.
2. After bootstrap succeeds, compare "$AEP_CLI" version against the skill's minimum,
   then run "$AEP_CLI" doctor --ping and report multimodal/search capabilities.
   Run every later auto-epublizer command as "$AEP_CLI", not a global namesake.
3. Collect from me: the file path, target language (optional, default zh-CN), metadata
   (title/author/copyright fields).
   - If the file is a scanned PDF, ask me for MINERU_API_KEY (export it as an environment
     variable, runtime only; never write it to source/config/commits); without a key,
     explain that you will fall back to traditional OCR.
4. Follow the routing table in skills/auto-epublizer/SKILL.md strictly:
   doctor → preprocess (CLI zero-token fact collection) → you write the analysis/plan/
   terms → meta (metadata verification write-back) → you translate unit by unit with
   sentence alignment → import/g0 registration and checks → you review (G1–G3) → build →
   qa (G4 + epubcheck + G5 release). Obey every red line and protocol in it.
5. Tell me the finished EPUB path. At delivery or when a problem arises, follow workflow's
   feedback procedure: ask about a sanitized issue (symptoms/synthetic reproduction)
   and/or an actual repair PR. Keep drafts in the work root's docs/ and show me the full
   body/patch first. Only after explicit consent may you issue create/fork/push/pr create.
   Without consent or authentication/permissions, stop at a local draft. Never upload
   book content, identity, paths, or history.
```

---

## Quick start

First execute the complete Bash [first-use / safe-reuse bootstrap](skills/auto-epublizer/references/work-root.md)
(Git + Python 3.12 + `uv`). After success, `AEP_ROOT` / `AEP_CLI` are set. The following
are **stage-command syntax examples** (`<input>`, `<slug>`, etc. must be replaced), with
relative paths based at the work root, not a separate installation convention.
Do not process books from the source checkout. In a new shell, perform safe reuse first;
installing the skill is not installing the engine.

```bash
# 1. Bootstrap has generated the skeleton without overwriting; check version, then environment
"$AEP_CLI" version
"$AEP_CLI" doctor [--ping]

# 2. Convert only (no translation): source → EPUB
"$AEP_CLI" convert <input> --workspace "$AEP_ROOT/workspaces" -o "$AEP_ROOT/outbox/book.epub"

# 3. Full translation (preprocess creates a <slug> workspace below workspaces)
"$AEP_CLI" preprocess <input> --workspace "$AEP_ROOT/workspaces"
"$AEP_CLI" meta --workspace "$AEP_ROOT/workspaces/<slug>" --translator OpenCode
# Follow the skill for agent understanding/plan/translation/alignment/review; CLI stages only below
"$AEP_CLI" import --workspace "$AEP_ROOT/workspaces/<slug>"
"$AEP_CLI" build --workspace "$AEP_ROOT/workspaces/<slug>"
"$AEP_CLI" qa --workspace "$AEP_ROOT/workspaces/<slug>"
"$AEP_CLI" status --workspace "$AEP_ROOT/workspaces/<slug>" [--json]
```

Configuration is documented in [docs/configuration.md](docs/configuration.md)
(`config.yaml`, no secret section; the optional external parsing API's `MINERU_API_KEY` is
read from the environment only).

### Feedback and contributions (local draft by default)

At delivery or when a technical problem arises, choose an **issue** (symptoms and minimal
synthetic reproduction) and/or a **PR** (actual repair, synthetic regression tests, docs).
See the complete [workflow feedback procedure](skills/auto-epublizer/references/workflow.md).
First draft in the work root's `docs/`, show the full title/body/patch, and obtain the
user's consent before issue create, fork, push, or pr create. Use only fictitious fixtures:
no real book titles/authors, file/workspace names, original/translated text, real paths,
credentials, sensitive report metadata, or user/book Git history. Never blindly `git add -A`.
Use the user's own GitHub account without soliciting tokens; without consent or
authentication/permissions, keep the local draft and do not submit.

---

## Capabilities

| Capability | Description |
|---|---|
| Input formats | TXT/Markdown, HTML, DOCX, EPUB, PDF (text layer), scanned PDF (OCR/MinerU) |
| Scanned PDF | **MinerU external API preferred** (layout/line-break/illustration recognition); without a key, traditional OCR + agent page-by-page reading as fallback |
| Output | Standard EPUB 3 (navigation, illustrations, cover, bidirectional footnote links) |
| Quality control | Six gates G0–G5: static validation → batch review → evidence gathering → arbitration / shadow revision → epubcheck + unpack audit → delivery release |
| Terminology | Three-state glossary (seed → candidate → conflict → confirmed) with externalized conflict arbitration; a **cross-book unified store** (`knowledge export/import`, default `~/Documents/auto-epublizer`, a private git repository) reuses terminology and knowledge |
| Reproducibility | The same input always yields the same output; resume skips completed units by unit state |

Translation-flow details: [docs/translation-flow.md](docs/translation-flow.md);
per-genre tuning (novel / academic / paper / poetry / newspaper):
[docs/genre-style.md](docs/genre-style.md); PDF parsing challenges and solutions:
[docs/pdf-parsing.md](docs/pdf-parsing.md).

---

## Workspace (one directory per book)

```text
<book-slug>/
├── source/          source file (untouched, never modified)
├── structured/      source split by the four-layer structure + raw/ (OCR page images, MinerU artifacts, ...)
├── analysis/        understanding of the source (translation context)
├── preprocessing/   CLI facts (facts.*) + agent-written analysis/plan/terms/risks
├── translation/     translation + align/ sentence-level alignment
├── reviews/         review-run records
├── output/          finished EPUB (<slug>.epub)
├── references/      user uploads + agent-retrieved reference material
├── publication.json authoritative index (metadata + content tree + state machine + config snapshot)
└── events.jsonl     append-only behavior ledger
```

Unit state machine: `pending → split → analyzed → translated → aligned → reviewed → built`.

> **Unified terminology/knowledge store (outside the workspace)**: default
> `~/Documents/auto-epublizer/`, persistent across books, maintained by the agent itself,
> and itself a **private git repository** (`knowledge push` syncs across devices); seed with
> `knowledge export` when starting and write back with `knowledge import` when finalized.

---

## Documentation index

| Document | Content |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Current components, agent/CLI data flow, authoritative storage and implementation boundaries |
| [docs/configuration.md](docs/configuration.md) | Full configuration schema (config.yaml) |
| [docs/development-plan.md](docs/development-plan.md) | Development tasks and milestones |
| [docs/translation-flow.md](docs/translation-flow.md) | Translation-flow design |
| [docs/quality-control.md](docs/quality-control.md) | Six-gate QC spec (data contracts / thresholds / convergence state machine) |
| [docs/epub-template-spec.md](docs/epub-template-spec.md) | EPUB form spec (unstyled template / limited themes / standard popup notes) |
| [docs/postprocessing-spec.md](docs/postprocessing-spec.md) | Post-processing acceptance (content provenance / media / TOC hierarchy) |
| [docs/pdf-content-spec.md](docs/pdf-content-spec.md) | PDF content-extraction spec (bookmark chaptering / illustration routing / tables / formulas / inserts provenance) |
| [docs/pdf-parsing.md](docs/pdf-parsing.md) | PDF parsing challenges and solution comparison |
| [docs/genre-style.md](docs/genre-style.md) + [docs/genres/](docs/genres/) | Per-genre design |
| [docs/publishing-workflow.md](docs/publishing-workflow.md) | Traditional three-stage editorial workflow mapping |
| [docs/reference-projects.md](docs/reference-projects.md) | Reference project (wenyi): borrowings and differences |
| [docs/plans/](docs/plans/) | Plan-document directory (per-task planning / status / index) |
| [docs/testing-doubao.md](docs/testing-doubao.md) | DouBao cloud-container field-testing guide |

AI-facing docs:
- **Agents maintaining this repository's code** → [AGENTS.md](AGENTS.md) (how the project
  is implemented and how to verify it)
- **Agents using this CLI on a book** → [`skills/auto-epublizer/`](skills/auto-epublizer/SKILL.md)
  (what to do at each step, how to read results, how to fix; includes `lessons/`
  field-experience notes)

---

## License

The project's own code is **AGPL-3.0-only** (SPDX expression; source files carry
`SPDX-License-Identifier: AGPL-3.0-only` plus a copyright line; distribution metadata is
in `pyproject.toml`'s `license`); third-party dependencies keep their own licenses and are
registered in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

**Origin is identifiable; nothing is tracked**: the program contains no telemetry,
heartbeat or deployment detection; a workspace records `meta.producer` (e.g.
`auto-epublizer@0.1.0`) in `publication.json` and the same identifier in the
`run_initialized` event of `events.jsonl`, and the `build` log always carries the tool
name + license + source URL — so a third party can point back at the source, while the
tool itself never makes an outbound call for this. (issue #40 §5)
