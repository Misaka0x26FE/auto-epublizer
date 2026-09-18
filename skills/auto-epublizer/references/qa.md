<!-- i18n: source=qa.zh.md sha256=9797a535913fe277482e8d182163ceec8ac988427029b8fe2b5abd4a11efb5c0 -->
> **English** | [中文](qa.zh.md)

# QA (epubcheck + unpack audit)

> For a quick troubleshooting and release-interpretation reference (full error-code / condition sets), see `references/invariants.md`.

The `qa` command performs structural QA (G4) on the finished EPUB and writes
`report.json`.

## Command

```bash
auto-epublizer qa [--epub <path>] [--workspace <dir>]
# Output: G4 audit: pass/fail; epubcheck errors: N; passed: true/false
```

## epubcheck

- Validate with `~/.cache/epubcheck.jar` (`java -jar`); zero error releases.
- When the jar is missing, `available=False`, `ran=False`, `errors=-1`, `passed=False`
  (not verified ≠ qualified).

## Item-by-item unpack audit (offline, zero token)

| Check | Failure code |
|---|---|
| not a zip | `E_NOT_EPUB` |
| mimetype not first / compressed / wrong content | `E_MIMETYPE_FIRST` / `E_MIMETYPE_STORED` / `E_MIMETYPE_CONTENT` |
| missing container.xml / OPF not declared | `E_NO_CONTAINER` / `E_CONTAINER_OPF` |
| OPF missing | `E_OPF_MISSING` |
| spine idref not in manifest | `E_SPINE_REF` |
| manifest href unresolvable | `E_MANIFEST_HREF` |
| nav link unresolvable | `E_NAV_HREF` |
| NCX content src unresolvable (dangling reference) | `E_NCX_HREF` |
| landmarks link unresolvable (dangling reference) | `E_LANDMARKS_HREF` |
| content document img src unresolvable (dangling media) | `E_IMG_SRC` |
| javascript:/data: URL injection | `E_UNSAFE_URL` |
| content document missing lang / h1 count not 1 | `W_NO_LANG` / `W_H1_COUNT` (warning) |
| heading level skip (h1→h3 etc.) | `E_HEADING_SKIP` |
| HTML comment residue / markdown marker residue (`![` `**` `:::` `{.` `[^`) | `E_RESIDUE` / `W_RESIDUE` (error/warning) |
| DC metadata missing (creator/date/publisher/rights) | `W_META_INCOMPLETE` (warning) |
| internal anchor unresolvable (including footnote noteref→footnote) | `E_ANCHOR` |
| footnote aside missing backlink or backlink unresolvable | `E_FN_BACKLINK` |
| bilingual src/tgt paragraph counts inconsistent | `E_BI_PAIRS` |
| theme contains a concrete font name/size / color | `E_THEME_FONT` / `E_THEME_COLOR` |
| cover properties and meta cross-verification fails | `E_COVER_META` |
| img alt empty or missing / poor format compatibility (.webp/.avif) | `W_IMG_NO_ALT` / `W_IMG_FORMAT` (warning) |
| image too large (>4000px) / too wide or tall (>5:1) / uncompressed (>2MB) | `W_IMG_LARGE` / `W_IMG_RATIO` / `W_IMG_UNCOMPRESSED` (warning) |
| EPUB total size over threshold (50MB) | `W_EPUB_SIZE` (warning) |

## Quality report `report.json`

```json
{"slug":"...","g4_audit":"pass","g4_epubcheck_errors":0,"passed":true,
 "audit":{"ok":true,"errors":0,"findings":[]},
 "epubcheck":{"available":true,"ran":true,"errors":0,"warnings":0}}
```

## Release conditions (G5)

- `g4_epubcheck_errors == 0` (epubcheck actually ran)
- `g4_audit == "pass"` (unpack audit zero error)
- G0 terminology hits cleared (`g0_terminology_open == 0`; length-ratio warnings are the
  advisory ones)
- G0 structural violations cleared (`g0_structure_open == 0`: marker/footnote
  conservation)
- Unresolved terminology conflicts cleared (`glossary_conflicts_open == 0`; if not
  cleared → `glossary_conflict_open` — go back to analysis/glossary_conflicts.jsonl,
  arbitrate and write back to glossary.csv, then rerun qa)
- Review `g2_confirmed == 0` or all revised
- Complete provenance (postprocessing-spec §5): `provenance_coverage ≈ 1.0` (null when
  there is no translation artifact, not applicable), `units_missing == 0`,
  `units_order_ok`, `media_lost == 0`, `toc_flat == false`,
  `inserts_missing_files == 0` (illustrations/tables/formulas traceable to the original
  location with the file present, pdf-content-spec §9)
- Finished-product presentation reconciliation cleared (delivery audit S1):
  `epub_media_missing == 0`, `epub_footnotes_missing == 0`, `align_md_drift == 0`,
  `epub_coverage ≈ 1.0` (actual product inclusion ↔ translation body/alignment)

> `qa released=True` only means all known contracts are green; **before delivery you must
> also execute the delivery-audit checklist in `references/delivery.md`** (independent
> reconciliation + manual spot-check + write the delivery record); only when both are
> done does it count as delivered.

When `released` is False, look at `released_reason` to determine the cause:
`unresolved_confirmed` (G2 confirmed but unrevised) / `audit_failed` /
`provenance_incomplete` (incomplete provenance: locate via the
E_UNIT_MISSING/E_UNIT_ORDER/E_MEDIA_LOST/E_MEDIA_ORDER/E_MEDIA_EPUB_LOST/E_FN_EPUB_LOST/E_EPUB_PARA_LOST/E_ALIGN_MD_DRIFT/
E_TOC_FLAT/E_INSERT_MISSING_FILE/E_INSERT_BAD_SOURCE entries in `provenance_findings`) /
`epubcheck_not_run` (missing jar, install the jar and rerun) / `epubcheck_errors`.
G0 **length-ratio** warnings are advisory clues and do not block release; **terminology
hits** (`g0_terminology_open`) are a release hard gate, and if not cleared →
`released_reason=terminology_open`.
`toc_missing` (facts source-TOC reconciliation) and `W_TOC_DEPTH` are warning clues and do
not block.

## Inserts audit interpretation

When `raw/inserts/<id>.json` (illustration/table/formula description files,
pdf-content-spec §2) exists, provenance adds a four-code check (E-level enters the release
gate; W-level does not block, but supplement per translation.md "inserts completion" and
rerun):

| Code | Level | Meaning and handling |
|---|---|---|
| `E_INSERT_MISSING_FILE` | error | the media file that `source.file` points to is not on disk — rerun that unit's ingest (`preprocess`/`init`) or re-extract from the source PDF; confirm it was not accidentally deleted |
| `E_INSERT_BAD_SOURCE` | error | `source.page` is not a positive integer or `bbox` is invalid — the description file is corrupt; manually fix the source field of that `<id>.json` (check the page number/coordinates against the source PDF) |
| `W_INSERT_NO_DESC` | warning | `content_desc` is empty — the agent writes a content description from the source page per translation.md "inserts completion" |
| `W_INSERT_NO_LATEX` | warning | formula record `latex` is empty — the agent hand-writes LaTeX into it (locate the formula by bbox; the image is authoritative) |

The only count field persisted in report.json is `inserts_missing_files` (enters the
release gate); `inserts_total` / `inserts_no_desc` / `inserts_no_latex` exist only inside
the provenance result object and are not persisted — when a count is needed, tally the
`W_INSERT_NO_DESC` / `W_INSERT_NO_LATEX` entries in `provenance_findings` yourself.

## Troubleshooting

- `epubcheck errors: -1` → jar not installed; download it per the `doctor` hint, place it
  at `~/.cache/epubcheck.jar`, and rerun.
- `product does not exist` → `build` or `convert` first.
- Audit finds `W_H1_COUNT` → content-document heading hierarchy problem (each chapter
  should have exactly one h1).
- `E_ZIP_DUPLICATE` → duplicate zip entry names (hand-edited package/corrupt); rebuild
  from the translation, do not fix the product.
- `E_IMG_REMOTE` → image external link; download the image into raw/media/, change the
  translation to a local reference, and rebuild.
- `E_TOC_COVERAGE` → spine↔nav bidirectional coverage gap (chapter missing a nav entry /
  ghost nav entry); note that super-deep units removed by **TOC depth projection**
  (`output.nav_depth`) are an expected exemption and do not count as gaps; otherwise
  check that unit's translation md heading hierarchy and rebuild.
- `E_MEDIA_EPUB_LOST` → an image referenced by the translation did not make it into the
  product (silently dropped by build / rendering missing): check whether the file exists
  in `structured/raw/media/` and the `media_dropped` event in `events.jsonl`; add the
  file and rebuild.
- `E_FN_EPUB_LOST` → product footnote count inconsistent with the translation: check
  whether the `[^label]:` definitions in the translation md are complete and rebuild;
  `W_RESIDUE` indicating a literal `[^` residue means a definition is missing.
- `E_EPUB_PARA_LOST` → product is missing a translation paragraph (body probe
  `epub_coverage` < 1.0): locate `unit:paragraph` from the report, check the translation
  md against structured, and rebuild.
- `E_ALIGN_MD_DRIFT` → translation body inconsistent with the alignment (one side missing
  content): check against align as authoritative, rewrite the md, and rerun `import`.
- `W_DELIVERY_AUDIT_MISSING` → all units built but no delivery record: perform the
  delivery audit per `references/delivery.md` and write `reviews/delivery-<ts>.md`.
- `W_REPAIR_UNRESOLVED` → semantic repair has an unresolved fix (status=unresolved in
  `preprocessing/repairs.jsonl`): fix it if possible and rerun qa; explain genuinely
  doubtful ones in the delivery record.
- `W_NAMING` → product filename does not match the slug prefix; rename with `-o` or output
  as `<slug>.epub`/`<slug>-bi.epub`.
- `W_STRUCT_MISSING` → structured/ source file missing (accidentally deleted); rerun that
  unit's ingest from the source file.
- `provenance_incomplete` →
  - `E_UNIT_MISSING`: spine missing a unit — check whether that unit's translation/source
    exists and whether it was skipped as an empty shell;
  - `E_MEDIA_LOST`/`E_MEDIA_ORDER`: the translation dropped an image or the image order
    changed — supplement against the `structured/` source text;
  - coverage < 1.0: `report.json` has no per-paragraph list; run `g0` and use its warnings
    to locate omitted paragraphs;
  - `E_TOC_FLAT`: the source text has hierarchy but the TOC is flat — confirm the source
    unit `level` is registered (rerun init/preprocess).
