<!-- i18n: source=build.zh.md sha256=17df60b37e6ca8b8da1b80f367cd0d9e4ae229f61616e0c0679c8e8039eb9ed5 -->
> **English** | [中文](build.zh.md)

# Build (EPUB packaging)

The `build` command packages the translation (falls back to the source text by default) as standard EPUB 3, into `output/`.

## Command

```bash
auto-epublizer build [-o <out.epub>] [--theme standard|compact|spacious] [--workspace <dir>]
```

- Reads the translation from `translation/<rel_path>` (falls back to `structured/` by default).

## EPUB 3 components

| File | Description |
|---|---|
| `mimetype` | `application/epub+zip`, first in the zip, uncompressed |
| `META-INF/container.xml` | points to `OEBPS/content.opf` |
| `OEBPS/content.opf` | manifest/spine/DC metadata/`dcterms:modified` |
| `OEBPS/nav.xhtml` | EPUB 3 navigation (toc) |
| `OEBPS/toc.ncx` | NCX (backward compatibility) |
| `OEBPS/landmarks.xhtml` | frontmatter/bodymatter/backmatter landmarks |

## Determinism

- The build timestamp uses a frozen value (not `time.Now()`); two builds of the same frozen workspace with the same builder version/source state and runtime fingerprint are byte-identical.
- Results are merged in stable source order and do not change with concurrent completion order.
- Internal stable IDs do not leak into artifacts (footnotes/endnotes use deterministic sequence numbers).

## Metadata

DC metadata comes from `publication.json.meta`: `dc:title`, `dc:creator`, `dc:language` (the translation uses `target_language`, pure conversion uses the source language), `dc:identifier` (isbn/uri/slug), `dc:date`, `dc:publisher`, `dc:rights`.

OPF `aep:render-mode` records the actual build entry: `source` (source only) or `translation` (translation preferred, with per-unit source fallback). QA reconstructs each note's host plan from this mode and the current inputs: the first spine reference determines the host; an unreferenced note uses its own source-location unit first, then a valid scope unit, and refuses to guess if neither exists. Only notes whose hosts actually use translation load and validate translated-note binding and complete text; other notes are reconciled against source text independently. Entirely unused stale or malformed translated notes do not block source output. Products with registered notes but no valid mode must be rebuilt, not guessed.

## Product software fingerprint

- OPF includes `generator` and custom `aep:` metadata (`aep:build` stores the structured build record); content XHTML carries a JSON comment prefixed with `auto-epublizer-build` in its head for offline identification.
- The fingerprint records `auto-epublizer`, its [source URL](https://github.com/Misaka0x26FE/auto-epublizer), the **actual current build version**, and source revision/dirty state when available. Initialization-time `meta.producer` is not the build version; unavailable values remain explicitly unknown.
- Python and Pydantic describe the current build runtime. Other tools appear only from actual-use records frozen after successful parsing, not from an inventory of installed dependencies. Unknown versions remain unknown; unrecorded historical tools are not inferred from the current environment (`processing_tools=null` means history unknown; `[]` means no additional external parsing tool was used). MinerU API is identified as an external service, without claiming an internal open-source version or license.
- When a copyright unit exists, a separate software statement is appended without replacing its copyright text. Otherwise, a separate production-information page is generated with a non-linear spine entry (`linear="no"`) and a `copyright-page` landmark. It is not a manuscript unit, but it does enter the nav/NCX TOC as a **top-level entry** (`制作信息` / `Production information`, the same language switch as the page title), positioned like its spine entry (before the first non-cover document), so readers that navigate only by TOC can reach it.
- That statement (or production-information page) carries a **publication and rights** block above the tool list, taken from `publication.json.meta` (`title`/`creator`/`translator`/`publisher`/`date`/`rights`), listing only non-empty fields; when all are empty the block is omitted entirely rather than leaving empty labels.
- The tool list also carries **generation-model (LLM)** entries: `meta.generation_tools` is written by `meta --generation-tools '<JSON array>'` (each entry `{name, version, task, url, license}`, missing keys tolerated; `[]` means explicitly no generation model was used) and each renders as `name version — task`, with a missing version marked "version unrecorded" rather than invented. All of this wording is emitted in Chinese or English to match the build language (Chinese is authoritative).
- Only those public credit fields are accepted; unknown keys and non-string/non-null values
  are rejected before persistence, keeping configuration/credential keys out of the list.
  `None` means history unrecorded; `[]` visibly states "No generation model was used
  (agent-reported)." Names, versions and tasks are self-reported, not detected or obtained
  through model-service calls. Metadata changes invalidate the old report.
- Software licenses do not grant or change rights to the manuscript, translation, or images. The fingerprint is removable, not a digital signature. Recording uses no telemetry or network requests and includes no machine paths, secrets, or unique tracking IDs.
- Legacy `output.about_page` remains reserved configuration, not a switch for this mandatory build fingerprint; it does not mean the legacy about-page feature is wired up.
- QA exempts only valid structured fingerprint comments from residue checks. A production page requires an OPF fingerprint declaration, its page marker, and a matching valid JSON fingerprint; a filename or arbitrary `linear="no"` alone grants no body-reconciliation/TOC exemption. Ordinary comments, forged prefixes, and malformed JSON remain `E_RESIDUE`.
- Production navigation is independently checked using OPF-declared nav/NCX and full package
  paths. Same-basename wrong-directory, duplicate or non-top-level entries produce
  `E_TOC_PRODUCTION_TARGET`. Completely missing legacy entries only warn with
  `W_TOC_PRODUCTION_MISSING`; they are not missing source units and do not weaken source-depth checks.

## Naming

- Default: `output/<slug>.epub`
- `-o` can override the output path.

## Notes

- **Media reference boundary** (2026-10, group D fix): the build only collects media that
  resolves **inside** `structured/raw/media/` (after following symlinks); `../…`, absolute
  paths and symlinks pointing outside the workspace are **refused** and recorded in the
  `media_dropped` event of `events.jsonl`, then blocked from release by provenance
  `E_MEDIA_EPUB_LOST` (media are never dropped silently).
- **Resource identity**: `%` is literal in Markdown/pandoc source file paths; HTML image URLs are decoded once; ZIP member names are never decoded. Bare names, subdirectories, and existing `media/` / `raw/media/` routes resolve through the actual source file. The note gate, ordinary-body provenance and general G4 use the same full-path identity rule; basename sets cannot exempt wrong-directory images. Media gates check images rather than treating HTML image tags as prose; surrounding text must still survive paragraph reconciliation.
- **Manifest identifiers**: media use legal, unique XML IDs assigned in stable order, independently of filenames/URIs. This avoids invalid characters and directory-path collisions; cover metadata references the actual manifest item rather than inferring a filename from its ID.
- **Code versus raw HTML**: preserve ordinary fences whole, including blank lines, and
  escape/display their contents. HTML-looking tags, headings, media paths, footnotes,
  anchors and container markers inside code generate neither navigation entries nor
  media reads. Source-text/Pandoc ingest must not split code headings into chapters or
  delete standalone code numbers as page numbers. Explicit Pandoc raw HTML is separate.
- **Inline SVG**: retain the real XHTML SVG namespace and set `svg` on the owning
  content manifest item. Local SVG image href/xlink:href uses the full-path media identity
  above. Missing source media, missing ZIP members or wrong-directory same-basename media
  block release; unbound XML prefixes must fail, never silently escape or disappear.
  SVG/img examples inside ordinary code are not resource references.
- **Build-log attribution** (issue #40; no outbound calls): the `EPUB 已生成` line always
  carries the tool name + version + license + source URL, and the workspace
  `meta.producer` plus the `run_initialized` event expose the same identifier so origin is
  machine-decidable.
- **Theme** (`--theme` / `config.output.theme`): `standard` (serif + 1.7 line spacing + indent + justified + centered headings,
  default) / `compact` (sans-serif + 1.4 + no indent) / `spacious` (serif + 2.0). Only controls typographic fine-tuning;
  no specific font names/colors/font sizes (audit blocks them: `E_THEME_FONT`/`E_THEME_COLOR`).
- **Cover**: the first image of the cover unit automatically becomes `cover-image` (`<meta name="cover">` +
  spine `linear="no"`); when there is no cover source image, audit warns `W_NO_COVER` (provenance).
  A **scanned cover** (#63) is never taken from page 1 automatically: `evidence source --json` lists
  `cover_candidates` (page/block/magic format/byte digest) as candidates only; after the agent verifies
  one and writes `preprocessing/cover.json` (`{"file": "structured/raw/media/…", "evidence": "…"}`, both
  required), build registers it through the existing cover-image path (media bytes unchanged). A declared
  cover unit without a resolvable image logs `cover_without_image` in `events.jsonl` and sets
  `cover.missing=true` in `status --json`.
- **Notes**: standard EPUB `noteref` + `footnote`/`endnote` semantics, complete content, resolvable links and backlinks, resource identity, and current registration binding are mandatory offline checks (see `references/notes.md`). Reader implementation and user settings determine whether a popup appears; readable note areas and round-trip navigation remain the fallback.
- **TOC hierarchy**: source heading levels (`level`) → nested nav `<ol>` + nested NCX navPoint;
  **in-unit sub-heading anchors** (since 2026-09-29): in-unit h2+ headings automatically get stable ids
  (`{unit_id}-h{n}`; explicit `{#id}` takes precedence) and enter nav/NCX as children of the unit entry
  via `file.xhtml#anchor` — translations should preserve these sub-headings (checked by the g0 `heading`
  conservation gate);
  **nav depth projection** (`--nav-depth` / `config.output.nav_depth`, default 3, 1–6): units/anchors beyond the
  depth do not enter nav/NCX (they remain in spine reading order, anchors preserved), the cover unit does not enter the TOC,
  `dtb:depth` is the actual depth after projection (anchors included);
  the **production-information page** (generated when there is no copyright unit) enters as the first top-level
  entry (depth 1; it does not take part in source-level projection), in the same order as the NCX `playOrder`
  (consecutive from 1).
- **Markdown parsing**: general inline/block syntax is parsed by `markdown-it-py` tokens (nested
  emphasis, reference links, nested lists, image paths with parentheses), while project-specific
  Pandoc anchors, original note numbers, verse lines, tables, footnotes and raw HTML keep their
  dedicated branches. Code spans stay **verbatim** (including line breaks and emphasis markers)
  and are never rewritten by the general parser.
- **Images**: only shrink, never enlarge, centered + page-break (`page-break-inside: avoid`); standalone image paragraphs (non-empty alt) →
  `figure+figcaption` captions.
- **Semantic tags**: quote `>` → `blockquote`; verse block `|` → `p.verse`; `- ` → `ul`;
  ordered lists render as `<ol>` **only when the markers run consecutively from 1 with `. `/`、`**
  (native auto-numbering then matches the source numbers); all other `N.`/`N、`/`N)` blocks —
  e.g. critical-edition apparatus notes `1) 2) 5)…` whose numbers are real note ids — render
  as literal paragraphs with the numbers preserved (`p.fnlist`), never renumbered by `<ol>`.
  A **single numbered block** (one line `1. …`) is also a paragraph: a lone endnote is not a
  one-item list, and `<ol>` would add list indentation/hanging style (#61; rationale in
  `docs/epub-template-spec.md`).
- **Tables**: md pipe tables (`| a | b |` + separator row) and pandoc simple/grid tables (rows of `---` column boundaries)
  are rendered as `<table class="data">` (`th`/`td` + functional borders); cell text is translated normally,
  structure stays unchanged. **Do not change column boundaries and separator lines during translation** (G0 table shape conservation).
- Original image first + supplementary layer is a future extension point.

## Print PDF (`pdf`, derived artifact)

Cover identity comes from package cover landmarks/semantics or an exact match to the registered cover-image resource, including nonlinear cover documents. An image-only registration produces a separate print cover page; other nonlinear appendices are not included automatically. Ambiguous cover identities fail rather than guessing from a filename containing cover or duplicating the cover. SVG graphics and existing cover text are retained.

The cover occupies absolute page 1 without a folio. Without a cover, the first body page is numbered 1 and keeps its normal margins. Cover geometry uses millimetres rather than 100vh, with a 0.5mm paper-rounding allowance to keep images inside the actual page.

Plate image height is budgeted from page size, top/bottom margins, and caption font/line height; images immediately after headings also reserve heading space. Short captions stay with their images; overlong captions may continue without drawing the image twice. Legitimate repeated references to the same source image remain repeated: resource deduplication is not a presentation audit.

Marker removal removes only positioning text, preserving underlying raster pixels and vector graphics. Resource URLs are decoded once and re-encoded for the browser so filename characters such as `#` are not mistaken for fragments.

Tables are constrained to the text area; cells may wrap, and table paragraphs inherit the table font rather than shrinking fonts arbitrarily by column count. JSON `diagnostics` separately reports requested/observed body and note sizes, source/matched character counts and distributions. Source paragraph prefixes bind PDF spans; the character-weighted mode requires at least 24 normalized matched characters and a 60% modal share. Ambiguous body/note prefixes, insufficient samples and unmatched text remain unknown, not a body-font guess from the whole-document median.

A measured font deviation above 5%, paper-size deviation above 1pt, or text/raster bounds more than 2pt outside the text area produces findings and notes. Overflow examples are capped at 100, with full counts/page sets retained. `--strict` exits nonzero on confirmed errors and preserves the previous PDF. Unknown font measurements remain unknown, not a claim of success. Diagnostics do not replace manual completeness, vector-graphic, table-semantic or glyph-readability acceptance.

```bash
auto-epublizer pdf --workspace <dir> [--epub <path>] [-o <out.pdf>] \
  [--size a5|32k|b5|16k] [--body-pt 10.5] [--note-pt 8.5] [--line-height 1.55] \
  [--no-bookmarks] [--strict] [--json]
```

- **Position**: the EPUB remains the delivery format; the PDF is regenerated from it on every
  run, never edited or written back. `artifacts_digest` does **not** walk `output/`, so
  re-rendering the PDF neither requires re-running `qa` nor invalidates the report.
- **Input**: defaults to `output/<slug>.epub`; the package document is located only through
  `META-INF/container.xml`; extraction rejects absolute paths, `..` and symlinks; a missing
  spine document is a Chinese error, not a silently shorter book.
- **Resources**: `src`/`href` are relocated per chapter directory (a subdirectory chapter's
  `../media/x.png` cannot be mismatched); remote/out-of-package references are dropped and
  recorded in `notes`; `script`/`on*` are always removed.
- **Bookmarks and TOC pages**: only the OPF item with `properties="nav"` and only the `epub:type="toc"` nav. Section start pages come from invisible locator marks (redacted after mapping); TOC rows and fragment bookmarks bind by full `href#fragment` identity to an anchor injected at the real id and use absolute page numbers from the final PDF, never a page-wide title substring or the section start page. TOC rewriting converges in at most three renders. Unlocated rows keep the source number but are explicitly labelled "original page, unlocated" in the product and reported as an error; non-convergence reports `E_PDF_TOC_UNSTABLE`. OPF3 `meta refines` translators never become the author.
- **Publication metadata**: `dc:publisher`, `dc:date`, `dc:rights`, `dc:language`, `dc:subject`, `dc:description`, `dc:identifier` are written verbatim to XMP (`dc:rights` is not truncated). Authors go to `dc:creator` and translators to `aep:translators`. Info carries only standard short fields: `/Title`←`dc:title`, `/Author`←authors (semicolon-joined, translators excluded), `/Subject`←description, `/Keywords`←subjects; `/CreationDate` and `/ModDate` are the **generation time**, not the `dc:date` publication date. Empty fields stay empty rather than being invented.
- **Artifact manifest**: every successful render writes `<pdf>.manifest.json` (schema, source EPUB/PDF sha256 and byte counts, PDF pages, actual parameters, Info/XMP read-back, TOC and diagnostics summaries). `pdf --json` returns the same `artifact`. `auto-epublizer pdf-verify --pdf <path> [--json]` recomputes the EPUB and PDF bytes and exits nonzero when the PDF changed, the manifest is corrupt, or the source is missing. Both PDF and manifest live under `output/` and remain outside the EPUB `artifacts_digest`: re-rendering does not change report state; the derived manifest carries the reconciliation.
- **Parameters**: body 4–24 pt, notes 4–20 pt, line height 1.0–3.0; non-finite or out-of-range
  values are rejected. Output equal to input is rejected; a missing Chromium, timeout (240 s),
  non-zero exit or a non-PDF product are Chinese errors; failures leave no partial product and
  never damage an existing PDF.
