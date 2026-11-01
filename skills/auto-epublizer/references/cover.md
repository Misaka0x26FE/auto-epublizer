<!-- i18n: source=cover.zh.md sha256=211d577d3f44d66cae1cb5e8cb524d561eb3bf31457d3904f53e9647621d4c6e -->
> **English** | [中文](cover.zh.md)

# Generated cover (Magadan layout)

For books with **no usable cover**: plain text / Markdown / DOCX / HTML sources have no cover
image at all, and a scanned book's first page is not automatically its cover (a candidate only
becomes one after `preprocessing/cover.json` is confirmed). Such books show up blank on the
shelf and lock screen. This flow gives them one shared typeset cover: white ground, full-width
band at the top, a vertical stripe on the right, a right-aligned serif title group, and a brush
signature near the bottom.

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
text) do you write `preprocessing/cover.json` and turn a candidate into the source cover. If it
does not check out, use this chapter's generated cover instead — never take "looks like a
cover" as evidence.

## Generate / remove

```bash
"$AEP_CLI" cover --workspace <ws>                        # defaults: indigo palette, a5, 300dpi
"$AEP_CLI" cover --workspace <ws> --palette maroon --pdf # different palette + print PDF
"$AEP_CLI" cover --workspace <ws> --json                 # machine-readable (design_digest/fonts/text)
"$AEP_CLI" cover --workspace <ws> --remove               # remove (source cover untouched)
```

Artifacts:

| File | Role |
|---|---|
| `structured/raw/media/cover-generated.png` | the image; build publishes it as `media/cover-generated.png` |
| `preprocessing/cover-generated.json` | registration: `design_digest`, `sha256`, fonts, the text actually set |
| `structured/raw/media/cover-generated.pdf` | only with `--pdf`; for print proofing (not in the EPUB) |

Afterwards `build` writes `properties="cover-image"` and `<meta name="cover">`, and logs
`cover_generated_used`. **Without a registration no cover appears**: build only *uses* and
*syncs* an existing registration — it never decides on its own that a book should have one.

## Design sheet `preprocessing/cover-spec.json` (optional, agent-written)

Anything metadata cannot carry — subtitle, original subtitle, series name, a small line above
the title, responsibility lines — comes from here. Field names are fixed; unknown fields are an
error (never silently ignored).

```json
{
  "series": "拜占庭历史文献集成",
  "lead": "前皇帝约翰尼斯 · 坎塔库泽努斯",
  "title": "史书",
  "subtitle": "伊斯兰共和国的权力焦虑",
  "original_title": "Ioannis Cantacuzeni Eximperatoris Historiarum",
  "original_subtitle": "Anxieties of Power in the Islamic Republic",
  "credits": ["[东罗马] 约翰尼斯 · 坎塔库泽努斯 著", "[德] 卢多维库斯 · 叔彭努斯 校订"],
  "imprint": "马加丹汉化组",
  "palette": "crimson",
  "size": "a5"
}
```

Defaults when a field is absent:

| Field | Default source |
|---|---|
| `title` | `meta.title_translated` → `meta.title`; both empty → error "no title" |
| `original_title` | `meta.title` (omitted when identical to the displayed title, so it is not printed twice) |
| `subtitle` / `original_subtitle` | empty (**never slice sentences out of `description`** — that is semantic guessing) |
| `credits` | `creator 著` + `translator 译`, one per line |
| `imprint` | config `cover.imprint` (default "马加丹汉化组"; empty string = no signature) |
| `palette` / `size` | config `cover.palette` / `cover.size` |

Three rules for writing the design sheet:

1. **State facts only**: if nationality, office, or the exact role (editor/translator) is
   unknown, write "某某 著" — do not add "[Ukraine]" from memory. The cover is a credit line,
   not an inference.
2. **Do not cut sentences**: a subtitle comes from the title/copyright page, or stays empty.
   Taking half a sentence from the blurb makes the cover speak for the author.
3. **Break lines explicitly** with `\n` or an array: where a line breaks is a typesetting
   decision you make, not something to leave to automatic wrapping.

## Palettes and trim sizes

| Palette | Band (primary) | Stripe |
|---|---|---|
| `indigo` (default, most used) | `#0D1168` | same |
| `blue` blue + gold edge | `#2C5F9E` | `#FECB00` |
| `maroon` | `#612326` | same |
| `purple` | `#4B2C65` | same |
| `crimson` | `#962311` | same |
| `brown` | `#5A2B1B` | same |
| `green` | `#236243` | same |
| `ink` | `#1A1A1A` | same |

Trim sizes match `pdf --size`: `a5` (148×210, default) / `32k` / `b5` / `16k`.
`--dpi` defaults to 300 (A5 → 1749×2481, plenty for an EPUB cover).

## Fonts

| Use | Discovery order | When missing |
|---|---|---|
| CJK serif (required) | Noto Serif CJK / Source Han Serif / Songti | **hard error** (no CJK, no layout) |
| Latin serif (optional) | Nimbus Roman → Times New Roman → Liberation Serif | original title falls back to the CJK font, and the command says so |
| Brush signature (optional) | Zhi Mang Xing → Ma Shan Zheng → Long Cang → STXingkai | signature degrades to serif (same position), and the command says so |

Explicit paths: config `cover.font_serif` / `cover.font_latin` / `cover.imprint_font`.
`"$AEP_CLI" doctor` reports the chosen files and anything missing under `cover-fonts`.

> Brush fonts are third-party OFL webfonts and are **not distributed with this repository**.
> For the brush signature, install one (e.g.
> [Zhi Mang Xing](https://fonts.google.com/specimen/Zhi+Mang+Xing)) into the system font
> directories, or point `cover.imprint_font` at a `.ttf`.

## Layout (do not hand-edit the ratios)

Ratios live in `GEOM`/`TYPE`/`GAPS`/`INK` in `src/auto_epublizer/cover.py`, all measured from
reference samples:

| Element | Ratio |
|---|---|
| Top band | `1.35%H` from the top, `5.28%H` tall, full width |
| Right stripe | left edge `89.7%W`, width `2.1%W` (`8.2%W` white gutter on the right) |
| Text column | right edge `88.2%W` |
| Title group origin | `30.99%H` (ink top of the title) |
| Title / subtitle / original title / original subtitle / credits | `7.67 / 3.75 / 3.83 / 2.95 / 2.94 %W` |
| Signature | centred on `47%W`, ink top `91.91%H` |

Changing these constants changes the design: re-run `tests/test_cover_render.py`, which
includes ink-position assertions.

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
| `没有书名，无法生成封面` | both `meta.title` and `meta.title_translated` are empty | run `meta --title`, or set `title` in the design sheet |
| `未知色板 / 未知开本` | misspelled name | use the tables above |
| `找不到中文字体` | no CJK font on the system | install `fonts-noto-cjk` or set `cover.font_serif` |
| `⚠ 未找到行书字库` | brush font missing, degraded to serif | install one or set `cover.imprint_font`; accepting the fallback is fine |
| event `cover_regenerated` | metadata/design changed, re-rendered during build | normal; confirm the cover text really changed |
| event `cover_generated_stale` | design changed while `cover.auto_sync=false` | re-run `cover`, or enable `auto_sync` |
| event `cover_generated_external` | registration points outside the standard location | re-run `cover` (standard is `structured/raw/media/`) |
| event `cover_generated_failed` | sync failed during build (fonts/design sheet) | read `reason`, fix, re-run `cover`; the build itself is not blocked |
