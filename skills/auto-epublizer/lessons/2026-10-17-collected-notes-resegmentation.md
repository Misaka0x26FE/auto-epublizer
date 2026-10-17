<!-- i18n: source=2026-10-17-collected-notes-resegmentation.zh.md sha256=16e2c517396480eb1fb631c814bebf8e561e6e6223d7e7ec02486c25fcdde0c7 -->
> **English** | [中文](2026-10-17-collected-notes-resegmentation.zh.md)

# Collected endnotes flattened page-by-page: every note ends up in one giant paragraph

> Date: 2026-10-17　Source: post-delivery proofreading feedback (work root `sample-notes-a`)
> Status: fixed on the work-root side (that workspace's `preprocessing/tools/rebuild_notes.py`);
> **no code change in this repository**

## Trigger

Books with a collected endnote section, especially the "one `1. 2. 3. …` numbered group per
chapter" layout. The product shows **extremely long note paragraphs**: one `<p>` chains several
notes, up to several thousand characters, and the reader cannot tell where one note ends.

## Criterion (how to tell you may be hitting this)

1. **Product side**: count the `<p>` elements of the notes unit XHTML. If it is **far fewer**
   than the number of notes, and a single `<p>` contains two or more note-number shapes
   (`(?<![0-9])\d{1,2}\.\s`), you have a hit.
   Warning: that metric has **false positives** — a note citing "chapter 3" or "vol. 2." matches
   too — so treat it as a **candidate list**, not a verdict.
2. **Source side (decides whether it is rebuildable)**: in `structured/raw/page-*.json`, a
   **single page carries several `font_size` values**, with the note blocks in a different size
   from the body blocks. Measured on one page: section title `27.5`, chapter title `15.0`,
   note text `11.25`.
   The segmentation was therefore **intact in the raw layer**; only extraction/preparation
   flattened it. The fix is a **rebuild from raw blocks** — no guessing, no model judgement.
3. **Counter-example (font-size method unusable)**: for MinerU-path books the raw layer is
   `structured/raw/mineru/content_list.json`, which has no `font_size` semantics; use `type`
   instead (`text`/`page_footnote`/`page_number`/`header`/`footer`/`list`/`image`).

## Handling (how to fix)

1. **Classify raw blocks by font size**: `fs >= 20` section title (skip); `14 < fs < 20` chapter
   title; `10 < fs <= 14` note text. Calibrate the thresholds on each book; do not hard-code them.
2. **Only accept a note number at line start**: `^\d{1,2}\.\s`. **This is the core criterion** —
   note bodies contain **numbers inside quotations**; measured examples
   `‘Nation: 4. Le nationalisme’` and `‘Nation: 3. Nation et idéologie’`. Splitting on "any `N. `
   inside the text" **shatters** one note and makes the next one **reuse a number**.
   Font size and indentation cannot save this cut; only "line start" can.
3. **Self-check (mandatory)**: within each chapter the note numbers must be exactly `1..N` with
   **zero skips**. Measured: 148 notes in 12 chapter groups, zero skips with the line-start rule;
   the same data with the inline rule immediately produced duplicates and fragments.
4. **Continuation blocks**: a block that does not start with a note number — lowercase letter or
   quote mark means **page-break continuation**, append it to the previous note; uppercase means a
   **quoted paragraph inside the same note** (whether it truly starts a new paragraph follows the
   book's own style; here we merged it into the same paragraph).
5. **Translation side (flattened text has no line-start information)**: use the **source as a
   template** and run a monotone DP — cut the translation into fragments at every inline `N. `,
   then pick a consecutive run of fragments for each source block. Costs: span-start number
   mismatch `100000`; number matches but the preceding character is not end-of-sentence
   punctuation `200`; each extra swallowed fragment `800`.
   Warning: the criterion must look at the **first** fragment of the span; using the **last** one
   caused 2 misalignments (end fragments often "match" too, so the error hides).
6. **md and align must change together**: the CLI has two gates — "document consistency"
   (translation md vs align `tgt`) and "source fidelity" (align `src` vs structured md).
   Changing one side always fails, and **changing the source md without align's `src` fails the
   same way** (measured: 148 findings in one go).

## Reproduction / verification (minimal fixture)

```bash
# 1) Product side: paragraphs containing two or more note-number shapes (candidate, not verdict)
python3 - <<'PY'
import zipfile, re, html
z = zipfile.ZipFile('output/<slug>.epub')
x = z.read('OEBPS/back-notes.xhtml').decode()
b = x[x.index('<body>'):]
ps = [html.unescape(re.sub(r'<[^>]+>', '', p)) for p in re.findall(r'<p[^>]*>(.*?)</p>', b, re.S)]
print(len(ps), sum(1 for t in ps if len(re.findall(r'(?<![0-9])[0-9]{1,2}\.\s', t)) >= 2))
PY

# 2) Source side: does one page carry several font sizes (decides rebuildability)?
python3 -c "
import json;d=json.load(open('structured/raw/page-244.json'));
print(sorted({round(b['font_size'],2) for b in d['blocks'] if b.get('font_size')}))"
```

Checklist after the rebuild:

- note numbers `1..N` contiguous per chapter, zero skips;
- `g0` hard defects 0, with **`heading` (heading-level conservation) and `terminology`** both clear;
- product notes page `<p>` count equals the note count;
- zero residual backslashes (if you used the note-number escape below).

**Idempotence is a hard requirement**: the rebuild tool must be re-runnable with byte-identical
output. The first version was not, read its own previous output on re-run, produced
`## ## Preface` plus a row of empty `##`, and **broke the heading-conservation gate outright**.

## Two traps hit along the way

1. **Trailing hyphens deleted as word-breaks**: 4 line-end hyphens in the notes
   (`self-`/`World-`/`Christian-`/`anti-`) were **all real compounds** that merely happened to
   break at the hyphen; the correct results are `self-contradiction`, `World-Economy`,
   `Christian-non-Christian`, `anti-capitalism`. The old pipeline always dropped the hyphen and
   produced `selfcontradiction` and friends. Criterion: first check whether this batch of
   line-end hyphens are real compounds, then decide "keep" or "join".
2. **A lone `1. …` block renders as a one-item ordered list**: the `_OL_MARK` branch of
   `build/html.py` emits `<ol>` (with auto-numbering) when the numbers run 1, 2, 3, … contiguously.
   So when one note occupies one paragraph block, **the first note of every chapter** renders as
   `<ol><li>` while the rest are `<p class="fnlist">` — two styles in one chapter.
   Handling: **escape** the note number as `1\. ` (the project already has precedent:
   `europe-an-empire-of-400-million` writes its lists as `1\. ` `2\. `).
   Warning: **the source md, align's `src` and the translation md must all be produced by one
   function** — the run that missed align's `src` tripped the fidelity gate 148 times.

## Code locations

- List detection: the `_OL_MARK` / `_OL_LINE` branches in `src/auto_epublizer/build/html.py`
  (the conditions under which `<ol>` auto-numbering applies);
- Heading-level conservation: `count_heading_levels` in `src/auto_translator/review/g0.py`;
- Two-way source fidelity: `src/auto_translator/review/fidelity.py`;
- Rebuild tool: work-root side `workspaces/<slug>/preprocessing/tools/rebuild_notes.py`
  (**not in this repository**).

## Detection port still missing

`qa/audit.py` has **no** check for "collected notes not segmented" — a product whose notes page
has far fewer `<p>` than notes, or paragraphs carrying several note numbers, raises no warning.
That is exactly why this class of defect reached delivery (same family as "what the audit covers
decides which defects can be found", see issue #38). The same shape appeared in 9 other
workspaces (one with 75 such paragraphs, another with 29), so it deserves a detection port
rather than manual surveys.
