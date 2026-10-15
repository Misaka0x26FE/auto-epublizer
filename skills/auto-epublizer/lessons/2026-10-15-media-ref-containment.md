<!-- i18n: source=2026-10-15-media-ref-containment.zh.md sha256=0241bab47fffa85588eccac55da95d4732f61baa1d0cd7f447a16618e5655a04 -->
> **English** | [中文](2026-10-15-media-ref-containment.zh.md)

# Media references escaping the media directory: `../`, absolute paths and outward symlinks get read into the product

> Date: 2026-10-15　Source: full-project review (`docs/plans/2026-10-14-review-and-repair.md`,
> group D), reproduced with minimal bad files and fixed at the root. Status: **fixed**
> (`build/__init__.py::collect_media._resolve` containment check;
> `qa/provenance.py::_audit_inserts` aligned; regression in `tests/test_ingest_boundary.py`).

## When this happens

A source file (Markdown/HTML/DOCX/EPUB …) references images not by an ordinary relative
path but by:

- a `../…` chain (deep enough to leave the workspace, e.g. an absolute location such as
  `../../../../etc/…`);
- an absolute path (`/etc/hostname`, `/home/...`);
- a symlink inside the workspace pointing at an **outside** target.

When that happens, the build collects the **content of files outside the workspace** as media
and embeds it in the EPUB, and writes illegal member names such as `media/../../…` into the
product — an out-of-workspace read (leak into the product) plus broken EPUB member naming.

## Criterion (how to tell you may have hit it)

1. The md under `structured/` contains absolute or `..`-laden image references
   (`grep -n '!\[.*\](.*\.\.'`);
2. `events.jsonl` carries a `media_dropped` event (listing the refused references);
3. the qa `report.json` shows `epub_media_missing > 0` and provenance `E_MEDIA_EPUB_LOST`;
4. unpacking the product shows `..`-bearing member names under `OEBPS/media/` (only before
   the fix).

`media_dropped` / `E_MEDIA_EPUB_LOST` is a **hard gate**: escaping references are never
dropped silently, they block release.

## Handling (how to fix)

1. **Do not hand-edit those references into in-workspace paths** — first judge the origin: if
   the source itself carries escaping references (a dirty source), the right move is to let the
   boundaries on both sides do their job:
   - build side (already fixed): each candidate path is `resolve()`d (following symlinks) and
     must stay inside `structured/raw/media/`; anything escaping is refused and only recorded
     as dropped;
   - ingest side: media references on the pandoc path are rewritten to workspace-relative
     `raw/media/<name>`; EPUB sources follow the same rule (see the sibling lesson).
2. **Put the image into `structured/raw/media/`** (correct name/subdirectory), re-run `build`,
   then `qa` and confirm `E_MEDIA_EPUB_LOST` is back to zero;
3. If the reference is a source error (e.g. pointing at an external site), record
   `unresolved`/`absent` in `preprocessing/catalog.csv` and leave a trace in
   `analysis`/`repairs`, then follow the release rules.

## Reproduction/verification (minimal fixture)

```python
# 1) pure function: an existing out-of-workspace target must be dropped, never read
media_root = tmp_path / "structured/raw/media"
media_root.mkdir(parents=True)
secret = tmp_path / "outside.txt"
secret.write_text("SECRET")
ref = os.path.relpath(secret, media_root)  # "../../outside.txt"
rewritten, files, dropped = collect_media(f"![x]({ref})", media_root)
assert files == [] and dropped == [ref]  # before the fix: files carried the SECRET bytes

# 2) end to end: the product must not contain ".." members, and qa must block with
#    E_MEDIA_EPUB_LOST
```

Regression: `tests/test_ingest_boundary.py` (relative `..`, absolute path, outward symlink,
legitimate nested control, product member names, provenance block).

## Code locations

- `src/auto_epublizer/build/__init__.py::collect_media._resolve` (containment check; `fixed`)
- `src/auto_epublizer/qa/provenance.py::_audit_inserts` (same rule for inserts; `fixed`)
- Plan recording this experience: `docs/plans/2026-10-14-review-and-repair.md` §7, group D
