<!-- i18n: source=2026-09-12-epub-internal-links-anchors.zh.md sha256=0ef7f68ae68dcdf7f5cf66184f074d448ea78fd9e221fd2ed8b465b6bdfc61c0 -->
> **English** | [中文](2026-09-12-epub-internal-links-anchors.zh.md)

# EPUB internal links / page anchors / heading id: pandoc source-file prefixes must be rewritten by spine

## Criterion (when it gets hit)

When processing an **EPUB with an index, TOC cross-references, page anchors** (common in
academic/nonfiction books) using `init`/`convert`, the finished product may show any of the following:

1. **All body page anchors lost**: the source XHTML empty anchor `<a id="page_311"></a>`, via
   `pandoc -f epub`, becomes the inline `[]{#ch17.html#page_311}` (**with the source filename prefix**).
   If the cleanup regex indiscriminately deletes `[]{#...}`, hundreds or thousands of page anchors
   disappear from the finished product, and the index jump targets do not exist.
2. **Internal links become illegal URIs**: `pandoc -f epub` (whole book) adds an extra leading `#` to
   internal links: source `href="ch17.html#page_311"` → `[311](#ch17.html#page_311)`, containing two
   `#`, and epubcheck reports RSC-020/RSC-005. Note that `pandoc -f html` (single file) does **not**
   add the leading `#`; the two behave differently, so do not infer whole-book behavior from
   single-file results.
3. **Link targets wholly misaligned (RSC-012)**: the `ch17.html` in the link is the **source filename**,
   while the finished product, after re-splitting by spine, names files by unit id (`ch19.xhtml`), and
   frontmatter causes an overall offset (offset 2 in this case). Without remapping, the files cannot be
   found at all.
4. **Heading id lost**: source `<h2 id="ch02">` → `## 标题 {#ch02.html#ch02 .h1}`; if `{#id}` is deleted
   as pandoc residue, the front-toc chapter anchors `chNN.xhtml#chNN` lose their landing point.

The criterion in one sentence: **the finished product's epubcheck reports RSC-012/RSC-020, or after
unpacking `grep 'href="#[^"]*#'` has hits, or the index link count is far larger than the actual
`<a id>` anchor count** → hit.

Key measurement (pandoc 3.1.x, `-f epub` whole book):

| Source XHTML | pandoc output |
|---|---|
| `<a id="page_311">` (inline) | `[]{#ch17.html#page_311}` (may carry `.class`) |
| `<a href="ch17.html#page_311">311</a>` | `[311](#ch17.html#page_311)` (leading #) |
| `<h2 id="ch02">` | `## 标题 {#ch17.html#ch02 .h1}` |
| spine item boundary | standalone line `[]{#ch17.html}` (**no #fragment**) |

## Handling

Distinguish "spine boundary markers" from "body navigation anchors": they look alike but their keep/delete
decisions are opposite:

- **Boundary markers**: standalone line, id is the whole filename and **has no second `#`**
  (`[]{#ch17.html}`) — delete (`_strip_anchor_lines` + `clean_pandoc_residue` use `[^}#]` to exclude
  anchors that carry a fragment).
- **Body anchors / links / heading ids**: always **keep and rewrite by spine**, done in two layers:

  1. When ingest chunks, the current spine filename is known (`strip_self_file_prefix`): strip the
     prefix from references pointing at **the file itself** — `[]{#ch1.xhtml#ncx_1}`→`[]{#ncx_1}`,
     `[x](#ch1.xhtml#p)`→`[x](#p)`, `{#ch1.xhtml#h .h1}`→`{#h}`; the first heading line is split with
     `_parse_heading_line` (pure heading, heading id, leading page anchor), the heading id is stored in
     `unit.meta.heading_id` (used for h1), and the leading page anchor is kept as the body's first anchor
     paragraph.
  2. In the structure stage, `classify_units` has already assigned the final unit ids, then
     `structure/links.py` `rewrite_internal_links` performs a **global** mapping (building a
     "source basename → unit id" table from each unit's `meta.spine_href`): cross-unit
     `[x](#ch17.html#p)`→`[x](ch19.xhtml#p)`, same-unit→`#p`; empty anchors/heading ids take only the
     pure fragment after `#` and drop the class; external protocols (http/mailto) and targets with no
     mapping are kept as-is, without guessing.

- Build side (`build/html.py`): `[]{#id}` renders as `<a id="id"></a>`, a heading-trailing `{#id}`
  renders as `<hN id="id">` (`_split_heading_id`); `_render_markdown` uses
  `# 标题 {#heading_id}` to give the chapter h1 the source anchor id.

**Counterexample (the root cause of this bug)**: the old cleanup used `\[\]\{#[^}]*\}` to
indiscriminately delete anchors, and `\{[.#][^}]*\}` to delete `{#id}` along with them — this deletes
every landing point the index relies on for jumping. Anchors are not pandoc noise; they are the book's
navigation structure.

## Verification

- Unpack the finished product: `grep -roh 'href="#[^"]*#' OEBPS | wc -l` (illegal double #) is **0**;
  `grep -rohE 'href="[^"]*\.html' OEBPS` (leftover source filenames) is **0**.
- **Link target closure** (the hardest indicator): enumerate every `href="file#frag"` and assert that
  frag appears in the target file's `id=` set. After the fix in this case (《Tobacco》), there were 1838
  internal links with 0 missing (thousands missing before the fix); all 347 page anchors were restored.
- In `structured/`, page anchors are the pure form `[]{#page_N}`, chapter h1 is `# 标题 {#chNN}`, with
  no `.html/.xhtml` source filename leftovers.
- epubcheck: 0 errors / 0 warnings (RSC-005/012/020 all gone).
- Regression tests: `tests/test_epub_reader.py` (cleanup/self-prefix/heading parsing),
  `tests/test_links.py` (leading #, spine offset, same/cross unit, external, no mapping, anchors and
  heading id), `tests/test_build.py` (anchor and heading id rendering).

## Source and destination

- Source: real-book dogfooding《Tobacco: A Cultural History...》(Iain Gately), 30 spine items,
  a two-cell offset in the body (ch03 unit = source ch01.html), index containing 1700+ page
  cross-references.
- Destination: fixed (`ingest/epub_reader.py` anchor preservation and heading parsing, new
  `structure/links.py`, `structure/rebuild.py` wiring, `build/html.py` anchor/heading id rendering)
  plus added unit tests.
- Related: replaces the old wording in `2026-09-11-epub-nonlinear-spine-tables.md` that "delete
  `[]{#id}`, `{#id}`" — that only applies to pure boundary markers; body navigation anchors must be kept.
