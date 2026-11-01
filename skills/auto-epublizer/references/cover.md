<!-- i18n: source=cover.zh.md sha256=450cdbe66f23c5b9bed5c08e665980bb802e85fd6045f1906b6a2f28d50a672b -->
> **English** | [中文](cover.zh.md)

# Generated cover (quarto 界栏 / hanze-academic 汉译学术本)

For books with **no usable cover**: plain text / Markdown / DOCX / HTML sources have no cover
image at all, and a scanned book's first page is not automatically its cover (a candidate only
becomes one after `preprocessing/cover.json` is confirmed). Such books show up blank on the
shelf and lock screen. This flow gives them two shared typeset covers; pick one per book group:

| Layout | Name | Look | For |
|---|---|---|---|
| `quarto` (default) | 界栏 | full-bleed ground, reversed flush-left title, double hairline at the left edge, short rule, italic original title | modern academic/humanities; a series is told apart by palette |
| `hanze-academic` | 汉译学术本 | cream paper grain, double frame, centred four-block text, optional motif | translated classics/research editions; one accent colour per book |

> **The previous layout is disabled**: `magadan` (white page + band/stripe) is no longer
> offered. Writing `style: magadan` in config or a design sheet is an explicit error, never a
> silent style switch.

## Legibility floor (hard constraint)

Covers are read down to **600px wide**; smaller resolutions are out of scope. A CJK serif
below roughly a 14px em turns to mush, so **every type size must be ≥ 2.34% of the page width**
(`MIN_TYPE_FRAC` = 14/600; ≈9.8pt on A5). The clamp lives in `_quarto_layout`
(`max(size, MIN_TYPE_FRAC * W)`) and `tests/test_cover_render.py` enforces it.

Changing ratios, weights or spacing is fine; **pushing any size below that line is a defect**.

> **Source cover wins**: a cover confirmed in `preprocessing/cover.json` is never replaced by
> a generated one. Generation only fills the "there really is no cover" case.

## When to do it

Check three things, in this order:

1. Does `preprocessing/cover.json` exist? Yes = the agent already verified a source cover;
   **do not generate**.
2. Does the cover unit's Markdown already reference an image (`![…]`) that really exists,
   in both `structured/` and `translation/`? Then nothing to do.
3. Neither → the book has no cover; generation applies.

```bash
# read-only inventory (cover candidates and confirmation state)
"$AEP_CLI" evidence source --workspace <ws> --json

# full picture (recommended: one call decides whether to generate)
"$AEP_CLI" status --workspace <ws> --json
# cover.confirmed / cover.has_image → a source cover exists
# cover.generated            → generated-cover registration (file/exists/palette/stale/fonts_missing)
# cover.effective            → source | generated | null: which one will actually be used
# cover.missing              → means "no source cover" only; do not read it as "no cover"
```

`cover_candidates` are **candidates, not conclusions**: the first full-page image may be a
title page, an illustration, or a copyright page. Only after checking it (page number, layout,
text) do you write `preprocessing/cover.json`; if it does not check out, use this chapter's
generated cover — never take "looks like a cover" as evidence.

## Generate / remove

```bash
"$AEP_CLI" cover --workspace <ws>                        # defaults: quarto, ink palette, a5, 300dpi, PNG
"$AEP_CLI" cover --workspace <ws> --palette oxblood --pdf
"$AEP_CLI" cover --workspace <ws> --json                 # machine-readable (style/format/design_digest/fonts/text)
"$AEP_CLI" cover --workspace <ws> --remove               # remove (source cover untouched)

# hanze-academic (issue #100's layout; --template is an alias of --style)
"$AEP_CLI" cover --workspace <ws> --template hanze-academic \
  --accent "#7A2222" --motif globe \
  --series "STUDIES IN CRITICAL SOCIAL SCIENCES · 229" \
  --subtitle "世界市场中的社会运动史与批判" \
  --note-line "内部研究译本　不公开分发"
```

The command line only supplies fields metadata cannot carry (series line, motif, accent,
disclaimer); title, credits, and the imprint line still come from `publication.json`.
`--accent` / `--motif` / `--series` / `--subtitle` / `--publisher-line` / `--note-line` /
`--credit-role` are **stored in the registration**, so build-time re-rendering reuses them —
`auto_sync` never wipes a command-line-styled cover.

Artifacts:

| File | Role |
|---|---|
| `structured/raw/media/cover-generated.png` / `.jpg` | the image; build publishes it as `media/cover-generated.{png,jpg}` |
| `preprocessing/cover-generated.json` | registration: `style`, `format`, `overrides`, `design_digest`, `sha256`, fonts, the text actually set |
| `structured/raw/media/cover-generated.pdf` | only with `--pdf`; for print proofing (not in the EPUB) |

**Output format**: `--format png|jpeg`; empty means the layout default — `quarto` uses PNG
(crisp flat colour), `hanze-academic` uses JPEG q92 (photographic paper grain, much smaller).
Switching format deletes the other suffix, so two versions never coexist.

| Layout | Default | Why |
|---|---|---|
| quarto | `png` | large flat areas and reversed type stay clean losslessly |
| hanze-academic | `jpeg` (q92) | the grain is continuous tone; JPEG is roughly a quarter of the PNG |

Afterwards `build` writes `properties="cover-image"` and `<meta name="cover">`, and logs
`cover_generated_used`. **Without a registration no cover appears**: build only *uses* and
*syncs* an existing registration.

## Layout (quarto, 界栏)

The design logic, most important first:

1. **A single full-bleed ground.** Books are told apart by **palette** (table below), so a
   shelf of them looks like one series without looking copy-pasted.
2. **Flush left, big type.** Chinese titles with few characters must still hold the page, so
   the size adapts to the content: short titles grow to 88% of the measure (at most 1.45× the
   base size); long titles drop to 0.75× and wrap — "few characters big, many characters
   steady".
3. **The double hairline at the left edge** (one thick, one thin, full height) is this
   layout's signature: a book's fore-edge, deliberately quiet.
4. **A short rule under the title** (30% of the measure) separates title from subtitle; the
   **original title is italic** at 60% strength, so Chinese and source text never mix.
5. **Credits bottom-left, signature bottom-right**, closed by a foot rule: the brush
   signature is this cover's sign-off.

### Palettes (quarto)

| Palette | Ground | Type | Accent |
|---|---|---|---|
| `ink` (default) | `#171A20` | `#F5F0E6` | `#C9A227` |
| `oxblood` | `#5B1B22` | `#F2EADD` | `#D8B26E` |
| `forest` | `#1D3A2F` | `#F1EDDF` | `#CBB27A` |
| `indigo` | `#1B2A55` | `#F3EFE4` | `#C9B37E` |
| `aubergine` | `#3A2340` | `#F3ECEE` | `#D9A7A0` |
| `slate` | `#22333B` | `#F0EEE7` | `#A8C3B5` |
| `rust` | `#6B2E17` | `#F5EDDF` | `#E3C08A` |
| `paper` | `#F4EFE3` (light) | `#1A1A1A` | `#8A2B2B` |

`paper` is the light variant for the "light books" in a series: paper ground, ink type, same
skeleton.

### Ratios (quarto, `QUARTO_GEOM`/`QUARTO_TYPE` in `src/auto_epublizer/cover.py`)

| Element | Ratio |
|---|---|
| Measure | `9.0%W` margin on both sides (measure = `82%W`) |
| Left rules | main line at `6.2%W`, thin line 3.4pt to its left; from `6.5%H` to `94.5%H` |
| Series baseline | `8.5%H` (preceded by a small accent square) |
| Title ink top | `25.5%H` |
| Size: title base / subtitle / original / original sub / credits / series / signature | `9.6 / 3.05 / 2.75 / 2.50 / 2.40 / 2.45 / 2.60 %W` |
| Actual size at 600px wide | title 57.6px; subtitle 18.3; original 16.5; original sub 15.0; credits 14.4; signature 15.6 |
| Rule under title | `3.0%H` below the title, `30%W` long |
| Last credit line ink bottom | `87.8%H` |
| Foot rule / signature baseline | `90.6%H` / `94.0%H` |

If the title group would collide with the credits, the whole block scales by 0.90 per step (at
most three steps) — it never overlaps.

## Layout two: hanze-academic 汉译学术本 (issue #100)

A 1600×2400 design canvas (A5 at 300dpi, ≈10.8 px/mm). **Coordinates are written in design
pixels and the whole board is scaled and centred at render time**, so changing the trim only
changes the paper margin — the layout never distorts.

### Frame and paper

| Element | Value (design px) |
|---|---|
| Paper | cream `#F0E7D4` + fine grain + low-frequency mottling + brown vignette (pure Python, deterministic, no numpy/PIL) |
| Outer frame | `[58,58,1558,2342]`, 3px, accent |
| Inner frame | `[72,72,1544,2328]`, 1px, gold `#A38248` |
| Corner ticks | 46px inward from each inner corner, 2px gold |

### Four text blocks (top to bottom, all centred)

| Line | Design y | Size | Colour | Tracking |
|---|---|---|---|---|
| Series line (small English caps) | 150 | 30 | muted `#6A6252` | 5 |
| Rule (gold, half-width 300 + centre dot) | 205 | — | gold | — |
| Chinese title | ink top 250 | 168→96 adaptive (wraps only if still too wide) | accent | 10 |
| Chinese subtitle | 500 | 60 | ink `#22201C` | 6 |
| Original title | 620 | 55 | `#4A4E3C` | 3 |
| Original subtitle (up to 2 lines) | from 680 | 40 | `#5E5242` | 1 |
| Credits | from 930 | 42 | ink | 2 |
| Foot rule (gold, half-width 330) | 1720 | — | gold | — |
| Signature "马加丹汉化组　译" | 1800 | 68 | ink | 10 |
| Series mark "汉 译 学 术 本" | 1896 | 40 | muted | 6 |
| Imprint "BRILL · 2023" | 2020 | 34 | muted | 8 |
| Disclaimer | 2080 | 30 | `#7E6E58` | 2 |

Blocks are positioned by **ink top and pushed down in order**: a wrapped title moves every
later block down instead of overlapping it.

### Motif band (`--motif`, 1000–1650)

| Value | Drawing | For |
|---|---|---|
| `none` (default) | nothing | frame and type only; do not invent a motif |
| `globe` | graticule globe (r≈236; 15/30/45/60/75° meridians + parallels + heavy equator), two orbit arcs, six nodes | world market / global history |
| `arch` | equilateral pointed arch (two arcs of radius = arch width meeting at the apex) + three-light tracery + apex trefoil, overlaid with 46px manuscript ruling | monastic / manuscript / medieval |

Accent per book (`--accent`, or a `--palette` preset): ochre `#7A2222` / forest `#1A3E2C` /
moss `#1B3428` / ink `#22201C` / navy `#1F3350` / plum `#5B2140`.

> **Small type obeys the same floor**: the issue's original 27–34px lines render at only
> 10–13px at 600px wide, so `TYPE` lifts them to the 14px equivalent through `MIN_TYPE_FRAC`
> (skeleton unchanged). `tests/test_cover_hanze.py::test_hanze_legibility_floor_at_600px`
> guards it.

## The previous layout (disabled)

The `magadan` layout (white page + band + stripe + right-aligned title group) is **disabled**:
the rendering path is gone, and `style: magadan` in config or a design sheet errors with
"unknown style … (the magadan layout is disabled)". Workspaces whose cover was generated with
it keep their PNG and record; re-running `cover` re-renders with the current layout (the
record's `style` becomes `quarto`).

## Design sheet `preprocessing/cover-spec.json` (optional, agent-written)

Anything metadata cannot carry — subtitle, original subtitle, series name, a small line above
the title, responsibility lines — comes from here. Field names are fixed; unknown fields are
an error.

```json
{
  "style": "quarto",
  "series": "拜占庭历史文献集成",
  "lead": "前皇帝约翰尼斯 · 坎塔库泽努斯",
  "title": "史书",
  "subtitle": "伊斯兰共和国的权力焦虑",
  "original_title": "Ioannis Cantacuzeni Eximperatoris Historiarum",
  "original_subtitle": "Anxieties of Power in the Islamic Republic",
  "credits": ["[东罗马] 约翰尼斯 · 坎塔库泽努斯 著", "[德] 卢多维库斯 · 叔彭努斯 校订"],
  "imprint": "马加丹汉化组",
  "palette": "oxblood",
  "size": "a5"
}
```

The hanze-academic sheet has a few extra fields (leave unused ones out):

```json
{
  "style": "hanze-academic",
  "palette": "ochre",
  "series": "STUDIES IN CRITICAL SOCIAL SCIENCES · 229",
  "subtitle": "世界市场中的社会运动史与批判",
  "original_title": "Global Marx",
  "original_subtitle": "History and Critique of the Social Movement in the World Market",
  "credits": ["[德] 马蒂亚斯 · 米德尔 等 著"],
  "motif": "globe",
  "series_mark": "汉 译 学 术 本",
  "publisher_line": "BRILL · 2023",
  "note_line": "内部研究译本　不公开分发",
  "credit_role": "译"
}
```

Defaults when a field is absent:

| Field | Default source |
|---|---|
| `style` | config `cover.style` (default `quarto`); `--style`/`--template` wins; `quarto` or `hanze-academic` |
| `title` | `meta.title_translated` → `meta.title`; both empty → error "no title" |
| `original_title` | `meta.title` (omitted when identical to the displayed title) |
| `subtitle` / `original_subtitle` | empty (**never slice sentences out of `description`**) |
| `credits` | `creator 著` + `translator 译`, one per line |
| `imprint` | config `cover.imprint` (default "马加丹汉化组"; empty string = none) |
| `palette` / `size` | config `cover.palette` / `cover.size` (empty palette = layout default: quarto→`ink`, hanze→`ochre`) |
| `format` | config `cover.format`; empty = layout default (quarto→png, hanze→jpeg) |
| `accent` / `motif` / `series_mark` / `publisher_line` / `note_line` / `credit_role` | hanze only: accent, motif, series mark, imprint line, disclaimer, signature suffix (CLI flags override) |

Three rules for writing the design sheet:

1. **State facts only**: if nationality, office, or the exact role (editor/translator) is
   unknown, write "某某 著" — do not add "[Ukraine]" from memory.
2. **Do not cut sentences**: a subtitle comes from the title/copyright page, or stays empty.
3. **Break lines explicitly** with `\n` or an array: where a line breaks is your typesetting
   decision.

## Trim sizes and dpi

`a5` (148×210, default) / `32k` / `b5` / `16k`, the same set as `pdf --size`.
`--dpi` defaults to 300 (A5 → 1749×2481, plenty for an EPUB cover).

## Fonts

| Use | Discovery order | When missing |
|---|---|---|
| CJK serif (required) | Noto Serif CJK / Source Han Serif / Songti | **hard error** |
| Latin serif (optional) | Nimbus Roman → Times New Roman → Liberation Serif | original title falls back to the CJK font, and the command says so |
| Latin italic (optional) | same family's `-Italic`/`-Oblique` | quarto's original title falls back to roman (still Latin serif) |
| Brush signature (optional) | Zhi Mang Xing → Ma Shan Zheng → Long Cang → STXingkai | signature degrades to serif (same position), and the command says so |

Explicit paths: config `cover.font_serif` / `cover.font_latin` / `cover.imprint_font`.
`"$AEP_CLI" doctor` reports the chosen files and anything missing under `cover-fonts`.

> Brush fonts are third-party OFL webfonts and are **not distributed with this repository**.
> Install one (e.g. [Zhi Mang Xing](https://fonts.google.com/specimen/Zhi+Mang+Xing)) into the
> system font directories, or point `cover.imprint_font` at a `.ttf`.

## Red lines

1. **Never replace a source cover**: with a confirmed `cover.json` the generated image is not
   used (the command says so right away), and an unconfirmed candidate is never promoted to
   cover.
2. **No semantic guessing**: subtitle, nationality, and role stay empty or neutral without
   evidence.
3. **Outside translation QC**: the generated cover is a typeset artifact — it does not enter
   G0, does not change unit state, and does not touch `align/`.
4. **Build syncs, never creates**: without a registration build adds no cover; `auto_sync`
   only re-renders an existing one when metadata or the design sheet changed.

## Troubleshooting

| Symptom / event | Meaning | Action |
|---|---|---|
| `没有书名，无法生成封面` | both title fields are empty | run `meta --title`, or set `title` in the design sheet |
| `未知版式 … 已停用` | `style: magadan` (or any other name) | drop the field; only `quarto` / `hanze-academic` exist |
| `未知主色` | a quarto palette name (e.g. `oxblood`) on hanze | use a hanze preset (ochre/forest/moss/ink/navy/plum) or `--accent #RRGGBB` |
| `未知意象` | misspelled `--motif` | use `none` / `globe` / `arch` |
| `未知封面格式` | misspelled `--format` | use `png` / `jpeg` |
| `未知色板 / 未知开本` | misspelled, or a palette from the retired layout | use the table above (`crimson` belonged to the old one) |
| `找不到中文字体` | no CJK font | install `fonts-noto-cjk` or set `cover.font_serif` |
| `⚠ 未找到行书字库` | brush font missing, degraded | install one or set `cover.imprint_font`; accepting the fallback is fine |
| event `cover_regenerated` | metadata/design changed, re-rendered during build | normal; confirm the cover text changed |
| event `cover_generated_stale` | design changed while `cover.auto_sync=false` | re-run `cover`, or enable `auto_sync` |
| event `cover_generated_external` | registration points outside the standard location | re-run `cover` |
| event `cover_generated_failed` | sync failed during build | read `reason`, fix, re-run `cover`; the build itself is not blocked |
