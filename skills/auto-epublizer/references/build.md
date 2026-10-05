<!-- i18n: source=build.zh.md sha256=c2b4c41846ad303e6343bbf40035cdc07ded7c1513edc4b814c7ee96942e9a64 -->
> **English** | [中文](build.zh.md)

# Build (EPUB packaging)

The `build` command packages the translation (falls back to the source text by default) as standard EPUB 3, into `output/`.

## Command

```bash
auto-epublizer build [--bilingual] [-o <out.epub>] [--theme standard|compact|spacious] [--workspace <dir>]
```

- Monolingual: reads the translation from `translation/<rel_path>` (falls back to `structured/` by default).
- Bilingual: `--bilingual` renders source/translation interleaved per the `align/` alignment table, outputting `<slug>-bi.epub`.

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

- The build timestamp uses a frozen value (not `time.Now()`); two builds of the same frozen workspace are byte-identical.
- Results are merged in stable source order and do not change with concurrent completion order.
- Internal stable IDs do not leak into artifacts (footnotes/endnotes use deterministic sequence numbers).

## Metadata

DC metadata comes from `publication.json.meta`: `dc:title`, `dc:creator`, `dc:language` (the translation uses `target_language`, pure conversion uses the source language), `dc:identifier` (isbn/uri/slug), `dc:date`, `dc:publisher`, `dc:rights`.

## Naming

- Pure translation: `output/<slug>.epub`
- Bilingual: `output/<slug>-bi.epub`
- `-o` can override the output path.

## Notes

- **Theme** (`--theme` / `config.output.theme`): `standard` (serif + 1.7 line spacing + indent + justified + centered headings,
  default) / `compact` (sans-serif + 1.4 + no indent) / `spacious` (serif + 2.0). Only controls typographic fine-tuning;
  no specific font names/colors/font sizes (audit blocks them: `E_THEME_FONT`/`E_THEME_COLOR`).
- **Cover**: the first image of the cover unit automatically becomes `cover-image` (`<meta name="cover">` +
  spine `linear="no"`); when there is no cover source image, audit warns `W_NO_COVER` (provenance).
- **Footnotes**: `[^label]` → standard popup notes (noteref/footnote), note reference `[N]`, **restarting from 1 per chapter**
  with independent numbering + bidirectional backlink (readers that do not support popups degrade to an end-of-chapter note area).
- **TOC hierarchy**: source heading levels (`level`) → nested nav `<ol>` + nested NCX navPoint;
  **in-unit sub-heading anchors** (since 2026-09-29): in-unit h2+ headings automatically get stable ids
  (`{unit_id}-h{n}`; explicit `{#id}` takes precedence) and enter nav/NCX as children of the unit entry
  via `file.xhtml#anchor` — translations should preserve these sub-headings (checked by the g0 `heading`
  conservation gate);
  **nav depth projection** (`--nav-depth` / `config.output.nav_depth`, default 3, 1–6): units/anchors beyond the
  depth do not enter nav/NCX (they remain in spine reading order, anchors preserved), the cover unit does not enter the TOC,
  bilingual documents have no anchor entries;
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
