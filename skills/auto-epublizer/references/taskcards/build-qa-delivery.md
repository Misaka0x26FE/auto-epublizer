<!-- i18n: source=build-qa-delivery.zh.md sha256=b9c189ba24e8e4b9e6a923b02dcde45191101111770d6dad70d67c7c8ad3f050 -->
> **English** | [中文](build-qa-delivery.zh.md)

# Task card: build / qa / delivery

Stage reference: `references/build.md`, `references/qa.md`, `references/delivery.md`.

**Scene (restate from disk)**: every unit is `reviewed`; `next_tasks[0].kind` is one of
`build`, `qa`, `delivery`.

**Action** (in order, re-running `status --json` between steps):
- `build`: `auto-epublizer build [--theme standard|compact|spacious]` → EPUB in `output/`.
- `qa`: `auto-epublizer qa` → epubcheck + unpack audit + independent registered-notes gate + `report.json`.
- `delivery`: follow `references/delivery.md` (independent content/resource/registration/link/backlink reconciliation + sampling + manual checks), write `reviews/delivery-<ts>.md`, and byte-check every distribution copy. A desktop is not required: record "reader not tested" when unavailable; reader GUI checks are conditional compatibility sampling and do not replace offline acceptance or promise popups.

**Done when**: `next_tasks` is empty, mandatory offline acceptance and the delivery record are complete, and distribution copies are byte-verified. An empty machine pointer alone is not delivery evidence.

**If it fails**: read the `qa` report error codes; fix `translation/` + `align/` and rebuild —
**never** hand-patch the EPUB (the product is not the source of truth).
