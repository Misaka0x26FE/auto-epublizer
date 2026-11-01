<!-- i18n: source=2026-11-01-pdf-toc-anchors-and-artifact-manifest.zh.md sha256=e2b560bb4fcac56f9ed998b5c59e0c412d619d404e2556f6503332873fb77997 -->
> **English** | [中文](2026-11-01-pdf-toc-anchors-and-artifact-manifest.zh.md)

# PDF TOC anchors, unique markers and derived-artifact manifest

## Criterion (when this applies)

- A print PDF's TOC still shows source page numbers, or bookmarks jump to the chapter start
  while the `href#fragment` target is later in that chapter.
- A source paragraph literally contains text that looks like a locator marker
  (`AEPMARK0001`), and that text disappears from the product.
- A failed Chromium/post-processing run replaces a previously approved PDF, or a successful
  render leaves no way to tell which EPUB bytes and parameters produced it.
- The OPF carries publisher/date/rights but the PDF's Info/XMP loses them or truncates rights.

## Handling

1. **Identity, not title text.** Map TOC rows and bookmarks by the full package-internal
   `href#fragment`; inject a locator immediately after the real `id` element. Do not search a
   page-wide title substring and do not fall back to the section start page when the fragment
   is missing — report an error instead.
2. **Rewrite only located rows.** A located row gets the final PDF page. An unlocated row keeps
   its source number but is explicitly labelled `[original page, unlocated]` in the product and
   produces an error; `--strict` blocks release. Different TOC structures (paragraphs, `<li>`,
   author emphasis, roman numerals) need their own fixtures.
3. **Three-pass convergence.** Render, measure anchors, rewrite the TOC, render again; compare
   page maps and stop when stable. More than three passes or an oscillation raises
   `E_PDF_TOC_UNSTABLE` and leaves the previous PDF untouched.
4. **Unique marker prefix.** Derive the locator prefix from the EPUB content hash and append
   `X` until it does not occur in any package text. Cleanup then removes only this run's exact
   marker set, so literal source text survives.
5. **Publish after post-processing.** Do TOC rewrite, bookmark mapping, folio stamping and
   metadata inside a staged copy; copy to a same-directory temporary file, `fsync`, then
   `os.replace`. A strict/DIAGNOSTIC or post-processing failure must keep the old bytes.
6. **Manifest the derivative.** Write `<pdf>.manifest.json` with source EPUB/PDF sha256 and byte
   counts, page count, actual parameters, Info/XMP read-back and TOC/diagnostics summaries.
   `pdf-verify` recomputes them; the PDF and manifest remain outside the EPUB
   `artifacts_digest`, so a stale report is detected by manifest reconciliation, not by
   invalidating the EPUB QA report.

## Reproduction / verification

- `tests/test_pdftoc.py`: cross-block titles, trailing chapter numbers, explicit link identity,
  equal-count wrong order, missing/duplicate anchors, escaping, URL identity.
- `tests/test_pdfexport.py`: fragment bookmarks use the final anchor page; marker-like source
  text survives; unstable page maps preserve the old PDF; TOC/Info/XMP read-back and manifest
  tamper detection; `pdf-verify` CLI.
- Real check: render a synthetic A5 EPUB with a TOC and 13-column table through Chromium, open
  the PDF with PyMuPDF, compare `doc.get_toc()` and TOC text against actual anchor pages, and
  `pdf-verify --pdf <out>`.
