<!-- i18n: source=testing-doubao.zh.md sha256=f7d0149debf6ca4b0124f900a3b020a0172938c0d649c54d8bae337b7d2dfdaa -->
> **English** | [中文](testing-doubao.zh.md)

# Testing Guide for Real Use in the DouBao Cloud Container

> ⚠️ **Historical record (outdated after 2026-09)**: the `llm:` section of `config.yaml` has
> been removed per the **single-LLM principle** (CLI makes zero LLM calls). The LLM
> configuration steps in this document (§2.3 Volcano Ark, etc.) no longer apply; the part of
> the field-test experience about "the agent main process completing translation/review"
> (§9) is exactly the current way of working. Kept as a historical reference for network/
> toolchain troubleshooting in the DouBao environment.

Purpose: in the **DouBao APP cloud container**, use a real book and a real agent to run the
complete pipeline, verify the behavior promised by `AGENTS.md` / `skills/`, and record the
deviations from expectations.

> This document is for **manual testing** (a human or a DouBao agent follows it literally).
> For offline automated testing see `uv run pytest -q`.

---

## 1. Environment constraints of the DouBao cloud container

| Constraint | Impact | Countermeasure |
|---|---|---|
| No external LLM API (DeepSeek/OpenAI etc. unavailable) | the default `api.deepseek.com` in `config.example.yaml` **cannot be reached** | LLM goes through the Volcano Ark (DouBao) OpenAI-compatible endpoint (§2.3) |
| Reachability of external networks such as GitHub / astral.sh is uncertain | `git clone`, the `uv` install script may fail | alternatives: upload a zip (§2.2), `pip install uv` |
| `pandoc` / `java` most likely not preinstalled | EPUB/DOCX/HTML reading, epubcheck skipped | `apt-get install pandoc`; epubcheck optional (§2.1) |
| The container may be a low-spec CPU | all local computation is light (no heavy models) | the main time cost is API round trips |

---

## 2. Environment preparation (inside the container)

### 2.1 Basic tools

```bash
# Python 3.12 + uv (fall back to pip when uv cannot be installed)
curl -LsSf https://astral.sh/uv/install.sh | sh || pip install uv
uv python install 3.12        # when the container ships python < 3.12

# pandoc (needed for EPUB/DOCX/HTML input; not needed for TXT/MD/PDF)
apt-get update && apt-get install -y pandoc

# epubcheck + java (optional; when missing, qa's epubcheck result is -1 and released is always False)
# java -jar ~/.cache/epubcheck.jar is the default lookup path
```

### 2.2 Obtaining the project

```bash
# preferred
git clone https://github.com/Misaka0x26FE/auto-epublizer.git
cd auto-epublizer

# when GitHub is unreachable: download the zip on your machine, then upload it to the container via the DouBao APP
unzip auto-epublizer-main.zip && cd auto-epublizer-main

uv sync                       # install the three-package dependencies
uv run pytest -q              # offline smoke: should be all green (no dependency on network or API Key)
```

### 2.3 LLM configuration: Volcano Ark (the only DouBao channel)

The DouBao model is provided through Volcano Ark's OpenAI-compatible endpoint; the provider
needs no code change, only a configuration change:

```bash
# API Key is read only from an environment variable (contract: forbidden to write into config.yaml / commit)
# Create the Key in the Volcano Ark console: console.volcengine.com/ark
export ARK_API_KEY="<Volcano Ark API Key>"
```

Write `config.yaml` at the project root (**the only difference from config.example.yaml is the llm section**):

```yaml
llm:
  provider: openai-compatible
  base_url: https://ark.cn-beijing.volces.com/api/v3   # note: no /chat/completions
  api_key_env: ARK_API_KEY
  timeout: 600
  max_retries: 4
  tiers:
    strong:                       # translation / evidence gathering / revision
      model: doubao-seed-1.6-250615
      options: {}                 # no private parameters such as thinking, to avoid 4xx
    cheap:                        # review G1 / analysis
      model: doubao-seed-1.6-flash-250615
      options: {}
    fast:
      model: doubao-seed-1.6-flash-250615
      options: {}
```

> Model IDs are subject to the "Online Inference" page of the Ark console; the examples in
> this document may be outdated. Using the flagship for strong and the low-price tier for
> cheap/fast can save considerably. The Ark endpoint belongs to the DouBao domain system and
> the container network should allow it.

For the remaining sections (segment/qc/paths…), copy directly from `config.example.yaml`.

### 2.4 General notes

- **All CLI commands are run from the project root** (the CLI reads `config.yaml` from the cwd by default).
- The workspace is created under the cwd by default: `auto-epublizer init ~/books/foo.txt` → `./foo/`.
- Run only one long-pipeline command at a time (`publication.json` has a file lock, but don't go asking for trouble).

---

## 3. Smoke test (5 minutes, first prove the path works)

```bash
cd auto-epublizer
printf '# Chapter One\n\nIt was a bright cold day in April, and the clocks were striking thirteen.\n' > /tmp/demo.md
uv run auto-epublizer init /tmp/demo.md
uv run auto-epublizer analyze
uv run auto-epublizer translate
uv run auto-epublizer review
uv run auto-epublizer build
uv run auto-epublizer qa
uv run auto-epublizer status --json
```

Expected: each step has green Chinese output; finally `output/demo.epub` exists; `qa` outputs
`G5 放行：否` (**without an epubcheck jar, released is always False; this is expected, not a bug**).

If analyze fails right away: first check whether `ARK_API_KEY` is exported and whether the Ark model ID is valid (§8).

---

## 4. Test cases

> Book selection: use only **public-domain** texts (Project Gutenberg public-domain books, etc.). It is recommended to start with a short piece (< 10,000 words) and then a long book.
> Cost intuition: a full pipeline for a short piece is about several dozen to just over a hundred API calls; each +1 review round approximately doubles the cost.

### T1 Full pipeline for a short TXT/MD translation (core, must-test)

```bash
uv run auto-epublizer init ~/books/poe-tell-tale.txt
uv run auto-epublizer analyze          # produces analysis/: language/genre detection + terminology seeding
uv run auto-epublizer translate        # produces translation/ + align/*.jsonl
uv run auto-epublizer review           # produces reviews/review-<ts>/
uv run auto-epublizer build            # produces output/<slug>.epub (translation only)
uv run auto-epublizer qa
```

Verification points:

| Item | Expectation |
|---|---|
| `status --json` | the unit goes through `split → analyzed → translated/aligned → reviewed → built` |
| `analysis/glossary.csv` | has seed-status terminology rows (record the DouBao extraction quality along the way) |
| `translation/align/*.jsonl` | each line is `{seq,src,tgt,note}`, seq contiguous 1..N |
| `reviews/review-<ts>/result.json` | `termination=clean_confirmed` (a real LLM may also reach max_rounds; just record it) |
| `report.json` | g0_flags / g1_candidates / g2_confirmed / g3_patched / error_rate fields all present |
| `usage.json` | merged_runs contains the `analyze-`, `translate-`, `review-` prefixes |
| Open the EPUB | translation complete, no leftover English paragraphs, Chinese punctuation normal |

### T2 Checkpoint resume (translate skips completed units)

```bash
# after T1 completes:
uv run auto-epublizer translate
# the output should show units=0 skipped=N; usage.json calls does not grow (no LLM calls)

uv run auto-epublizer translate --force
# the output should show units=N skipped=0; everything is retranslated and re-charged
```

### T3 Genuine review convergence

Using the T1 workspace, read `reviews/review-<ts>/rounds/`:

- If R1 has issues → `issues.json` has candidates → `summary.json` records the confirmed count;
- `shadow_overlay.json` exists and **contains only the revised sentences** (the official `translation/` is unchanged; verify by diff);
- Blind re-review: the next round's issue count should drop or stay at 0; two consecutive rounds of 0 → `clean_confirmed`.
- If `termination=max_rounds / no_progress / unresolved_fixes`: the unit **must not** be marked
  `reviewed` (`status --json` should stop at aligned) — this is intentional behavior; rerun after manual handling.

### T4 Conversion path (no translation)

```bash
uv run auto-epublizer convert ~/books/some.epub -o /tmp/out.epub
```

Verification: consumes no LLM calls (usage unchanged); the `dc:language` of the OPF of an English book is the source language
rather than zh-CN; the unit status is directly `built`.

### T5 Bilingual EPUB

```bash
uv run auto-epublizer build --bilingual    # produces <slug>-bi.epub
```

Verification: each translated-sentence paragraph `xml:lang="zh-CN"` and source-sentence paragraph `xml:lang="<source language>"` interleave.

### T6 pandoc formats (EPUB / DOCX / HTML)

Requires pandoc from §2.1. init a small book in each format and run the full T1 pipeline. Focus:
chapter splitting into multiple chXX units (TXT/MD is heading-heuristic; EPUB/DOCX should follow the document structure).

### T7 PDF (text layer)

```bash
uv run auto-epublizer init ~/books/legacy.pdf
```

Known behavior: **the whole book is grouped into a single `ch01` unit** (no chapter-level splitting); `structured/raw/page-NNN.json`
keeps a per-page archive. A scanned PDF (no text layer) reports an error directing you to OCR — **OCR is not wired into the CLI**, a known
unwired item (see §6); just record it when encountered, don't fix it as a bug.

### T8 Error paths (zero cost)

| Operation | Expectation |
|---|---|
| Do not export ARK_API_KEY and run translate directly | Chinese error `缺少 API Key`, no traceback |
| `init /tmp/不存在.md` | Chinese error `源文件不存在` |
| init again with the same-named workspace | reports `工作区已存在` |
| run a follow-up command after modifying the source file | reports `输入文件内容与工作区不一致` (sha256 binding) |
| `qa` without a prior build | reports `成品不存在…请先 build/convert` |

---

## 5. Interpretation guide

**`status --json`**: `units[].status` is the only source of progress truth. Stuck in an intermediate state → resume from that stage.

**`report.json` (qa product, aggregating G0–G5)**:

| Field | Meaning |
|---|---|
| `g0_flags[]` | zero-token static warnings (length ratio / empty translation / missing terminology / seq gaps); advisory clues do not block release (English→Chinese length ratio has many false positives; all 994 measured entries were false positives) |
| `g1_candidates` / `g2_confirmed` / `g3_patched` | G1 candidates → G2 evidence-confirmed → G3 actual revision count |
| `error_rate` | `g2_confirmed / total sentence count` |
| `g4_audit` / `g4_epubcheck_errors` | unpack audit / epubcheck (-1 = not run) |
| `released` | release decision: issues cleared to zero or all revised + audit pass + epubcheck 0 error + no G0 warnings |

**`usage.json`**: the `merged_runs` run_id is idempotent — rerunning the same command does not double-charge;
`totals.calls` is the cumulative call count.

**`reviews/review-<ts>/result.json`**: for the meaning of the four termination states and the next step, see
`skills/auto-epublizer/references/review.md`.

---

## 6. Known limitations (encountering ≠ bug, just record it)

> 2026-09-04 recheck: the two items OCR and terminology proposal are now wired (`pdf.ocr: auto/off` + `import --terms`);
> analyze truncation, review/translation serialization, convert source language, and PDF chapter-level aggregation have been fixed by fix plans
> P2/P3/P4 and removed accordingly; the remaining items still hold.

| Symptom | Cause |
|---|---|
| `released` always False | the container has no epubcheck jar; only after installing it will release follow the real result (environment limitation, not a bug) |
| `.progress.json` not persisted | reserved checkpoint file; the actual checkpoint = unit-level skip (the contract already marks it as reserved) |
| Still fails after automated batch retries | each batch has already retried 2 times; it stops on error, and a human reads the message |

## 7. Result record template

After each test case, archive the following materials (for backfilling issues / improvement iterations):

```text
test case number / book title / size (word count or sentence count)
environment: DouBao cloud container spec, whether pandoc is present, whether epubcheck is present
the llm section of config.yaml (Key scrubbed) + model ID
command sequence and time per step (wall-clock time of uv run …)
status --json final state, full report.json, latest reviews result.json
usage.json totals and merged_runs count
list of deviations from expectations (including new findings beyond §6)
3 sampled translation paragraphs (source/translation side by side)
```

## 8. Troubleshooting

| Symptom | Handling |
|---|---|
| analyze reports HTTP 401/403 | `ARK_API_KEY` not exported or invalid |
| reports HTTP 404 | base_url is wrong (should end at `/api/v3`) or the model ID does not exist |
| reports 4xx and mentions `response_format` | the chosen DouBao model does not support json_object; switch to a pro/seed series model ID |
| all requests time out | the container network does not allow the Ark domain; confirm on the DouBao side |
| `审校输出协议违例` appears repeatedly | DouBao model JSON stability problem; switch to a strong-tier model and retry, keep the message |
| pandoc reports an error | convert EPUB/DOCX to PDF/TXT as a fallback (`IngestError` has a Chinese message) |
| translate is interrupted | just rerun the same command: completed units are skipped automatically (T2) |

---

## 9. DouBao environment field-test record (2026-09-02)

> This section is the actual result and deviations of running this guide for real inside the **DouBao APP cloud container**, backfilled for subsequent iterations.
> Test subject: Baka-Tsuki《A Certain Magical Index GT Vol. 1》(English, about 66,619 words, 42 structural units, 13 illustrations).

### 9.1 Problems found in the field test and their handling

| # | Symptom | Root cause | Handling |
|---|---|---|---|
| 1 | `uv run pytest` collection had ImportError in 4 files; CLI startup immediately `ModuleNotFoundError: auto_epublizer.build` | the repository **had never committed `src/auto_epublizer/build/`**: the unanchored pattern `build/` in `.gitignore` accidentally harmed the source directory | completed the build module per the test and QA contract; **main repo already fixed** (`585f3a2`: `build/` → `/build/` and re-pushed the module) |
| 2 | after `init`/`convert`, `structured/raw/media/` was empty and illustrations did not enter the EPUB | pandoc resolves relative-path resources against the **cwd** (not the source file directory) | `run_pandoc` changed to `cwd=source file directory` + absolute paths; **main repo back-ported** (`d7a3e46`) |
| 3 | pandoc output the placeholder syntax `[alt]{.image .placeholder …}` for isolated image paragraphs, which the standard regex cannot match | inherent pandoc behavior | `collect_media` recognizes the placeholder syntax; **main repo back-ported** |
| 4 | MediaWiki skin traces (`[]{#…}`, `[edit]`) caused classify misjudgment | pandoc retains skin traces | preprocessing script lxml-extracted `#mw-content-text` for deep cleaning (user-side script, not in the main repo) |
| 5 | **container has no external LLM API**: no usable Ark Key, `analyze` reports 401; some external networks (wikimedia) time out | environment limitation | see §9.2 |

### 9.2 Key decision: translation is done by the agent main process

> In the DouBao environment with no usable external LLM API, the translation pipeline is done by the **agent main process**: the agent reads `structured/`
> → translates with its own capabilities → writes `translation/` (mirrored structure) + `align/` sentence-level alignment → `build` → `qa`.
> The CLI's `analyze`/`translate`/`review` are **not the main translation path** inside the DouBao container; the Ark configuration in §2.3
> degrades to an **optional branch** (environments with a Key can still use it).

### 9.3 Build-layer defects (found during full Chinese delivery)

| # | Symptom | Handling | Main repo status |
|---|---|---|---|
| 6 | TOC and page titles show English (source titles) | build/convert take precedence from the first `# ` heading of the translation file | back-ported (`d7a3e46`) |
| 7 | MediaWiki container div empty-shell units mixed into the TOC | skip empty-shell units with no body and a placeholder title | back-ported |
| 8 | HTML `<img>`/`<figure>` were escaped wholesale, pandoc thumbnails double-escaped | `collect_media` recognizes HTML images; `_PANDOC_LINKED_IMG` normalization | back-ported |

### 9.4 Quality validation results

- ch20 translation misalignment (missing one translated paragraph causing an overall shift forward) was found by a "dialogue-quote continuity + image-paragraph alignment" scan and fixed; a full re-scan of all 42 units found no misalignment.
- Final delivery: 41 spine units + 13 images full Chinese EPUB, G4 audit pass, error rate 0.0.
- **All 994 G0 length-ratio warnings were false positives** (English→Chinese information density difference) → the main repo has fixed the release logic (G0 warnings are advisory and do not block `released`).
- epubcheck was not run because the container has no jar (known limitation).

### 9.5 Main repo back-port status (2026-09-02)

| Fix | Commit |
|---|---|
| `.gitignore` accidentally harming the build module (P0) | `585f3a2` |
| pandoc cwd / collect_media / translated titles / empty-shell units / HTML images (P4/P5/P8/P9/P10) | `d7a3e46` (including 4 new regression tests) |
| G0 warnings do not block release (P12, aligning with the AGENTS.md G5 contract) | see `git log -- qa/report.py` |
