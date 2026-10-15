<!-- i18n: source=2026-10-15-epub-source-media-normalization.zh.md sha256=bf829ff2ec497c1b24b7f0f359bfe9b4bf13feec8f2716ae6ce269714ace8909 -->
> **English** | [中文](2026-10-15-epub-source-media-normalization.zh.md)

# EPUB sources with absolute media paths: machine paths leak into the workspace and nested illustrations are lost from the product

> Date: 2026-10-15　Source: full-project review (`docs/plans/2026-10-14-review-and-repair.md`,
> group D), reproduced with a synthetic EPUB and fixed at the root. Status: **fixed**
> (`ingest/epub_reader.py::read_epub` now calls `normalize_media_refs`; regression
> `tests/test_ingest_boundary.py::test_epub_source_conserves_*`).

## When this happens

The source is an **EPUB** (or a Kindle container converted by calibre) and its images live in
a **subdirectory** (e.g. `OEBPS/img/pic.png`). After read_epub runs pandoc with media
extraction:

- the md under `structured/` references images by **absolute path**
  (`/tmp/.../raw/media/img/pic.png`) — machine paths leak into a persisted, git-tracked artifact;
- at build time the normalised absolute path resolves to nothing (`media_root/tmp/...` does
  not exist) and the basename fallback cannot find a file nested in a subdirectory either →
  the **illustration is lost from the product** (only `media_dropped` and a provenance block
  remain).

## Criterion (how to tell you may have hit it)

1. The md under `structured/` has **absolute** image references
   (`grep -n '!\[.*\](/[^)]*'`);
2. `events.jsonl` carries `media_dropped`, or qa reports `epub_media_missing` /
   `E_MEDIA_EPUB_LOST`;
3. Unpacking the product shows images missing whose source had a subdirectory level (e.g.
   `media/img/pic.png` should exist).

Note the difference from the docx path: docx always went through `read_pandoc` with
normalisation; the **EPUB/Kindle chain used to skip that step**, so the mirrored fix belongs
in `read_epub`.

## Handling (how to fix)

1. The source is already fixed (since 2026-10-14): `read_epub` calls
   `normalize_media_refs(run_pandoc(...), media_dir)` exactly like docx — absolute paths become
   workspace-relative `raw/media/<name>`, the extra `media/` level is flattened and image
   attribute blocks are stripped;
2. If a workspace still holds absolute paths (old artifacts): **re-run ingest/structure
   preparation** (or hand-edit the reference to `raw/media/<correct relative path>`, keeping
   the subdirectory) → `build` → `qa` and confirm `epub_media_missing == 0`;
3. Do not "fix" it by copying images into the media root — that loses the hierarchy, diverges
   from the source, and silently overwrites same-named images.

## Reproduction/verification (minimal fixture)

Synthetic EPUB: `OEBPS/c1.xhtml` with `<h1>/<h2>` + a footnote + `<img src="img/pic.png">`,
and a real PNG at `OEBPS/img/pic.png`; then `orch.init(epub) → orch.build`:

```python
md = (store.structured_dir / "body/ch01.md").read_text()
assert "raw/media/img/pic.png" in md  # reference relativised
assert str(store.dir) not in md  # no machine absolute path may land in artifacts
# product: OEBPS/media/img/pic.png exists, body has <img src="media/img/pic.png">, footnote text present
```

Regression: `tests/test_ingest_boundary.py::test_epub_source_conserves_headings_footnote_and_nested_media`
(pandoc-gated via `skipif`, with an explicit skip reason).

## Code locations

- `src/auto_epublizer/ingest/epub_reader.py::read_epub` (normalisation call; `fixed`)
- `src/auto_epublizer/ingest/pandoc_reader.py::normalize_media_refs` (implementation; docx path already had it)
- Plan recording this experience: `docs/plans/2026-10-14-review-and-repair.md` §7, group D
