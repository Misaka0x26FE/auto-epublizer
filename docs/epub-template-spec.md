<!-- i18n: source=epub-template-spec.zh.md sha256=8135267d17fd9fd9057d5c20f35c682ce7a77553152d6dcc0f83e302e21a8b29 -->
> **English** | [中文](epub-template-spec.zh.md)

# EPUB File Spec: Unstyled Standard Template + Limited Themes

This document specifies the **form spec** of the EPUB 3 files produced by `auto-epublizer`:
content and presentation separated, presentation authority handed to the reading system,
keeping only functional minimal styles, and reserving restrained theme options. It is the
basis for the media/style acceptance criteria in the "post-processing spec"
(`docs/postprocessing-spec.md`).

## 1. Design Philosophy

> The design philosophy of EPUB 3 is "separation of content and presentation": the
> structural layer determines navigation and accessibility; the presentation layer is
> handed to the reader.

Three principles:

1. **Almost no styling**: the default template sets no font, color, or font size, keeping
   only functional styles that prevent content overflow.
2. **Limited themes**: personalization is expressed only through "preset minimal themes";
   arbitrary CSS is not opened up, and multi-reader compatibility is not broken.
3. **Standard notes**: all notes use EPUB 3 standard popup notes
   (`epub:type="noteref"`/`"footnote"`), with uniform numbering across the book and
   bidirectional jumping.

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
| TOC anchors | ✅ | unit-level nesting (source headings already split into units; h1–h6 anchors implemented and covered along the hierarchy) |
| Semantic tags | ✅ | quotes `blockquote`, verse blocks `p.verse`, lists `ul/ol` retain semantics (P2) |
| Bilingual src/tgt each with `lang` | ✅ | each paragraph is annotated with source/target language |

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
- **Degradation**: readers supporting popups display them as popups; those that do not
  degrade to an end-of-chapter list (`<aside>` is already located at the end of the
  chapter).
- Distinguished from `{fig:NNN}`/`{table:NNN}`: the latter are **figure/table placeholder
  markers** (inserts) and do not use footnote semantics.

## 7. Configuration and Implementation Impact

### 7.1 Configuration

Presentation and structure switches of `config.output`:

```yaml
output:
  theme: standard        # standard | compact | spacious
  nav_depth: 3           # maximum TOC nesting depth (1–6, projection: beyond-depth units do not enter the TOC)
  mono: true
  bilingual: false
```

### 7.2 Implementation Impact List (✅ All Landed)

1. ✅ `build/__init__.py`: `_STYLE_CSS` slimmed to functional styles + `_THEMES` theme table; `build_epub` accepts `theme`/`cover_media`/`nav_depth`.
2. ✅ `build/html.py`: `render_document` produces only semantic XHTML (including blockquote/verse/ul/ol), CSS injected from template/theme (decoupled).
3. ✅ Footnote semanticization: `FootnoteState` in-chapter numbering + `[N]` note reference + noteref/footnote rendering + backlinks.
4. ✅ Cover `cover-image`: first image of the cover unit automatically recognized + `<meta name="cover">` + `linear="no"`.
5. ✅ Semantic tag retention + page-break/figure-caption styles (TOC is unit-level nesting; no need for in-unit sub-heading anchors).
6. ✅ `qa/audit.py`: `E_THEME_FONT`/`E_THEME_COLOR`/`E_COVER_META`/`E_HEADING_SKIP`/
   `E_RESIDUE`/`W_RESIDUE`/`W_META_INCOMPLETE`/`E_ANCHOR`/`E_FN_BACKLINK`/`E_BI_PAIRS`/
   `W_EPUB_SIZE`/`W_IMG_UNCOMPRESSED`; provenance audit `W_NO_COVER`/`W_NAMING`.
7. ✅ TOC depth projection: `nav_toc_entries` (cover excluded + `nav_depth` truncation) → nav/NCX;
   `dtb:depth` is the post-projection depth; nav.xhtml declares `<meta name="nav-depth" content="K"/>`
   (qa audit uses this as authoritative); `nav_exempt` exempts `E_TOC_COVERAGE`.

## 8. Follow-Up Implementation List (by Priority)

| Priority | Item | Belongs to |
|---|---|---|
| P0 ✅ | Footnote semanticization (popup + bidirectional jumping; `[N]` in-chapter numbering since 2026-09-13) | Structural layer |
| P0 ✅ | TOC hierarchy (nested nav/NCX + `dtb:depth`, level chain completed) | Structural layer |
| P0 ✅ | `_STYLE_CSS` slimming (remove font/color/font size, regression-test locked) | Presentation layer |
| P1 ✅ | Theme mechanism (three presets + `--theme` + `output.theme` + audit validation) | Theme layer |
| P1 ✅ | Cover `cover-image` + `linear="no"` + `W_NO_COVER` reconciliation | Structural layer |
| P2 ✅ | Semantic tag retention (blockquote/verse/ul/ol) | Structural layer |
| P2 ✅ | Audit hardening (heading skips/residue/anchor backlinks/bilingual pairing/metadata completeness/size) | Structural layer |
| P2 ✅ | TOC depth projection (`output.nav_depth` + cover excluded from TOC + coverage-audit exemption) | Structural layer |

> P0/P1/P2 all landed on 2026-09-04 (see `docs/postprocessing-spec.md` §4);
> TOC depth projection and `[N]` in-chapter numbering landed on 2026-09-13 (`docs/plans/2026-09-13-toc-depth-footnotes.md`).
