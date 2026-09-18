<!-- i18n: source=semantic-repair.zh.md sha256=5928e93c2036f3e7da8a82c76f9f4835e543f79f09b7ea160c2763e531768e8d -->
> **English** | [中文](semantic-repair.zh.md)

# Semantic Repair (Agent semantic task)

> **Positioning**: systematize "processing that relies on the agent's language ability" —
> the CLI emits signals, the agent repairs, the contract leaves a trace, the CLI registers.
> It is the expansion of the main criterion in `docs/agent-vs-code.md` ("needs understanding/
> weighing/judgement → agent") onto parse defects, OCR noise, and structural judgement.
> **Operational manual**: `skills/auto-epublizer/references/repair.md` (copy and go);
> **Plan**: `docs/plans/2026-09-13-semantic-repair.md`.

## 1. Principles and anti-patterns

1. **Writing "intelligent repair/merge/split scripts" is forbidden** — thresholds/regex are
   always just a bit off (real lesson: `merge_paragraphs` v1/v2/v3 repeatedly tuned
   parameters and was left unfinished, and the MinerU split script repeatedly failed).
   Semantic judgement (which is a heading / where the paragraph breaks / which character is
   wrong) is completed by the agent reading the source text.
2. When the agent writes scripts, it is **only allowed to do deterministic retrieval/
   statistics/transport** (find clues, count, batch-replace already spot-confirmed
   deterministic patterns), not semantic judgement.
3. **Batch repair must sample head/middle/tail against raw page evidence** (to prevent batch
   cleaning from silently swallowing content).
4. Repair must leave a trace (`preprocessing/repairs.jsonl`); what cannot be determined is
   written as `unresolved`, not force-fixed.

## 2. Scenario list (by processing window)

### Window A: text-stream repair after parsing (modify structured/, before translation)

| # | Scenario | Typical symptom/signal | Agent action (evidence → artifact) |
|---|---|---|---|
| A1 | Hard line breaks/paragraph re-composition | Line-end sentence breaks, mid-sentence line breaks, glued paragraphs | Re-break/merge by semantics; cross-check against `raw/page-NNN.json` or page images |
| A2 | Continued paragraph across pages | Page-end sentence truncated, next page's first line continues it | Locate via `source_page`, merge the continuation |
| A3 | Running head/footer/page number wrongly cleared or missed | Odd/even pages differ, chapter first pages differ; short dialogue lines wrongly cleared | Judge keep/remove page by page against images |
| A4 | Footnote/endnote/marginal note attribution | Body and note area mixed, note references mismatch | Separate the note area, establish note reference ↔ note text correspondence |
| A5 | Multi-column/irregular reading order | Boxes, nested columns, full-width headings cause misalignment | View page images and reorder by layout semantics |
| A6 | Cross-page table/figure | Cut by the page boundary, header only on the first page | Merge or adjust presentation |
| A7 | Lost semantic markup | Superscript note references, underline/italic/bold emphasis lost | Restore markdown semantic markup |
| A8 | Duplicate/hidden text layer | PDF white-text duplicate layer, OCR overlap | Deduplicate and cross-check page evidence |
| A9 | Mixed-type PDF | Some pages have a broken text layer, some are scanned | Judge page by page which pages switch to OCR/viewing images |

### Window B: OCR / transcription noise repair

| # | Scenario | Typical symptom | Existing signal/support |
|---|---|---|---|
| B1 | Character confusion | `l/1/I`, `O/0`, `rn/m`, `己/已/巳`, `日/曰` | — (agent judgement) |
| B2 | Latin glue/split words | `delos`→`de los`, hyphenated word breaks | `hyphen_eol` / `long_latin_run` |
| B3 | Chinese misrecognition/variant characters | Rare characters, old glyphs, mixed traditional/simplified | — (agent judgement) |
| B4 | Punctuation errors | Full/half-width mixing, quote direction, ellipsis/dash | `ascii_punct_cjk` |
| B5 | Garbled text/mojibake | `Ã©`, `\ufffd` | `garbled_marks`; sniff the whole-book garble rate |
| B6 | Layout noise turned into characters | Gutter, stains, frame lines become garbage strings | — (cross-check page images) |
| B7 | OCR paragraph merging | Each line is an independent paragraph (inevitable with traditional OCR) | `hard_wrap_lines`; `raw/pages/` |
| B8 | Multilingual mixed typesetting | Multiple languages, pronunciation/original interlinear notes | `analysis/detect.py` (reference) |
| B9 | Speech transcription (forward-looking) | Homophones, no punctuation, speaker segmentation | Not done this round (see plan D3) |

### Window C: structure and classification judgement

| # | Scenario | Existing fallback | Agent action |
|---|---|---|---|
| C1 | Heading determination | `_is_chapter_heading` (font size/keywords) | Determine headings by semantics |
| C2 | Level derivation | `_derive_heading_levels` (PART/numbering) | Reorder `level` (re-splitting goes through restructure) |
| C3 | Unit boundaries | — | Re-split/merge + `restructure` registration |
| C4 | Four-layer classification | `_classify_title` (keyword table) | Correct region/kind |
| C5 | Junk content | — | Remove; record destination in catalog (excluded) |
| C6 | Heading residue | `clean_pandoc_residue` / `E_RESIDUE` | Clean up |
| C7 | TOC consistency | `W_TOC_MISSING` / `W_TOC_DEPTH` | Reconcile and correct |

### Window D: media and inserts

Cover determination (choose one among multiple candidates), illustration attribution (full-page
plate vs inline vs decoration vs scan background), figure caption/table caption and figure
numbering, table structure restoration (borderless/merged cells/cross-page/header), formula
LaTeX (`inserts` semantic layer), inline position of non-linear spine items, media-missing
alignment.

### Window E: metadata and external knowledge (existing flow)

`meta` metadata verification, `terms.csv` terminology pre-extraction, `risks.md` risks,
`corr:` erratum precedents, background-knowledge completion (search → `references/web/`).

### Window F: source defects found during translation/review (backflow)

After locating and verifying against the source page: affecting single-point wording → the
existing `corr:` mechanism (only change tgt + align note for the trace); affecting paragraph/
structure → write back to structured and retranslate that unit (goes through repairs for the
trace).

## 3. Three-layer mechanism

```text
Signal layer (CLI, zero token)   Repair layer (agent)           Registration layer (CLI)
─────────────────────           ─────────────────────          ─────────────────────
facts suspicious signals (per unit) → read raw evidence (page  →  repairs.jsonl (trace contract)
  hard_wrap/hyphen/dup/               images/page JSON/             structural content repair needs no
  garbled/ascii_punct/                MinerU full.md/source file)   registration, goes directly to
  latin_run                           fix structured/ (content)     build/provenance
                                      sample self-check (head/   →  restructure (boundary level):
                                      middle/tail × page evidence)  structure.csv validation +
                                                                    publication.units update
```

### 3.1 Signal layer (already wired)

`preprocess/signals.py::repair_signals` tallies six conservative counts per unit's structured
md (`hard_wrap_lines`/`hyphen_eol`/`duplicate_paras`/`garbled_marks`/`ascii_punct_cjk`/
`long_latin_run`), into `facts.json` (`structure.units[].signals` + `repair_signals`
aggregate) and the `facts.md` "suspicious signals" table; when there is a signal, `agent_todo`
appends a "semantic repair" item.
**A signal is a clue, not a defect**, and does not enter any release gate.

### 3.2 Repair trace contract (already wired)

`preprocessing/repairs.jsonl` (hand-written by the agent, operation level): `{unit, kind,
pages?, count?, summary, method?, evidence?, status}`; `status ∈ done|unresolved`; `unit`
must exist, the `kind` enum is in `references/repair.md`, `summary` is non-empty, `evidence`
is a workspace-relative path and must exist (to prevent fabrication). CLI validation
(`orchestrator.read_repairs`, no breakage when the file does not exist; invalid →
`OrchestrationError` with a line number); `unresolved` goes into `report.json`
(`repairs_total`/`repairs_unresolved`) and triggers a `W_REPAIR_UNRESOLVED` hint
(W level, does not block release).

### 3.3 Restructure registration (already wired)

After the agent re-splits/merges units, it writes `preprocessing/structure.csv` (`id,region,
kind,title,level,rel_path`) and runs `auto-epublizer restructure` to register: the CLI
validates (file present, exactly one h1 per md with a consistent title, no orphans, region
consistent with path, id unique and valid) and then updates `publication.json.units`; same id
unchanged keeps its state, changed units fall back to `split` awaiting retranslation;
disappeared ids output an orphan-artifact hint. The contract and operations are in
`references/repair.md` / `references/structure.md`.

## 4. Relationship with existing mechanisms

| Mechanism | Division of labour |
|---|---|
| `catalog.csv` | Governs "whether source content was **included**" (missing inclusion blocks) |
| `repairs.jsonl` | Governs "whether the included text is **correct**" (repair trace; unresolved only warns) |
| `corr:` erratum | Single-point source error during translation — only changes tgt + align note trace, does not touch src |
| G0 conservation / fidelity | The automatic defense line after repair: marker/footnote/table conservation + align↔structured source fidelity |
| Delivery audit (`references/delivery.md`) | Full re-verification after repair: `E_ALIGN_MD_DRIFT`/finished-product presentation reconciliation, etc. |
