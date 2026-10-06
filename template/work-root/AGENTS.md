# 工作根规范（本目录怎么工作）

本目录是 `auto-epublizer` 的**长期多书工作根**。唯一权威是各工作区的 `publication.json`；
本文件只规定「本目录怎么工作」，**不记录任何一本书的具体状态**（那属于跨书台账
`docs/工作台账.md`）。

## 红线

1. **根目录只保留一个 `.md`**：本文件。过程文档一律进 `docs/`（避免新会话把过程记录误当规范）。
2. **源身份以 `publication.json.meta.source_sha256` 为准**，不认文件名。
3. `workspaces/<slug>/source/` 只读；`publication.json` **禁止手编**（状态只经 CLI 命令推进）。
4. **数字一律重算**：单元数/词数/进度由 `status --all` / `ledger` 生成，禁止手维护。

## 流转

- 新书：`inbox/` → `sources/<slug>.<ext>` → `preprocess ... --workspace ./workspaces`；
- 交付原件（入库前加工过）用 `preprocess --original` 归档到工作区 `references/user/`；
- 交付或状态变化时更新 `docs/工作台账.md`（骨架由 `auto-epublizer ledger` 生成）。

## 常用命令

```bash
auto-epublizer doctor --json
auto-epublizer preprocess sources/<slug>.<ext> --workspace ./workspaces
auto-epublizer status --all --workspace . --json
auto-epublizer ledger -o docs/工作台账.md
```
