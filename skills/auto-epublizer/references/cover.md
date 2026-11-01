<!-- i18n: source=cover.zh.md sha256=832126325d659eeb3b00b5fc0ad3282dabf1b1d3a3bd7409d6b056a6cb344f6c -->
> **English** | [中文](cover.zh.md)

# Generated cover (quarto, 界栏)

For books with **no usable cover**: plain text / Markdown / DOCX / HTML sources have no cover
image at all, and a scanned book's first page is not automatically its cover (a candidate only
becomes one after `preprocessing/cover.json` is confirmed). Such books show up blank on the
shelf and lock screen. This flow gives them one shared typeset cover: `quarto` (界栏) —
full-bleed ground, reversed flush-left title, double hairline at the left edge, a short accent
rule, italic original title, credits bottom-left, signature bottom-right.

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
"$AEP_CLI" cover --workspace <ws>                        # defaults: quarto, ink palette, a5, 300dpi
"$AEP_CLI" cover --workspace <ws> --palette oxblood --pdf
"$AEP_CLI" cover --workspace <ws> --json                 # machine-readable (style/design_digest/fonts/text)
"$AEP_CLI" cover --workspace <ws> --remove               # remove (source cover untouched)
```

Artifacts:

| File | Role |
|---|---|
| `structured/raw/media/cover-generated.png` | the image; build publishes it as `media/cover-generated.png` |
| `preprocessing/cover-generated.json` | registration: `style`, `design_digest`, `sha256`, fonts, the text actually set |
| `structured/raw/media/cover-generated.pdf` | only with `--pdf`; for print proofing (not in the EPUB) |

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

Defaults when a field is absent:

| Field | Default source |
|---|---|
| `style` | config `cover.style` (default `quarto`); `--style` wins |
| `title` | `meta.title_translated` → `meta.title`; both empty → error "no title" |
| `original_title` | `meta.title` (omitted when identical to the displayed title) |
| `subtitle` / `original_subtitle` | empty (**never slice sentences out of `description`**) |
| `credits` | `creator 著` + `translator 译`, one per line |
| `imprint` | config `cover.imprint` (default "马加丹汉化组"; empty string = none) |
| `palette` / `size` | config `cover.palette` / `cover.size` |

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
| `未知版式 … 已停用` | `style: magadan` (or any other name) | drop the field; only `quarto` exists |
| `未知色板 / 未知开本` | misspelled, or a palette from the retired layout | use the table above (`crimson` belonged to the old one) |
| `找不到中文字体` | no CJK font | install `fonts-noto-cjk` or set `cover.font_serif` |
| `⚠ 未找到行书字库` | brush font missing, degraded | install one or set `cover.imprint_font`; accepting the fallback is fine |
| event `cover_regenerated` | metadata/design changed, re-rendered during build | normal; confirm the cover text changed |
| event `cover_generated_stale` | design changed while `cover.auto_sync=false` | re-run `cover`, or enable `auto_sync` |
| event `cover_generated_external` | registration points outside the standard location | re-run `cover` |
| event `cover_generated_failed` | sync failed during build | read `reason`, fix, re-run `cover`; the build itself is not blocked |
