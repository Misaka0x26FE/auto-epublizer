<!-- i18n: source=2026-09-11-epub-nonlinear-spine-tables.zh.md sha256=150439ea7ca77b2665912ae57b1d0c0580a4d87aee2b6c9a5f21c6ece2ca24a5 -->
> **English** | [中文](2026-09-11-epub-nonlinear-spine-tables.zh.md)

# EPUB nonlinear spine items (tables/figures) and heading anchor leftovers

## Criterion (when it gets hit)

When processing an **EPUB** source with `preprocess`/`init`, if any of the following occurs:

1. **Table/figure data loss**: the body retains only the caption link (e.g.
   `[*Table 1.1* ...](...._table_1.xhtml){#...#t1}`), and grepping the table-body values (e.g. `4,235`, `911`)
   finds nothing in `structured/`. Root cause: pandoc reads only linear spine items; the table file is
   `<itemref ... linear="no"/>` in the OPF and gets skipped.
2. **Headings polluted by anchors**: unit headings look like
   `[]{#200..._Part08.xhtml#ncx_12}1 WHAT IS TOBACCO? [The botany...]{.small}`,
   and go straight into the EPUB chapter titles and the TOC.
3. **Frontmatter fragmented**: when splitting by ATX heading, spine items without an `<h1>` (copyright
   page, dedication) get their body merged into the previous heading's unit, so heading and content are
   misaligned; all frontmatter falls into `body/chNN`.

The criterion in one sentence: **the unit count is clearly larger than the TOC entries, or headings
contain `[]{#`, or table values in the body are missing** → hit.

## Handling

Prefer upgrading to a version with `read_epub` (see `src/auto_epublizer/ingest/epub_reader.py`):

- **Split by OPF spine**: pandoc outputs exactly one separate anchor line per linear spine item
  `[]{#<href basename>.xhtml}` (stable in practice; verify with `grep -nE '^\[\]\{#.*\.xhtml\}$'`),
  and using it as the boundary means "one spine item = one unit". If any anchor is missing/out of
  order, fall back to splitting by heading.
- **Heading cleanup**: delete `[]{#id}`, `{#id}`, `[text]{.class}` (keep the text), `<br>`; the heading
  value order is nav/NCX label → cleaned `<h1>` → `<title>` → top-level `<div class>` (e.g. dedication)
  → "body". Note the cleanup function **must not strip leading whitespace**, otherwise grid-table
  indentation is broken.
- **Inline nonlinear items**: convert the `linear="no"` XHTML separately to md with
  `pandoc -f html -t markdown --wrap=none`, and replace it inline at the point in the body that is
  **exactly the standalone caption link paragraph pointing at that item**; ordinary cross-references
  embedded in the body (a `[Table 1.1](...)` inside a long sentence) are left alone; if no reference is
  found, append to the last unit.

Manual fallback without `read_epub`: unpack the EPUB, read `<spine>` in `OEBPS/*.opf`, find the
`linear="no"` table files against the `manifest`, convert each with `pandoc` to md and merge into the
corresponding chapter by table number, then clean the heading anchors — but this is a temporary patch,
the structure (unit boundaries) is still wrong, so push for the upgrade.

## Verification

- Unit count ≈ linear spine item count (`facts.md` structure list is the same order of magnitude as the
  NCX TOC count).
- `grep -rl "\[\]{#" structured/` has no hits.
- Sample-grep the original book's table values (in this case `4,235`) and find them in
  `structured/body/<chapter>.md`.
- `structured/frontmatter/` contains copyright/dedication/titlepage rather than fragments falling into body.
- Regression tests: `tests/test_epub_reader.py` (pure functions + minimal zipfile fixture + pandoc integration).

## Source and destination

- Source: real-book dogfooding《Tobacco In History: The Cultures of Dependence》(Jordan Goodman,
  26 linear spine items / 15 `linear="no"` table items).
- Destination: fixed (`read_epub` + `tests/test_epub_reader.py`); in `load.py`, `.epub` routes to
  `read_epub`, and structural anomalies fall back to `read_pandoc`.
