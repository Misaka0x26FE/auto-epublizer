<!-- i18n: source=work-root.zh.md sha256=5ebc908486369f108d3e0bb1cb06c0a9624a2b72d889f327d7254fdad0ab1dc1 -->
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
   `auto-epublizer ledger -o docs/工作台账.md` (fill the domain/summary columns yourself).
3. **Identity is `publication.json.meta.source_sha256`**, never the file name. If the source was
   pre-processed (bookmarks injected, format converted), archive the untouched original with
   `preprocess --original <path>`.
4. **Numbers are always recomputed by the commands** — never hand-maintained.

## What to tell the user (relay this)

> 这是你的**长期工作区**：`inbox/` 放还没开工的原书；开工时复制到 `sources/<slug>.<ext>` 交给
> agent 处理；每本书成为 `workspaces/<slug>/` 下一个标准工作区；`docs/` 放过程文档与跨书台账；
> `references/` 放跨书共享资料。随时用 `auto-epublizer status --all` 看全部书的进度
> （已交付 / 已建未放行 / 仅预处理），`auto-epublizer ledger` 生成台账。源身份以 sha256 为准。
