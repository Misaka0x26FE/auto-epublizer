<!-- i18n: source=2026-11-01-titlepage-echo-deletion.zh.md sha256=679aa50d55bb253b14b932e7f5a10de83d11c3df393723352f1ea42a7292cc45 -->
> **English** | [中文](2026-11-01-titlepage-echo-deletion.zh.md)

# A title-page title deleted as a "header echo"

## Criterion (when this applies)

- The product or `structured/` title page keeps only `# Title Page` plus editors and place,
  while the book title/subtitle is gone.
- `structured/raw/page-*.json` still holds both title lines, and their `font_size` is clearly
  larger than body text (a title page usually carries the page's largest type).
- The deletion happened while an agent cleaned md under the rule "a header echo block repeats
  the unit title"; the CLI did not do it during splitting.
- Only short lines repeating at page top/bottom are layout furniture. The same text in the
  **middle of a page**, or inside a `titlepage` / half-title / `cover` unit, is not removable.

## Handling

1. Freeze source evidence first: `auto-epublizer evidence source --json` gives that page's
   blocks with `page`, `block`, `bbox`, `font_size` and `column`, confirming the title-page
   text and type hierarchy.
2. Echo removal applies only to body units (chapter/section), and must satisfy all of: the
   block is the page's first or last body block, it repeats across pages, and its font size is
   not larger than body text. "Same text as the unit title" alone is not a reason to delete.
3. Title page, half-title and cover: lines repeating the book title/subtitle are always kept;
   heading segments are never removed as running headers.
4. Every deletion goes into `preprocessing/repairs.jsonl`: unit, source page, block number,
   font size, reason and retained evidence. A deletion without a source location and reason is
   unapproved; never leave only the result.
5. Rebuild the title page afterwards: title, subtitle, editors and place in `structured/` must
   match the corresponding raw blocks literally; sync `translation/` and `align/`, then rerun
   `g0`, `qa` and the length/drift checks.

## Current code boundaries

- `_render_markdown` in `src/auto_epublizer/structure/rebuild.py` omits a heading segment only
  when it repeats the `# title` being written; the text still appears as the h1. It makes no
  cross-page repetition judgement and deletes no title-page lines.
- `clean_header_footer` in `src/auto_epublizer/structure/classify.py` removes only the
  page-first/page-last occurrence and keeps segments with `kind == "heading"`.
- `clean_unit` in the same file returns `cover` / `titlepage` units unchanged; such a page is
  all content, so publication years and page-number-shaped lines are not furniture either.
- `init`/`preprocess` do not apply these cleaning functions when writing `structured/`.
  Structural repair is an agent semantic task and must carry its own location and reason.
  "The CLI did not delete it" does not mean "the cleanup needs no record".

## Reproduction/verification

```bash
uv run --offline pytest -q tests/test_structure.py \
  -k 'title_page or header_footer or clean_unit'
```

- A synthetic title page (title + subtitle + editors + place) keeps every byte through
  `rebuild_structure` → `write_structured`.
- A short line repeating in mid-page is kept three times, heading segments are kept three
  times, and only the page-first/page-last occurrence is removed.
- On-site check: render and read the source PDF title page, compare
  `structured/raw/page-*.json` with `structured/frontmatter/front-titlepage.md`, then inspect
  the same page in the product XHTML, not just the md.
- If a historical book was already repaired by hand, keep the repair record and state the
  original deletion source in the delivery record. Passing tests now do not prove nothing was
  deleted then.
