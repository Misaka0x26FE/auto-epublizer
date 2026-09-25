<!-- i18n: source=translation-flow.zh.md sha256=998ec3f500bef3fb48b9de1a940dc9310a131fd972fe4523c7404d485d4a49eb -->
> **English** | [中文](translation-flow.zh.md)

# Translation Flow Design

Building on the traditional "chunked translation" (`split/` → batched translation), this adds
**chapter TOC structure division** and **whole-book → chapter → key-content layered understanding
+ glossary assistance** as input for quality control.
Scope unchanged: only responsible for delivery quality, makes no value judgements.

> **Single-LLM principle**: translation/understanding/review are done by the agent operating the CLI
> (the CLI makes zero LLM calls). This document describes the workflow and data-flow contracts
> (structured/analysis/translation+align/reviews); the **semantic executor of the "analysis",
> "translation" and "review" steps is the agent**, and the CLI only performs structural validation /
> state advance / build QA.

## 1. Overall flow

```text
source ──ingest──▶ structured/ (chapter TOC structure division, four-layer structure)
                       │
                       ▼
                   analysis/ (layered understanding: overview whole-book + global + units chapters + keypoints
                       │      + glossary + characters) 〔agent writes〕
                       ▼
                   translate (chunked translation: chapter → paragraph → sentence pair) 〔agent writes translation/ + align/〕
                       │
                       ▼
                   import (register hand-written artifacts: G0 validation + state advance + terminology-conflict externalization)
                       │
                       ▼
                   review (QC G0–G3, agent reviews and writes result.json) → build → qa (G4–G5)
```

## 2. Chapter TOC structure division (the base unit of chunking)

`structured/` is split into **units** by the publication's four-layer structure; each unit is one
file with a stable ID:

```text
structured/
├── frontmatter/{titlepage,copyright,dedication,foreword,preface,toc}.md
├── body/ch01.md            # body unit (the main battlefield for translation)
├── backmatter/{afterword,appendix,notes,bibliography,index}.md
└── media/…
```

- **A unit = the smallest manageable unit of translation**, state machine: `pending → split → analyzed → translated → aligned → reviewed → built`.
- Each source unit corresponds to one translation unit (`translation/<mirror path>/<id>.md`) + one sentence-level alignment (`translation/align/<id>.jsonl`).
- The "slice" of chunking is a **batch**, not a chapter; chapters are the boundary of scheduling and state management, batches are the boundary sent to the model.

## 3. Chunking mechanism

Within a unit, paragraphs (Segments) are packed into batches by character budget:

> The internal translation pipeline was removed along with the "remove internal LLM" work (2026-09-04);
> the parameters in the table below **have no CLI defaults**, and serve only as operational suggestions
> when the agent translates on its own (how big a batch is, how much prior context to inject, are decided
> by the agent according to its context window).

| Parameter | Suggested value | Description |
|---|---|---|
| `max_chars_per_segment` | 1200 | A single paragraph exceeding this is split further at sentence-ending punctuation (continuation segments are merged back and traced in the align `note`) |
| `max_chars_per_batch` | 1800 | Target size of one batch (sentence group) (agent context budget) |
| `rolling_context_segments` | 6 | Number of trailing segments of prior translation carried when translating |
| `align_retry_limit` | 2 | (Historical parameter; equal-length array validation was removed along with the internal pipeline) |

- Paragraph = Segment (the smallest alignable unit), one paragraph corresponds to one source/translation each;
- Batch = several paragraphs, sent to the model at once; the model **must return an equal-length sentence-pair JSON**;
- Over-long paragraphs are split into multiple segments; continuation segments have `cont=True` and no independent anchor, and are merged back into the original paragraph on write-back;
- Batch boundary = checkpoint for resume (which batch each unit has been translated to is reflected by unit state + align progress; `.progress.json` is reserved and not persisted).

## 4. Layered-understanding injection (whole book → chapter → key points)

Before translating each batch, assemble context in "static → dynamic" order (prefix-cache friendly, following the wenyi experience):

| Level | Source file | Content | Stability |
|---|---|---|---|
| Whole-book overview | `analysis/overview.md` | Main line, character arcs, foreshadowing, ending | Book-level static |
| Style guide/global | `analysis/global.md` | Narrative person, tone, register, dialogue style, cross-chapter dependencies | Book-level static |
| Chapter summary | `analysis/units/<id>.md` | Plot/argument progression of this chapter, characters appearing, terminology notes | Chapter-level static |
| Key points | `analysis/keypoints.md` | High-risk paragraphs, complex layout, multilingual-fragment reminders | Book-level static (injected on hit) |
| Terminology subset | unified store + `glossary.csv` | Terms **actually appearing** in this batch's body text (`terms_in_text`); the unified store is seeded via `knowledge export` | Batch-level dynamic |
| Prior translation | `tgt` of the previous batch's `align/` | Most recent N paragraphs, maintaining pronoun/appellation/tone continuity | Batch-level dynamic |
| Text to translate | This batch's `src` paragraphs (with numbers) | Translation object | Batch-level dynamic |

> prompt structure (corresponding to wenyi's cache convention): system is fully static; user is arranged as
> "style/overview → chapter summary → key points → glossary → prior translation → text to translate",
> the earlier the more stable, and the more prefix-cache hits.

## 5. Translation batch data flow (chunk → sentence pair)

```
paragraph array [p0, p1, …] + layered context + terminology subset   (the agent translates paragraph by paragraph after reading the understanding layer and terminology)
        │
        ▼
translation/<rel>.md + align/<id>.jsonl  ← one sentence or several per paragraph: {seq, src, tgt, note}
        │  (import validation: seq continuous, no empty translation; splits/merges declared in note)
        ▼
state advance translated → aligned
```

Key guarantees:

1. **Paragraph-level equal length**: input N paragraphs, output must have N items (each item is that paragraph's array of translated sentences); mismatch is retried, with per-paragraph fallback — structurally eliminating whole-paragraph omissions.
2. **Sentence-level alignment**: each paragraph's translation is split by sentence and mapped one-to-one with the source sentences, written into `align/<id>.jsonl` as `{seq, src, tgt, note}`; sentence splits/merges are declared in `note`. This is the sole source for QC G0 (alignment completeness) and bilingual layout.
3. **Continuation merge-back**: the translation of a continuation segment with `cont=True` is merged back into the previous paragraph and does not start a new paragraph.

## 6. Glossary assistance (three-state closed loop)

```text
seed ── analyze seeding + references/user import
    │
    ▼
inject ── each batch filtered by terms_in_text then injected into the prompt (confirmed-state translations must be followed)
    │
    ▼
propose ── after translation, extract new terms/appellation variants, append to glossary_conflicts.jsonl
    │
    ▼
resolve ── single-threaded merge: same source with different target records a conflict; after human/agent confirmation write back to glossary.csv
    │
    ▼
record ── knowledge import: merge the workspace's confirmed terms into the unified store (cross-book reuse + auto git commit)
```

- Appellations/honorifics/catchphrases/fixed expressions match exactly only by the complete source, avoiding false injection of bare-name aliases;
- Conflicts do not automatically overwrite confirmed translations; candidates are retained pending arbitration (corresponding to the traditional "unified translated names + established usage").
- **Unified store** (default `~/Documents/auto-epublizer/`, itself a private git repository)
  shares terminology decisions across books: seed with `knowledge export` when a new book
  starts and write back with `knowledge import` at the end; the same key with different
  confirmed targets across books is externalized to the store's `conflicts.jsonl` pending
  agent arbitration (see `references/workflow.md`).

## 7. State machine and resume

- Unit: `pending → split → analyzed → translated → aligned → reviewed → built`.
- Resume = skip completed batches by unit state + align progress (`.progress.json` is a reserved checkpoint file, not persisted).
- When changing the glossary/understanding/parsing cache, the affected units' post-interruption resume must be covered (consistent with the RunStore invariants).

## 8. Interface with quality control

| Translation link | Corresponding QC gate |
|---|---|
| Sentence-level alignment produces `align/` | G0 alignment completeness, sentence-count consistency, length ratio, empty translation |
| Terminology injection → translation terminology | G0 terminology hit (deterministic) + G1 terminology violation + G2 arbitration |
| Layered-understanding injection | Translation consistency (pronoun/appellation/tone), contextual basis for G1 review |
| Chunk batches | Resume granularity + G1 per-batch review granularity |

## 9. Differences from traditional chunked translation

| Traditional chunking | This project |
|---|---|
| `split/NNNN.md` plain-text chunks | `structured/` chapter TOC structure + stable unit IDs |
| `_analysis.md` / `_understanding.md` single file | `analysis/` layers: overview/global/units/keypoints |
| `GLOSSARY.csv` manually maintained | glossary three states + conflict externalization + injection filtering |
| No sentence-level alignment after translation | `align/<id>.jsonl` sentence-level alignment (anchor for QC and bilingual) |
| No QC closed loop | Translation → G0–G3 review closed loop |
