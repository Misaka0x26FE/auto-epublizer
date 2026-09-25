<!-- i18n: source=configuration.zh.md sha256=e2b378fd8b3e52e3fe1b628c604de2ebed55db82f1a2788b8a800dfc640c3104 -->
> **English** | [中文](configuration.zh.md)

# Configuration reference (target `config.yaml` schema)

This document collects the configuration items of each stage as the unified shape of
`config.yaml`.
The implementation contract is `src/auto_common/config.py`; newly added configuration items
must be synced to this document, the root example, and the tests.
At `init` time, only key items are snapshotted into `publication.json.config` (a top-level
field, containing only `bilingual` / `target_language`, see `workspace/models.py::ConfigSnapshot`),
not a full mirror of this table.

**Single-LLM principle**: the CLI does not call any LLM, and the configuration has no
provider/secret/tier section; all semantic work (understanding/translation/review) is done by
the agent operating the CLI with its own abilities.

```yaml
# ── language and genre ───────────────────────────────────────
language:
  source: auto          # auto=deterministic script heuristic detection; or hard-code ISO 639-1 (en/ja/ru/ko/fr/de/es…)
  target: zh-CN         # target language, any configurable value
  genre: auto           # auto=heuristic determination; or explicit novel/academic/paper/poetry/newspaper

# ── pipeline switches ────────────────────────────────────────
pipeline:
  bilingual: false

# ── quality control ──────────────────────────────────────────
qc:
  length_ratio: { too_short: 0.30, too_long: 3.0 }   # G0 length-ratio warning thresholds
  epubcheck:
    jar: "~/.cache/epubcheck.jar"
    strict: true

# ── PDF parsing ──────────────────────────────────────────────
pdf:
  backend: auto           # auto | pymupdf | mineru (auto=prefer MinerU when it is a scan and MINERU_API_KEY exists)
  ocr: auto               # auto | off | force rapidocr
  page_dpi: 300           # page render resolution (OCR fallback)
  mineru_effort: medium   # not wired (the MinerU v4 API has no such parameter); kept for compatibility with old configs
  mineru_model: pipeline  # pipeline (default, deterministic, zero hallucination) | vlm (high precision, internally a VLM)
  mineru_language: ch     # MinerU OCR language (PaddleOCR language code: ch/en/ja/…)
  mineru_batch_pages: 200 # automatically batch above this page count (MinerU single-file ≤200 pages limit; ≤0 disables)

# ── glossary ─────────────────────────────────────────────────
glossary:
  storage: csv            # csv (default, authoritative storage); sqlite not implemented (reserved)
  scope: chapter          # not wired (reserved; currently terminology injection is filtered by the agent per chapter occurrence)

# ── paths ────────────────────────────────────────────────────
paths:
  workspaces_dir: .       # workspace root directory (one <book-slug>/ per book)
  knowledge_dir: ""       # unified terminology/knowledge store; empty = default ~/Documents/auto-epublizer
                          # override: --dir > AUTO_EPUBLIZER_HOME > this field > default
  knowledge_remote: ""    # unified store git remote (cross-device sync); empty = not auto-configured
                          # override: --remote > AUTO_EPUBLIZER_REMOTE > this field

# ── output ───────────────────────────────────────────────────
output:
  mono: true              # not wired (reserved; mono/bilingual is decided by build --bilingual)
  bilingual: false        # not wired (same as above)
  about_page: true        # not wired (reserved; the "about this translation" page is not implemented)
  theme: standard         # layout theme: standard | compact | spacious (docs/epub-template-spec.md §5)
                          # only layout micro-adjustments (generic font family/line spacing/indent/alignment), no concrete font name/color/size
  nav_depth: 3            # maximum TOC nesting depth (1–6, docs/epub-template-spec.md §3 projection)
                          # overly deep units do not enter nav/NCX, but are kept in the spine reading order and anchors
```

## Unified terminology / knowledge store

A cross-workspace persistent terminology store and knowledge base (maintained by the agent
itself, avoiding repeated research and repeated arbitration). The directory defaults to
`~/Documents/auto-epublizer/` and is itself a **git repository** (private by default; push
to a hosting platform for cross-device sync when possible). See
`auto-epublizer knowledge --help`:

- `knowledge path` resolves the directory; `knowledge init [--remote URL] [--push]` creates
  the skeleton + git initialization;
- `knowledge export --workspace <ws>` seeds the same-language-pair confirmed terms into
  `preprocessing/terms.csv`;
- `knowledge import --workspace <ws>` merges the workspace `analysis/glossary.csv` into the
  unified store and auto-commits;
- `knowledge status` / `knowledge push` show statistics and push.

When the source language is `auto` (`publication.json.meta.language` not written back),
`import`/`export` require `--src-lang` to declare the source language explicitly, so the
unified store stays isolated per language pair.

## Configuration snapshot and resume

After `init` succeeds, the key configuration of this run (`language.target`,
`pipeline.bilingual`, etc.) is snapshotted into `publication.json.config`; on resume the
snapshot is preferred, avoiding inconsistent results caused by configuration drift.

## Secrets

This project's configuration has no secret section whatsoever (the only LLM = the agent
itself; the agent's own credentials are unrelated to the CLI).
The only external credential is the optional `MINERU_API_KEY` environment variable (the
MinerU external parsing API), read only from the environment variable, and forbidden from
being written into configuration files, source, tests, or commits.
