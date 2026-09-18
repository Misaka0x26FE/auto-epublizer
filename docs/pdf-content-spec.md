<!-- i18n: source=pdf-content-spec.zh.md sha256=6168261c20a7bafe40e79ee89cd37494a11aa8f7c00b4518968ce87987a0c175 -->
> **English** | [中文](pdf-content-spec.zh.md)

# PDF Content Extraction Spec (pdf-content-spec)

> Status: **Implemented** (P0–P2 landed in the same batch as this spec; deviations between the implementation and the spec have been written back into this document).
> This document defines the acceptance criteria, data contract, and implementation stages of PDF content extraction (ingest stage, plan C).
> For strategic background see `docs/pdf-parsing.md`; this spec is the landing point of plan C in `docs/plans/preprocessing-plan-v2.md`.
> Changes must be synced back to this spec and to `skills/`.

## 1. Positioning and Scope

PDF is coordinate positioning instructions, with no semantic structure; EPUB is a semantic document. PDF content extraction = **reconstructing semantic structure from coordinates**; this spec focuses on six gaps (aligned with `docs/pdf-parsing.md` §5):

| Capability | Current state | Goal |
|---|---|---|
| Bookmark chaptering | `sniff_pdf` already has `get_toc`, `aggregate_pdf_chapters` not wired in | bookmark TOC chaptering as priority, font-size heuristic as degraded fallback |
| Embedded image extraction | only the text layer is extracted, image blocks skipped | `get_images` / `extract_image` → `raw/media/` + md reference |
| Multi-column reading order | `get_text("dict")` internal block order | column clustering (x) → within-column y → between-column x, single-column flow |
| Tables | none | `find_tables`: pure text → md table; containing images/formulas → region cropped into an image |
| Formulas | none | detection (features) → mark `type=formula` + description file; **latex handwritten by the agent** |
| Insert content provenance | only media basename reconciliation | description file + original address `{page,bbox,xref,method}` |

**Division of labour**: the CLI only does deterministic detection/extraction/persistence (zero LLM calls); content description (`content_desc`) and formula LaTeX (`latex`) are semantic judgements, to be supplemented by the agent. **No LLM automatic formula-to-LaTeX conversion (FormulaAgent)**.

## 2. Data Contract

### 2.1 inserts directory

Each identified inserted content (image / table / formula) generates a description file + summary index:

```text
structured/raw/inserts/
├── p012-img01.json    # single insert content (CLI skeleton + agent-supplied semantics)
├── p012-tbl01.json
├── p012-fml01.json
└── index.jsonl        # summary index (one record per line, sorted by id)
```

- id naming: `p{page:03d}-{img|tbl|fml}{nn:02d}` (in-page sequence number, deterministic and stable).
- `index.jsonl` has one record (JSON) per line, for provenance auditing and review.
- Directory lifecycle same as `structured/raw/`: persisted for review, rebuildable from the source file.

### 2.2 Description file schema

```jsonc
// p012-img01.json
{
  "id": "p012-img01",
  "type": "image",            // image | table | formula
  "source": {
    "page": 12,               // source page number (1-based, required)
    "bbox": [x0, y0, x1, y1], // in-page coordinates (image/table/formula region; full-page image = full-page bbox)
    "xref": 34,               // PDF object number (required for embedded images; may be null for regions/full pages)
    "method": "embedded"      // embedded | full_page | crop | table | formula
  },
  "file": "media/p012-img01.png",  // path relative to structured/raw/; null for pure-text tables
  "markdown": null,               // md of pure-text tables (self-contained); null otherwise
  "content_desc": "",             // agent-supplied: what this insert content is about (rendering purpose/scene)
  "latex": null                   // for formula, agent-handwritten LaTeX; null otherwise
}
```

- `source` (page / bbox / xref / method) is the "original content address", the sole basis for tracing back to the source file.
- The CLI generates deterministic fields (id / type / source / file / markdown); the agent adds semantic fields (content_desc / latex).
- method semantics:
  - `embedded`: embedded raster image, `extract_image` extracts the original bytes;
  - `full_page`: full page rendered as an image (plate page / full-page illustration);
  - `crop`: in-page region crop (rendered image of a table containing images/formulas, etc.);
  - `table`: table (md or cropped image, distinguished together with file);
  - `formula`: formula (detection marker, latex pending the agent).

### 2.3 Page blocks and md representation

`page-NNN.json`'s `blocks[]` extends four types, preserving bbox:

```jsonc
{ "type": "text",  "bbox": [...], "text": "...", "font_size": 12.0 }
{ "type": "image", "bbox": [...], "file": "media/p012-img01.png", "xref": 34, "method": "embedded" }
{ "type": "table", "bbox": [...], "markdown": "| a | b |\n|---|---|", "file": null }
{ "type": "formula", "bbox": [...], "text": "E = mc2" }
```

Representation in structured md (the segment's source, by type):

| Type | md representation | Example |
|---|---|---|
| image (embedded/crop/full_page) | image reference, alt=insert id | `![p012-img01](raw/media/p012-img01.png)` |
| table (pure text) | markdown table inline | `\| a \| b \|\n\|---|---\|` |
| table (containing image/formula) | image reference (cropped image) | `![p012-tbl01](raw/media/p012-tbl01.png)` |
| formula | `$$originally extracted text$$` (draft), latex in the inserts record | `$$E = mc2$$` |

> `![…](raw/media/…)` shares the same directory and the same parsing path as pandoc-extracted media; `collect_media` (build) and `_img_refs` (provenance) are automatically compatible (prefix stripping + basename fallback).

## 3. Illustration Routing (layout criteria + genre weighting)

**Layout criteria (deterministic primary criteria)**:

| Criterion | Judgement | Action |
|---|---|---|
| image block occupies ≥ 0.70 of page area, text coverage < 0.15, **and page text < 200 characters** | full-page illustration / plate page | `page.get_pixmap` full-page render → `media/pNNN-page.png`, method=`full_page` |
| other image blocks area ≥ 32×32 px | embedded illustration | `extract_image` extracts the original bytes → method=`embedded` |
| area < 32×32 px | decoration (bullet/separator) | ignored, no record produced |

- **Character-count guard (implementation supplement)**: scanned pages with an OCR text layer naturally have glyph coverage < 0.15 and a full-page scan background image ratio ≈ 1.0; relying on the area criterion alone would misroute every page as a full-page plate and lose the body text — hence full-page routing requires page text < 200 characters. For the same reason, when page text ≥ 200 characters, an image occupying ≥ 0.85 of the page is judged as a **scan background** and skipped directly (not extracted, not recorded); pages in the OCR domain (`ocr:true`) do not undergo full-page routing/table/formula detection.
- Multiple images per page: after sorting by reading order, the in-page sequence number increments; multiple rectangles of the same xref extract the original bytes only once.
- **Genre weighting**: thresholds are CLI constants (see §7 configuration items); the agent adjusts them in `plan.md` per the `detect_genre` hint (e.g. relaxing the plate-page threshold for novels, treating small embedded icons in textbooks as decoration). The CLI does not make genre judgements.

## 4. Table Dual Path

`page.find_tables()` (pymupdf ≥ 1.23):

- **Pure-text table**: `table.extract()` where all cells are text and no image/formula block intersects → markdown table (header row + separator row), the `markdown` field stores the self-contained md;
- **Table containing images/formulas**: table bbox intersects an image block (or a cell contains formula features) → region render `page.get_pixmap(clip=table.bbox)` → `media/pNNN-tblNN.png`, method=`table` (crop semantics).
- **False-positive guards (empirically validated on real books via dogfooding)**:
  - bbox area ≥ `TABLE_MAX_AREA_RATIO`(0.5)× page area → abandon (the bordered code boxes of runoob-style tutorials get glued into a fake table spanning half a page, swallowing body text/illustrations);
  - md path single-cell length > `MAX_TABLE_CELL_CHARS`(300) → abandon (the entire page's body text gets sucked into one cell);
  - after abandonment the content returns to an ordinary text block; the body text is lossless, only table structuring is lost.
- Cross-page tables: pymupdf table objects are split by page; this spec does not merge across pages (a future extension point, `pdf-parsing.md` §2.1).

## 5. Formula Detection and Marking

Deterministic detection (any single hit marks `type=formula`):

1. **Symbol feature**: text is short (≤200 characters, `MAX_FORMULA_TEXT`) and contains ≥2 mathematical symbols (code set `_MATH_CHARS`: `∫∑√∂∓±×÷≤≥∞∈∉∋∀∃∇⋅∗¬≈≡∏°′″ℓ℘ℑℜ` etc. (excluding `≠`) or Greek letters; **excluding the `·` interpunct and `…` ellipsis** — high-frequency Chinese punctuation; counting them would misjudge body text, empirically validated by dogfooding);
2. **Font feature**: span font name contains mathematical fonts such as `Math` / `CMMI` / `CMSY` / `CMEX` / `Symbol` (**except `CMR`** — it is the default TeX body font; counting it would misjudge entire books typeset in pure TeX), and **the proportion of math-font characters ≥ `MATH_FONT_RATIO`(0.5)** — quotes/angle brackets in TeX books are often rendered in CMSY; looking only at "has appeared" would misjudge whole paragraphs of body text (On Lisp measured 80+ false positives → 2);
3. **Isolated-line feature**: a centered short text forming its own block (≤120 characters, no punctuation at sentence end) and containing ≥1 mathematical symbol.

Handling:

- The formula block keeps the originally extracted text as a draft; md presents `$$original text$$`;
- Generates a `type=formula` description file (`latex: null`); the agent **handwrites LaTeX** to fill the `latex` field (and updates the translation md accordingly); the CLI does not call an LLM and does not produce LaTeX candidates.

## 6. Multi-column Reading Order

`ingest/reading_order.py` pure function `sort_reading_order(blocks) -> list[dict]`:

1. Any block without bbox (OCR path) → return in original order (OCR text is itself in order);
2. If the whole page consists of **wide blocks** (width ≥ 0.6 × page width, e.g. headings) or there is no horizontal coexistence between blocks → single column, sort by y;
3. Otherwise detect column boundaries: merge the x intervals of narrow blocks into column clusters, sort by x0 to obtain the column order;
4. Stream-merge by y: wide blocks are output at their y position; narrow blocks are output by their "owning column (x center) → within-column y" (within a line band, cross-column output follows column order, realizing "left→right within a line, top→bottom between lines").

## 7. Configuration and Constants

- This spec's implementation adds no config section; thresholds are module constants of `ingest/images.py` / `ingest/tables.py` / `ingest/formula.py` (`FULL_PAGE_AREA_RATIO=0.70`, `TEXT_COVERAGE_MAX=0.15`, `MIN_IMAGE_SIZE=32`, `MAX_IMAGE_DIM=1800`, `RENDER_DPI=150`, `BACKGROUND_AREA_RATIO=0.85`, `MAX_TABLE_CELL_CHARS=300`, `TABLE_MAX_AREA_RATIO=0.5`, `MAX_FORMULA_TEXT=200`, `MAX_ISOLATED_TEXT=120`, `CENTER_TOLERANCE=0.12`, `MATH_FONT_RATIO=0.5`).
- The agent overriding a threshold in `plan.md` = handling it directly with its own ability (no CLI parameter passed).
- The inserts record additionally contains an `extra` extension field (dict, e.g. implementation details such as the median font size of formula detection); the schema is not fixed.

## 8. Image Optimization

- Rendering category (full_page / crop): control the render dpi/scale so the **longest side ≤ 1800px** (`MAX_IMAGE_DIM`), pure fitz, deterministic;
- Embedded images: keep the original bytes from `extract_image` (PNG with alpha preserved — EPUB supports it), no recompression; Pillow resampling/JPEG quantization left as extension points (requires new dependencies, not done this round).

## 9. provenance Audit Extension

`qa/provenance.py::audit_provenance` adds inserts auditing (only when `raw/inserts/index.jsonl` exists):

| Code | Level | Condition |
|---|---|---|
| E_INSERT_MISSING_FILE | error | record.file is non-empty but the file does not exist at `raw/<file>` |
| E_INSERT_BAD_SOURCE | error | source.page is not a positive integer or bbox is not 4 finite numbers |
| W_INSERT_NO_DESC | warning | `content_desc` is empty (the agent has not supplied the semantic description) |
| W_INSERT_NO_LATEX | warning | type=formula and `latex` is empty (the agent has not handwritten LaTeX) |

`ProvenanceResult` gains new fields: `inserts_total`, `inserts_missing_files`, `inserts_no_desc`, `inserts_no_latex`. The release condition `prov_ok` incorporates `inserts_missing_files == 0` (provenance complete = every insert content can be traced back to its original address and the file exists); `report.json` exposes the `inserts_missing_files` field, and W-level findings surface through `provenance_findings`.

## 10. Phased Implementation (all completed)

| Stage | Content | Modules |
|---|---|---|
| P0 ✅ | bookmark chaptering + embedded image extraction + inserts base + multi-column ordering | `pdf_reader.py`, `images.py`, `inserts.py`, `reading_order.py` |
| P1 ✅ | illustration routing (full-page/embedded) + table dual path + formula detection marking | `images.py`, `tables.py`, `formula.py`, `inserts.py` |
| P2 ✅ | provenance audit extension + image optimization | `qa/provenance.py`, `qa/report.py`, `images.py` |

## 11. Test Plan

- `tests/test_inserts.py`: description file schema / id naming / index.jsonl persistence and reading.
- `tests/test_reading_order.py`: single column by y; two columns (left column top→bottom → right column); wide block headings interspersed; OCR without bbox keeps the original order.
- `tests/test_ingest.py` (extended): PDF with a bookmark TOC chapters by TOC, no TOC font-size fallback; embedded image extraction persisted to `raw/media/` + md reference; correct reading order when the page order contains images.
- `tests/test_tables.py`: pure-text table → md; table containing images → cropped image + record.
- `tests/test_formula.py`: symbol/font/isolated-line three-path detection; md presents `$$…$$`; record.latex is null.
- `tests/test_provenance.py` (extended): confirms each inserts audit code; `prov_ok` incorporates file missing.
- Full `uv run pytest -q` (baseline 207) + `ruff check .` + `ruff format --check .`.

## 12. Not Done This Round

- Cross-page table merging, dedicated footnote/endnote work (`pdf-parsing.md` §2.2 remains an extension point), vertical typesetting / Traditional Chinese reading order
- LLM automatic formula-to-LaTeX conversion (FormulaAgent)
- Embedded image Pillow resampling/JPEG quantization (extension point)
- marker-pdf / MinerU local engine as default backend (optional external API, `plans/preprocessing-plan-v2` §3.4)
