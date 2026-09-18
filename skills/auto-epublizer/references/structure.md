<!-- i18n: source=structure.zh.md sha256=4a334cd400864934e2ef9e33548f49938eb9181f1ced6bf9b390c32495738f3d -->
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

- **Page-number removal**: standalone page-number paragraphs (`12`, `- 8 -`, `page 3`).
- **Running head/footer removal**: group by `source_page`; a short text that appears at the
  top/bottom of ≥50% of pages is removed (`min_pages` guard).
- **EPUB anchor/attribute leftovers**: `read_epub` already clears `[]{#id}` anchors,
  `{#id}` attributes, `[text]{.class}` class attributes and `<br>` on ingest; if such
  leftovers are still seen in headings in `structured/`, it means the generic pandoc
  fallback path was taken — troubleshoot per `references/ingest.md` "EPUB split by spine".
- **Provenance**: each `Segment` carries `meta.source_page`; each PDF page has a
  corresponding `page-NNN.json`.

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
content-level modifications need no registration (build/provenance read `structured/`
directly), but boundary-level changes must be registered, otherwise
`publication.json.units` becomes decoupled from disk:

1. Manually rewrite `structured/` according to the real chapters (one md per unit, first
   line `# title`);
2. Write `preprocessing/structure.csv` (columns `id,region,kind,title,level,rel_path`; one
   unit per row; `title` must equal that file's first-line heading, `rel_path` must match
   the region prefix);
3. Run `auto-epublizer restructure`: after validation (files exist, no orphan md, no
   duplicate id) it updates `publication.json.units`;
4. State semantics: same id and unchanged content → state retained; changed → roll back to
   `split` (requires re-translation and re-import); a vanished id → output an orphan-artifact
   hint (old translation/align can be cleaned up).

> When to use: MinerU/OCR hierarchy is messy and needs re-splitting, fragmented units need
> merging, a single unit that lost nav needs splitting.
> See `references/repair.md` and `docs/semantic-repair.md` §3.3.

## Notes

Column-order reading, complex-table shape preservation, and dedicated footnote/endnote
extraction are complex PDF scenarios and are currently future extension points; basic
four-layer classification + running-head/footer/page-number removal are implemented.
