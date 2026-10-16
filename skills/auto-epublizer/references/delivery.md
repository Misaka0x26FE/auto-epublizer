<!-- i18n: source=delivery.zh.md sha256=9c3f52905b36fa164e5cfee355d7060887793c986038a40cc1f107f4ef36dd20 -->
> **English** | [中文](delivery.zh.md)

# Delivery (delivery audit: mandatory full validation after qa and before delivery)

> **Positioning**: `qa` passing only means all **known contracts** are green. This
> checklist requires you to independently perform a full
> "source citation ↔ product inclusion" reconciliation and manual spot-check before
> delivery, preventing "gaps the tools did not catch" from reaching the product. Real
> case: in the *History of Russian Railways* translation task the tool QA fully passed,
> but the product included only 34 of 72 cited images — the root cause was that the
> translation body dropped image segments while tool conservation only checked the
> alignment (align).

## When to execute

After `qa` returns `released=True` and before handing the product to the user/distribution.
**Mandatory**, cannot be skipped (small books may compress the sampling volume of steps
2–4, but not omit it).

## 0. Prerequisite: refresh facts

```bash
auto-epublizer preprocess          # idempotently refresh facts (reconcile against current artifacts, not an old snapshot)
auto-epublizer qa                  # confirm released=True; released_reason=ok
```

## 1. Tool reconciliation review (read report.json)

| Field | Requirement |
|---|---|
| `released` / `released_reason` | True / ok |
| `epubcheck.ran` / `epubcheck.returncode` / `epubcheck.errors` | true / actual process value 0 / 0 |
| `epub_coverage` | ≈ 1.0 (product paragraph probe; null when there is no probe) |
| `epub_media_missing` / `epub_footnotes_missing` | 0 |
| `align_md_drift` | 0 (translation body consistent with alignment) |
| `g0_terminology_open` / `g0_structure_open` | 0 / 0 |
| `glossary_conflicts_open` / `catalog_unresolved_open` | 0 / 0 |
| `W_INSERT_NO_DESC` / `W_REPAIR_UNRESOLVED` / `W_REPAIR_STALE_UNIT` / `W_DELIVERY_AUDIT_MISSING` | review and handle item by item (see §4) |

Error-level provenance findings (`provenance_findings`) must be cleared; warnings are
interpreted item by item.

A jar's presence, Java process startup, or a legacy `ran` field cannot prove EPUBCheck passed. Keep the complete distribution's `lib` beside the jar; headless Java is sufficient, with no GUI required. `report.epubcheck.returncode` must record the actual process exit value, or `null` when not executed; never guess 0 for an unknown result. Process failure or FATAL must not release as zero errors. Legacy released reports missing the field or reliable success evidence do not establish current compliance: `status` marks them stale; rerun `qa`, never hand-edit the old `released` value. An existing `digest_missing` reason takes priority; otherwise the stale reason for such legacy reports is `epubcheck_unverified`.

Standard EPUB note acceptance is mandatory and independent of a desktop: verify current registration binding, `noteref`/`footnote`/`endnote` semantics, complete note content, every reference target and backlink, and packaged resource identity through the independent notes gate and offline ZIP/XML reconciliation. Do not replace this with legacy marker counts or a reader screenshot; a registered empty note graph also requires zero-to-zero reconciliation.

## 2. Unpack sampling (first/middle/last + high-risk chapters: image/table/footnote/multilingual dense)

First unpack the product:

```bash
mkdir -p /tmp/epub-check && cd /tmp/epub-check && unzip -o <slug>.epub
```

- **Body probe**: pick 3–5 representative sentences from the translation and grep each
  one in `OEBPS/*.xhtml` for a hit (the tool already reconciles everything; this step is
  a **second safeguard** against the tool itself being misaligned);
- **Images**: confirm the file count in `OEBPS/media/` = the citation count (the tool
  already checked); then **look at 2–3 images** (multimodal) to confirm the image content
  matches the surrounding position — preventing "the image is there but misplaced/wrong";
- **Notes**: sample up to 3 available references (all if fewer) against the source/translation evidence and complete packaged note **content**, not merely the existence of a backlink; inspect resolvable round-trip links and readable note areas offline;
- **TOC**: nav entry count = unit count, and hierarchy consistent with the original
  book's TOC (against the source TOC in facts).

## 3. Manual checks

- Cover: `cover-image` points to the correct image, no cropping anomaly;
- Metadata: `dc:title/creator/translator/language` vs the copyright page (already written
  back via `meta` during preprocessing; recheck here);
- landmarks: frontmatter/bodymatter/backmatter point to existing documents.

## 4. inserts description and open items

- An empty `content_desc` in `raw/inserts/<id>.json` (`W_INSERT_NO_DESC`) affects the EPUB
  image alt: fill in item by item, or state "explicitly accepted" and the reason in the
  delivery record (decorative images are acceptable);
- `W_REPAIR_UNRESOLVED` (unresolved semantic-repair fixes) interpreted item by item: fix
  what can be fixed; record genuinely doubtful ones in the delivery record.
- `W_REPAIR_STALE_UNIT` (`repairs.jsonl` rows for units removed by a structure rebuild):
  historical `done` rows are harmless; re-attach `unresolved` rows to a surviving unit.

## 5. Reader compatibility spot-check (conditional, non-blocking)

When a desktop and target reader are available, use Foliate / Apple Books / a phone reader to inspect first/middle/last: TOC targets, note navigation and return position, image rendering, and any popup behavior. Record reader/version and actual observations. Reader implementation and user settings determine popups; standard EPUB semantics do not guarantee them in every reader.

Without a desktop/reader, record **reader not tested** with the reason; do not block standard delivery or claim GUI compatibility. The mandatory offline content, links/backlinks, resources, registration, notes gate, epubcheck, and independent reconciliation checks still apply.

## 6. Repair loop (when a defect is found)

```text
defect found → locate (source text structured / translation translation / build)
  → repair (text defects go through semantic repair repairs.jsonl for traceability; boundary/structure goes through restructure)
  → import (validate + advance state) → g0 → build → qa → return to step 0 of this checklist and rerun
```

- After repairing the translation body you must re-`import` (an md↔align inconsistency
  blocks it);
- After a repair you must **rerun the entire reconciliation + sampling**, not only verify
  the one place that was fixed.

## 7. Delivery record (mandatory)

Write `reviews/delivery-<YYYYMMDD-HHMMSS>.md` (once this file exists, qa no longer warns
`W_DELIVERY_AUDIT_MISSING`):

```markdown
# Delivery audit <YYYYMMDD-HHMMSS>

- Audit target: <slug>.epub (qa released, reason=ok); facts refresh time …
- Tool reconciliation: epub_coverage=…; epub_media_missing=0; epub_footnotes_missing=0; align_md_drift=0
- Sampled chapters: <list of first/middle/last/high-risk chapters>
- [ ] Body probe N/N hits
- [ ] Image semantic spot-check M images correct (list them)
- [ ] Note content spot-check: up to 3 available references correct (or no notes, zero-to-zero verified)
- [ ] TOC/cover/metadata check (conclusion)
- [ ] inserts desc empty-value handling: fill in X / explicitly accept Y (reason)
- Mandatory offline notes gate: registration/semantics/content/links/backlinks/resources (result)
- Reader compatibility: <reader/version and observed behavior, or "reader not tested: no desktop/reader">
- Findings and handling: (defect → root cause → fix → re-verify; or "none")
- Repair loop rounds: 0 (or N)
- Artifact list and sync: local/backup/cloud/repository (byte-check result)
```

## 8. Artifact sync and distribution

Per `references/publishing.md`: product checklist + byte verification of distributed
copies (all copies updated: local `output/`, backup, cloud/repository, etc.); update the
distribution notes and version record.

## 9. Distilling experience

**Reusable criteria** found during delivery (not just this book's special case) go into
`lessons/` (the three-part criterion/handling/verification form) and are cross-referenced
in the delivery record; plan-level verification context is written back to the
corresponding `docs/plans/` document.

## Common misconceptions

- **Trusting only tool QA**: tools validate the contracts they know (align conservation /
  structural audit); the translation body that build actually consumes and the product
  inclusion must be independently reconciled (this round is now automated, sampling is the
  second safeguard);
- **Treating facts as live**: facts is a snapshot; after rebuild/re-split/repair, first
  `preprocess` to refresh before reconciling;
- **Verifying only the fixed point**: a repair introduces new inconsistencies
  (state/artifacts/distribution), so a full re-verification is required.
