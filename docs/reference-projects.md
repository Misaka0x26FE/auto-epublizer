<!-- i18n: source=reference-projects.zh.md sha256=6e21aaf4357fd323d088b8cc56ead3f866b14b5b1863ca14ac1fcd08eaf45390 -->
> **English** | [中文](reference-projects.zh.md)

# Reference project: wenyi

> **Positioning**: a source of design inspiration. wenyi (`trans_novel`) implements several capabilities that auto-epublizer wants;
> this document records the **borrowings** (directly adopting its patterns) and the **differences** (where we do things differently / more strongly).
> The design contract for agents maintaining this repository is in `AGENTS.md`; this is the provenance reference.

Reference [wenyi](https://github.com/BigDawnGhost/wenyi) (package name `trans-novel`) — a multi-stage translation tool for long texts.

## Borrowings (directly adopting its patterns)

1. **Data model**: `Document → Chapter → Segment`. Segment is the smallest translatable/alignable unit (usually one paragraph), carrying `anchor` (an EPUB backfill placeholder), `resource_href`, `cont` (the continuation-segment marker after splitting an over-long paragraph, merged back into the original paragraph on backfill).
2. **State and resume (RunStore)**:
   - same-directory temp file + `os.replace` atomic write;
   - `source_sha256` binds the source content, rejecting silent reuse of state for "same name, different content";
   - multi-level file locks (run/state/event/assemble) isolate long pipelines from short state reads/writes;
   - `manifest.json` is committed atomically last, as the initialization-complete marker ("derived state first to disk, manifest last");
   - `events.jsonl` append-only behavior ledger, used for auditing and batch-checkpoint recovery;
   - freeze a consistent snapshot before export (ExportSnapshotStore), avoiding reading a mixed moment of the manifest and chapter files.
3. **Paragraph-level alignment strategy**: send a batch of N paragraphs to the model as a whole, requiring a **same-length JSON array** in return; retry on count mismatch (align_retry_limit), and if it still mismatches, fall back to translating paragraph by paragraph — structurally eliminating whole-paragraph omissions. On top of this we add a **sentence-level alignment table** (see AGENTS.md "sentence-level alignment").
4. **Terminology store**: SQLite storage + `term_conflicts` conflict table; when the same source has different targets, keep the current translation and record the candidate for manual adjudication; filter and inject into the prompt per batch according to the actual occurrences in the body; sort by rowid for a stable prefix cache.
5. **Punctuation norms**: unify Chinese punctuation (the PUNCT_RULE idea); keep the source text's punctuation/paragraph structure during translation.
6. **Architecture boundaries**: `CLI → Orchestrator (thin façade) → domain services`, lower layers must not import upper layers in reverse, concurrency belongs only to domain services, results are merged in stable order; the contract is fixed by `test_architecture_boundaries.py`.
7. **Configuration and resume**: YAML configuration (language/pipeline/qc/pdf/glossary/paths/output), idempotent resume of the same command.

## Differences (where we do things differently / more strongly)

| Dimension | wenyi | auto-epublizer |
|---|---|---|
| Target language | Simplified Chinese only | any language, configurable |
| Alignment granularity | paragraph-level same-length arrays | paragraph-level alignment + **sentence-level JSONL alignment table** |
| Structure model | everything processed by chapter | explicit publication **four-layer structure** (frontmatter/body/backmatter + appearance) |
| Core function | translation-first | **convert as a first-class function**, translation optional |
| PDF | depends on the MinerU external API | local OCR (RapidOCR) + text-layer/illustration/table/formula extraction + agent vision (MinerU external API takes top priority) |
| Workspace | `state/<slug>/` | `publication.json` + workspace directory |
