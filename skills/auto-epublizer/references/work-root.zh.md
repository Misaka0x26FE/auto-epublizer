> **中文** | [English](work-root.md)

# 长期工作区（多书工作根）

当用户要**长期处理多本书**（而非一本）时使用。它建立单一目录，里面每本书一个工作区，
外加一份跨书索引。

## 生成

```bash
auto-epublizer work-root <目录> [--force]
```

命令复制仓库内的 `template/work-root/` 骨架（**唯一权威模板**）。已存在文件默认保留，
加 `--force` 才覆盖。之后把下一本源书放进 `inbox/`。

## 各组件的作用

| 组件 | 作用 |
|---|---|
| `AGENTS.md` | 本目录怎么工作（红线：根目录只保留一个 `.md`、源身份以 sha256 为准、禁手编、数字必须重算） |
| `config.example.yaml` | 复制为 `config.yaml`；关键项 `paths.workspaces_dir: ./workspaces` |
| `inbox/` | 尚未开工的源书（原名原字节） |
| `sources/` | 送审暂存副本，命名 `<slug>.<ext>`（交给 `preprocess`） |
| `workspaces/<slug>/` | 每本书一个**标准工作区**（由 CLI 生成） |
| `docs/` | 过程文档：计划 / 规范 / 审计 + 跨书台账 |
| `references/` | 跨书共享资料（只读） |
| `README.md` | 上面这些的**用户说明** |

## 怎么用

1. **新书**：`cp inbox/<原名> sources/<slug>.<ext>` →
   `auto-epublizer preprocess sources/<slug>.<ext> --workspace ./workspaces` → 之后按单书常规流程
   推进（`status --json` → 任务卡 → `import` / `g0` / `build` / `qa` / 交付审计）。
2. **跨书总览**：`auto-epublizer status --all --workspace . --json`（三档进度：
   `released` / `built_not_released` / `preprocessing`）；
   `auto-epublizer ledger -o docs/工作台账.md`（领域/摘要两列由你填）。
3. **身份以 `publication.json.meta.source_sha256` 为准**，不认文件名。入库前对源做过加工
   （注入书签、格式转换）时，用 `preprocess --original <原始件>` 归档未改动的交付原件。
4. **数字一律由命令重算**，绝不手维护。

## 告诉用户的话（可直接转述）

> 这是你的**长期工作区**：`inbox/` 放还没开工的原书；开工时复制到 `sources/<slug>.<ext>` 交给
> agent 处理；每本书成为 `workspaces/<slug>/` 下一个标准工作区；`docs/` 放过程文档与跨书台账；
> `references/` 放跨书共享资料。随时用 `auto-epublizer status --all` 看全部书的进度
> （已交付 / 已建未放行 / 仅预处理），`auto-epublizer ledger` 生成台账。源身份以 sha256 为准。
