<!-- i18n: source=2026-09-05-scanned-pdf-mineru-first.zh.md sha256=16f9440a81b1ac71b69898ebc107fe08cb8803c08548fa949a86620d1104a650 -->
> **English** | [中文](2026-09-05-scanned-pdf-mineru-first.zh.md)

# Scanned-copy PDF: MinerU first, traditional OCR page-by-page reading as fallback

> Date: 2026-09-05　Source: hands-on probing of the MinerU API (end-to-end measurement of the `/file-urls/batch` flow).
> Status: the MinerU backend has landed (`ingest/mineru.py`); this document preserves the routing-decision basis and the fallback workflow.

## Trigger scenario

The input is a **scanned-copy PDF** (sniffed as `scanned=true`: the proportion of sampled pages with an empty text layer ≥ 60%). The capability boundaries of the two paths (settled by measurement in 2026-09):

| Path | Characters | Line breaks/paragraphs | Illustrations | Tables/formulas |
|---|---|---|---|---|
| MinerU external API (highest priority) | ✓ | ✓ (measured: `## Heading`/blank-line paragraphs) | ✓ (measured: a full-page plate is also extracted as type `chart`) | ✓ (latex/html) |
| Traditional OCR (tesseract/ocrmypdf/rapidocr) | ✓ | **✗** | **✗** | ✗ |
| Traditional OCR + agent page-by-page reading (second choice) | ✓ | ✓ (agent re-breaks paragraphs) | ✓ (agent looks at images to find + crop) | Partial (agent looks at images) |

**Decision order**: `MINERU_API_KEY` configured → go straight to MinerU; not configured → **first ask the user whether they have a key** (this is the highest-quality path for scanned copies); only after confirming there is no key fall back to traditional OCR + page-by-page reading.

## MinerU path (CLI-automatic, no agent intervention needed)

`pdf.backend=auto` + key present + scanned copy → init automatically takes MinerU; the artifacts are fully landed on disk:

- `structured/raw/mineru/content_list.json` + `full.md`: audit-reconciliation ground truth;
- `structured/raw/media/`: illustrations (including full-page plates); `raw/inserts/`: provenance records (`source.method="mineru"`, page/bbox complete);
- The body is split into chapters by the MinerU heading hierarchy (title page = a single instance of the smallest level, automatically skipped).

**Measured pitfall (already handled by the parser; be aware during audit)**: body lines immediately following an illustration are classified by MinerU as `image_footnote` — the CLI already spits the caption/footnote text back into the body paragraph, but when translating, if you find "the sentence immediately after an illustration looks like a caption", first check the original attribution in `raw/mineru/content_list.json` before deciding.

## Traditional OCR + agent page-by-page reading fallback (second-choice workflow)

1. **Read the OCR artifacts**: the `ocr:true` text blocks of `raw/page-NNN.json` — OCR text has no paragraph information, so re-break paragraphs according to semantics;
2. **Look at page images to find illustrations**: `raw/pages/pNNN.png` (the rendered scanned-page images persisted by init), look at the images page by page;
3. **Extract illustrations**: for pages containing illustrations, use the shell (pymupdf) to crop the image by bbox → `raw/media/` + `raw/inserts/<id>.json` (fill in content_desc);
4. **Rewrite structured**: write the body text with re-broken paragraphs + the `![<id>](raw/media/…)` reference back into `structured/<unit>.md`, aligning page by page without losing the original text.

## Reproduce / verify

```python
# Offline regression: tests/test_mineru.py (httpx.MockTransport injection, zero network)
uv run pytest -q tests/test_mineru.py
# Hands-on probe script (runnable only with a key): /tmp/opencode/mineru-probe/probe.py, same-flow shape
```

## Related

- Routing decision table: `references/ingest.md`; the plan: `docs/plans/` (scanned-copy handling update).
- MinerU API contract comments: the module docstring of `src/auto_epublizer/ingest/mineru.py`.
