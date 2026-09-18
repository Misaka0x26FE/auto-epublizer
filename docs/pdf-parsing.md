<!-- i18n: source=pdf-parsing.zh.md sha256=8aba86a33a6f733a25d8f7fe05bfedbcf819554fcb6b42a98d42a25bd0fd63f1 -->
> **English** | [中文](pdf-parsing.zh.md)

# PDF Parsing and EPUB Conversion Plan

> **Single-LLM principle**: "multimodal LLM / visual LLM" in this document all refer to the **visual ability of the agent operating the CLI itself** (multimodal self-reported), not to a CLI-internal endpoint; the CLI only does deterministic extraction/detection/rendering, and pages that need to be "seen" are rendered by the agent and understood by the agent itself. Backends are pluggable: PyMuPDF (text layer) / RapidOCR / MinerU (external API) are deterministic options; "multimodal LLM backend" = agent visual fallback.

PDF is our most important input format (especially scanned documents). This document records the core difficulties of PDF → EPUB, the current technical routes, and design suggestions for auto-epublizer. Sources: technical materials from MinerU / Docling / pdf2epub.ai and 2026 evaluation data.

## 1. Core Difficulties: Why It Is Hard

PDF stores **coordinate positioning instructions** ("place 12-point type at (72,720)"), containing no semantic structure; EPUB is a **semantic structured document** (headings/paragraphs/footnotes/tables). The essence of PDF-to-EPUB is **reconstructing semantic structure from coordinates**.

Ten major difficulties ordered by severity:

| # | Difficulty | Symptom |
|---|---|---|
| 1 | Multi-column typesetting (two-column/three-column) | text interleaves between columns, reading order is scrambled |
| 2 | Running heads/footers/page numbers | appear repeatedly on every page, mixed into the middle of the body text |
| 3 | Footnotes/endnotes | mixed into the body text or simply lost (the hardest, cross-chapter linking) |
| 4 | Cross-page paragraphs | one paragraph split into two unrelated parts |
| 5 | Mathematical formulas | become meaningless scattered coordinate characters |
| 6 | Tables | row/column structure lost, become "number soup" |
| 7 | Code blocks | indentation lost, mixed into the body text |
| 8 | Mixed text and images | images lost or misplaced |
| 9 | Scanned documents | no text layer, require OCR + structure reconstruction (two-step engineering) |
| 10 | Vertical typesetting / Traditional Chinese | completely different reading order, a traditional OCR disaster zone |

> Key conclusion: **structure reconstruction is decisive for success, not character recognition**. OCR recognizing characters is easy (step one); reconstructing headings/footnotes/tables/reading order is hard (step two). Traditional OCR only does step one — "tearing a building down into a pile of bricks".

## 2. Comparison of Three Technical Routes

| Route | Representative | Principle | Pros | Cons |
|---|---|---|---|---|
| Traditional deterministic rules | Calibre, PyMuPDF | parse internal objects → text block coordinates + fonts → heuristic rules ("14pt bold = heading") → order reading by coordinates | fast, free, local, sufficient for single-column novels | rules cannot cover diverse layouts, collapses in complex scenarios (multi-column/formulas/tables) |
| Local document parsing engines | MinerU, Docling | layout analysis + specialized models (OCR/formula/table) → structured Markdown/JSON | local, structured, human reading order, automatic header/footer removal | heavy deployment (model weights), accuracy depends on backend choice |
| Multimodal VLM vision | pdf2epub.ai class | render pages as images → VLM (Gemini etc.) "sees" the page and understands semantics → semantic markup | strongest recognition of complex layouts (95–99%), understands like a human | cloud/paid, slow, per-page token cost |

### 2.1 Local Engine MinerU (key evaluation)

- Three backends: `pipeline` (runs on CPU, 4GB VRAM, 86.47 score, zero hallucination) / `vlm-engine` (8GB, 95.30) / `hybrid` (default `effort=medium`, 2GB, 95.26, extracts native text first, VLM only supplements layout understanding);
- Outputs `content_list.json` (in reading order + `type` + `bbox` + `text_level`), suitable for programmatic post-processing;
- Formula→LaTeX, table→HTML, 109-language OCR, automatic scanned-document detection, cross-page table merging, vertical typesetting support;
- **License changed 2026-04 from AGPLv3 → Apache 2.0-based (MinerU Open Source License)**, commercially usable.

### 2.2 Footnote/Endnote Special Work (pdf2epub.ai six-stage pipeline, most referenceable)

1. **Per-page detection**: have the VLM output metadata alongside OCR (`has_note_refs` / `has_note_defs` / `ref_format` / `def_count` / `is_notes_section`);
2. **Statistical voting to determine type**: aggregate across the whole book, determine `footnote / endnote_book / endnote_chapter / mixed / none` (position thresholds + co-occurrence voting, robust against single-page misjudgement);
3. **Endnote pre-extraction**: regex as the base, AI as the fallback, identifying note-section headings and matching three-level fuzzy chapter names;
4. **Dual-marker system**: footnotes use `[^N]`+`[^N]: definition`, endnotes use `ⓝ` (store the original HTML first, then reconcile) — **blocking, at the format level, the AI from fabricating footnote definitions for endnote references**;
5. **Reconciliation fallback**: recovery of lost footnote definitions, cross-chapter `data-en-id` links for endnotes;
6. **EPUB generation**: footnotes use the markdown footnotes extension, endnotes get a self-built `endnotes.xhtml` with cross-file links.

> Core idea: **reconciliation fallback is more practical than prevention** — AI losing information during merging is the norm; rather than preventing it, use the original OCR as ground truth to build a recovery mechanism.

## 3. Scanned-Document OCR + Structure Reconstruction

- Text-based PDFs (with a text layer) are read directly; scanned PDFs must be OCR'd;
- How to judge: can text be selected; is copying garbled (garbled = the text layer is broken, also requiring re-OCR);
- OCR errors cluster in italics/small font sizes/special fonts (an entire footnote or quotation may be ruined); spot-check the hardest pages, not the cleanest ones.

## 4. License Constraints

This project's own code uses **AGPL-3.0**; third-party dependencies retain their own licenses and are registered in `THIRD_PARTY_LICENSES.md`.
Because the project is AGPL, **AGPL dependencies may be used directly** (same-license compatible), with no need for process isolation as in MIT projects:

| Library | License | Conclusion |
|---|---|---|
| PyMuPDF / pymupdf4llm | **AGPL-3.0** | ✅ can depend on it (same license as the project) |
| pypdf / pdfplumber | BSD / MIT | ✅ lightweight text-layer extraction alternative |
| Docling | MIT | ✅ structured (heavier) |
| MinerU | Apache 2.0-based | ✅ can serve as a local backend (heavier) |

> Note: previously, following the MIT-project mindset, PyMuPDF was avoided; now that the project is positioned as AGPL, PyMuPDF is the **first choice for text-layer extraction** and no longer needs to be avoided. The third-party license list still needs to be registered to ensure compliance.

## 5. Design Suggestions for auto-epublizer

### 5.1 Page-Slicing Processing Model (processing granularity = page)

The basic processing unit of a PDF is the **page**, not the chapter:

```text
source/book.pdf
  ──slice by page──▶ process page by page: render page image + text-layer extraction (or OCR) + layout analysis
                  └─▶ structured/raw/page-NNN.json (page-level structured result: type/bbox/text/page_idx)
```

- Each page is processed independently, persisted independently, and can be re-run individually (resume granularity = page);
- Page-level results retain complete coordinates and type information, and are the sole basis for subsequent aggregation and reconciliation.

### 5.2 Chapter Structure as the TOC Basis (organization granularity = chapter)

Page-level results are aggregated by **chapter membership** into the directory structure of `structured/` (`body/ch01.md`, etc.); the chapter is the TOC organization boundary and the page is the slicing boundary, the two linked by a mapping table:

```jsonc
// in publication.json each unit records a page range (page→chapter mapping)
{ "id": "ch01", "kind": "chapter", "meta": { "page_range": [1, 24] } }
{ "id": "ch02", "kind": "chapter", "meta": { "page_range": [25, 48] } }
```

- The page → chapter mapping is determined at the parsing stage by the TOC (bookmarks/TOC/heading inference);
- The chapter TOC structure inherits the "four-layer publication structure" contract and shares the same unit ID with translation/review/build.

### 5.3 Layered Routing + Flexible Handling of Complex Cases (pluggable, per-page fallback)

```text
PDF input (judged per page)
  ├─ text-based (has text layer) → PyMuPDF deterministic extraction (fast, zero hallucination)
  ├─ complex layout (multi-column/formula/table) → optional MinerU local backend (Apache 2.0)
  └─ scanned/image-based → OCR (RapidOCR offline default); pages needing "seeing" fall back to agent vision
```

**Flexible handling principles**:

- **Pluggable backends**: PyMuPDF / RapidOCR / MinerU (external API) deterministic backends, selected per page and on demand;
- **Per-page degradation**: if a single page fails to parse or is of poor quality (e.g. complex layout, low OCR confidence) → that page is degraded to a heavier backend (e.g. agent visual fallback) and redone, **without one difficult page dragging down the whole book**;
- **Page-to-image conversion**: for PDF content requiring multimodal understanding (tables, formulas, mixed text-image layout, scanned pages, etc.), render **the pages that need processing** into images for the agent to understand by looking — convert only the needed pages, not the whole book;
- **Record the processing method**: for each page, record which backend was used and whether it was degraded, for review and audit.

### 5.4 End-to-End Traceability (provenance, throughout the whole pipeline)

From the finished EPUB, one can trace all the way back to a certain block on a certain page of the original PDF:

```text
output/<slug>.epub
  └─ translation/body/ch01.md  /  structured/body/ch01.md
        └─ Segment.meta: { source_page: 12, source_bbox: [x0,y0,x1,y1] }
              └─ structured/raw/page-012.json (page-level result, containing type/bbox/text/page_idx)
                    └─ source/book.pdf (bound by source_sha256)
```

- **Each Segment records `source_page`** (source page number), optionally `source_bbox` (in-page coordinates);
- The `align/<id>.jsonl` alignment table reuses the same provenance (translated sentence ↔ original sentence ↔ source page);
- `structured/raw/` retains per-page intermediate products as ground truth; translation/review/build all reference the same page number throughout;
- `source_sha256` binds the source file content, so at any stage one can locate "which page of the original book this text comes from".

### 5.5 Structure Reconstruction Is the Core Module

The `structure/` module independently handles: heading level inference, running head/footer/page number removal, multi-column reading order, footnote pairing, table shape preservation, formulas (MathML/LaTeX), code blocks. It outputs structured intermediate products **including page numbers and coordinates**, for review.

### 5.6 Intermediate Product Persistence (corresponding to `structured/raw/`)

- Page render images, per-page parsing results `page-NNN.json`, layout visualization (debugging reading order);
- These are the **ground truth for review and reconciliation**, persisted (echoing the directory design: rebuildable but retained for review).

### 5.7 Footnote/Endnote Special Work + Reconciliation

- The things most easily lost when converting academic books/translations to EPUB are footnotes and endnotes;
- Adopt "dual-marker system + statistical voting to determine type + reconciliation fallback"; on the EPUB side ensure bidirectional navigation (a QC G4 check item);
- Footnotes/endnotes also carry page-number provenance, so when lost they can be located to the source page and restored.

### 5.8 Interface with QC

| PDF difficulty | QC gate |
|---|---|
| Reading order/multi-column scrambling | G0 structure check + manual review of raw/ layout visualization |
| Running head/footer leftovers | G0 leftover artifact check |
| Footnotes/endnotes lost | G4 footnote bidirectional navigation audit |
| Tables/formulas lost | G4 structure audit + spot check |
| OCR typos | G0 terminology hits + G1 review (better to omit than to over-flag) |
| Provenance break (source page not found) | G0 provenance completeness check (every Segment has source_page) |

## 6. Unified File Format Processing Strategy (all formats)

```text
Input file
  ├─ TXT / Markdown / HTML / DOCX / EPUB
  │     └─ pandoc unified processing → Markdown (plain text) + extracted media → structured/
  │           └─ what pandoc cannot handle → convert to PDF → go through the PDF pipeline below
  └─ PDF
        └─ slice by page (§5.1)
              ├─ text-based → PyMuPDF deterministic extraction
              ├─ scanned → OCR (RapidOCR offline default)
              └─ content needing "seeing" → convert the pages that need processing into images → agent visual fallback
```

- **Non-PDF always goes through pandoc first**: separate the structure (headings/paragraphs/lists/tables) from the media (images, etc.) to obtain plain-text Markdown + inserted media content, persisted to `structured/`;
- **pandoc fallback to PDF**: when pandoc cannot handle an individual format/document, convert it to PDF and go through the page-slicing pipeline — a unified fallback, without writing a second parsing system;
- **Page-to-image for the agent**: for PDF content that needs "seeing" such as tables, formulas, mixed text-image layout, and scanned pages, render the corresponding pages into images for the agent to understand by looking — **convert only the pages that need processing, not the whole book**;
- Whichever route is taken, everything ultimately converges into the `structured/` directory structure + end-to-end provenance (§5.4).
