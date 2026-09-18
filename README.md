<!-- i18n: source=README.zh.md sha256=e68687956b24ce563b16dd7649abf0beae6eb8f02cb2ebe28b956b9c92c429f2 -->
> **English** | [中文](README.zh.md)

# auto-epublizer

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
agents**. Send the repository URL to your agent (a connected, execution-capable agent such
as OpenCode / DouBao / Cursor) and tell it which file to process; it will pull this project
**as a new subdirectory** in your working directory and then follow
`skills/auto-epublizer/SKILL.md` to run preprocessing, analysis, translation, review,
packaging and QA on its own.

You only need to do three things:

1. Send the agent the address (or make the project reachable by any agent through a Git UI
   or the command line:
   `https://github.com/Misaka0x26FE/auto-epublizer.git`, Gitee mirror:
   `https://gitee.com/misaka0x26fe/auto-epublizer.git`).
2. Provide the file to process (book source PDF/EPUB/DOCX/HTML/TXT/MD, etc.).
3. Optionally provide the target language, metadata (title/author/copyright-page fields),
   reference material or notes.

> **Scanned-PDF note**: if the source is a scanned PDF (no text layer), the agent will
> prefer the MinerU external parsing API (best layout/illustration recognition). In that
> case please provide a **MinerU API key** (`MINERU_API_KEY` environment variable, read at
> runtime only, never written to any file); without a key the agent falls back to
> traditional OCR plus page-by-page reading — slightly lower quality but workable.

### Prompt (copy-paste to your agent)

```text
You are a book-translation assistant. Follow these steps exactly:

1. In the current working directory, pull this project as a new subdirectory and install:
   git clone https://github.com/Misaka0x26FE/auto-epublizer.git
   cd auto-epublizer && uv sync
2. Run `uv run auto-epublizer doctor --ping` to self-check the environment (pandoc/pymupdf/
   OCR/epubcheck/MinerU/network), and tell me your multimodal (can you see images) and
   search (do you have a search tool) capabilities.
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
5. When done, tell me the finished EPUB path.
```

---

## Quick start

```bash
# 1. Install (Python 3.12 + uv)
uv sync

# 2. Environment self-check (toolchain / OCR / epubcheck / MinerU probe)
uv run auto-epublizer doctor [--ping]

# 3. Convert only (no translation): source → EPUB
uv run auto-epublizer convert <input> -o output/book.epub

# 4. Full translation flow (agent translates → import registration → build → QA)
uv run auto-epublizer preprocess <input>   # preprocessing: init + fact collection → preprocessing/facts.*
uv run auto-epublizer meta --translator OpenCode  # metadata verification write-back + translator credit
uv run auto-epublizer import               # register agent-written translation/alignment
uv run auto-epublizer build                # package EPUB (translation-only / --bilingual)
uv run auto-epublizer qa                   # structure audit + epubcheck + release report
uv run auto-epublizer status [--json]      # progress / state machine / artifact reconciliation
```

Configuration is documented in [docs/configuration.md](docs/configuration.md)
(`config.yaml`, no secret section; the optional external parsing API's `MINERU_API_KEY` is
read from the environment only).

---

## Capabilities

| Capability | Description |
|---|---|
| Input formats | TXT/Markdown, HTML, DOCX, EPUB, PDF (text layer), scanned PDF (OCR/MinerU) |
| Scanned PDF | **MinerU external API preferred** (layout/line-break/illustration recognition); without a key, traditional OCR + agent page-by-page reading as fallback |
| Output | Translation-only or bilingual; standard EPUB 3 (navigation, illustrations, cover, bidirectional footnote links) |
| Quality control | Six gates G0–G5: static validation → batch review → evidence gathering → arbitration / shadow revision → epubcheck + unpack audit → delivery release |
| Terminology | Three-state glossary (seed → candidate → conflict → confirmed) with externalized conflict arbitration; consistent across chapters and books |
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
├── output/          finished EPUB (<slug>.epub / <slug>-bi.epub)
├── references/      user uploads + agent-retrieved reference material
├── publication.json authoritative index (metadata + content tree + state machine + config snapshot)
└── events.jsonl     append-only behavior ledger
```

Unit state machine: `pending → split → analyzed → translated → aligned → reviewed → built`.

---

## Documentation index

| Document | Content |
|---|---|
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

The project's own code is **AGPL-3.0**; third-party dependencies keep their own licenses
and are registered in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
