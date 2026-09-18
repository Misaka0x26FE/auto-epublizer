<!-- i18n: source=configuration.zh.md sha256=26bbb96cc5418b8a16cdf64725f41a69a9439ead73725200163d34238778d9b6 -->
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
