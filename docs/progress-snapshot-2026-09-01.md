<!-- i18n: source=progress-snapshot-2026-09-01.zh.md sha256=5aa14da2307f9d072e2f64aa30941bb7abbc2853fcdb8c5dd12778b3d170b685 -->
> **English** | [中文](progress-snapshot-2026-09-01.zh.md)

# Progress snapshot (auto-generated, for resume reference)

> ⚠️ **Historical archive (2026-09-01)**: this file is a progress snapshot from an early
> development stage; its content is outdated — the `agents/` package and the
> `analyze`/`translate`/`review` commands mentioned have been deleted in "remove the internal
> LLM path" (`docs/plans/2026-09-04-remove-internal-llm.md`); now defer to `AGENTS.md` +
> the authoritative `docs/` documents. Kept only for historical traceability.

> Updated 2026-09-01. All current source/tests are not yet git-committed (all `??` untracked).

## Completed

- **convert path (stage A) fully usable**: `init`/`convert`/`status`/`version` + `qa`/`build` commands.
  - ingest (TXT/MD/HTML/DOCX/EPUB/text-based PDF), structure (four-layer classification/running head and footer/page-number stripping),
    build (deterministic EPUB 3 direct write), qa (unpack audit + epubcheck skipped).
- **translation path (stage B) main body implemented and tests passing**:
  - `glossary/`: three-state terminology (seed→candidate→conflict→confirmed), CSV authoritative, conflicts externalized,
    legacy-case `category,source,target,note` format reading, injection filtering (terms_in_text), terminology hit.
  - `review/g0.py`: zero-token validation (alignment completeness/length ratio/sentence-count consistency/marker conservation/footnote note references/
    h1-h6 hierarchy/paragraph 1:1/hyphen repair/typographic error correction/copyright fragment stripping/punctuation normalization).
  - `analysis/`: language/genre detection (heuristics), genre profile style.md, layered understanding (overview/global/
    units/keypoints), terminology seeding, characters.csv, write-back meta.language/genre.
  - `translation/`: slicing (split_paragraph/batch), sentence-level alignment align/, translation service.
  - `review/` (G1–G3): review agent (strict JSON protocol) + evidence gathering + arbitration/shadow revision + convergence state machine.
  - `genre/`: declarative genre profiles (novel/academic/paper/poetry/newspaper) + language guidance.
  - `agents/`: analyzer/translator/reviewer/evidence/arbiter/fixer prompt wrappers.
  - CLI has exposed the `analyze`/`translate`/`review`/`build`/`qa` commands.
- **P0/P1 defects fixed**: update_meta deadlock, convert taking source language as target language, NCX/OPF uid alignment,
  report passed semantics (epubcheck not run does not count as pass), tier options passthrough.
- **Legacy real-case tests**: `tests/fixtures/real_cases/glossary_{fleming,morris}.csv` +
  `tests/test_real_cases.py` (terminology conflict, Han Fuju, marker conservation, hyphenation, typographic errors and other golden vectors).

## Test and quality status

- `uv run pytest -q` → **125 passed**.
- `uv run ruff check .` → **All checks passed**; `ruff format --check .` passes.

## Not yet done

1. **CLI end-to-end real integration**: the `analyze`/`translate`/`review`/`build`/`qa` commands have not yet run a real
   smoke test beyond FakeClient (currently only `convert` has been run end-to-end). Suggest adding a `test_cli.py` or
   manually smoke-testing the command chain.
2. **Bilingual EPUB**: the `--bilingual` parameter is already wired to `build` (produces `-bi.epub`), but the body renders only one language;
   bilingual layout (source/translation side by side) is not implemented.
3. **review G2/G3 evidence tools**: the evidence-gathering agent currently has `context=""`, and the read tools (glossary_term/
   term_occurrences/segment_context/book_context) are not wired in.
4. **usage.json merge idempotency**: `merge_usage` has no dedup yet (retries/resumes must not double-charge is not enforced).
5. **PDF complex scenarios**: OCR (RapidOCR optional extra), scanned-document vision LLM fallback, multi-column/table/footnote special handling
   are still placeholders (`ingest/ocr.py`, `pdf_reader.py` only handle the text layer).
6. **skills/ documentation (S1–S10)** and `THIRD_PARTY_LICENSES.md` are not written.
7. **Packaging and release**: `uv build` is not yet verified; shipping the finished EPUB via Release is not wired.

## Resume notes

- **LSP reporting `pytest`/`httpx`/`fitz`/`pydantic` unresolved is the interpreter not pointing at the venv**, ignore it and defer to
  `uv run`.
- **`import fitz` is a deprecated pymupdf API**, and running it produces a deprecation warning; not blocking for now, change to `import pymupdf` later.
- **FakeClient scripting is strictly FIFO**: each agent `complete`/`complete_json` consumes one entry;
  the `enqueue`/`enqueue_json` order in tests must match the actual call order (analyze additionally calls
  characters, review additionally calls evidence/fixer).
- **ruff rules**: select `E W F I UP B SIM`, ignore `E501 B008`; zip() requires an explicit `strict=`.
- **Architecture-boundary test** `test_architecture_boundaries.py` verifies the dependency direction; new modules must not reversely import
  orchestrator; agents must not import workspace.
- **New unit fields**: `PublicationMeta.genre`; `Unit.meta` stores `rel_path` and `region`
  (written by `set_units`), and translation/analysis/build all rely on it to locate structured files.
- **epubcheck jar missing**: `~/.cache/epubcheck.jar` does not exist on this machine, and QA-related tests are skipped as expected;
  `report.passed` is now False when epubcheck has not run.
