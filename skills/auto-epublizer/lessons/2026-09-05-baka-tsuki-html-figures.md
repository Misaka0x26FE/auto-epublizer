<!-- i18n: source=2026-09-05-baka-tsuki-html-figures.zh.md sha256=be98777dfbe4dd633bbd55ad5d81c878741ea32946c9a25f1a70de201b841ae2 -->
> **English** | [中文](2026-09-05-baka-tsuki-html-figures.zh.md)

# Illustration paragraph fidelity in Baka-Tsuki source-site HTML

> Date: 2026-09-05　Source: DouBao GT2 (Genesis Testament A Certain Magical Index GT2)
> measurement.
> Status: the build-side defect is fixed (1766e7a); this document retains "how to judge and
> how to fix when encountering the same type of situation".

## Trigger scenario

The input is **HTML exported from a Baka-Tsuki / MediaWiki-family source site** (`init`
extracts via pandoc); in the body, illustrations appear in a three-line structure:

```html
<figure class="mw-default-size" typeof="mw:File/Thumb">
<a href="/project/index.php?title=File:GT_Index_v02_055.jpg" class="mw-file-description"><img src="/path/to/media/<hash>.jpg" class="mw-file-element" decoding="async" srcset="…" data-file-width="…" data-file-height="…" width="300" height="426" /></a>
</figure>
```

- The three lines are `<figure>`, `<a>…<img …/></a>`, `</figure>` respectively; after
  pandoc extraction, `<img src>` is often rewritten to an **absolute local path in the
  workspace media** (`…/structured/raw/media/<hash>.jpg`).

## Criterion (how to hit this situation)

1. `<figure` and `<img src="…">` appear in the structured unit md;
2. after build, the corresponding illustration in the finished EPUB is **missing**;
3. the source-site original image URL is downloadable, but build cannot find the local file.

**Root cause (measurement-corrected)**: the build side `collect_media`
(`src/auto_epublizer/build/__init__.py`, whose `_HTML_FIG_IMG`/`_HTML_IMG` rewrite logic is
around L426) uses `_HTML_FIG_IMG`/`_HTML_IMG` to extract `<img src>` and resolves the file
by `raw/media/`; **if the file is not found → the reference is dropped**. `\s*` allows
newlines, so "three consecutive lines / a blank line in between / carrying a little text"
can all be recognized (measured); the scenario that actually loses the image is:

- in the translated segment the `<img …>` **entire line was deleted/rewritten** (DouBao
  GT2: 8 units' translated image segments lacked the `<img src>` line);
- or the file pointed to by `<img src>` is not in `structured/raw/media/` (pandoc
  extraction failed / not downloaded).

## Handling

1. **Keep the `<img>` line in the translated segment**: in `translation/<unit>.md` and
   `align/<unit>.jsonl`, the image segment must **keep the complete line containing
   `<img src="…">`** (it may be kept together with `<figure>/<a>`), tgt=src (do not
   translate alt/srcset/path); do not split it into multiple segments, do not delete
   `<img>`.
2. **Verify the file exists**: confirm the `<img src>` relative path can resolve to a file
   under `structured/raw/media/`; if not, download the original image from the source site
   into that directory with the file name aligned.
3. **build verification**: after `auto-epublizer build`, unpacking `OEBPS/*.xhtml` should
   contain `<img src="media/…">`; `qa` should show `media_lost == 0`.
4. **Multi-image units**: handle all the multiple illustrations within a chapter this way
   (this time ch07/10/12/18/23/32/36/45).

## Already-fixed main-repo problems (same-type defects, do not hit again)

| Problem | Root cause | Fix |
|---|---|---|
| manifest media id contains `/` → epubcheck RSC-005 | `item_id = epub_path` (contains `/`, an invalid XML name) | `1766e7a`: `epub_path.replace("/", "_")` |
| spine missing `toc="ncx"` → RSC-005 | NCX is always generated but the spine does not reference it | `1766e7a`: `<spine toc="ncx">` |
| `import --terms` crashes on first call | `row_to_entry` calls `.strip()` on a None value | `1766e7a`: `(row.get(x) or "")` |

## Reproduction / verification

```python
# collect_media can recognize three forms (three consecutive lines / blank line in between / carrying text); the key is that the file exists
from auto_epublizer.build import collect_media
import pathlib

media = pathlib.Path("/tmp/opencode/med")
media.mkdir(exist_ok=True)
(media / "x.png").write_bytes(b"PNG")
for md in [
    '<figure>\n<a><img src="media/x.png"/></a>\n</figure>\n',  # three consecutive lines
    '<figure>\n\n<a><img src="media/x.png"/></a>\n\n</figure>\n',  # blank line in between
    '<figure>\n<a><img src="media/x.png"/></a>\n夹带文本\n</figure>\n',  # carrying text
]:
    out, files = collect_media(md, media)
    assert "![](media/x.png)" in out and len(files) == 1, md[:20]

# Counter-example: `<img>` exists but the file is missing → the reference is replaced with empty (the image is dropped)
out, files = collect_media('<figure>\n<a><img src="media/gone.png"/></a>\n</figure>\n', media)
assert "![](media/gone.png)" not in out and not files
```

Full end-to-end: `tests/test_build.py::test_build_epub_embeds_media_files` (including media
id/spine regression assertions).

## Related

- Source-site HTML extraction: `references/ingest.md` (pandoc route);
- md image-reference forms and provenance reconciliation: `docs/pdf-content-spec.md` §2.3,
  `references/qa.md` (`media_lost`).
