<!-- i18n: source=2026-09-05-scanned-pdf-issue-checklist.zh.md sha256=94fb2d38209ea2849dee9d2a31b36fcdde736748ea1a620e035b7df3b1cee0f7 -->
> **English** | [中文](2026-09-05-scanned-pdf-issue-checklist.zh.md)

# Scanned-file PDF full-flow issue checklist (DouBao JS authoritative guide 15-issue measurement)

> Date: 2026-09-05　Source: DouBao cloud agent's measurement of the《JavaScript: The
> Definitive Guide》6th edition scanned file (1018 pages, Chinese edition) → EPUB full flow,
> 15 issues' root causes and handling.
> Status: experience retained; among them the **main-repo gaps have been verified item by
> item** (the ✅/❌ below).

## Trigger scenario

The complete problem set from running a scanned PDF (especially code/technical books)
through both the traditional OCR and MinerU routes. This checklist supplements the two
lessons of "the same task": `scanned-pdf-operations.md` (solution selection/batching/
splitting) and `agent-translation-workflow.md` (translation workflow).

## Issue classification analysis

### Category A: real main-repo gaps (verified, can be merged as fixes)

| # | Issue | Main-repo status (verified 2026-09-05) |
|---|---|---|
| 7 | `markdown_to_xhtml` only supports inline backticks, not ``` fenced code blocks | ❌ `html.py` only has `_CODE_RE` (inline); fenced code goes entirely into `<p>` |
| 8 | `_inline` does not support `\[` escaping (link first then escape, escaping ineffective) | ❌ no escape handling |
| 11 | link regex `\[([^\]]+)\]\(([^)]+)\)` does not validate the URL; `[9](1个数字元素)` is misjudged as a link → epubcheck RSC-007 | ❌ `_LINK_RE` matches any `[x](y)` |
| 9 | code-block placeholder uses `\x00` → illegal XML character FATAL | ⚠️ the main repo **does not yet have** a code-block placeholder (same as above); when fenced support is implemented in the future, **control characters must not be used as placeholders** |
| 12 | manually creating publication.json with units.status set to "built" → build skips | ✅ a usage trap, not a code bug; the state machine is managed by the CLI, and a manually created workspace must be `pending` |
| 13 | manually creating publication.json with units.meta missing `rel_path`/`region`/`level` → build cannot find the source | ✅ usage trap; let CLI `init` generate it rather than hand-writing |

> Cover (DouBao report #2 says "not supported"): **the main repo now supports**
> `cover_media` + `<meta name="cover">` + spine `linear="no"` (the cover unit is recognized
> automatically). DouBao was at the old repo state at the time, and it is hard to
> automatically determine the cover from a full-page scanned image; the manual
> spine/playOrder patch injected (reports #14/#15) is no longer needed in the new repo.

### Category B: MinerU/OCR solution-level lessons (consistent with the previous two lessons; here focusing on new details)

- **#1 Line breaks not handled**: when OCR writes block by block, each line is one text
  block → each line becomes an independent `<p>`. Traditional OCR inevitably requires
  paragraph merging (v1 ineffective / v2 over-merged / v3 conservative threshold, tuned
  repeatedly) — **switch directly to MinerU**.
- **#3 Single-unit build loses nav**: the whole book's markdown as a single unit → nav has
  only 1 item. Units must be split by chapter.
- **#4 Inconsistent heading levels**: MinerU output for the same book mixes `#`/`##` (ch1
  `#`, ch2 `##`, ch6 `## 第6章`); `build` generates the TOC from the unit `title`, and the
  first line `#` of the structured md is the heading. → Unify each chapter's first line as
  `# 第X章 标题`.
- **#5/#6 Manual splitting**: ch1's title page is a full-page large image with no "第1章"
  prefix → TOC page-number location fails; when splitting, the write path is misaligned and
  overwrites the original ch01. → When splitting chapters, **first write a temporary file
  then rename from back to front**, and heading determination is left to the agent manually
  (see `scanned-pdf-operations.md` §3).
- **#10 No blank line before/after code blocks**: the placeholder and text in the same block
  cannot be recognized by `re.match` → markdown cleanup must ensure blank lines before and
  after code blocks.

### Category C: epubcheck error codes → root cause cross-reference (debug quick reference)

| epubcheck error | Usual root cause | Handling |
|---|---|---|
| FATAL "invalid XML character (Unicode: 0x0)" | placeholder/content contains control characters | clean null characters; use a printable string for the placeholder |
| RSC-007 "Referenced resource … could not be found" | square brackets mis-parsed as a link; wrong resource path | link regex validates the URL; check href |
| "Element type spine must be followed by attribute" | tag concatenation error during XML injection | only change tag content, not structure |
| "playOrder value not 1 / gaps" | NCX not renumbered after manually inserting the cover | renumber consecutively |

## Handling checklist (fix suggestions when merging into the main repo)

1. **Fenced code blocks**: `html.py` block-level preprocessing — extract ``` blocks →
   `<pre><code class="language-xxx">`; use a printable marker for the placeholder (e.g.
   `__AUTOEPUBLIZERCODEBLOCK__`), **control characters forbidden**.
2. **`_inline` escape order**: handle `\[`/`\]` escaping before link matching, or have the
   link regex exclude escapes first.
3. **`_LINK_RE` URL validation**: only treat legal protocols such as http/https/#/mailto as
   links, otherwise treat as plain text (`[9](1个数字元素)` is not a link). Refer to the way
   `_DANGEROUS_URL` is written.

> After fixing, regression must be added: fenced code-block rendering, `\[` escaping not
> producing a link, `[x](non-URL)` not generating `<a>`.

## Reproduction / verification

```bash
# Current main repo: `[9](1个数字元素)` will be rendered as <a> (the source of RSC-007)
uv run python -c "from auto_epublizer.build.html import _inline; print(_inline('[9](1个数字元素)'))"
# Fenced code blocks currently go into <p> as-is:
uv run python -c "from auto_epublizer.build.html import render_document; print('```' in render_document('T','```js\nlet a=1\n```', lang='zh-CN'))"
```

## Related

- Solution selection/splitting/batching: `2026-09-05-scanned-pdf-operations.md`
- Translation workflow: `2026-09-05-agent-translation-workflow.md`
- MinerU backend: `2026-09-05-scanned-pdf-mineru-first.md`, `src/auto_epublizer/ingest/mineru.py`
