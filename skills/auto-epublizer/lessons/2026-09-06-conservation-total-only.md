<!-- i18n: source=2026-09-06-conservation-total-only.zh.md sha256=05962ff198a03262d04398a42aafec7df426f4c8ff00734cfdf99c75b7324a73 -->
> **English** | [中文](2026-09-06-conservation-total-only.zh.md)

# Conservation checks must compare unit-level totals (line-level comparison false-positives on split/merged sentences)

> Source: implementation verification of S1.2/S4.1 in `docs/plans/2026-09-06-adoption-plan.md`.
> Destination: `review/g0.py::g0_unit_flags` (marker/footnote total conservation), `review/fidelity.py` (block-level concatenation matching).

## Criteria

When you need to perform an src↔tgt conservation check on "discrete markers in the source text" (insert markers, footnote markers, image references, tables, etc.):

- **Line-level comparison** (comparing the marker count of src/tgt line by line across align lines) produces false positives — sentence splitting/merging moves a marker to an adjacent line (e.g. the `[^1]` on line 1 of src lands on line 2 in the translation); the line-level counts are unequal but the unit totals are equal, and this is not a defect.
- **Unit-level total comparison** (sum over rows) corresponds exactly to the semantics of "not a single one may be lost": unequal totals necessarily mean loss/fabrication, while equal totals mean the markers are safe no matter how they are moved around.

Likewise, block-level content matching (source fidelity) uses **normalized concatenated substrings** (strip all whitespace, concat, then an `in` test), which naturally tolerates split/merged sentences and sentence-order adjustments; do not do line-level one-to-one correspondence.

## Handling

1. The conservation check accumulates the totals on both sides inside the loop, compares once after the loop ends, and the flag's data carries `{src: N, tgt: M}` for locating.
2. Content matching uses `norm_text` (whitespace-stripped) + concatenated substrings; the reverse check (whether align src is copied from the source text) uses **all non-empty lines** as the corpus (including heading lines), while the forward check (whether the source blocks are all translated) **skips heading lines** — the agent may put the heading as the first src line.
3. Each conservation invariant ships with two tests: loss must be reported + moving positions must not false-positive (see `test_g0_marker_conservation` / `test_g0_footnote_conservation`).

## Verification

- `tests/test_review.py`: marker loss reports `{src:2, tgt:1}`, moving positions gives 0 flags; the same for pandoc/numeric footnotes.
- `tests/test_review.py::test_fidelity_tolerates_split_merge`: split/merged sentences / sentence-order adjustments give 0 flags.
