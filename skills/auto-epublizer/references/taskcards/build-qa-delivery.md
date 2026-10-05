<!-- i18n: source=build-qa-delivery.zh.md sha256=1bdc2ab80c741ca25f717ab6b3f33d7da46007c9266bca315eb83fedc8b742f7 -->
> **English** | [中文](build-qa-delivery.zh.md)

# Task card: build / qa / delivery

Stage reference: `references/build.md`, `references/qa.md`, `references/delivery.md`.

**Scene (restate from disk)**: every unit is `reviewed`; `next_tasks[0].kind` is one of
`build`, `qa`, `delivery`.

**Action** (in order, re-running `status --json` between steps):
- `build`: `auto-epublizer build [--bilingual] [--theme standard|compact|spacious]` → EPUB in `output/`.
- `qa`: `auto-epublizer qa` → epubcheck + unpack audit + `report.json`.
- `delivery`: follow `references/delivery.md` (independent reconciliation + sampling + manual
  checks) and write `reviews/delivery-<ts>.md`.

**Done when**: `next_tasks` is empty (no more entries).

**If it fails**: read the `qa` report error codes; fix `translation/` + `align/` and rebuild —
**never** hand-patch the EPUB (the product is not the source of truth).
