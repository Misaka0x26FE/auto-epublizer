<!-- i18n: source=structure.zh.md sha256=c50f2de1a661c06db6b1ad623ea567cc73885b04d004b4abff715840d76b9178 -->
> **English** | [中文](structure.zh.md)

# Structure (four-layer structural rebuild + provenance)

Classify normalized units into the publication's four-layer structure; after cleaning, land
them in `structured/`, serving as the authoritative source text for translation and
packaging.

## Four-layer structure

```text
structured/
├── cover.md                        # cover
├── frontmatter/{titlepage,copyright,dedication,foreword,preface,toc}.md
├── body/ch01.md ...                # body units (the main battleground of translation)
├── backmatter/{afterword,appendix,notes,bibliography,index,glossary}.md
└── media/                          # media assets
```

## Classification rules

Title keyword → (region, kind), for example:

| Title contains | region | kind |
|---|---|---|
| cover | cover | cover |
| title page | frontmatter | titlepage |
| copyright | frontmatter | copyright |
| dedication | frontmatter | dedication |
| foreword | frontmatter | foreword |
| preface / author's preface | frontmatter | preface |
| toc / contents | frontmatter | toc |
| afterword / postscript | backmatter | afterword |
| appendix | backmatter | appendix |
| bibliography | backmatter | bibliography |
| index | backmatter | index |

No keyword hit → `body` + `chNN` (sequential numbering). Unit IDs are stable (`ch01`,
`front-preface`, `back-index`).

## Cleaning

- **Page-number removal (requires layout evidence)**: explicit labels (`page 3`, `p12`),
  decorated numbers (`- 8 -`), and bare numbers that sit on a page boundary and form an
  increasing sequence across ≥5 `source_page` values within a 0–3 page offset. Bare numbers without such evidence
  (years, verse numbers, table values) are **kept** and reported as candidates in
  `structured/raw/structure-clean.json`; never delete on shape alone.
- **Running head/footer removal**: group by `source_page`; a short text that appears at the
  top/bottom of ≥50% of pages is removed (`min_pages` guard). Removals are recorded in the
  same `structure-clean.json` (`removed` / `candidates`).
- **Cleaning follows classification**: cover/title-page exemption uses the classified
  `kind`, not a second title-only decision; aggregated units recognised as title pages keep
  their furniture.
- **Written output is cleaned**: `write_structured` writes cleaned segments, so running
  heads/page numbers never reach `structured/`. Preview a rebuild with
  `preprocess --force --dry-run` (reports new/changed/unchanged plus the ledger, writes
  nothing).
- **EPUB anchor/attribute leftovers**: `read_epub` already clears `[]{#id}` anchors,
  `{#id}` attributes, `[text]{.class}` class attributes and `<br>` on ingest; if such
  leftovers are still seen in headings in `structured/`, it means the generic pandoc
  fallback path was taken — troubleshoot per `references/ingest.md` "EPUB split by spine".
- **Provenance**: each `Segment` carries `meta.source_page`; each PDF page has a
  corresponding `page-NNN.json`.

## Media identity and migration mapping

- Delivery audit (QA / notes gate) accepts only **exact paths** (original relative path,
  repeated root prefix) or an **explicit mapping**. Same-basename files in another directory
  are no longer silently substituted; a wrong-directory reference is reported missing.
- The build path still accepts legacy paths (basename fallback) as a transition; mismatches
  surface at the delivery gate.
- Register legacy absolute paths one by one in `preprocessing/media-map.json`:

  ```json
  {"schema": 1, "entries": [
    {"ref": "/home/agent/book/media/fig1.png", "member": "fig1.png",
     "reason": "legacy absolute path migration", "sha256": "optional, 64 lowercase hex"}
  ]}
  ```

  `member` is relative to `structured/raw/media/`; `reason` is mandatory; optional `sha256`
  pins the target bytes. Traversal, duplicate refs, missing targets and digest mismatches
  become audit findings, never silent passes.

## Contract

- Unit = the smallest manageable unit of translation; `Unit.meta` stores `rel_path` and
  `region` (written into `publication.json` by `set_units`), and analysis/translation/build
  all rely on it to locate files.
- The number of heading levels (h1/h2) and the number of paragraph blocks should be
  consistent with the source text — **the review's reconciliation anchor** (g0.py provides
  pure counting functions but they are not wired into automatic validation; it is a future
  extension point).
- Insert elements (`{fig:NNN}` etc.) marker counts are conserved (G0 unit-level total
  conservation is already wired; loss is a hard defect);
  **md table shape conservation is already wired** (table count/row-column counts, import
  hard validation);
  footnote/endnote reference↔definition pairing and backlinks are covered by the G4 audit
  (`E_FN_BACKLINK`/`E_ANCHOR`).

## Unit-boundary rebuild (restructure registration)

When repair/re-splitting causes **a change in the unit set** (split, merge, add, delete),
or changes the source body of a completed unit, register the structure and content digests again; otherwise
`publication.json.units` becomes decoupled from disk:

1. Manually rewrite `structured/` according to the real chapters (one md per unit, first
   line `# title`);
2. Write `preprocessing/structure.csv` (columns `id,region,kind,title,level,rel_path`; one
   unit per row; `title` must equal that file's first-line heading, `rel_path` must match
    the region prefix);
   optional seventh column `nav` accepts `yes`/`no` (default `yes`). `no` keeps the unit
   in spine reading order but excludes it from nav/NCX, e.g. a dedication page. It does
   not delete content; changing this switch invalidates the QA report digest.
3. Run `auto-epublizer restructure`: after validation (files exist, no orphan md, no
   duplicate id) it updates `publication.json.units`;
4. State semantics: retain state only when the id, structural fields and registered body SHA-256 are unchanged; changes roll back to
   `split` (requires re-translation and re-import). Legacy workspaces without a body digest roll back to `split` on their first `restructure`, registering the current baseline rather than inferring historical completion. Repeating registration without changes does not reset again; a vanished id → output an orphan-artifact
   hint (old translation/align can be cleaned up).

> When to use: MinerU/OCR hierarchy is messy and needs re-splitting, fragmented units need
> merging, a single unit that lost nav needs splitting.
> See `references/repair.md` and `docs/semantic-repair.md` §3.3.

## Notes

### Source inventory catalog.csv

Columns are `item,kind,status,locator,unit_id,note`. kind accepts toc/figure/table/footnote/section/physical/blank. figure includes maps and full-page images; image input normalizes to figure. blank is a content type, not a disposition status. Empty OCR text does not prove a blank page: inspect the source page image.

| status (for every kind) | Required constraints | Release meaning |
|---|---|---|
| included | unit_id bound to a real unit | Content included |
| physical | Keep a locator for the physical-carrier record | Not automatically unresolved |
| excluded | note explaining exclusion | Not automatically unresolved |
| absent | note evidencing absence in the source itself | Not automatically unresolved |
| unresolved | Await verification; do not guess missing content | Blocks release |

blank always requires locator; except for unresolved, note must record verification evidence. `repairs.jsonl.evidence` must be an existing workspace-relative file (e.g. `structured/body/ch01.md`); paths and symlinks escaping the workspace are errors.

Column-order reading, complex-table shape preservation, and dedicated footnote/endnote
extraction are complex PDF scenarios and are currently future extension points; basic
four-layer classification + running-head/footer/page-number removal are implemented.
