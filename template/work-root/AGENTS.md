# 工作根规范（本目录怎么工作）

本目录是 `auto-epublizer` 的**长期多书工作根**。唯一权威是各工作区的 `publication.json`；
本文件只规定「本目录怎么工作」，**不记录任何一本书的具体状态**（那属于跨书台账
`docs/工作台账.md`）。

## CLI 入口与首次使用

安装 Skill 只安装指引，不安装 Python 引擎。首次使用/新 shell 按
[安全 bootstrap 指引](https://github.com/Misaka0x26FE/auto-epublizer/blob/main/skills/auto-epublizer/references/work-root.md) 执行；
源码的目标位置为 `<工作根>/auto-epublizer/`，尚未克隆时不要假定它存在。
该目录存放官方 GitHub main 源码与项目 `.venv`；书籍在同级目录，
不放进源码 checkout。已有 checkout 校验 root/origin/main、tracked+untracked dirty，
clean 后才 fetch/只快进；错误分支/来源或 ahead/divergent 就停止，绝不 reset/stash/clean。
骨架由现有 CLI `work-root` 生成，不加 `--force`。以下命令使用 bootstrap 导出的
`"$AEP_CLI"`（`$AEP_ROOT/auto-epublizer/.venv/bin/auto-epublizer`），不调用未知全局 CLI。

## 红线

1. **根目录只保留一个 `.md`**：本文件。过程文档一律进 `docs/`（避免新会话把过程记录误当规范）。
2. **源身份以 `publication.json.meta.source_sha256` 为准**，不认文件名。
3. `workspaces/<slug>/source/` 只读；`publication.json` **禁止手编**（状态只经 CLI 命令推进）。
4. **数字一律重算**：单元数/词数/进度由 `status --all` / `ledger` 生成，禁止手维护。
5. **机器接口按命令能力选**：`doctor`/`status`（含 `--all`）/`notes status`/`knowledge status`
   支持 `--json`；`qa` 后读 `report.json` 并用 `status --json` 核时效。`build`/`qa`/`ledger`/
   `g0`/`import`/`meta` 不可盲加 `--json`；不解析彩色摘要。退出 0 不等于 `released=true`。

## 流转

- 新书：`inbox/` → `sources/<slug>.<ext>` → `preprocess ... --workspace ./workspaces`；
- 交付原件（入库前加工过）用 `preprocess --original` 归档到 `workspaces/<slug>/references/user/`；
- 交付或状态变化时用 `python3 docs/build_ledger.py --cli "$AEP_CLI"` 更新 `docs/工作台账.md`，重算机器列并按 slug 保留人工列。

## 常用命令

```bash
"$AEP_CLI" doctor --json
"$AEP_CLI" preprocess sources/<slug>.<ext> --workspace ./workspaces
"$AEP_CLI" status --all --workspace . --json
python3 docs/build_ledger.py --cli "$AEP_CLI"
python3 docs/check_doc_links.py
python3 docs/check_tracked.py --repo workspaces/<slug>
python3 docs/pack_outbox.py --cli "$AEP_CLI" workspaces/<slug> --batch <batch>
```

## 反馈贡献（可选）

交付或遇到问题时询问用户是否需要脱敏 issue（症状/合成复现）和/或 PR（实际修复/文档）。
完整流程见[脱敏反馈指引](https://github.com/Misaka0x26FE/auto-epublizer/blob/main/skills/auto-epublizer/references/workflow.md)。先在本根 `docs/`
留草稿并展示完整标题/正文/补丁，获明确同意才 issue create/fork/push/pr create。
只用虚构夹具，不外发真实书名/作者、文件/工作区名、原文/译文、路径、凭据、
敏感报告元数据或用户/书籍 Git 历史；不盲目 `git add -A`。以用户账户认证，不索要 token；
未授权或缺认证/权限时只留本地草稿，不提交。
