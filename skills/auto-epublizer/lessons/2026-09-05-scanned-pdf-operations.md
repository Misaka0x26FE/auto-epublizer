<!-- i18n: source=2026-09-05-scanned-pdf-operations.zh.md sha256=980d3b780a1f8d5015a4d293bdf40cbee6252143c3cd581b0fe4c084ddf2e8fd -->
> **English** | [中文](2026-09-05-scanned-pdf-operations.zh.md)

# Scanned-copy PDF in practice: traditional OCR disaster vs MinerU (measured on 1018 pages)

> Date: 2026-09-05　Source: measured by the DouBao cloud agent — *JavaScript: The Definitive Guide (6th Edition)*, a 1018-page pure scanned copy (Chinese edition, RapidOCR → post-processing vs a full MinerU vlm redo).
> Status: experience retained. The MinerU backend has entered the main repository (`d16badb`, see `2026-09-05-scanned-pdf-mineru-first.md`); this document is **operational experience** (batching/merging/splitting/build granularity).

## Trigger scenario

You have a scanned-copy PDF (no text layer) and want to make an EPUB. The traditional OCR path works end to end but the artifacts are a disaster; after redoing it with the MinerU approach the quality crushes it. The criteria and handling below are the empirical basis for "think of MinerU first".

## Criteria (disaster characteristics of traditional OCR; switch to MinerU on a hit)

| Dimension | RapidOCR (traditional) | MinerU (vlm model) |
|---|---|---|
| Line breaks/paragraphs | ❌ Each line becomes its own paragraph, sentences are split apart | ✅ Paragraphs intact, blank-line separation correct |
| Heading hierarchy | ❌ None, requires manually extracting the TOC + locating | ✅ Automatic leveling (216 headings) |
| Image extraction | ❌ Full-page scan images cannot be separated | ✅ Automatic extraction (125 images, 30 referenced in the body) |
| Code blocks | ❌ Requires manual identification and repair | ✅ Automatic (389 ``` blocks) |
| Tables/formulas | ❌ Cannot handle | ✅ enable_table/formula automatic recognition |
| Time (1018 pages) | 75.5 minutes | ~2 minutes (6 batches in parallel) |
| Post-processing | merge_paragraphs_v3 + TOC coordinate matching + code correction + bracket escaping | Almost zero |

**Core conclusion**: For scanned copies (especially code/technical books) go straight to MinerU; don't waste time on the traditional OCR + post-processing script chain — a script that does "each line its own paragraph → merge paragraphs" and repeatedly tweaks thresholds (40→20, allow colons) is still an unfinished project.

## Handling

### 1. Batch PDFs >200 pages

A single MinerU task is ≤200 pages / ≤200MB. Split 1018 pages into 6 batches (1-200, 201-400, … 1001-1018):
- Use pymupdf slicing to generate sub-PDFs (`doc.subset([range])` / page-by-page insert_pdf);
- **Local upload goes through `/api/v4/file-urls/batch`** (request presigned URLs → PUT raw bytes) → poll `GET /api/v4/extract-results/batch/{batch_id}`;
- ⚠️ Not `/api/v4/extract/task` (that is the URL method, which needs a publicly accessible address);
- Submit 6 batches in parallel; after all are done, download each zip.

### 2. Merge the 6 batches' results

Each batch's zip contains `full.md` + `images/`. Merging = concatenating markdown in page order + merging the images directories (deduplicating same-name hash collisions by batch prefix) + rewriting image reference paths.

### 3. Splitting units: don't script it, the agent splits manually (key lesson)

The heading hierarchy output by MinerU **may be chaotic** (code content mislabeled as headings, inconsistent levels). At this point **do not write an "intelligent split script"** — script thresholds/regex always fall a little short (this time it repeatedly failed). The correct approach (from DouBao's final summary):

> **"Stop scripting, can't you just split it manually yourself"** — structural splitting is a semantic judgement and belongs to the agent: read `full.md` directly, manually cut out `structured/<unit>.md` by the real chapter headings, and check chapter by chapter.

The script only does deterministic hauling (landing to disk / editing publication.json units/rel_path); a judgement like "which one is a heading" is left to the agent to complete with its comprehension.

### 4. Build granularity = unit granularity, otherwise the TOC navigation is lost

⚠️ Building the whole book's markdown as a **single unit** → the EPUB has no nav TOC (only one body page). You must split it into multiple units by chapter (publication.json.units each carrying `rel_path`) before building; only then is nav.xhtml complete. When done, check that the number of items in `OEBPS/nav.xhtml` = the number of units.

## Verified: differences between the main repository and DouBao's local fixes

| Capability | Main repository (this repo) | DouBao container local |
|---|---|---|
| Fenced code block ` ```language ` → `<pre><code>` | ❌ None (`html.py` only handles inline `` ` ``) | ✅ Added (including a `\x00` placeholder) |
| `\[` bracket escaping (to prevent misdetecting links) | ❌ None | ✅ Added |
| Manual cover injection (add_cover.py) | ❌ None | ✅ Temporary script |

> If code-dense scanned copies (technical books) are to be formally supported, evaluate merging these capabilities into the main repository — especially fenced code blocks, which are currently missing.

## Reproduce / verify

```python
# Main-repository MinerU backend offline regression (the hands-on flow is already covered by tests + the /tmp probe script)
uv run pytest -q tests/test_mineru.py
```

- Batching: slice PDFs + parallel submission → poll until all done → merge; for the script flow see the DouBao execution log (Feishu cloud drive "JavaScript: The Definitive Guide (6th Edition) - MinerU version").
- Single-unit nav-loss regression: construct a single-unit publication.json → build → assert nav has only 1 item.

## Related

- MinerU backend contract/routing: `lessons/2026-09-05-scanned-pdf-mineru-first.md`, `src/auto_epublizer/ingest/mineru.py`;
- Scanned-copy routing table: `references/ingest.md` (MinerU first, ask the user first when there is no key);
- Agent translation workflow lesson: `lessons/2026-09-05-agent-translation-workflow.md`.
