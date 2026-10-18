<!-- i18n: source=build.zh.md sha256=12286b4182d15362ab549650accb157621a91d53c5e563c62f5988b0b8ca4725 -->
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

OPF `aep:render-mode` records the actual build entry: `source` (source only) or `translation` (translation preferred, with per-unit source fallback). QA reconstructs each note's host plan from this mode and the current inputs: the first spine reference determines the host; an unreferenced note uses its scope unit or the first actually rendered unit. Only notes whose hosts actually use translation load and validate translated-note binding and complete text; other notes are reconciled against source text independently. Entirely unused stale or malformed translated notes do not block source output. Products with registered notes but no valid mode must be rebuilt, not guessed.

## Product software fingerprint

- OPF includes `generator` and custom `aep:` metadata (`aep:build` stores the structured build record); content XHTML carries a JSON comment prefixed with `auto-epublizer-build` in its head for offline identification.
- The fingerprint records `auto-epublizer`, its [source URL](https://github.com/Misaka0x26FE/auto-epublizer), the **actual current build version**, and source revision/dirty state when available. Initialization-time `meta.producer` is not the build version; unavailable values remain explicitly unknown.
- Python and Pydantic describe the current build runtime. Other tools appear only from actual-use records frozen after successful parsing, not from an inventory of installed dependencies. Unknown versions remain unknown; unrecorded historical tools are not inferred from the current environment (`processing_tools=null` means history unknown; `[]` means no additional external parsing tool was used). MinerU API is identified as an external service, without claiming an internal open-source version or license.
- When a copyright unit exists, a separate software statement is appended without replacing its copyright text. Otherwise, a separate production-information page is generated with a non-linear spine entry (`linear="no"`) and a `copyright-page` landmark. It is not a manuscript unit and does not enter the body nav/NCX TOC.
- That statement (or production-information page) carries a **publication and rights** block above the tool list, taken from `publication.json.meta` (`title`/`creator`/`translator`/`publisher`/`date`/`rights`), listing only non-empty fields; when all are empty the block is omitted entirely rather than leaving empty labels.
- The tool list also carries **generation-model (LLM)** entries: `meta.generation_tools` is written by `meta --generation-tools '<JSON array>'` (each entry `{name, version, task, url, license}`, missing keys tolerated; `[]` means explicitly no generation model was used) and each renders as `name version — task`, with a missing version marked "version unrecorded" rather than invented. All of this wording is emitted in Chinese or English to match the build language (Chinese is authoritative).
- Software licenses do not grant or change rights to the manuscript, translation, or images. The fingerprint is removable, not a digital signature. Recording uses no telemetry or network requests and includes no machine paths, secrets, or unique tracking IDs.
- Legacy `output.about_page` remains reserved configuration, not a switch for this mandatory build fingerprint; it does not mean the legacy about-page feature is wired up.
- QA exempts only valid structured fingerprint comments from residue checks. A production page requires an OPF fingerprint declaration, its page marker, and a matching valid JSON fingerprint; a filename or arbitrary `linear="no"` alone grants no body-reconciliation/TOC exemption. Ordinary comments, forged prefixes, and malformed JSON remain `E_RESIDUE`.

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
- **Build-log attribution** (issue #40; no outbound calls): the `EPUB 已生成` line always
  carries the tool name + version + license + source URL, and the workspace
  `meta.producer` plus the `run_initialized` event expose the same identifier so origin is
  machine-decidable.
- **Theme** (`--theme` / `config.output.theme`): `standard` (serif + 1.7 line spacing + indent + justified + centered headings,
  default) / `compact` (sans-serif + 1.4 + no indent) / `spacious` (serif + 2.0). Only controls typographic fine-tuning;
  no specific font names/colors/font sizes (audit blocks them: `E_THEME_FONT`/`E_THEME_COLOR`).
- **Cover**: the first image of the cover unit automatically becomes `cover-image` (`<meta name="cover">` +
  spine `linear="no"`); when there is no cover source image, audit warns `W_NO_COVER` (provenance).
- **Notes**: standard EPUB `noteref` + `footnote`/`endnote` semantics, complete content, resolvable links and backlinks, resource identity, and current registration binding are mandatory offline checks (see `references/notes.md`). Reader implementation and user settings determine whether a popup appears; readable note areas and round-trip navigation remain the fallback.
- **TOC hierarchy**: source heading levels (`level`) → nested nav `<ol>` + nested NCX navPoint;
  **in-unit sub-heading anchors** (since 2026-09-29): in-unit h2+ headings automatically get stable ids
  (`{unit_id}-h{n}`; explicit `{#id}` takes precedence) and enter nav/NCX as children of the unit entry
  via `file.xhtml#anchor` — translations should preserve these sub-headings (checked by the g0 `heading`
  conservation gate);
  **nav depth projection** (`--nav-depth` / `config.output.nav_depth`, default 3, 1–6): units/anchors beyond the
  depth do not enter nav/NCX (they remain in spine reading order, anchors preserved), the cover unit does not enter the TOC,
  `dtb:depth` is the actual depth after projection (anchors included).
- **Images**: only shrink, never enlarge, centered + page-break (`page-break-inside: avoid`); standalone image paragraphs (non-empty alt) →
  `figure+figcaption` captions.
- **Semantic tags**: quote `>` → `blockquote`; verse block `|` → `p.verse`; `- ` → `ul`;
  ordered lists render as `<ol>` **only when the markers run consecutively from 1 with `. `/`、`**
  (native auto-numbering then matches the source numbers); all other `N.`/`N、`/`N)` blocks —
  e.g. critical-edition apparatus notes `1) 2) 5)…` whose numbers are real note ids — render
  as literal paragraphs with the numbers preserved (`p.fnlist`), never renumbered by `<ol>`.
- **Tables**: md pipe tables (`| a | b |` + separator row) and pandoc simple/grid tables (rows of `---` column boundaries)
  are rendered as `<table class="data">` (`th`/`td` + functional borders); cell text is translated normally,
  structure stays unchanged. **Do not change column boundaries and separator lines during translation** (G0 table shape conservation).
- Original image first + supplementary layer is a future extension point.
