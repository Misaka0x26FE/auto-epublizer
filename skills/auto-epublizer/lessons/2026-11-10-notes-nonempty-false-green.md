<!-- i18n: source=2026-11-10-notes-nonempty-false-green.zh.md sha256=c3404725b97529eb7f69d8d3eb8dafd1fd67d3f2aeef4f39ebe4ef2c1cc3f973 -->
> **English** | [中文](2026-11-10-notes-nonempty-false-green.zh.md)

# The "non-empty means translated" false green in the notes layer

## Criterion (when this applies)

- A book has collected notes (`structured/notes.json` + `translation/notes.json`), and `qa`
  reports `released=true/ok`, `notes_findings` empty, `notes_missing` empty.
- Yet the notes in the product (or in `translation/notes.json`) are **still source language**:
  entirely foreign, or byte-identical to `source_markdown`.
- A quick human read shows "the notes were never translated" while every gate is green —
  this is **not a missed `qa` run, the criterion itself never looks at language**.

Machine triage (seconds):

```python
# target_markdown is non-empty but contains zero Han characters (target is zh*)
b = (note.target_markdown or "").strip()
CJK = re.search(r"[\u4e00-\u9fff]", b)
suspect = bool(b) and not CJK
```

## Handling

1. **Locate the criterion first; do not start by editing translations.** The product notes gate
   only reconciles *registered text ↔ rendered text*: a non-empty `target_markdown` is taken as
   "translated", so "register foreign text, render foreign text" matches on both sides → pass.

   ```text
   translation/notes.json target_markdown
     → non-empty → expected = that string → compare with product aside → equal → pass   ← the gap
     → empty     → fall back to source_markdown (source fallback = semantically untranslated)
   ```

2. **Make the language check a separate hard gate**, parallel to the content reconciliation
   (do not fold it into the same comparison):

   - `target_markdown` normalised == `source_markdown` → untranslated;
   - target language `zh*` and zero Han characters after normalisation → untranslated;
   - legitimate exceptions (pure bibliographic entries, Latin book titles, URLs/DOIs, whole
     foreign quotations) go through **per-item exemptions with evidence**, still reported
     (`blocking=false`); never exempt a whole unit.

3. **Run a whole-library census** (statistics only, no edits): per book, list
   "no-Han notes / total notes". In practice any book with a non-zero ratio almost always has a
   whole chapter layer or whole block layer untranslated; sampling the first 20 notes per unit
   settles it.

4. **Acceptance**: a synthetic fixture with three notes (real translation / source copied /
   pure bibliography) asserting ① only the real translation and the exempt bibliography pass;
   ② the copied-source note raises `E_NOTES_UNTRANSLATED`; ③ the exempt note still appears in
   the report (it must not vanish).

## Why this is worth more than "one more review pass"

- **The false green has the widest blast radius**: notes are the dominant cost of an academic
  translation (96–2,215 notes per book measured), and they are routinely deferred as
  "bibliography, low value". Once the gate ignores language, the book ships with
  "structure intact, epubcheck 0 errors, provenance 1.0" — the most convincing possible artefact.
- **It is asymmetric with the body language gate**: the body has
  "normalised source == normalised target → hard defect" (`language_identical` in
  `auto_translator/review/g0.py`); the notes layer has no counterpart. Whenever you add a gate,
  ask the same question about the other path.

## Reproduce / verify

```bash
# 1) Read-only census: count no-Han notes per book
python3 - <<'PY'
import json, glob, re
CJK = re.compile(r"[\u4e00-\u9fff]")
for p in sorted(glob.glob("workspaces/*/translation/notes.json")):
    slug = p.split("/")[0]
    notes = json.load(open(p)).get("notes") or []
    if not notes:
        continue
    bad = sum(1 for n in notes
              if (n.get("target_markdown") or "").strip()
              and not CJK.search(n["target_markdown"]))
    print(f"{slug}: {bad}/{len(notes)}")
PY

# 2) Minimal per-note reproduction (criterion level): write the same source-language text into
#    target_markdown. Expected: a new hard gate raises E_NOTES_UNTRANSLATED; today it reports nothing.

# 3) Negative test: a real translation and an exempt bibliographic entry must not be flagged.
```

- Gate location: `src/auto_epublizer/qa/notes_audit.py` (product notes gate);
  body-side counterpart: `auto_translator/review/g0.py::language_identical`.
- Scale analysis: `docs/plans/2026-11-10-field-archive-gap-analysis.md` §2 P0-1.
