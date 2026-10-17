<!-- i18n: source=notes.zh.md sha256=4ee9b71a98b8e447dd073c99edb54e357165be13df429ad6ed45ecc13322e603 -->
> **English** | [中文](notes.zh.md)

# Note Structuring and Binding (phase N)

For books **with notes** (footnotes/endnotes/sidenotes, collected note sections): give every
note a stable identity, keep a reference marker at the original in-text position, render the
whole book to standard semantic notes, and let **independent hard gates** block a product that
has notes but zero semantic nodes, has partial omissions, or mismatches content.

> Books without notes do not enter this flow (no `notes.json`; build/audit keep the original
> path) — "no notes" is a **verified** conclusion (`inventory=none`), not "zero detected".

## Flow (zero-token CLI + agent semantic verification)

1. **Collect candidates** (CLI):

   ```bash
   auto-epublizer notes candidates --workspace <ws>
   # → preprocessing/note_candidates.jsonl (marker/pandoc_ref/definition/numbered_paragraph)
   ```

   Candidates carry `unit/line/text` evidence; their identity is a content hash (line numbers
   excluded), so re-running preserves existing dispositions.

2. **Agent verification** (semantic work; the CLI never does it):

   - review the source file / `structured/raw/` evidence and set `disposition=note|not_note`
     for each candidate;
   - decide the **true note boundaries** (page-bottom fragments, cross-page continuations,
     numbering shifts), the **note-number scope** (original chapter/section) and the position
     of **each reference**;
   - `unverified` is a transient state: before registration it must become `present` (notes
     exist and bindings are built) or `none`.

3. **Write the source-note authority** `structured/notes.json` (schema below); full note text
   goes into `source_markdown` (multi-paragraph/list/emphasis/image/formula Markdown kept
   as-is).

4. **In-place marker in the body**: write `[^ref-000123]` at the **original reference
   position** (the marker text is the `ref_id`; it encodes no visible number, is not inserted
   by source character offsets, and is not forced to a sentence end). When one source note is
   referenced several times, register one independent `references` entry (independent
   `ref_id`) per occurrence.

   Never replace canonical `[^label]` or stable `[^ref-ID]` with Unicode superscripts
   to pass G0; mathematical superscripts cannot offset lost citations. Quotes or ellipses
   before a real citation are not automatic OCR-noise waiver evidence. The agent must
   repair ambiguity against source evidence and register the note/ref graph, not suppress
   warnings with broad regexes.

5. **Register** (separation-registration gate):

   ```bash
   auto-epublizer notes register --workspace <ws>
   ```

   Validates schema/source-hash binding/unique identity/scope/two-way location evidence/
   unresolved status/**body marker ↔ reference reconciliation**/candidate disposition
   completeness; on success it writes a **summary** into `publication.json.notes` (the agent
   never edits official state by hand).

6. **Translation**: keep the same `ref_id` at the corresponding semantic position in the
   translated body; the note itself is stored in `translation/notes.json` under the same
   `note_id` as a complete translated note. Translated notes take part in terminology checks,
   content completeness and G1–G3 review.

7. **`import`** (translation-import gate): translated markers conserved (each reference
   exactly once, no unregistered marker), required translated notes complete, translated-note
   digest bound to the source notes. Failure blocks registration of that unit.

8. **`build`**: whole-book rendering — body markers → `epub:type="noteref"` links; notes render
   as `epub:type="footnote"` asides (`id="fn-<note_id>"`, full block-level Markdown + one
   independent backlink per reference); cross-file references point at the note's host file
   (the first unit in spine order that references it); display numbers are generated
   deterministically per scope (same number inside a scope is legal, one note keeps one
   number). If the build finds an unregistered marker or a reference that did not make it into
   the product, it errors out and **never drops it silently**.

9. **`qa`** (product gate): independently parses the final XHTML and reconciles reference
   anchors/href/aside/backlinks/content item by item; `released_reason=notes_open` blocks
   release; tampering/omission/mismatch are located to a concrete `ref_id`/`note_id`.

## JSON contract (N2)

`structured/notes.json` (source-note authority):

```json
{
  "schema_version": "1",
  "source_sha256": "<publication.json.meta.source_sha256>",
  "inventory": "present | none | unverified",
  "notes": [
    {
      "note_id": "n-000001", "scope_id": "ch01", "source_label": "23",
      "note_type": "footnote | endnote | sidenote",
      "source_markdown": "full source note (Markdown)",
      "source_locations": [{"kind": "page", "page": 12, "text_block": "…"}],
      "status": "verified | unresolved",
      "orphan_ok": false, "orphan_reason": ""
    }
  ],
  "references": [
    {
      "ref_id": "ref-000001", "note_id": "n-000001", "unit": "ch01", "scope_id": "ch01",
      "label_text": "23", "context": "…text around the marker…", "status": "verified"
    }
  ]
}
```

`translation/notes.json` (translated notes; no source references/locations duplicated):

```json
{
  "schema_version": "1",
  "source_notes_sha256": "<sha256 of structured/notes.json>",
  "notes": [{"note_id": "n-000001", "target_markdown": "full translated note (Markdown)"}]
}
```

Conventions:

- Stable identity: `note_id`/`ref_id` must never be renumbered or reused after registration;
  display numbers are separate from identity.
- `scope_id` is a source-confirmed chapter/section; the same number in different scopes is
  legal, the same number inside one scope is an error.
- Unreferenced notes (genuinely present in the original) require `orphan_ok=true` +
  `orphan_reason`; the build still renders them.
- Source-fallback builds use `source_markdown`; translation builds require the corresponding
  translated notes (missing ones block).

## Gates and invalidation

| Gate | Checks | Trigger |
|---|---|---|
| Separation-registration | schema/source hash/identity/scope/two-way locations/unresolved/marker reconciliation/candidate disposition | `notes register` |
| Translation-import | translated marker conservation + complete translated notes + digest binding | `import` |
| Product | noteref/href/aside/backlink/content reconciliation; zero-to-zero for none | `qa` (`notes_open`) |

**Invalidation**: after the source hash, body markers, `structured/notes.json` or the
translated notes change, the registration summary goes stale — `notes status` reports
`stale`, and `import`/`build`/`qa` fail or block explicitly (`E_NOTES_STALE`); re-run
`notes register` and re-translate the affected notes as needed.

## Status and troubleshooting

```bash
auto-epublizer notes status --workspace <ws>        # summary / stale / candidate disposition
auto-epublizer status --workspace <ws> --json       # notes section + next_tasks
```

`next_tasks` provides the pre-translation note tasks (`notes_verify` → `notes_register`);
translation/delivery do not start before they are done.

Common blocks and fixes:

- `inventory=unverified`: verify first, then register;
- `未决注文`/`候选未全部处置`: give a verification verdict per item (`note`/`not_note`);
- `正文缺原位标记`/`标记出现 N 次`/`未登记标记`: align the body and `references` both ways;
- `译文缺 [^ref-…]`/`出现未登记标记`: translated markers disagree with the registration;
- `译注摘要不符`/`E_NOTES_STALE`: source notes changed — re-register and re-translate affected
  notes;
- notes without references: add `orphan_ok=true` + `orphan_reason` (never delete a genuine
  unreferenced source note).

## Candidate identity and note locations (required for registration)

Reference candidates (`marker/pandoc_ref`) explicitly bind `ref_id`: the reference must
exist in the same unit, agree on the label when both have one, and be bound by only one
candidate per actual reference. Note candidates (`definition/numbered_paragraph`) explicitly
bind `note_id`; that note's `source_locations` must contain each corresponding
`candidate_id`. Never infer bindings from shared numbers or text prefixes.

```json
{
  "candidates": [
    {"candidate_id": "c-ref", "kind": "marker", "unit": "ch01", "line": 3, "label": "23", "disposition": "note", "ref_id": "ref-000001"},
    {"candidate_id": "c-start", "kind": "numbered_paragraph", "unit": "appendix", "line": 8, "disposition": "note", "note_id": "n-000001"},
    {"candidate_id": "c-cont", "kind": "numbered_paragraph", "unit": "appendix", "line": 12, "disposition": "note", "note_id": "n-000001"}
  ],
  "note": {
    "note_id": "n-000001", "scope_id": "ch01", "source_label": "23",
    "note_type": "endnote", "source_markdown": "Opening paragraph.\n\nComplete cross-page continuation.",
    "status": "verified",
    "source_locations": [
      {"kind": "page", "page": 40, "bbox": [10, 20, 300, 400], "candidate_id": "c-start", "unit": "appendix", "line": 8},
      {"kind": "page", "page": 41, "candidate_id": "c-cont"}
    ]
  },
  "reference": {"ref_id": "ref-000001", "note_id": "n-000001", "unit": "ch01", "scope_id": "ch01", "label_text": "23", "status": "verified"}
}
```

Place these entries in the candidate JSONL, `notes`, and `references` respectively;
this is not an additional file format. Multiple physical locations may bind one note.
Keep original PDF page/bbox evidence and add candidate identity. If `unit/line` are also
specified, they must agree with the candidate's corresponding fields. A mixed appendix
need not be a `notes` unit, and an endnote's physical location need not match its reference.
Real unreferenced notes use `orphan_ok=true` plus `orphan_reason` and the same location
evidence: never invent references or delete genuine continuations. Re-exporting candidates
preserves dispositions and `note_id/ref_id`; after review, check evidence against updated
line numbers.
