<!-- i18n: source=2026-10-17-collected-notes-resegmentation.zh.md sha256=fcdf37f892bea6e08a291ffb5c050610698e35da7fc03f68899e9a3146ab9e3e -->
> **English** | [中文](2026-10-17-collected-notes-resegmentation.zh.md)

# Collected endnotes flattened page-by-page: several notes in one giant paragraph

> Date: 2026-10-17　Source: post-delivery proofreading feedback (work root `sample-notes-a`)
> Historical status: the author reported a work-root repair using `preprocessing/tools/rebuild_notes.py`; that tool is not in this repository.
> All field counts below are author-reported, not local measurements for this repository revision, nor evidence of acceptance by the current phase N gates.

## Trigger and candidate criteria

Collected endnotes, especially numbering restarted as `1. 2. 3. …` per chapter.
The author reported 148 notes in 12 chapter groups but only 14 product paragraphs, a longest
paragraph exceeding 7000 characters, and a previous `released=true` result.

Compare only confirmed notes units or explicit semantic notes regions: far fewer product
paragraphs than note-number-shape candidates in the corresponding Markdown, or long paragraphs
containing multiple `N. ` shapes, merit paragraph-by-paragraph review. Counts need file and
paragraph indices. Candidates are not note counts; quoted `vol. 2.` or bibliography numbering
can match. Never block release or split notes automatically from this heuristic, or identify
notes from whole-book numbers or a filename containing notes.

## Raw evidence and semantic judgement

1. Inspect `structured/raw/page-*.json` and the original page: the author reported font sizes
   `27.5` for a section heading, `15.0` for a chapter heading and `11.25` for note text.
   Different sizes are classification clues, **not proof that raw segmentation is intact**.
   Reconcile text, coordinates, reading order, indentation and adjacent pages for merged,
   missing or duplicated blocks.
2. For MinerU, inspect `type` in `structured/raw/mineru/content_list.json`
   (e.g. `text`/`page_footnote`/`header`/`footer`/`list`/`image`) and original pages;
   a type is not a semantic verdict either.
3. The author's thresholds `fs >= 20`, `14 < fs < 20`, `10 < fs <= 14` classified section
   headings, chapter headings and notes for that book only; do not generalize them.
4. Raw line-start `^\d{1,2}\.\s` is more useful than arbitrary inline `N. `, but still only a
   candidate boundary. The author reported inline splits damaging `‘Nation: 4. Le nationalisme’`
   and `‘Nation: 3. Nation et idéologie’`. Line starts can also be quotations, lists or page
   fragments; the agent must verify each note against the original.
5. Lowercase, uppercase and quotation marks **cannot automatically decide** page-break
   continuation versus a new paragraph within a note. Preserve legitimate multiple paragraphs,
   lists, quotations and media; do not merge them to force one paragraph per note.

## Repair: candidate reconstruction must lead into canonical phase N

1. Restore boundaries from raw evidence and verified source notes. The author reported that
   the line-start approach produced 148 notes / 12 groups with no skips; contiguous `1..N` was
   a check for that book only. Other books can continue, restart, skip or use nonnumeric labels;
   record source evidence rather than inventing, deleting or reordering notes to force a series.
   Identity is separate from display numbering.
2. Flattened translation can use verified source notes as a template for monotone DP alignment
   **candidates**. The author split at inline `N. ` and used costs `100000` for a first-fragment
   number mismatch, `200` for a matching number not preceded by sentence-ending punctuation,
   and `800` per extra fragment. These are field heuristics, not universal correctness rules;
   scoring the last fragment once caused 2 mismatches. The agent must verify content, boundaries
   and positions note by note, never accept DP output automatically.
3. Intermediate Markdown/align repairs still obey both gates: translation md ↔ align `tgt`
   document consistency, and align `src` ↔ structured md source fidelity. The author reported
   148 findings after failing to update align `src`.
4. **Legacy resegmentation is intermediate, not final delivery**. Follow
   [notes.md](../references/notes.md): extract complete `structured/notes.json`, preserving
   legitimate multiple paragraphs/media; restore in-place `[^ref-ID]` body markers; dispose of
   each candidate and run `notes register`; establish stable `note_id`/`ref_id`, scopes and
   two-way location evidence. Store translated notes in `translation/notes.json` bound to the
   source-note digest; import and build standard noteref/footnote popup links.
5. Final acceptance reconciles note/ref identities, complete content, media, hrefs and one
   backlink per reference; the independent N hard gate is unchanged. **Do not require `<p>`
   count to equal note count**: a legitimate note may contain multiple paragraphs or lists.

## Reproduction and verification checklist

- Use anonymized fixtures, not real book sources/translations in the repository. Historical
  author reports are not local verification evidence.
- Parse the final EPUB's confirmed notes regions using the project XML parser; record file,
  paragraph index, length and number-shape counts. Compare with actual rendered Markdown
  inputs, not translations that have not been rendered.
- Verify boundaries, page continuations and reference positions against `structured/raw/`
  and original pages; font size is only supporting evidence.
- Check the book's evidenced label ranges; retain G0 (including heading and terminology),
  two-way source fidelity and the N gate.
- Rebuild tools must be idempotent and read immutable inputs; the author reported an early
  version reading its own output and producing `## ## Preface` plus empty headings.
- Check every note/ref's content, media, semantic links and backlinks rather than substituting
  paragraph counts for completeness.

## Two historical repair traps

1. The author reported 4 line-end hyphens `self-`/`World-`/`Christian-`/`anti-` that were genuine
   compounds: `self-contradiction`, `World-Economy`, `Christian-non-Christian`, `anti-capitalism`.
   This does not justify keeping or deleting all line-end hyphens; verify against the original.
2. A plain `1. …` paragraph can trigger the `_OL_MARK` / `_OL_LINE` ordered-list rules in
   `build/html.py`. The legacy repair used `1\. ` to avoid automatic numbering and synchronized
   source md, align `src` and translation md. **Escaped-number plain `<p>` elements are not
   canonical note delivery**; phase N is still required.

## Code locations and the historical detection gap

- List rendering: `src/auto_epublizer/build/html.py`; heading conservation:
  `src/auto_translator/review/g0.py`.
- Two-way fidelity: `src/auto_translator/review/fidelity.py`; canonical notes: reference above.
- Work-root rebuild: `workspaces/<slug>/preprocessing/tools/rebuild_notes.py` (not in this repo).
- At the time of the report, `qa/audit.py` lacked a collected-notes segmentation advisory;
  the author also reported candidates in 9 other books (75 and 29 paragraphs in two books).
  This historical gap is not a verdict that all those candidates were verified defects.
