<!-- i18n: source=2026-10-27-scanned-academic-false-green.zh.md sha256=ff1a22d87f726d04cb7981847376b7f468b8728f62aca3fc1d951f66e50f6237 -->
> **English** | [中文](2026-10-27-scanned-academic-false-green.zh.md)

# Scanned academic books: mechanical green is not content acceptance

## Trigger and status

This lesson comes from translating, reviewing, rebuilding a two-column people list,
and versioning a 21-unit scanned academic book. No manuscript or user materials are
included. See the complete matrix in
[field report #69](https://github.com/Misaka0x26FE/auto-epublizer/issues/69) and the
review-shadowing defect in [#68](https://github.com/Misaka0x26FE/auto-epublizer/issues/68).
The inspected baseline is main `a3aee9e`.

**Status: lessons and proposals submitted, not code defects fixed or the original book
semantically reaccepted.** Distinguish existing capabilities, workarounds, operator
failures, and proposed development.

## Criteria and handling matrix

| # | Signal / responsibility boundary | Handling and verification |
|---|---|---|
| 1 | Default import skips reviewed/built; zero failures is not revalidation | Existing `import --force` is the post-delivery registration entry (#13); inspect validation/rollback state, then build/qa |
| 2 | Historical first import reported zero failures despite hard terminology findings | No current-version minimal reproduction yet; capture version, original command and JSON before claiming a regression |
| 3 | English words remain inside Chinese sentences without triggering identical-text detection | Scan candidates across body, furniture and semantic notes; agent adjudicates names, abbreviations, bibliography and code. #54 is not a mixed-language detector |
| 4 | Thousands of length advisories obscure real omissions | Group/rank by unit and consider language/style (#39/#54); preserve real content, never pad prose to silence warnings |
| 5 | OCR garbage, broken words, cross-page sentences or missing paragraphs | Read page images and neighbours, restore structured/translation/align from evidence and log repairs (#14/#38/#58); deleting fragments or adding punctuation/ellipses does not restore missing text |
| 6 | Two-column people list interleaves names, offices and terms | Preserve page/bbox/column evidence; inventory entries first, then one person per paragraph; verify names, life dates, offices, terms, categories and reading order (#58) |
| 7 | Local script zips blocks positionally and pads missing tail blocks | Stop rather than equalize counts; freeze an entry inventory and explicitly establish correspondence. Equal counts and source fidelity do not prove semantic alignment. This script is not an upstream feature |
| 8 | Registered notes equal aside counts without a full source inventory | Inventory source pages by chapter; independently verify bare-number candidates, cross-page tails and gaps. The observed 615 registrations do not prove the source total (#37/#46/#58) |
| 9 | Notes distributed proportionally by length, copied continuations or generic filler | An operator failure, not a solution; rebuild each source note_id→complete target with source evidence, leaving unverified entries unresolved (#57) |
| 10 | Quotes, spaces, measures and ambiguous OCR alter note-number detection | Verify original pages and Notes, preserve stable ref_id; never alter numbers/punctuation to satisfy regexes (#22/#29/#34) |
| 11 | Formula candidates blanket-dismissed as OCR noise with placeholder LaTeX | Inspect every bbox; transcribe real formulas, individually evidence false positives, keep unverified cases open. Nonempty descriptions prove only nonempty fields |
| 12 | New local review clears older global findings | Current path ordering lacks inheritance (#68); retain history and individually document prior findings and closure evidence; local clean cannot replace global review |
| 13 | JPX cover becomes octet-stream, OPF-012/MED-003; filename used as caption | Observed workaround: convert real bytes to JPEG and update references, not just extension; describe content in captions, rebuild/epubcheck and inspect cover; automatic normalization is not delivered here |
| 14 | Title echo excluded by align tolerance but duplicated in md | Only after confirming furniture, remove duplicate target prose and retain the align row expected by current title tolerance; verify drift/product. Do not delete all opening paragraphs or hide them as indented headings |
| 15 | CJK spaces, stray quotes and unclosed paragraphs | Distinguish publication data/index from broken prose, verify individually against source; pair quotes, do not globally append punctuation or delete quotes (#38) |
| 16 | Local packer missing zhconv; wrong batch and duplicate version keys | Ad-hoc installation is only a workaround; propose declared dependencies/preflight and reject duplicate batch keys or inconsistent versions. These are work-root scripts, not claims about upstream files (#47) |
| 17 | Local commit/copy exists but tag/push unverified | Keep old copies immutable; verify current report freshness, each SHA256, version/manifest/tag identity and remote state. Successful copying or skipping an existing directory is not acceptance |
| 18 | Counts/few grep probes presented as full semantic verification | Record pass/fail/unknown/manual, actual scope and untested readers; never pre-check items or report unperformed work as complete (#57) |

## Reproduction and verification

Run this entirely synthetic example with `uv run python` in the repository environment;
it needs neither network nor manuscripts. It characterizes current boundaries, **not
a recommendation to rewrite prose to satisfy detectors**.

```python
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from auto_epublizer.qa.artifacts import latest_review_result_path
from auto_translator.review.g0 import footnote_numbers, language_identical

assert not language_identical("The committee continued its work.", "委员会 continued 工作。")
assert footnote_numbers("“示例”40，接下文") == set()
assert footnote_numbers("“示例”。40 接下文") == {40}
assert footnote_numbers("句末。65 年龄") == set()
assert footnote_numbers("句末。65 就年龄而言") == {65}

with TemporaryDirectory() as d:
    root = Path(d)
    for name, result in [
        ("review-20261026-comprehensive", {"g2_confirmed": 24, "g3_patched": 0}),
        ("review-20261027-local", {"g2_confirmed": 0, "g3_patched": 0}),
    ]:
        path = root / name / "result.json"
        path.parent.mkdir()
        path.write_text(json.dumps(result), encoding="utf-8")
    selected = latest_review_result_path(SimpleNamespace(reviews_dir=root))
    assert selected.parent.name == "review-20261027-local"
```

Code locations (baseline lines): `src/auto_epublizer/qa/artifacts.py:28` selects the
latest path; `:130` hashes only that result. `src/auto_epublizer/qa/report.py:99` reads
counts and `:167` compares confirmed/patched. `src/auto_translator/review/g0.py:204`
extracts note numbers and `:308` checks identical text. These observations are not an
end-to-end EPUB release reproduction.

Synthetic two-column counterexample: left Alice/Editor, right Bob/Scientist flattens
to Alice/Bob/Editor/Scientist. Four blocks on each side can still be wrongly paired.
Verify Alice→Editor and Bob→Scientist against page evidence and the entry inventory,
not merely block totals.

## Proposed contracts and acceptance

- Stable finding IDs, scope, input digests, inheritance/supersession and per-item closure
  evidence; local clean must not close findings outside its scope.
- Digest all active findings and closure evidence, not just the “latest” file; unknown
  inheritance means unknown/open, with legacy-format compatibility.
- Offline bad fixtures for ordering/local shadowing, mixed-language candidates,
  note-number contexts, multi-column and cross-page source inventories.
- Machines provide candidates and consistency evidence, never guessed names, notes,
  formula classifications or semantic reconstruction.

This does not replace [delivery audit](../references/delivery.md),
[note contracts](../references/notes.md) or [semantic repair](../references/repair.md).
Correct overstated delivery claims through new records, without modifying historical
copies or claiming unperformed full reviews.
