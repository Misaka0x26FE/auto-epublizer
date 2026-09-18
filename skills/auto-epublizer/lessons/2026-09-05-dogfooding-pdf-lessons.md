<!-- i18n: source=2026-09-05-dogfooding-pdf-lessons.zh.md sha256=095cfcea17427145b083401be3ded5d6da87eb5523f203d08afb02350d0a0a65 -->
> **English** | [中文](2026-09-05-dogfooding-pdf-lessons.zh.md)

# Real-book dogfooding: 5 real defects in the PDF pipeline (criterion/handling)

> Date: 2026-09-04 (verification)　Source: `docs/plans/2026-09-04-pdf-dogfooding.md` §6 —
> the 5 defects exposed when running the PDF content-extraction pipeline on three kinds of
> real books (text layer + bookmarks / TeX without bookmarks / scanned file mixed with a
> text layer / true scan). This document **formally deposits the plan's verification record
> as lessons** (criterion/handling format); the plan document retains the verification
> context, and here is the reusable "how to judge when encountering the same type of
> situation".

## Trigger scenario

The new PDF pipeline (bookmark chaptering / multi-column / illustration routing / table
dual path / formula detection / inserts provenance) had only passed synthetic fixture
tests, and was run on real books for the first time — synthetic fixtures cannot expose:
real font-size distributions, fake bookmarks, incomplete table rules, formula font
diversity, scanned files mixed with a text layer.

## Criterion and handling (5 defects)

### 1. Chinese body text misjudged as formulas (· / … treated as mathematical symbols)

- **Criterion**: in the C language tutorial p1 body (name separator `·`, ellipsis `…`) was
  hit by formula detection.
- **Root cause**: the formula symbol set treated `·`(U+00B7) / `…`(U+2026) as mathematical
  symbols.
- **Handling**: remove them from the symbol set, and instead include the real mathematical
  symbols `⋅`(U+22C5) / `∗`(U+2217). `e4f21db`
- **Verification**: construct a Chinese paragraph containing "surname·given name" and
  "he…said" → formula detection does not hit.

### 2. qa ignores the configured epubcheck jar + `~` path not expanded

- **Criterion**: the jar path passed by `orch.qa` does not take effect (it has always been
  using the default).
- **Root cause**: `orch.qa` did not pass `config.qc.epubcheck.jar` down; pydantic v2
  defaults do not go through field_validator, so `~` was not expanded.
- **Handling**: two fixes `e4f21db`/`5cd5a8a`.
- **Verification**: `Config().qc.epubcheck.jar` asserts expansion to an absolute path.

### 3. TeX body quotes/angle-bracket spans use a math font → the whole paragraph misjudged as a formula

- **Criterion**: On Lisp 86 false formula reports (normal quotes/angle brackets in the body
  used the CMSY math font).
- **Root cause**: a font feature hitting the whole paragraph was judged a formula, without
  considering the ratio.
- **Handling**: add a ratio guard to font features `MATH_FONT_RATIO=0.5` (`0d47818`).
- **Verification**: a paragraph containing a small amount of CMSY font in the body is not
  wholly misjudged.

### 4. OCR page with no media does not create the raw directory → page json write crashes

- **Criterion**: the OCR path crashes on a true scanned file (Hackers & Painters).
- **Root cause**: `read_pdf` only mkdirs the raw directory when there is media; for a fully
  scanned file with no embedded images the directory is missing.
- **Handling**: `read_pdf` explicitly mkdirs (`0bd8adb`).
- **Verification**: a pure scanned PDF going through the OCR path does not crash and page
  json is written to disk.

### 5. Bordered code boxes stuck together into a cross-half-page fake table

- **Criterion**: 36/108 table records had a single cell > 300 characters; the p29 cropped
  image swallowed the flowchart + body text.
- **Root cause**: `find_tables` misjudged bordered code boxes as table regions.
- **Handling**: double guard `TABLE_MAX_AREA_RATIO=0.5` + `MAX_TABLE_CELL_CHARS=300`.
- **Verification**: code boxes do not trigger tables; real tables still go through the
  md/cropped-image path.

## Core method (reusable)

**Visual reconciliation**: render the suspected page to PNG and the agent directly looks at
the image to reconcile (p66 table/code boundaries, p29 flowchart attribution) — the key
means of locating defects 1/5. "Looking" is the agent's own ability and cannot be replaced
by a script.

## Related

- Plan/verification record: `docs/plans/2026-09-04-pdf-dogfooding.md` §6
- spec threshold backfill: `docs/pdf-content-spec.md` §4/§5/§7
- Commits: `e4f21db`/`5cd5a8a`/`0d47818`/`0bd8adb`
