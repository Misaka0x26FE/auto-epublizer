# 工作根模板（长期多书项目）

> `auto-epublizer` **持续处理多本书**时的标准工作根布局（来源：GitHub issue #30 / #32）。
> 复制本目录为新项目根、按需改名即可；每本书在其中累积为一个工作区。

## 目录布局

```text
<work-root>/
├── AGENTS.md           # 本目录怎么工作（根目录只保留这一个 .md）
├── config.example.yaml # 配置模板（复制为 config.yaml；workspaces_dir=./workspaces）
├── inbox/              # 收件箱：只放「尚未开工」的源文件（原名原字节）
├── sources/            # 送审暂存：inbox 文件按 <slug>.<ext> 复制一份，供 preprocess
├── workspaces/         # 每书一个工作区 <slug>/（由 CLI 生成）
├── docs/               # 过程文档：计划 / 规范 / 审计 / 交接 / 工作台账
└── references/         # 跨书共享基准（只读）
```

## 流转（身份以 sha256 为准，不认文件名）

1. 定 slug（书名取短横线小写）→ `cp inbox/<原名> sources/<slug>.<ext>`
2. `auto-epublizer preprocess sources/<slug>.<ext> --workspace ./workspaces`
3. 源已入库（`source_sha256` 写入 `publication.json`）后，收件箱副本即视为已处理；
4. 若入库前对源做过加工（注入书签 / 格式转换），用 `--original <原件>` 把**未改动的交付
   原件**归档到工作区 `references/user/`。

## 跨书索引

```bash
auto-epublizer status --all --workspace . --json   # 三档进度 + 单元/词数（机器可重算）
auto-epublizer ledger -o docs/工作台账.md           # 台账 markdown（领域/摘要两列由 agent 填）
```

**数字列永远由命令重算，绝不手维护。**

## 约定

详见 `skills/auto-epublizer/references/workflow.md`「多工作区工作根」：

- 根目录只允许一个 `.md`（`AGENTS.md`），过程文档一律进 `docs/`；
- 每书一个独立 git 仓库（工作区内 `git init`、全量入库，默认私有远端）；
- `inbox/` 与 `sources/` 只做暂存，不入库。
