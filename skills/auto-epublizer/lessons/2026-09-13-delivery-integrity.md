<!-- i18n: source=2026-09-13-delivery-integrity.zh.md sha256=5e7d2a1ad1dfca234d4a2210553158d3e490d0c8904618c96a5bebc31fad3031 -->
> **English** | [中文](2026-09-13-delivery-integrity.zh.md)

# Finished-product integrity reconciliation: tool QA all passes yet 38/72 images missing (delivery audit lesson)

> Date: 2026-09-13　Source: manual full inspection before delivery of the《俄国铁路史》Chinese
> translation task (external toolchain, retrospective in this project). Status: **landed** —
> reconciliation automation is in `qa/provenance.py` (E_MEDIA_EPUB_LOST/
> E_FN_EPUB_LOST/E_EPUB_PARA_LOST/E_ALIGN_MD_DRIFT) and
> `docs/plans/2026-09-13-delivery-audit.md`; the mandatory checklist is in `references/delivery.md`.

## Trigger scenario

The translation task flow has ended and tool QA is all green (epubcheck 0 error, structure audit pass),
preparing to deliver/distribute. At this point a **delivery audit must be done once more**: perform an
independent-of-tool-contract "source references ↔ finished product inclusion" reconciliation on the
finished product.

## Criterion (how to judge that this situation may be hit)

The tool validates the contract it "knows", while build consumes some other files — the two can be
out of sync:

| Actual case | Root cause | Why the tool did not catch it |
|---|---|---|
| EPUB contains only 34/72 body-referenced images | the translated body files (translation/body) lost 38 image reference paragraphs during translation | the conservation check looked at the alignment (align, script-backfilled, complete), while build consumed md |
| Part of the footnote content missing | the same batch of md also lost some footnote markers | footnote conservation likewise only looked at align |
| 80 inserts descriptions empty | not filled in at the semantic layer | the tool only gives W-level warnings, easily overlooked |

Hit signals:
- Using `grep` to count the image references / footnote markers in structured does not match the actual
  counts in translation/finished product;
- the text volume of the translated md and align are inconsistent (align longer/shorter);
- after unpacking the finished product, the `OEBPS/media/` file count ≠ the body `<img>` reference count;
- "unpack sampling" was never done before delivery.

## Handling (how to fix)

1. **Independent reconciliation (quantify first)**: separately count the image references, footnote
   markers, paragraph counts of structured/, translation/, and the unpacked finished product — this case
   thereby located the 38 missing images concentrated in ch02/ch04/ch05/ch06/ch07, exactly matching the
   EPUB missing list;
2. **Rebuild the body using align as the authority** (align is the authoritative alignment validated by
   import): rebuild md in order from align's tgt (fixing both image paragraphs and footnotes);
   **back up the original files** before rebuilding (`*_backup_pre_rebuild/`);
3. **Verify the rebuild has no content loss**: compare the overlap ratio of translation probes against
   before the rebuild (95–98% in this case; the unmatched items were all probe false negatives at
   heading/quote paragraph boundaries);
4. **Rebuild + re-QA**: confirm images go from 34 → 72, no broken links, no extras, epubcheck 0 error;
5. **After full re-verification, sync all distribution copies**: byte-check the local finished product,
   cloud drive, and repository against each other; write the fix record into the ISSUES report/delivery record.

## Reproduction/verification

```bash
# Automated reconciliation (already wired in the main repo): error case → qa should block with E_MEDIA_EPUB_LOST
uv run pytest -q tests/test_provenance.py -k "epub_media_lost or silent_media_drop"
uv run pytest -q tests/test_provenance.py -k "epub_footnote_lost or epub_para_lost"
uv run pytest -q tests/test_import.py -k drift
```

Minimal end-to-end reproduction: the workspace translation md references `raw/media/ghost.png` but the
file does not exist → build silently drops it (`events.jsonl` records `media_dropped`) → `qa` reports
`E_MEDIA_EPUB_LOST` and `released=False` (see
`tests/test_provenance.py::test_silent_media_drop_blocks_via_epub_reconciliation`).

## Reusable criteria (cross-task)

- **Finished-product validation must independently do "source references ↔ finished product inclusion"
  reconciliation**, and must not rely only on tool QA — tool all-green does not mean the build input
  and the finished product are consistent;
- md is the build input and align is the validation baseline: the two must be consistent
  (`E_ALIGN_MD_DRIFT` is already automatically reconciled);
- after a fix, **full re-verification + syncing all distribution copies** is mandatory; do not verify
  only the fix point.

## Related

- Plan/design: `docs/plans/2026-09-13-delivery-audit.md` (S1 reconciliation automation + delivery.md);
- Mandatory checklist: `references/delivery.md` (delivery audit steps and record template after qa released);
- Current code: `qa/provenance.py` (finished-product presentation reconciliation),
  `review/g0.py::md_align_drift`,
  `build/__init__.py::collect_media` (drop list + `media_dropped` event).
