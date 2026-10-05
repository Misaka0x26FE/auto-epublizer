<!-- i18n: source=translate-unit.zh.md sha256=ab9fea64e52d7d03887aa865f27743d35918a294dd29e7379f11aaccb8fbb877 -->
> **English** | [中文](translate-unit.zh.md)

# Task card: translate-unit

Stage reference: `references/translation.md`.

**Scene (restate from disk)**: `next_tasks[0].kind=translate` with a `unit` id; that unit's
status is `pending` / `split` and it has no registered translation. Read
`analysis/glossary.csv` (or `preprocessing/terms.csv`) for confirmed terms first.

**Action**: read `structured/<unit>`, translate into `translation/<rel_path>`, and write the
sentence-level table `translation/align/<unit>.jsonl` (one sentence per line:
`{"seq","src","tgt","note"}`). Do exactly this one unit — the pointer gives one at a time.

**Done when**: `auto-epublizer import --unit <unit>` succeeds and the unit status advances
(`done_when` is `{"cmd":"import","unit":<unit>}`).

**If it fails**: run `auto-epublizer g0 --unit <unit>`; terminology hits / marker / footnote /
heading conservation are real defects — fix and re-import (see `references/review.md` for G0
fixes).
