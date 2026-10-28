<!-- i18n: source=epub-template-spec.zh.md sha256=c3e5b3ec14fd8c3b69266a08f0b26fb5e7c53e5996e89acddd26dc30b9271791 -->
> **English** | [中文](epub-template-spec.zh.md)

# EPUB File Spec: Unstyled Standard Template + Limited Themes

This document specifies the **form spec** of the EPUB 3 files produced by `auto-epublizer`:
content and presentation separated, presentation authority handed to the reading system,
keeping only functional minimal styles, and reserving restrained theme options. It is the
basis for the media/style acceptance criteria in the "post-processing spec"
(`docs/postprocessing-spec.md`).

### Product software provenance and manuscript rights

Builds must write `generator` and custom `aep:` OPF metadata (the structured record is `aep:build`), plus an `auto-epublizer-build` JSON comment in each content XHTML head. The record contains `auto-epublizer`, its [project URL](https://github.com/Misaka0x26FE/auto-epublizer), the current build version, and source revision/dirty state when available. Initialization-time `meta.producer` is not the current build identity.

The actual build entry is recorded as OPF `aep:render-mode`: `source` / `translation`. `translation` permits per-unit source fallback. Each note's source/translation choice follows its actual host. QA reconstructs expectations from the declared mode and verifies actual content. Products with registered notes must be rebuilt if the mode is absent or ambiguous; QA must not guess or waive version binding. This field is not a digital signature.

Python/Pydantic describe the build runtime. Other tools come only from records frozen after successful parsing, never from installed-dependency inventories. Unknown versions remain explicit; missing historical records cannot be reconstructed from the current installation. MinerU API is an external service, with no claim about its internal open-source version or license.

A separate software statement is appended to an existing copyright unit without replacing author/translator rights. Otherwise, a separate production-information page has a non-linear spine entry (`linear="no"`), a `copyright-page` landmark and a top-level nav/NCX entry, without adding a manuscript unit. The statement displays nonempty publication/rights fields and agent-reported generation models; unknown history and explicit non-use remain distinct, without guessed versions. Software licenses do not grant or change manuscript, translation, or image rights. Legacy `output.about_page` remains reserved configuration, not a switch for the mandatory fingerprint or evidence that the legacy about-page feature is wired up.

The fingerprint is readable offline, uses no telemetry or network requests, and includes no machine paths, secrets, or unique tracking IDs. It is removable, not a digital signature. QA exempts only valid structured fingerprint comments. A separate production page requires the OPF fingerprint declaration, its page marker, and a matching valid JSON fingerprint; neither its filename nor `linear="no"` alone exempts it from content-reconciliation/TOC checks. Ordinary residual comments, forged prefixes, and malformed JSON still produce `E_RESIDUE`. See `skills/auto-epublizer/references/build.md`.

## 1. Design Philosophy

> The design philosophy of EPUB 3 is "separation of content and presentation": the
> structural layer determines navigation and accessibility; the presentation layer is
> handed to the reader.

Three principles:

1. **Almost no styling**: the default template sets no font, color, or font size, keeping
   only functional styles that prevent content overflow.
2. **Limited themes**: personalization is expressed only through "preset minimal themes";
   arbitrary CSS is not opened up, and multi-reader compatibility is not broken.
3. **Standard notes**: use EPUB 3 standard note semantics
   (`epub:type="noteref"`/`"footnote"`), chapter-local numbering and
   bidirectional links; popup presentation is determined by the reader.

## 2. Three-Layer Framework

```text
Structural layer (skeleton, fully standardized, style-independent)  ← core of validity and accessibility; the reader navigates by it
Presentation layer (almost no styling = template default)           ← keeps only functional minimal styles
Theme layer (limited personalization)                               ← restrained switch, never touches font/color/font size
```

## 3. Structural Layer (Fully Standardized)

The structural layer is the core of EPUB validity, entirely deterministically generated and
style-independent. Completed ✅ / to be added ⬜:

| Item | Current state | Spec requirement |
|---|---|---|
| mimetype / container / OPF | ✅ | mimetype first and uncompressed, content exactly `application/epub+zip` |
| nav.xhtml + toc.ncx | ✅ | TOC hierarchy matches the source file hierarchy (level chain connected, nested rendering landed) |
| **TOC depth projection** | ✅ | nav/NCX nests at most `output.nav_depth` levels (default 3, 1–6); units beyond the depth do not enter the TOC but remain in the spine reading order and anchors; the cover unit does not enter the TOC |
| Semantic landmarks | ✅ | frontmatter/bodymatter/backmatter each take the first landing landmark |
| Per-document `xml:lang` + exactly one `h1` | ✅ | consistent across the whole document |
| Heading level h1–h6 semantics + no skipped levels | ✅ | `E_HEADING_SKIP` validation (P2) |
| **Footnote semanticization** | ✅ | `noteref`/`footnote` + `[N]` note reference + per-chapter independent numbering + bidirectional jumping (§6) |
| Cover `cover-image` | ✅ | `properties="cover-image"` + `<meta name="cover">` + spine `linear="no"` |
| Cover/TOC page `linear="no"` | ✅ | the cover unit content document does not enter the body reading order |
| TOC anchors | ✅ | unit-level nesting + **in-unit sub-heading anchors** (`file.xhtml#anchor`, stable `{unit_id}-h{n}` ids) |
| Semantic tags | ✅ | quotes `blockquote`, verse blocks `p.verse`, `- ` lists `ul` retain semantics (P2); `<ol>` only for markers consecutive from 1 with `. `/`、`, **at least two items** — other `N)`/`N.`/`N、` blocks (critical-apparatus notes) keep their literal numbers (`p.fnlist`), never renumbered. A lone `1. …` is a note paragraph, not a one-item list: `<ol>` adds list indentation/hanging style while readers present the same text identically (#61 trade-off) |

## 4. Presentation Layer (Unstyled Default Template)

The default template keeps only **functional styles**, leaving the rest to the reader:

| Item | Spec | Note |
|---|---|---|
| Font | **Not set** | use the reader's font |
| Color | **Not set** | handled by the reader (including night mode) |
| Font size | **Not set** | headings use only relative levels h1–h6, no pt/px |
| Images | `max-width:100%` + centered + not enlarged | functional: prevent image overflow; small images at original size, large images scaled proportionally |
| Emphasis | `strong`/`em` semantics | rendering left to reader default |
| Links | `a href` semantics | dangerous URLs (javascript:/data:) degrade to plain text |

### Deviation of the Current Implementation (✅ Fixed 2026-09-04)

`_STYLE_CSS` in `build/__init__.py` has been slimmed: removed `font-family`, `font-size`,
`line-height`, `text-indent: 2em`, `text-align: justify`, heading centering, and other
non-functional styles, keeping only functional rules (`img` width limit, `p.imgp` image
paragraph centering, `section.footnotes`), with regression tests locking it down (forbids
font-family/color/font-size/line-height/justify from returning).

## 5. Theme Layer (Limited Personalization)

**Boundary**: themes only control typographic fine-tuning, never touching font/color/font
size (the reader's domain). The only "font-related" exception is the **generic font-family
base**—using `serif`/`sans-serif` family names rather than concrete font names, mapped by
the reader to its own fonts.

### 5.1 Optional Dimensions

| Dimension | Values |
|---|---|
| Font-family base | `serif` (default) / `sans-serif` |
| Line-spacing density | `compact`(1.4) / `normal`(1.7, default) / `spacious`(2.0) |
| Paragraph spacing | tight / standard (default) / loose |
| First-line indent | Chinese indent 2em (default) / no indent (Western) |
| Alignment | justified (default) / left-aligned |
| Heading presentation | centered (default) / left-aligned |
| Footnote method | popup (default, standard) / end-of-chapter list (legacy reader fallback) |

### 5.2 Preset Themes (✅ Implemented 2026-09-04)

Arbitrary CSS is not opened up. Three minimal themes are preset, selected by `--theme` /
`config.output.theme`:

```text
standard  → serif + 1.7 line spacing + indent + justified + heading centered (default)
compact   → sans-serif + 1.4 line spacing + no indent + left-aligned
spacious  → serif + 2.0 line spacing + indent + justified + heading centered
```

Each theme derives only a few CSS properties for "typographic fine-tuning", introducing no
font names, colors, or font sizes; audit blocks violations (`E_THEME_FONT`: concrete font
name/font size; `E_THEME_COLOR`: color).

## 6. Note Standardization (Standard Popup + In-Chapter Numbering)

- Body note reference (sentence-final note reference) → `<a epub:type="noteref" role="doc-noteref" id="ref-N" href="#fn-N">[N]</a>` (superscript)
- Note text → concentrated area at the end of the chapter `<section epub:type="footnotes">`, entry
  `<aside epub:type="footnote" id="fn-N" role="doc-footnote"><p>[N] … <a epub:type="backlink" href="#ref-N">↩</a></p></aside>`
- **In-chapter numbering**: each chapter is numbered independently starting from `[1]` (a
  new `FootnoteState` is created per unit at build time); ids are scoped and unique within
  each XHTML document.
- **Bidirectional jumping**: note reference → note (forward), note backlink (`#ref-N`) →
  note reference (backward); the backlink is the universal fallback (required by Kindle
  KDP; readers that do not support popups rely on it to return).
- **Compatibility**: capable readers may show popups. Popups are not guaranteed in every reader; link navigation and chapter-end content must remain accessible (`<aside>` is at the end of the chapter).
- Distinguished from `{fig:NNN}`/`{table:NNN}`: the latter are **figure/table placeholder
  markers** (inserts) and do not use footnote semantics.
- **Mandatory offline acceptance**: CLI independent audits and epubcheck require no desktop. Verify noteref/aside semantics, hrefs, every backlink, registered-graph and version-binding consistency, and each note's content and resources. A registered `none` graph also requires zero-to-zero reconciliation. All five semantic quality gates remain mandatory; no desktop never excuses content or structural defects.
- **Conditional reader sampling**: where a GUI is available, record reader name/version and popup/navigation/return observations. Without a GUI, explicitly record “reader not tested”; this alone does not block delivery and must not be presented as tested compatibility.

## 7. Configuration and Implementation Impact

### 7.1 Configuration

Presentation and structure switches of `config.output`:

```yaml
output:
  theme: standard        # standard | compact | spacious
  nav_depth: 3           # maximum TOC nesting depth (1–6, projection: beyond-depth units do not enter the TOC)
```

### 7.2 Implementation Impact List (✅ All Landed)

1. ✅ `build/__init__.py`: `_STYLE_CSS` slimmed to functional styles + `_THEMES` theme table; `build_epub` accepts `theme`/`cover_media`/`nav_depth`.
2. ✅ `build/html.py`: `render_document` produces only semantic XHTML (including blockquote/verse/ul/ol), CSS injected from template/theme (decoupled).
3. ✅ Footnote semanticization: `FootnoteState` in-chapter numbering + `[N]` note reference + noteref/footnote rendering + backlinks.
4. ✅ Cover `cover-image`: first image of the cover unit automatically recognized + `<meta name="cover">` + `linear="no"`.
5. ✅ Semantic tag retention + page-break/figure-caption styles (TOC is unit-level nesting + in-unit sub-heading anchors, since 2026-09-29).
6. ✅ `qa/audit.py`: `E_THEME_FONT`/`E_THEME_COLOR`/`E_COVER_META`/`E_HEADING_SKIP`/
   `E_RESIDUE`/`W_RESIDUE`/`W_META_INCOMPLETE`/`E_ANCHOR`/`E_FN_BACKLINK`/
   `W_EPUB_SIZE`/`W_IMG_UNCOMPRESSED`; provenance audit `W_NO_COVER`/`W_NAMING`.
7. ✅ TOC depth projection: `nav_toc_entries` (cover excluded + `nav_depth` truncation) → nav/NCX.
   nav.xhtml declares two separate metas: `<meta name="nav-depth" content="A"/>` = the **actual
   rendered depth** A (same source as NCX `dtb:depth`; truthful for external tools) and
   `<meta name="nav-projection" content="K"/>` = the **projection cap** K; the qa audit uses K as
   authoritative to rebuild the expected set (using A would let a flat/broken build self-certify
   as "expected flat" and hide `E_TOC_FLAT`). `nav_exempt` exempts `E_TOC_COVERAGE`.

## 8. Follow-Up Implementation List (by Priority)

| Priority | Item | Belongs to |
|---|---|---|
| P0 ✅ | Footnote semanticization (popup + bidirectional jumping; `[N]` in-chapter numbering since 2026-09-13) | Structural layer |
| P0 ✅ | TOC hierarchy (nested nav/NCX + `dtb:depth`, level chain completed) | Structural layer |
| P0 ✅ | `_STYLE_CSS` slimming (remove font/color/font size, regression-test locked) | Presentation layer |
| P1 ✅ | Theme mechanism (three presets + `--theme` + `output.theme` + audit validation) | Theme layer |
| P1 ✅ | Cover `cover-image` + `linear="no"` + `W_NO_COVER` reconciliation | Structural layer |
| P2 ✅ | Semantic tag retention (blockquote/verse/ul/ol) | Structural layer |
| P2 ✅ | Audit hardening (heading skips/residue/anchor backlinks/metadata completeness/size) | Structural layer |
| P2 ✅ | TOC depth projection (`output.nav_depth` + cover excluded from TOC + coverage-audit exemption) | Structural layer |

> P0/P1/P2 all landed on 2026-09-04 (see `docs/postprocessing-spec.md` §4);
> TOC depth projection and `[N]` in-chapter numbering landed on 2026-09-13 (`docs/plans/2026-09-13-toc-depth-footnotes.md`).
