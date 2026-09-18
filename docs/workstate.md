<!-- i18n: source=workstate.zh.md sha256=aae4c6ac187aa54a81d07d763c0d4dd4737a79be54981bb63e3f17e2f6c190d0 -->
> **English** | [中文](workstate.zh.md)

# Work-state handover (workstate)

> Purpose: **session-compaction handover**. This file records the status of the task that
> lands the three preprocessing v2 plans (A/B/C).
> **As of 2026-09-04 this task is fully complete** (S0–S5 all committed and pushed), kept
> for traceability and reference for follow-up tasks.
> The authoritative plan is `docs/plans/preprocessing-plan-v2.md`; the Plan C spec is
> `docs/pdf-content-spec.md`.
>
> ⚠️ **Follow-up**: on 2026-09-04 "remove the internal LLM path" was also completed (the
> single-LLM principle, `docs/plans/2026-09-04-remove-internal-llm.md`); the
> `llm_vision_model`/`usage.json`/`analyze` etc. mentioned in this file are outdated — defer
> to that plan.
> The OCR-priority decision in §2 has been superseded by the 2026-09-05 "MinerU external API
> first" decision (`lessons/2026-09-05-scanned-pdf-mineru-first.md`); the statement in §6
> that "qa/report.py needs no new fields" is also outdated (`QaResult` already contains
> provenance fields such as `inserts_missing_files`).

## 1. Goal and route

Develop `auto-epublizer` (a Python three-package monorepo). Current task: **land all three
new plans of the preprocessing v2 plan (A OCR routing / B web search / C PDF content
extraction)**. Stages:

- **S0** write `docs/pdf-content-spec.md` (Plan C spec) — ✅ **done**
- **S1** expand doctor probes + facts five-tier routing + skills routing table (Plan A/B) — ✅ **done** (42eef38)
- **S2** C-P0: bookmark chaptering + embedded image extraction + inserts base + multi-column ordering — ✅ **done** (a1b7306)
- **S3** C-P1: illustration routing + dual table paths + formula detection marking — ✅ **done** (d84fbcd)
- **S4** C-P2: provenance inserts audit + release-gate wiring — ✅ **done** (d14e6f4)
- **S5** documentation sync (AGENTS/README/SKILL/workflow/postprocessing-spec/spec write-back) — ✅ **done**

**Each stage: regression tests + ruff + one commit per stage**. Commit messages use
Conventional Commits; stage only the files of this stage.

## 2. Settled decisions (user has decided; do not ask again)

- OCR backend priority is fixed: **traditional OCR (tesseract/ocrmypdf) → rapidocr → vision LLM/multimodal → MinerU API → ask the user**.
- Illustration "full page vs crop" criterion: **layout criterion primary + genre weighting** (the agent overrides thresholds in plan.md; the CLI only emits constants).
- Formula → LaTeX: **agent hand-writing only** (no FormulaAgent/LLM calls); the CLI only detects + marks `type=formula` + leaves `latex:null`.
- Delivery cadence: **spec first, then implementation** (spec already written).
- Purpose of preprocessing = **capability-boundary confirmation**: the agent's own abilities / agent model / OS environment / external API boundaries / workload of files to process.
- `.progress.json`: make the documentation honest (reserved, not persisted); resume = unit-level skip via publication.json.
- **marker-pdf / MinerU local engines are not introduced** (heavy, offline-unfriendly); MinerU is only an optional external API (`MINERU_API_KEY`).

## 3. Current git state (key! uncommitted)

```
 M src/auto_epublizer/doctor.py             # S1: add ocrmypdf probe + probe_mineru + probe_network + summary adds search
 M src/auto_epublizer/preprocess/facts.py   # S1: add _ocr_routing five-tier routing
?? docs/pdf-content-spec.md                 # S0 artifact (brand-new file)
```

- **207 tests all green** (run on the current tree with changes); ruff/format not yet run.
- These two changes have **no regression-test coverage yet**; tests must be added before S1 is complete.
- Do not `git stash pop` and then commit — continue directly with the current changes.

## 4. Completed (S1 code half)

### doctor.py (`src/auto_epublizer/doctor.py`)
- `_probe_tool` adds `ocrmypdf`.
- New `probe_mineru()`: reads the `MINERU_API_KEY` environment variable (local read-only, no network).
- New `probe_network(timeout=5.0)`: `httpx.get` probes baidu/github; either being reachable means online; called only under `--ping`.
- `collect_capabilities` adds `probe_mineru()`; `if ping: caps.append(probe_network())`.
- `capabilities_summary` adds `"search": None` (parallel to multimodal, agent self-reported).

### facts.py (`src/auto_epublizer/preprocess/facts.py`)
- New `_ocr_routing(capabilities) -> list[str]`: five-tier hints (tesseract/ocrmypdf → rapidocr → llm_vision_model → mineru → ask the user).
- The scanned branch of `_route_suggestions` now calls `_ocr_routing`.
- `render_facts_md` **unchanged** (still missing the search self-report line + routing-hint rendering; to be added).

## 5. Next steps (remaining S1 + S2)

### S1 wrap-up
1. `render_facts_md`: add to the capabilities snapshot area the line `search: awaiting agent self-report (whether a web search tool is available)`.
2. `skills/auto-epublizer/references/ingest.md`: change the capability self-check and routing table to five tiers (see the §2 decisions).
3. `skills/auto-epublizer/references/preprocessing.md`: add the `capabilities.md` artifact (the five dimensions the agent self-reports that the CLI cannot probe: multimodal/search/model ID/context/external API tools) + a "background-knowledge filling" routing subsection
   (search available → `references/web/`, not available → ask the user → `references/user/`).
4. Tests:
   - `tests/test_doctor.py`: assert the new probes exist (ocrmypdf/mineru/network); `search is None`;
     `probe_network` uses monkeypatch to control httpx (offline-deterministic).
   - `tests/test_preprocess.py`: `_ocr_routing` five-tier priority (fake caps dict).
5. `uv run pytest -q` + `ruff check .` + `ruff format --check .` → **commit S1**.

### S2 (C-P0, changes concentrated in ingest)
- `src/auto_epublizer/ingest/pdf_reader.py`:
  - `aggregate_pdf_chapters` adds a `toc` parameter: `doc.get_toc()` (simple, `[[level,title,page]]`) takes priority for chaptering, with level-1 entries as boundaries; falls back to the font-size heuristic (existing logic) when there is no valid toc. Boundary handling: pages before the first toc entry → frontmatter
    (kind=frontmatter); after the last entry → backmatter. page_range meta.
  - `read_pdf` passes in `doc.get_toc()`; image/table/formula extraction is wired up (see below).
- New `src/auto_epublizer/ingest/inserts.py`: `InsertSource`/`InsertRecord` pydantic (id/type/source{page,bbox,xref,method}/file/markdown/content_desc/latex)
  + `write_inserts(raw_dir, records)` → `raw/inserts/<id>.json` + `index.jsonl` (sorted by id) + `read_inserts()`.
- New `src/auto_epublizer/ingest/images.py`: constants (`FULL_PAGE_AREA_RATIO=0.70`/`TEXT_COVERAGE_MAX=0.15`/`MIN_IMAGE_SIZE=32`/`MAX_IMAGE_DIM=1800`);
  embedded image extraction `page.get_images(full=True)` + `page.get_image_rects(xref)` + `doc.extract_image(xref)` → `raw/media/pNNN-imgKK.<ext>`.
- New `src/auto_epublizer/ingest/reading_order.py`: pure function `sort_reading_order(blocks)` (see spec §6).
- md representation (spec §2.3): image `![<id>](raw/media/<file>)`; table md inline; formula `$$original text$$`.
- `page-NNN.json` blocks extend the `image`/`table`/`formula` type.

### S3 (C-P1)
- Illustration routing (full page get_pixmap vs embedded extract_image vs <32px ignored).
- `ingest/tables.py`: `page.find_tables()` text-only → md; with images → region-cropped image.
- Formula detection (three features: symbols/fonts/standalone line) + mark `type=formula`.

### S4 (C-P2)
- `qa/provenance.py` `audit_provenance`: reads `raw/inserts/index.jsonl` (when present) and audits:
  E_INSERT_MISSING_FILE / E_INSERT_BAD_SOURCE / W_INSERT_NO_DESC / W_INSERT_NO_LATEX;
  `ProvenanceResult` adds `inserts_total/inserts_missing_files/inserts_no_desc/inserts_no_latex`;
  `prov_ok` includes `inserts_missing_files == 0` (qa/report.py needs no field changes, the prov dict automatically enters findings).
- Image optimization: rendering classes control dpi so the longest edge ≤1800 (pure fitz); embedded images keep original bytes (Pillow reserved as an extension point, **no dependency introduced**).

## 6. Key code facts (saves re-reading the source)

- Architecture: `auto_common` (config/llm/workspace) ← `auto_translator` ← `auto_epublizer`, the dependency direction is fixed by
  `tests/test_architecture_boundaries.py`. The orchestrator only assembles and does not directly call domain functions.
- **media pipeline**: pandoc extracts media to `structured/raw/media/`; build's `collect_media` parses md image references
  (prefix stripping + basename fallback) → `media/` inside the EPUB. PDF images are written to `raw/media/` + md references `raw/media/...`, auto-compatible,
  and provenance `_img_refs` also consumes the same format.
- `read_pdf(path, raw_dir=None, ocr_backend=None, page_dpi=150)`; in `load_document`,
  `raw_dir = store.structured_dir/"raw"`. OCR has only the `OcrBackend` Protocol + RapidOcrBackend + FakeOcrBackend.
- `SourceSegment.meta` is a free dict (already uses source_page/source_bbox/source_font_size); the segment's `source` text goes directly into md
  (`_render_markdown`: heading→`##`, text→paragraph).
- classify_units/clean_unit reprocess unit kind/title; the aggregate's kind can be overridden.
- qa report.py maps specific keys from the provenance dict (coverage/units_missing/media_lost/toc_flat/findings) into report.json;
  `prov_ok` = coverage≈1 and no missing units/media/toc not flat. New E_INSERT_* findings enter findings only, without changing the report schema.

## 7. Environment and verification

- Verification commands: `uv run pytest -q` (baseline 207), `uv run ruff check .`, `uv run ruff format --check .`.
- **LSP reporting pytest/fitz/pydantic/typer/httpx "unresolved" is a false positive from the venv not being pointed at**; defer to `uv run`;
  the `fitz` deprecation warning is known. **Do not change imports because of LSP errors**.
- Install packages with `uv` (pip forbidden); tests write `tempfile` fixtures and do not depend on real books.
- Construct PDFs in tests with fitz (`pdf.new_page()` + `page.insert_text(...)` + `page.insert_image(...)`);
  to make an image just `insert_image` directly (needs real png bytes; a 1x1 or small png constant works).

## 8. Known issues / notes

- `render_facts_md` does not yet render the `search` self-report line → fix in S1.
- `_ocr_routing` only triggers for `scanned`; mineru/network for non-scanned PDFs are bonus items and currently silent (an empty branch is reserved).
- The existing C9 test of `aggregate_pdf_chapters` depends on the font-size/keyword heuristic — **adding the toc parameter must be backward compatible** (behavior unchanged when there is no toc),
  otherwise the existing test_ingest will fail.
- inserts id naming `p{page:03d}-{img|tbl|fml}{nn:02d}`; index.jsonl sorted by id (deterministic).
- The E_INSERT_BAD_SOURCE check in spec §9 requires bbox to be 4 finite numbers.
