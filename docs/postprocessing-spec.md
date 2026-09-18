<!-- i18n: source=postprocessing-spec.zh.md sha256=401b75a6e7b005b4330699469be064b705db4c71c0138c68e723e17de429d1d8 -->
> **English** | [中文](postprocessing-spec.zh.md)

# Post-Processing Spec: Acceptance and Implementation of Content Integrity / Media / EPUB Structure

This document specifies the **post-processing acceptance criteria and implementation plan**
after translation/import completes and before delivery (the `build` → `qa` interval). It
covers three major categories: **content integrity and provenance**, **media position and
style**, **EPUB structure and TOC hierarchy**.

> The scope boundary follows: it is responsible only for **delivery quality**
> (accurate/complete/consistent/normative/structurally correct/reproducible) and makes no
> value/political/ideological judgements. The style spec is governed by
> `docs/epub-template-spec.md`; this document is responsible only for
> "acceptance and validation" and does not redefine styles.

## 1. Positioning

Post-processing is not a new stage but a specification-level completion of the existing
**G4/G5 (+ part of build/G0)**. The three acceptances fall respectively into: provenance
into G0/G5, media into build+G4, structure into G4.

## 2. Three Categories of Acceptance Criteria and Current Gaps

> The current-state column is a **snapshot at project inception (before 2026-09-04)**;
> completion status follows §4 (P0–P2 all completed), and all ⬜ items in the table below
> have been implemented and wired into `qa`.

### 2.1 Content Integrity and Provenance

> Goal: repository content is complete without omission, and every translated part can be
> traced back to the original text.

| Acceptance item | Current state | Gap / action |
|---|---|---|
| Sentence-by-sentence provenance anchor | ✅ `align/<id>.jsonl` each line `{seq,src,tgt,note}` | — |
| Alignment completeness | ✅ G0 `check_alignment` (seq consecutive, src/tgt non-empty) | — |
| Structural conservation | ✅ G0 (paragraph blocks/markers/footnotes/headings 1:1) | — |
| **Tri-lateral reconciliation** (structured↔translation↔output) | ⬜ | new: per-unit tri-lateral existence, consistent order, no omission/extra |
| **Media provenance** (image count/order matches the source) | ⬜ | new: translated image references vs source, to prevent lost/extra/misplaced images |
| **Per-paragraph provenance coverage** | ✅ | every structured paragraph ↔ full align coverage, producing `provenance_coverage` |
| **Finished-product presentation reconciliation** (build input ↔ what the EPUB actually contains) | ✅ | md image references ↔ product `<img>` (`E_MEDIA_EPUB_LOST`), md footnote definition count ↔ product `<aside>` count (`E_FN_EPUB_LOST`), full body-paragraph probe (`E_EPUB_PARA_LOST` + `epub_coverage`); md↔align consistency (`E_ALIGN_MD_DRIFT`) |
| **Source erratum trace** | ✅ | `apply_corrections` hits written to align `note` (e.g. `corr:IDG→IDF`), distinguishing translation errors/source errors |

### 2.2 Media Position and Style

> Goal: images inserted at the corresponding positions in the original text; full size when
> possible, otherwise scaled proportionally and centered.

| Acceptance item | Current state | Gap / action |
|---|---|---|
| Images do not overflow + centered | ✅ `max-width:100%` + centered + not enlarged | semantic confirmation see epub-template-spec §4 |
| Byte collection + dangling removal | ✅ `collect_media` | — |
| **Size strategy made explicit** | ⬜ | "shrink only, never enlarge" written as the sole strategy; over-wide/over-tall/large-image audit warnings |
| **Position provenance** | ⬜ | the relative order of images in the translation matches the source (merged into 2.1 media provenance) |
| Figure caption caption / alt | ⬜ | figure caption `<figcaption>`; alt empty value warning (accessibility) |
| Cover `cover-image` | ⬜ | see epub-template-spec §3 |
| Format compatibility | ⬜ | `.avif`/`.webp` compatibility warning |

### 2.3 EPUB Structure and TOC Hierarchy

> Goal: EPUB valid, TOC complete, hierarchy matches the source file.

| Acceptance item | Current state | Gap / action |
|---|---|---|
| epubcheck 0 error | ✅ | — |
| G4 unpack audit | ✅ mimetype/container/OPF/nav/NCX/landmarks/img dangling/URL/lang/h1 | — |
| **TOC hierarchy** | ⬜ | nav/NCX currently flat single-level, source h2/h3 do not enter the TOC |
| **TOC reconciliation** | ⬜ | source TOC extracted by preprocess vs nav entries, missing entries warning |
| Footnote bidirectional jumping | ⬜ | see epub-template-spec §6 (footnote semanticization) |
| No heading level skips | ⬜ | h1→h3 skip warning |

## 3. Data Contract

### 3.1 Provenance Audit (Zero-Token Pure Function)

Input `structured/<id>.md` + `translation/align/<id>.jsonl` + finished EPUB spine,
output **whole-book aggregate** result (`qa/provenance.py::ProvenanceResult`, via `to_dict()`
into report.json):

```json
{
  "units_total": 12,
  "units_missing": [],
  "units_unexpected": [],
  "units_order_ok": true,
  "coverage": 1.0,
  "coverage_missing": [],
  "media_lost": [],
  "media_order_violations": [],
  "toc_depths_expected": [1, 2],
  "toc_depths_nav": [1, 2],
  "toc_flat": false,
  "toc_depth_mismatch": false,
  "nav_exempt": [],
  "align_md_drift": [],
  "epub_media_missing": [],
  "epub_footnotes_missing": [],
  "epub_coverage": 1.0,
  "epub_coverage_missing": [],
  "inserts_total": 3,
  "inserts_missing_files": 0,
  "inserts_no_desc": 0,
  "inserts_no_latex": 0,
  "findings": [
    {"level": "error", "code": "E_UNIT_ORDER", "message": "…"},
    {"level": "warning", "code": "W_INSERT_NO_DESC", "message": "…"}
  ]
}
```

> TOC hierarchy reconciliation is performed after projection by `output.nav_depth` (same
> algorithm as build); the projected depth follows the product's declaration (`nav.xhtml`'s
> `<meta name="nav-depth">`; config parameters are only a fallback for old products),
> avoiding false positives from config drift. `toc_depths_expected` is the expected sequence
> after projection; spine document names removed by projection are recorded in `nav_exempt`,
> handed to `audit_epub` to exempt `E_TOC_COVERAGE` (the content is still in the spine
> reading order, not missing).

### 3.2 report.json Extension (G5)

```json
{
  "provenance_coverage": 1.0,
  "units_missing": 0,
  "units_order_ok": true,
  "media_lost": 0,
  "toc_missing": [],
  "toc_flat": false,
  "align_md_drift": 0,
  "epub_media_missing": 0,
  "epub_footnotes_missing": 0,
  "epub_coverage": 1.0
}
```

## 4. Phased Implementation Plan

### P0 — Structure / Provenance / TOC Hierarchy (✅ Completed 2026-09-04)

1. ✅ **TOC hierarchy** (chain completion; information already in `SourceUnit.meta["heading_level"]`):
   - ✅ `structure/rebuild.py`: `rebuild_structure` writes `heading_level` into entry (`entry["level"]`)
   - ✅ `orchestrator`/`store`: level stored into `Unit.meta`, `structure_entries` backfilled
   - ✅ `build/__init__.py`: `_render_nav` nests `<ol>`, `_render_ncx` nests `<navPoint>` (including `dtb:depth`)
   - ✅ TOC hierarchy audit: `E_TOC_FLAT` (source has hierarchy but nav is flat) / `W_TOC_DEPTH` (depth sequence inconsistent)
     ——in `qa/provenance.py` (needs to compare against source level, not audit_epub)
   - PDF source: a single unit has no hierarchy; relies on the agent splitting and registering level in preprocessing (the CLI provides the mechanism)
2. ✅ **Tri-lateral reconciliation**: `qa/provenance.py` (`E_UNIT_MISSING`/`E_UNIT_ORDER`), wired into `qa`
3. ✅ **Media provenance**: `E_MEDIA_LOST`/`E_MEDIA_ORDER`
4. ✅ **Per-paragraph coverage**: `provenance_coverage` into report.json (null when there is no translation artifact)
5. ✅ **Source erratum trace**: `detect_corrections` + `annotate_correction_notes`;
   the import path writes align `note` prefix `corr:wrong→right` (the translate command was removed along with the internal LLM)
6. ✅ **TOC reconciliation**: facts source TOC vs unit headings → `W_TOC_MISSING` (warning clue)
7. ✅ **Footnote semanticization**: `noteref`/`footnote` + global numbering + bidirectional jumping (`FootnoteState`)
8. ✅ **Style slimming**: `_STYLE_CSS` removes font/color/font size/line spacing/indent/alignment (regression-test locked)

### P1 — Media Position / Style / Theme (✅ Completed 2026-09-04)

- ✅ Theme mechanism: three preset minimal themes (`standard`/`compact`/`spacious`) + `--theme` +
  `config.output.theme` (epub-template-spec §5); audit blocks concrete font names/font sizes/colors
  (`E_THEME_FONT`/`E_THEME_COLOR`)
- ✅ Cover `cover-image` (`<meta name="cover">` + spine `linear="no"`) + `W_NO_COVER` reconciliation
- ✅ Media audit: over-wide/over-tall/large image (`W_IMG_RATIO`/`W_IMG_LARGE`), alt empty value (`W_IMG_NO_ALT`),
  format compatibility (`.webp`/`.avif` → `W_IMG_FORMAT`)
- ✅ Figure caption `<figcaption>`: standalone figure paragraph (alt non-empty) → `figure+figcaption`
- Size strategy "shrink only, never enlarge": already locked as a functional rule during P0 style slimming (regression test)

### P2 — Supplementary Items (✅ Completed 2026-09-04)

- ✅ Accessibility: no heading level skips (`E_HEADING_SKIP`); alt empty value (P1 already did `W_IMG_NO_ALT`), lang (existing `W_NO_LANG`)
- ✅ Residue check: HTML comments (`E_RESIDUE`) / markdown·pandoc markers (`W_RESIDUE`: `![` `**` `:::` `{.` `[^`);
  source-language character residue is a semantic judgement and goes to G1 review (agent task), not a deterministic check
- ✅ Metadata completeness: missing creator/date/publisher/rights → `W_META_INCOMPLETE` (warning, for the agent to complete)
- ✅ Bilingual provenance: `build --bilingual` src/tgt paragraph counts paired (`E_BI_PAIRS`)
- ✅ Internal links: internal anchors resolvable (`E_ANCHOR`, including noteref→footnote) + footnote backlinks (`E_FN_BACKLINK`)
- ✅ Size audit: total EPUB size (`W_EPUB_SIZE`, 50MB) + single image uncompressed (`W_IMG_UNCOMPRESSED`, 2MB)
- ✅ Naming convention: product file name prefixed with slug (`W_NAMING`, qa wiring); spine order = source order (P0 provenance already covers)
- ✅ Packaging integrity (2026-09-06 S1.3): duplicate zip entries (`E_ZIP_DUPLICATE`), remote images
  (`E_IMG_REMOTE`—media must be packaged, readers lose images offline), spine↔nav bidirectional coverage
  (`E_TOC_COVERAGE`, with nav/landmarks themselves and the cover `linear="no"` exempted),
  metadata missing **or blank** (`W_META_INCOMPLETE`)
- ✅ Image page-break: `page-break-inside: avoid` (functional style)

## 5. Release Condition Extension

On top of the existing G5 release conditions (`g2_confirmed==0 or all revised` + `g0_terminology_open==0` +
`epubcheck 0 error (and actually run)` + `audit pass`), add:

- `provenance_coverage ≈ 1.0` (≥0.9999, every paragraph traceable; null when there is no translation artifact, not applicable to the convert path)
- zero tri-lateral reconciliation errors, zero media provenance errors, no error-level provenance findings
  (`E_UNIT_ORDER`/`E_MEDIA_ORDER`/`E_INSERT_BAD_SOURCE` etc. all block release)
- `inserts_missing_files == 0` (insert content files not missing)
- zero `E_TOC_FLAT` in TOC hierarchy (source with hierarchy)
- finished-product presentation reconciliation zeroed (delivery audit S1): `align_md_drift == 0`, `epub_media_missing == 0`,
  `epub_footnotes_missing == 0`, `epub_coverage ≈ 1.0` (md↔align consistent, product actual content
  reconciled against build input with no missing); build-time media drops are written to an `events.jsonl` `media_dropped` event for tracing

> Implementation see `qa/report.py::generate_report` (`prov_ok` aggregate determination + `released_reason` breakdown).
- Insert content files zero missing (`inserts_missing_files == 0`, pdf-content-spec §9:
  every illustration/table/formula can be traced back to its original address `{page,bbox,xref,method}` and the media file is on disk)

## 6. Test Plan

Add a minimal regression test for each item (following the tempfile offline convention, depending on no external LLM):

- TOC hierarchy: markdown with h1/h2/h3 → assert nav nests `<ol>` + NCX nests navPoint + does not report `E_TOC_FLAT`
- Tri-lateral reconciliation/media provenance/coverage: missing/out-of-order/lost-image fixture → assert the corresponding error code
- Footnote semanticization: note reference → `noteref`/`footnote` + globally consecutive numbering + bidirectional href resolvable
- Style slimming: assert `_STYLE_CSS` contains no `font-family`/`font-size`/`color`
- Theme: `--theme compact` → assert the corresponding typographic properties are injected
- Cover/figcaption/alt/residue: individual assertions
- Full `uv run pytest -q` + `ruff` regression

## 7. Relationship with epub-template-spec

| Document | Answers |
|---|---|
| `epub-template-spec.md` | what the EPUB **should look like** (three-layer spec, themes, note standardization) |
| This document | how post-processing **is accepted and implemented** (acceptance criteria, audit, implementation plan) |

The specific style values for 2.2 (media style) and the style-related items in P0/P1 of this
document are governed by `epub-template-spec.md`; this document describes only the
"validation actions" and "implementation landing points".
