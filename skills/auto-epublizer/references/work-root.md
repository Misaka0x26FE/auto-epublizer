<!-- i18n: source=work-root.zh.md sha256=6f755d7ab0e8193ab583f1e2f6267657274080bd9758536992588d7725bd5476 -->
> **English** | [中文](work-root.zh.md)

# Work root (long-running multi-book workspace)

Use this when the user wants to translate/convert **many books over time**, not one. It sets up
a single directory holding one workspace per book plus a cross-book index.

## Generate it

```bash
auto-epublizer work-root <dir> [--force]
```

The command copies the repository's `template/work-root/` skeleton (the **authoritative**
template). Existing files are kept unless `--force`. Then put the next source in `inbox/`.

## What each component is for

| Component | Function |
|---|---|
| `AGENTS.md` | how this root works (red lines: one `.md` at the root, sha256 identity, no hand-editing, recompute numbers) |
| `config.example.yaml` | copy to `config.yaml`; key setting `paths.workspaces_dir: ./workspaces` |
| `inbox/` | sources not yet started (original name/bytes) |
| `sources/` | staging copies named `<slug>.<ext>` (input to `preprocess`) |
| `workspaces/<slug>/` | one standard book workspace per book (created by the CLI) |
| `docs/` | process docs: plans / specs / audits + the cross-book ledger |
| `references/` | cross-book shared baselines (read-only) |
| `README.md` | the user-facing explanation of the above |

## How to use it

1. **New book**: `cp inbox/<name> sources/<slug>.<ext>` →
   `auto-epublizer preprocess sources/<slug>.<ext> --workspace ./workspaces` → then drive the
   normal per-book loop (`status --json` → task cards → `import` / `g0` / `build` / `qa` /
   delivery).
2. **Cross-book overview**: `auto-epublizer status --all --workspace . --json` (three-tier
   progress: `released` / `built_not_released` / `preprocessing`) and
   `python3 docs/build_ledger.py` (recompute the ledger while retaining manual columns by unique slug).
3. **Identity is `publication.json.meta.source_sha256`**, never the file name. If the source was
   pre-processed (bookmarks injected, format converted), archive the untouched original with
   `preprocess --original <path>`.
4. **Numbers are always recomputed by the commands** — never hand-maintained.

## What to tell the user (relay this)

> 这是你的**长期工作区**：`inbox/` 放还没开工的原书；开工时复制到 `sources/<slug>.<ext>` 交给
> agent 处理；每本书成为 `workspaces/<slug>/` 下一个标准工作区；`docs/` 放过程文档与跨书台账；
> `references/` 放跨书共享资料。随时用 `auto-epublizer status --all` 看全部书的进度
> （已交付 / 已建未放行 / 仅预处理），`auto-epublizer ledger` 生成台账。源身份以 sha256 为准。

## Runnable operational guards (issue #47)

The generator also copies `docs/{pack_outbox,build_ledger,check_doc_links,check_tracked}.py`.
All four are Python 3.11+ standard-library scripts: no original repository dependency, network,
LLM, automatic staging, or pushing. The first two call the actual installed CLI; use
`--cli /absolute/path/to/auto-epublizer` outside an activated environment. They do not implement
another QA digest or progress calculation. Default paths come from the script's work root;
explicit relative arguments are relative to the shell's current directory. Run directly after
copying or generating a root; the empty ledger and documentation checks need no books.

```bash
python3 docs/build_ledger.py --workspace workspaces --output docs/工作台账.md
python3 docs/pack_outbox.py workspaces/book-a workspaces/book-b --batch 2026-10-17
python3 docs/check_doc_links.py --root .
python3 docs/check_tracked.py --repo workspaces/book-a
```

### Conservative delivery

List **every actual workspace in the batch** as positional packer arguments. For a nested layout,
pass the `book/` directory containing `publication.json`. Before any copying, the entire batch
must pass actual `status --json` with current `released=true`, `stale=false`, and `reason=ok`.
The packer then selects exactly `report.artifacts_epub` (relative paths are workspace-relative).
It neither guesses output files nor rejects a valid source-language conversion for lacking
translations. Any preflight failure prevents all copying; case-insensitive filename conflicts
also fail.

New batches default to `outbox/<batch>/epub/` (`--outbox` changes the root). Both existing complete
batches and interrupted batches without `MANIFEST.md` are refused, returning nonzero and stating
that nothing was copied. After copying, it hashes both each source and its copy again and rechecks
actual status and the report snapshot. Only when all agree does it atomically publish the batch
`MANIFEST.md` through a temporary file. A failed manifest write must not leave a completion marker.
Mid-run failures preserve an incomplete directory; inspect it and retry under a new batch name.
Do not deliver fragments or edit workspaces concurrently.

### Machine ledger and manual columns

`build_ledger.py` really invokes `ledger --workspace … --output <temporary-file>` and parses headers
and column counts. Every machine cell retains its actual CLI value. Only four manual columns,
`批次` (batch), `领域` (domain), `摘要` (summary), and `最后修改` (last modified), are carried across
by unique stable `slug`; missing manual columns are added and escaped `\|` is preserved verbatim.
It never moves word counts into domains, downgrades a release for lacking translations, matches by
title/row number, or separately counts releases. Slugs must remain stable and unique within the
scan. Duplicate/empty slugs, malformed column counts, incompatible old machine headers, and CLI
failure leave the previous ledger untouched. Successful writes use atomic replacement; concurrent
edits to the old ledger also prevent replacement. If changing a slug, inspect and migrate its
manual cells explicitly.
The CLI escapes backslashes/pipes in titles/slugs and replaces line breaks with spaces; the
tool retains these serialized machine values rather than guessing cell boundaries.

### Local documentation references

`check_doc_links.py` checks only the known root `AGENTS.md` and `docs/*.md`, covering ordinary
inline and full/collapsed/shortcut reference links, plus standalone inline-code relative document,
script, and directory paths. Broken targets and undefined explicit references report file/line
locations and return nonzero. External links, fragment-only references, fenced/indented examples,
explicit `<slug>`/brace/glob placeholders, and EPUB-internal members are skipped. It makes no
network requests and does not validate anchors. Run the ledger first after generation: the
`AGENTS.md` reference to a not-yet-created ledger otherwise correctly fails.
Real links inside Markdown footnote content and links to ordinary HTML documents are checked too;
the footnote text itself is not a file path.

### Git/disk/ignore reconciliation

`check_tracked.py --repo <actual-repository-root>` reads tracked, ignored, untracked, and disk
files, reports missing/unclassified files, and groups ignored files by top-level component.
Check each independent book repository separately; the work root need not itself be a repository.
Nested repository contents require checking their own root. Untracked, missing, unclassified,
and unexpectedly ignored files all fail.

The independent default ignore allowance is **only** `docs/__pycache__/**` and
`outbox/*/epub/**`, not a copy of `.gitignore`. Thus ignored `outbox/batch/secret.txt` and
`.tr/draft.txt` still fail. After inspection, extend the allowance using repeated
`--allow 'precise/pattern'` or `--allow-file <independent-policy-file>` (one rule per line,
`#` comments; `*` does not cross path segments, `**` does, and trailing `/` allows a subtree).
`.gitignore` is not accepted as the independent policy file. Failure does not mean files should
be committed: first inspect content and confidentiality boundaries, add a precise allowance
when ignoring is intentional, and **never add secrets to Git merely to silence a warning**.
The tool never runs `git add`.

These guards do not replace per-book QA or content verification. All four return nonzero on
failure and never repair files automatically or manufacture release evidence.
