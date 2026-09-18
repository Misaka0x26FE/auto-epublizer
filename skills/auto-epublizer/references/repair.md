<!-- i18n: source=repair.zh.md sha256=fa40649653ee5aa682077a956e61223b1d051ac4bcb6089da78662d4e818b5bc -->
> **English** | [中文](repair.zh.md)

# Repair (semantic repair: parse defects / OCR correction / structural re-split)

> **Positioning**: any source-text problem that "can only be judged correctly through
> language understanding" is your job, not the script's job. Signals are given by the
> "suspicious signals" table in `facts.md` (`references/preprocessing.md` §2.0b); this
> manual gives "what evidence to read → how to repair → how to leave a trace → how to
> self-check".
> **Spec**: `docs/semantic-repair.md` (full scenario list and anti-patterns).

## When to do it

- **Signal-triggered**: facts.md has a "suspicious signals" table → verify and repair unit
  by unit;
- **OCR / scanned-copy route**: do it once whether or not there is a signal (line breaks
  and misrecognitions of traditional OCR are inevitable items);
- **MinerU messy hierarchy**: heading hierarchy is chaotic and unit boundaries need
  re-splitting (go through restructure);
- **Translation/review backflow**: a missing sentence/duplication/incoherent meaning is
  found during translation, locate it back to the source (window F).

## Where the evidence is (look at the evidence before acting)

| Evidence | Location | Purpose |
|---|---|---|
| Per-page text blocks (including bbox/OCR marks) | `structured/raw/page-NNN.json` | page boundaries, line breaks, OCR raw text |
| Scanned-page rendered images | `structured/raw/pages/pNNN.png` | view the image to determine layout/illustrations/running head and footer |
| MinerU raw artifacts | `structured/raw/mineru/` (content_list.json + full.md) | ground truth when the hierarchy is garbled |
| Source file | `source/` (read-only) | final-review basis |
| Current structured text | `structured/<unit>.md` | the object being repaired |

## Operations by category (summary; full list in `docs/semantic-repair.md` §2)

**A. Text flow**: re-break hard line breaks into paragraphs by semantics; merge
cross-page continuation paragraphs; determine running heads/footers/page numbers from the
page images (the tool only backstops with the 50% frequency method); separate
footnotes/marginal notes and establish note-reference↔note-text correspondence; reorder
multi-column/irregular layouts by reading order; deduplicate repeated text layers.

**B. OCR noise**: correct character confusions (`l/1/I`, `己/已/巳`…) by language and
context; restore word boundaries for run-together Western text (`delos`→`de los`); apply
publishing norms to punctuation; restore mojibake by language; remove layout noise against
the page images; **every line broken into a paragraph must be re-broken by semantics
(writing threshold-based merge scripts is forbidden)**.

**C. Structure**: heading determination (misjudged font size/code/figure caption), level
inference, unit-boundary re-split/merge (go through restructure), four-layer
classification correction, garbage-page removal (record the destination in `catalog.csv`).

**D. Media**: choose one among multiple cover candidates; illustration attribution
(full-page plate/inline/decoration/scan background); figure captions and figure order;
table structure recovery (borderless/merged cells/cross-page/header); formula LaTeX (the
`inserts` semantic layer).

**E/F. Metadata and source-defect backflow**: `meta` verification; single-point source
errata during translation go through `corr:`; source defects that affect
paragraphs/structure are written back to structured and the unit is re-translated.

## Trace: `preprocessing/repairs.jsonl` (operation level, one repair action per line)

```json
{"unit": "ch03", "kind": "line_join", "pages": [12, 13], "count": 18,
 "summary": "OCR one line per paragraph, re-broken and merged by semantics", "method": "view images page by page + manual re-arrangement",
 "evidence": "structured/raw/pages/p012.png", "status": "done"}
```

- `unit`: required, must be a unit in `publication.json`;
- `kind`: `line_join|hyphen|ocr_char|mojibake|punct|header_footer|footnote|order|
  heading|boundary|classification|garbage|media|metadata|other`;
- `pages` / `count`: optional (source page number / number of affected places);
- `summary`: required (what was done); `method`: optional (how it was done);
- `evidence`: optional, a workspace-relative path and **must exist** (page image/page
  JSON/MinerU artifact);
- `status`: `done` (repaired) or `unresolved` (cannot be determined, do not force a fix;
  qa will hint).

## Structure rebuild: `preprocessing/structure.csv` + `restructure`

Split units only by the first S levels and keep deeper headings inside the unit, or simply
re-split/merge manually:

```csv
id,region,kind,title,level,rel_path
ch01,body,chapter,Chapter 1 Origins,1,body/ch01.md
ch02,body,chapter,Chapter 2 Entering the City,1,body/ch02.md
```

```bash
auto-epublizer restructure      # validate + update publication.units (same id with unchanged content keeps state)
```

- `rel_path` must be inside `structured/` and the file must exist; each md's first line
  `# title` must match `title`; `structured/` (except raw/) must not contain unregistered
  orphan md;
- If a unit's content changes → state rolls back to `split` (requires re-translation and
  re-import); a vanished unit hints at orphan artifacts.

## Three self-checks (mandatory after bulk repair)

1. **Conservation**: the counts of grep markers (`{fig:NNN}`)/footnotes (`[^label]`)/image
   references are the same as before the repair (loss is blocked by G0/delivery audit);
2. **Sampling**: sample several pages from the first/middle/last and compare against the
   `raw/` page evidence to confirm nothing was silently swallowed;
3. **Cannot determine**: write `status: unresolved` with an explanation; do not "guess-fix".

## Anti-patterns (re-emphasized)

- Do not write "smart merge/split/cleaning scripts" — the threshold is always slightly off
  (real lessons flip over repeatedly);
- Scripts only do deterministic retrieval/statistics/moving; semantic judgements (which is
  a heading/where to break a paragraph/which character is wrong) are read by you yourself;
- After repair you must re-run `import` (md↔align inconsistency blocks) and full
  validation.
