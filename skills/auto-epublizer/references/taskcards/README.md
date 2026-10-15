<!-- i18n: source=README.zh.md sha256=08ddfad50ad89f353b6a6332a373209c870cd1f944bdf408aa1b979efd743f61 -->
> **English** | [中文](README.zh.md)

# Task cards (weak-model path)

The intended loop for a weaker model: read `references/workflow.md` once, then drive the
work from the machine pointer returned by `status --json`.

1. run `auto-epublizer status --json` and take `next_tasks[0]`;
2. open the card matching that `kind` (table below) and do it;
3. re-run `status --json`, repeat until `next_tasks` is empty.

| `next_tasks[0].kind` | Card |
|---|---|
| `preprocess` | [preprocess.md](preprocess.md) |
| `write_preprocessing` | [write-preprocessing.md](write-preprocessing.md) |
| `repair` | [repair.md](repair.md) |
| `analyze` | [analyze.md](analyze.md) |
| `translate` | [translate-unit.md](translate-unit.md) |
| `import` | [import-unit.md](import-unit.md) |
| `review` | [review-unit.md](review-unit.md) |
| `notes_verify` / `notes_register` | [notes.md](notes.md) |
| `build` / `qa` / `delivery` | [build-qa-delivery.md](build-qa-delivery.md) |

Each card is self-contained (one screen): restate the scene → action → done-when → failure
handling. The stage-level references in `references/` remain the full guide; task cards are
the minimal path for a weak model.
