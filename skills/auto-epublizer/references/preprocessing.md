<!-- i18n: source=preprocessing.zh.md sha256=b24e1b5a1d1ed149d9aa92f127be568c5d486cf36bea022e319d3f0afe492b7f -->
> **English** | [中文](preprocessing.zh.md)

# Preprocessing (fact collection + agent-authored understanding)

Preprocessing is an **agent task**: the CLI only produces zero-token facts
(`preprocessing/facts.json` / `facts.md`); approach decisions and layered understanding
are written by you (the agent) with your own capabilities. All artifacts land in
`preprocessing/`.

## 1. Run fact collection

```bash
# New book (= init + fact collection: sniffing/metadata/TOC/health check/size)
auto-epublizer preprocess <input> [--reference <path...>] [--target zh-CN]
# Existing workspace (idempotent refresh of facts)
auto-epublizer preprocess
```

`facts.md` contains: source file type and sniffing results (DRM/text layer/scanned-copy
detection/garbled-character rate), DC metadata, table of contents TOC, size statistics
(units/words/sentences/rough token estimate), content health check, environment
capability snapshot (doctor), deterministic routing hints, and the **agent to-do list**.

## 1.1 Capability self-report (capabilities.md)

The five-dimension capability boundary that the CLI cannot probe is self-reported by you
(the agent) before starting work, written to `preprocessing/capabilities.md`:

| Dimension | Self-report content | Impact |
|---|---|---|
| Agent's own capabilities | multimodal (can it look at images), search (does it have a web search tool) | Scanned PDF visual fallback / background-knowledge completion routing |
| Agent model | Model ID, context window, whether it is a vision model | Amount of book content processable per pass, whether multimodal can be used |
| OS environment | Locally reachable CLI tools (the part doctor already probed) | ingest/OCR routing |
| External API boundary | Available external parsing API (MinerU key), network reachability | Parsing/retrieval availability |
| Workload of files to process | Rough size estimate (facts has a rough token estimate), difficulty estimate | Splitting and phased plan |
| Persistent unified store | Whether the persistent directory is writable (check with `knowledge path`), whether the unified terminology/knowledge store is used | Cross-book terminology/knowledge reuse (without write permission, only the local workspace glossary is used) |

`multimodal` / `search` can also be confirmed from the "environment capability snapshot"
in `facts.md` (what the CLI cannot probe shows "awaiting agent self-report").

## 1.2 Background-knowledge completion (Plan B routing)

Before translation, if background knowledge is missing (proper names, historical facts,
cultural background, suspicious OCR text), route as follows:

1. **With a web search tool** (self-reported search=true): search on your own, record
   results and sources in `references/web/` (URL, title, time), append to
   `references/index.jsonl`;
2. **Without a search tool**: explicitly ask the user, and place the material the user
   provides in `references/user/`;
3. If neither is available, do not force completion; write the gap into `risks.md` to be
   handled during translation/review.

## 2. Write in to-do order (all written under `preprocessing/`)

### 1.2 Metadata verification (first facts to-do item; written back by the `meta` command)

The metadata sniffed by facts (title/creator/publisher/date/rights) is only an
**inference** — metadata carried by the source file is often wrong, often missing, often
garbled. First step of the work: verify item by item against the source copyright
page/bibliographic record (ask the user where in doubt), and after confirming/completing,
write back:

```bash
auto-epublizer meta --publisher "..." --date "..." --rights "..."
```

**Default rule for translator credit**: when the user gives no special instruction, the
translator = your agent framework name (OpenCode writes `OpenCode`, DouBao writes
`DouBao`, and so on); a name specified by the user takes priority.

```bash
auto-epublizer meta --translator OpenCode
```

The credit enters the EPUB metadata along with build (`dc:creator` + `role=trl`); the
`W_META_INCOMPLETE` of the QA phase should already have been handled by this step during
preprocessing.

### 2.0 `todo.md` (detailed task list — the first thing to do, running through the whole process)

**Requirement**: after reading facts and before starting translation, break "every action
needed to process this book" down into a checkable task list. The granularity must be
small enough that **it can be followed without thinking**: one item per unit (read
structured → write translation + align → import → g0), one build validation every 3–5
units, and each review/QA/delivery phase listed item by item. Throughout translation,
**check off one item each time one is completed**, and append/correct as progress is made.

Template (add or remove items on this basis according to the book, e.g. group by
"part/chapter/interlude", attach estimated tokens or word counts):

```markdown
# todo.md (detailed task list)

> The first artifact of the work. Check off one item each time one is completed (- [x]); append new tasks to the corresponding phase.
> Works together with the status --json / publication.json state machine to prevent "thinking it was done when it was not".

## 0. Preprocessing understanding (after facts)
- [ ] capabilities.md: self-report the five-dimension capability boundary
- [ ] plan.md: approach decisions (route + basis + workload)
- [ ] global.md: global understanding
- [ ] units/<id>.md: per-chapter understanding
- [ ] terms.csv: terminology pre-extraction + import --terms
- [ ] risks.md + report.md

## 0.5 Semantic repair (signal-triggered; mandatory on the OCR/scanned-copy path)
- [ ] Read the "suspicious signals" table in facts.md, check/repair structured/ unit by unit (references/repair.md)
- [ ] Write preprocessing/repairs.jsonl (leave a trace for every repair; write unresolved when undecidable)
- [ ] When re-splitting/merging units, write preprocessing/structure.csv + run restructure

## 1. Unit translation (per unit: read structured → write translation + align → import --unit → g0 --unit)
- [ ] ch01 <title> (about N paragraphs)
- [ ] ch02 <title>
- [ ] ... (list one by one across 48 units / 25 chapters)

## 2. In-process validation (once every 3–5 units translated)
- [ ] build once, validate the format contract (image segments / blank lines / escaping / TOC hierarchy)
- [ ] Unpack and spot-check: illustrations, TOC, headings

## 3. Review (G1–G3)
- [ ] Review batch by batch, write reviews/review-<ts>/{issues,patches,summary,result.json}
- [ ] Externalize terminology conflicts to glossary_conflicts.jsonl, arbitrate item by item and write back to glossary.csv
- [ ] Spot-check the bilingual build (--bilingual), focusing on ellipsis-ending paragraphs

## 4. Build and QA (G4–G5)
- [ ] build the full EPUB
- [ ] qa: epubcheck 0 error + audit pass + G0 terminology hits cleared
- [ ] Check that status --json has no stale, and the TOC hierarchy matches the source book
- [ ] Delivery: artifacts land in output/ + record events
```

### 2.0b `repairs.jsonl` + semantic repair (conditionally triggered)

When a row in the "suspicious signals (semantic-repair clues)" table of facts.md is hit
(the OCR/scanned-copy path should do this whether or not there is a signal), follow
`references/repair.md` to repair `structured/` against the evidence in `raw/`, and write
every repair action into `preprocessing/repairs.jsonl` (contract in repair.md;
`unresolved` items are flagged by qa).
A signal is a clue, not a defect — judgement and handling are done by you (the agent),
**do not write heuristic repair scripts**.

If the repair is accompanied by re-splitting/merging of unit boundaries: write
`preprocessing/structure.csv` and then run `auto-epublizer restructure` to register it
(for state-machine rollback semantics see `references/structure.md`).

### 2.1 `plan.md` (approach decisions)

Input: facts.md (source type/health check/capability snapshot/routing hints) +
the decision table in `references/ingest.md`.
State clearly: the chosen ingest route (pandoc / page slicing / scanned-copy route:
**MinerU API first — when there is no key, first ask the user whether they have one**;
only without a key fall back to traditional OCR/rapidocr + page-by-page reading) and the
**basis** for it; for scanned copies, specify how OCR or page-by-page reading will be
executed (including workload estimate: page count × cost of page-by-page reading); blocking
problems such as DRM/corruption are escalated to the user here.

### 2.2 `global.md` (global understanding)

Main content, central idea, language style (register/tone/sentence-pattern preference),
narrative structure (person/tense/cross-chapter dependencies), genre determination
(novel/academic/paper/poetry/newspaper, see `references/style.md`).
This is one of the sources of translation context (when `analysis/` is missing, the agent
falls back to reading this file during translation).

### 2.3 `units/<id>.md` (chapter understanding)

One per unit: this chapter's summary/development of ideas/characters appearing/terminology
notes/connection with other chapters.
It likewise serves as chapter-level context for agent translation (fallback order as above).

### 2.4 `terms.csv` (terminology pre-extraction)

The column format is identical to the authoritative columns of `glossary.csv`:
`source,target,type,aliases,gender,reading,status,note`
Coverage: personal names/place names/institutions/proper names, source-only verbal
tics/forms of address/fixed expressions, abbreviations and known erratum precedents.
Import the terminology store before translation:
`auto-epublizer import --terms preprocessing/terms.csv`.

**Seed first (cross-book reuse)**: run `auto-epublizer knowledge export --workspace .`
(add `--src-lang <code>` when the source language is `auto`) to write the unified store's
same-language-pair confirmed terms into this file; then add/remove/revise as you see fit —
avoiding repeated research and cross-book name inconsistency (see `references/workflow.md`).

### 2.5 `risks.md` (risk annotation)

Multilingual passages/poetry/puns/cultural references, long difficult sentences and
terminology-dense passages, expected terminology conflicts,
list of difficult OCR pages of scanned copies. For translation and review to focus on.

### 2.6 `report.md` (summary)

The distilled merge of the above items; it is the "pre-translation input anchor": one
table that answers "which approach to use, what the whole book is about, how the style is
set, how terminology is unified, where the risks are, how big the scale is".

### 2.7 `catalog.csv` (optional: source content inventory)

Table-of-contents completeness contract: declare the destination of each item of source
content — `included` (included, unit_id required), `physical` (physical elements such as
dust jacket/belly band/spine, intentionally not in the EPUB), `excluded` (intentionally
excluded, note must give the reason), `absent` (**absent from the source itself**, e.g. an
illustration the caption refers to but the source package does not contain; note must give
the evidence, **does not block release**), `unresolved` (undecided, **qa blocks release**).
Complementary to provenance: catalog governs "whether anything was missed on the source
side", provenance governs "whether anything was untranslated on the translation side".
When the facts to-do list has this item, it is recommended to write it; if not written,
all checks are skipped.

## 3. Completion criteria

- `preprocessing_complete == true` in `auto-epublizer status --json`
  (facts + todo.md + global.md + capabilities.md all four present)
  and no more `preprocessing_plan_missing` stale hint.
- **todo.md must be generated**: the detailed task list has listed all unit translation
  items and phase validation items
  (this is the whole-process work anchor for subsequent translation/review/delivery).
- The seven artifact types capabilities/plan/global/units/terms/risks/report are all
  present (for small books risks and report may be merged, but
  capabilities/plan/global/terms are required).

## 4. Relationship with analysis

- The understanding layer is written by you: you may write `preprocessing/`
  (plan/global/units/terms/risks/report), or write `analysis/`
  (overview/global/units/keypoints/style/glossary, see `references/analysis.md`) — both
  are read as context sources for translation/review, with `analysis/` taking priority.
- `preprocess` only produces zero-token facts and the to-do list; it performs no semantic
  generation.

## Notes

- `preprocessing/facts.*` is generated idempotently by the CLI, **do not edit it by hand**;
  the other files are intelligent artifacts written by you.
- The "routing hints" in facts are deterministic conclusions, not decisions; the final
  approach is governed by plan.md.
- The scale token figure is a rough estimate (chars/2), used for planning only, not a
  billing basis.
