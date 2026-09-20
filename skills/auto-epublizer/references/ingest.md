<!-- i18n: source=ingest.zh.md sha256=9d9d9d1291fdcda47c4342a22fc9aa45f72472d5f6afb733e1ca795d2a817d91 -->
> **English** | [中文](ingest.zh.md)

# Ingest (file parsing)

The `init` / `convert` phases normalize the source file into a `Document → Unit → Segment`
structure, landing in `structured/`, with intermediates landing in `structured/raw/`.

## Capability self-check and routing (read here before starting)

First run `auto-epublizer preprocess <input>` (new book) to get `preprocessing/facts.md` —
it already contains the source-file sniffing results (type/DRM/text layer/scanned-copy
detection/garbled-character rate), the doctor capability snapshot and deterministic routing
hints; then combine the **agent self-reported multimodal** (can it look at images) and
**search** (whether it has a web search tool, which the CLI cannot probe) to decide the
approach according to this table (written into `preprocessing/plan.md`):

**Scanned-copy PDF routing (2026-09 priority update: MinerU first)** — traditional OCR can
only recognize characters and **cannot recognize line breaks or illustrations**; MinerU is
a layout-analysis service that recognizes line breaks/paragraphs/illustrations/tables/
formulas across the board:

| Order | Input | Condition | Route |
|---|---|---|---|
| ① Highest priority | PDF scanned copy | `MINERU_API_KEY` configured | **MinerU external API** (init goes there automatically when `pdf.backend=auto`; force it with `pdf.backend: mineru`). Layout/line breaks/illustrations/tables/formulas all recognized by MinerU |
| ① Highest priority | PDF scanned copy | key not configured | **First ask the user whether they have a MinerU API key** (the facts routing hint includes this guidance) — this is the highest-quality path for scanned copies, worth one extra question |
| ② Second choice | PDF scanned copy | no key, `tesseract`/`ocrmypdf` ✓ | Traditional OCR to rebuild the text layer and re-ingest + **agent page-by-page reading fallback** (see the workflow below) |
| ② Second choice | PDF scanned copy | no key, `rapidocr` ✓ (`uv sync --extra ocr`) | Offline OCR (`pdf.ocr: auto`, automatic in init) + **agent page-by-page reading fallback** (see the workflow below) |
| Fallback | PDF scanned copy | none of the above | Clearly report that it cannot be processed; ask the user to provide a MinerU key / another OCR / manual OCR, or switch sources |

| Input | Condition | Route |
|---|---|---|
| TXT / MD | — | Read directly (`read_text`) |
| EPUB | `pandoc` ✓ | **Split by OPF spine**: one linear item per unit, non-linear items (tables etc.) converted to md and inlined at the reference point; on failure fall back to generic pandoc (see "EPUB split by spine" below) |
| DOCX / HTML | `pandoc` ✓ | pandoc → Markdown + extract media |
| EPUB / DOCX / HTML | `pandoc` ✗ | Ask the user to convert to PDF/TXT/MD first |
| PDF text layer | `pymupdf` ✓ | Slice by page to extract the text layer (offline, zero cost; in auto mode this path is taken even if a MinerU key exists) |

**OCR routing priority is fixed**: **MinerU external API (ask the user for a key) →
traditional OCR/rapidocr + agent page-by-page reading fallback → ask the user**. The
"routing hints" in facts.md give the deterministic choice;
the agent records the final route and basis in plan.md (including "whether the user was
asked for a MinerU key").

`pdf.backend: mineru` forces MinerU (clear error when there is no key); `pdf.backend:
pymupdf` disables it; `auto` (default) = scanned copy and key present → MinerU, text-layer
PDF → pymupdf.
`pdf.ocr: off` can disable automatic OCR; `pdf.ocr: <other value>` is treated as a forced
requirement (error when unavailable).

## The agent page-by-page reading workflow for traditional OCR (second-choice approach)

Traditional OCR (tesseract/ocrmypdf/rapidocr) only guarantees **character** recognition;
line breaks (paragraph boundaries) and illustrations need the agent's page-by-page reading
to fill in:

1. **Read the OCR artifacts**: the `ocr:true` text blocks of each page in
   `structured/raw/page-NNN.json` — OCR text has no paragraph information (often joined
   into one long string for the whole page); you need to re-break paragraphs/line breaks
   according to semantics;
2. **Look at page images to find illustrations**: init has already persisted the rendered
   scanned-page images to `structured/raw/pages/pNNN.png` —
   look at the images page by page (multimodal self-report) to find illustration locations;
3. **Extract illustrations**: for pages containing illustrations, use the shell (pymupdf)
   to crop the image by bbox into `structured/raw/media/`, and add an inserts record
   (`raw/inserts/<id>.json`, including content_desc);
4. **Rewrite structured**: write the body text after re-breaking paragraphs + the
   `![<id>](raw/media/…)` illustration reference back into `structured/<unit>.md` (align by
   page, do not lose the semantics of the original OCR text).

> Page-by-page reading is token-intensive work: first use the size estimate in facts
> (page count/character count) to assess the workload and write it into plan.md; when there
> are many pages and no MinerU key, prioritize asking the user for a key again.

## Format routing (after doctor probes successfully)

| Format | Handling |
|---|---|
| `.txt` `.md` `.markdown` | Read the text directly, recognize chapter headings, split paragraphs by blank lines |
| `.epub` | **Split by OPF spine** (one linear item per unit + non-linear items inlined); fall back to generic pandoc on structural abnormality |
| `.html` `.htm` `.xhtml` `.docx` | Go through pandoc → Markdown plain text + `--extract-media` to extract media |
| `.pdf` (with text layer) | pymupdf slices by page to extract the text layer, writing `structured/raw/page-NNN.json` page by page |
| `.pdf` (scanned copy, MinerU) | MinerU API parses the whole book (>200 pages automatically batched, `pdf.mineru_batch_pages`): `raw/media/` illustrations + `raw/mineru/` (content_list.json + full.md audit artifacts) + `raw/inserts/` records; body chapters split according to MinerU heading hierarchy |
| `.pdf` (scanned copy, no key) | OCR fallback: render page by page to images → OCR → use as that page's text block (`ocr:true`); rendered page images persisted to `raw/pages/pNNN.png` |

**pandoc media references are normalized on ingest** (2026-09 fix): `--extract-media`
lays DOCX `word/media/*` out under `<media_dir>/media/*` and writes **absolute paths**
into the Markdown, and pandoc appends `{width="…" height="…"}` attribute blocks. All
three would otherwise persist into `structured/`. Ingest now flattens the extra `media/`
level into `raw/media/`, rewrites references to workspace-relative `raw/media/<name>`
(matching the layout documented under "Intermediates"), and drops image attribute blocks
(the renderer does not handle that syntax, so they used to leak into the EPUB as literal
text). Non-local references (http/…) are left untouched.

Other unsupported formats: convert to PDF/TXT/Markdown first, or process with `pandoc`
and fall back to PDF.

## EPUB split by spine (2026-09 fix)

`read_epub` no longer splits by ATX headings, but **splits by OPF spine** — pandoc outputs
exactly one line of an independent anchor `[]{#<href basename>.xhtml}` for each linear
spine item, and using it as the boundary means "one spine item = one unit"; the heading is
taken from the nav/NCX label → the cleaned `<h1>` → `<title>` → top-level `<div class>` →
"Body".
Only **boundary markers** are cleaned (a standalone line with no fragment
`[]{#xx.xhtml}`), `[text]{.class}`-style attributes, and `<br>`;
**body navigation anchors `[]{#xx.html#page_N}` and heading ids `{#id}` must be kept**
(after removing their own file prefix, `structure/links.py` remaps them to finished-product
anchors by spine); see
`lessons/2026-09-12-epub-internal-links-anchors.md` for details.

**Non-linear spine items** (`linear="no"`, usually table/figure files) are skipped by
pandoc by default, leaving only links in the body:
the reader converts them to md separately and inlines them at the position in the body
**that is exactly the item's standalone link paragraph (table caption/figure caption)**
(ordinary cross-references embedded in the body are left untouched); when there is no
reference, they are appended to the last unit.

Self-check after ingest (written into `plan.md`):
- Unit count ≈ linear spine item count (the structural list in `facts.md` should be of the
  same order of magnitude as the NCX/TOC entry count);
- Headings have no **class-attribute** residue such as `{.small}` (but `{#id}` heading
  anchors and `[]{#page_N}` page-number anchors should be kept);
- Internal links/anchors have no `.html/.xhtml` source-filename residue and no double `#`
  of the form `#xx.html#frag` (after links rewriting they are `chNN.xhtml#frag` or plain
  `#frag`);
- Spot-check by grep for numeric values/table headers in the original book's tables, to
  confirm that the table bodies of non-linear items really entered `structured/`;
- Frontmatter (copyright page/dedication etc.) is classified into `frontmatter/`, rather
  than being broken into multiple `body/chNN`.

If you find that a non-linear item has not been inlined or headings still have residue:
check the OPF `spine`'s `linear` attribute and the `manifest` href,
and refer to `lessons/2026-09-11-epub-nonlinear-spine-tables.md`.

## PDF page slicing

- Each page is processed independently and landed on disk independently as
  `page-NNN.json` (`{page_idx, blocks:[{type,bbox,text}], source}`), and can be re-run on
  its own — the resume granularity = page.
- Each page's text blocks retain `bbox` and the page number, which is the ground truth for
  subsequent structural aggregation and reconciliation.
- Scanned copies without a text layer: `page.get_pixmap(dpi)` renders a PNG → OCR → use as
  that page's text block (`ocr:true`).
- Page blocks support four types: `text` / `image` / `table` / `formula` (retaining bbox)
  — for the extraction of illustrations/tables/formulas and their md representation see
  `docs/pdf-content-spec.md`; the corresponding description files land in `raw/inserts/`.

## Intermediates

```text
structured/raw/
├── page-001.json ...   # PDF page-by-page slicing (text layer/OCR; blocks contain text/image/table/formula)
├── pages/              # rendered scanned-page images pNNN.png (traditional OCR path; material for the agent's page-by-page reading to find illustrations)
├── mineru/             # MinerU path: content_list.json + full.md (audit reconciliation ground truth)
├── inserts/            # illustration/table/formula description files (<id>.json is authoritative) + index.jsonl (snapshot)
└── media/              # images extracted by pandoc + illustrations/crops extracted from PDF + MinerU illustrations
```

`raw/` is persisted for review and can be rebuilt from the source file. The inserts
`index.jsonl` is only an aggregated snapshot at ingest time;
**reading and auditing always take the single `<id>.json` file as authoritative** — for the
agent to add semantics (content_desc/latex) you only need to edit the corresponding single
file, see "inserts completion" in `references/translation.md`.

## Notes

- `source/` stays as-is, never modified; source content identity is bound via
  `publication.json.meta.source_sha256`.
- MinerU is an **external parsing API (not an LLM)**: uploads the whole book
  (≤200MB/≤200 pages), asynchronous polling,
  with a free high-priority page quota each day; >200 pages is automatically split into
  batches according to `pdf.mineru_batch_pages` (default 200), parsed in order and then
  merged (global page order continuous, image names collision-proof, blocks completely
  concatenated), and network failures are clearly reported with a Chinese error.
- OCR engine lazy loading: text-layer PDFs do not pay the model-loading cost; `init`
  automatically calls RapidOCR when encountering scanned pages.
- Difficult-page visual fallback is your capability (multimodal self-report): you may
  render difficult pages yourself and look at them to understand, writing the result back
  page by page to `structured/raw/page-NNN.json` (`ocr:true`).
- **Spot-check after batch rewriting**: after batch cleaning/OCR correction of
  `structured/`, compare representative pages from the beginning/middle/end against the
  page evidence in `raw/` (page-NNN.json or page images), to prevent batch cleaning from
  silently swallowing content.
- Common errors: `不支持的格式` (unsupported format, change the extension), `该 PDF 没有可抽取的文字层` (this PDF has no extractable text layer — scanned copy, install the OCR extra / configure a MinerU key / use page-by-page reading fallback), `未配置 MINERU_API_KEY` (not configured MINERU_API_KEY — forced mineru backend but key missing, ask the user).

### EPUB TOC hierarchy (nav nesting)

`read_epub` derives the TOC hierarchy (`heading_level`) from the unit headings in spine
order:
part titles (`PART I/II/…`, case-insensitive) are level 1 and turn on the "in-part" state;
numbered chapters after them (`2.`, `10.`, etc.) are level 2 (child chapters of the part);
all other headings return to level 1 and turn off that state.
Books without a part structure all land at level 1 (flat TOC). After ingest, please check
that the `level` of each unit in `status --json` matches the source book structure (e.g.
"part → chapter" nesting); if not, fix ingest before translating.
