<!-- i18n: source=build-qa-delivery.zh.md sha256=4f1a3c4fbbeecb6bea47975fbe8c00443e5169c2e9f2fa83fd1f22a96ab1daf9 -->
> **English** | [中文](build-qa-delivery.zh.md)

# Task card: build / qa / delivery

Stage reference: `references/build.md`, `references/qa.md`, `references/delivery.md`.

**Scene (restate from disk)**: every unit is `reviewed`; `next_tasks[0].kind` is one of
`build`, `qa`, `delivery`.

**Action** (in order, re-running `status --json` between steps):
- Cover (before `build`): read `cover.effective` from `status --json`
  - `source` → a source cover exists, do nothing;
  - `generated` → the generated cover is ready, just build;
  - `null` → this book has no cover: follow `references/cover.md` to decide, write
    `preprocessing/cover-spec.json` when you have evidence for subtitle/original
    title/credits, run `auto-epublizer cover --workspace <ws>`, then build.
- `build`: `auto-epublizer build [--theme standard|compact|spacious]` → EPUB in `output/`.
- `qa`: `auto-epublizer qa` → epubcheck + unpack audit + independent registered-notes gate + `report.json`.
- `delivery`: follow `references/delivery.md` (independent content/resource/registration/link/backlink reconciliation + sampling + manual checks), write `reviews/delivery-<ts>.md`, and byte-check every distribution copy. A desktop is not required: record "reader not tested" when unavailable; reader GUI checks are conditional compatibility sampling and do not replace offline acceptance or promise popups.
- If delivering a print PDF: `pdf --strict` → `pdf-verify --pdf <out> --json`; record the PDF and source EPUB hashes in the delivery record. PDF/manifest stay outside the EPUB QA digest.

**Done when**: `next_tasks` is empty, mandatory offline acceptance and the delivery record are complete, and distribution copies are byte-verified. An empty machine pointer alone is not delivery evidence.

**If it fails**: read the `qa` report error codes; fix `translation/` + `align/` and rebuild —
**never** hand-patch the EPUB (the product is not the source of truth).
