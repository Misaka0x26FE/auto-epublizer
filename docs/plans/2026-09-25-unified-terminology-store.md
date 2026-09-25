# 统一术语库 / 知识库（跨工作区持久化 + git 持续维护）

> 状态：已完成（34d6d2b）
> 立项：2026-09-25
> 关联：`AGENTS.md`「版权与发布责任」、`skills/auto-epublizer/references/publishing.md`、`references/preprocessing.md`、`references/translation.md`

## 1. 背景与问题

现状：每本书（工作区）内的术语闭环是**自包含**的——

- 权威存储 `analysis/glossary.csv`（agent 手写，三态 `seed → candidate → conflict → confirmed`）；
- 播种入口 `import --terms preprocessing/terms.csv`（agent 预提取）；
- 冲突外置 `analysis/glossary_conflicts.jsonl`，由 agent 裁决后写回 CSV。

问题：**跨书没有共享**。上一本书确认的人名/地名/机构译名、考据结论、体例决策，下一本书的
agent 无从复用，只能重新检索、重新判断、重新裁决——重复劳动，且跨书不一致（同一人物在
两本书里译名不同）。`glossary.db` 是预留的 SQLite 索引，从未实现，也不解决跨书问题。

## 2. 目标（本任务两点）

1. **统一术语库 + 知识库**：由 agent 自行维护，存到一个**持久化目录**，供后续访问、
   跨书复用、避免重复工作。
2. **该目录本身作为 git 仓库持续维护**：每次写入自动提交；条件允许时推送到 GitHub 等
   托管平台，实现**跨设备**维护（私有仓，沿用项目「默认私有」政策）。

## 3. 设计

### 3.1 持久化目录

- 默认：`~/Documents/auto-epublizer/`（用户指定；显式可见，便于人工翻看）。
- 覆盖优先级：`--dir` 参数 > 环境变量 `AUTO_EPUBLIZER_HOME` > 配置 `paths.knowledge_dir`
  > 默认路径。
- 目录布局（本身是一个 git 仓库）：

```text
<store>/
├── .git/                  # git init（持续维护；默认私有，可推托管平台跨设备）
├── .gitignore             # 锁文件/临时/系统文件
├── README.md              # store 说明与用法（CLI 生成）
├── terminology.csv        # 统一术语表（工作区 schema + 溯源列 src_lang,tgt_lang,book）
├── conflicts.jsonl        # 跨书术语冲突账本（append-only，去重追加；待 agent 裁决）
└── knowledge/             # 知识库（agent 自由撰写 markdown：考据/决策依据/体例）
    └── INDEX.md           # 目录约定（agent 维护）
```

### 3.2 统一术语表 schema 与键

工作区权威列序 `source,target,type,aliases,gender,reading,status,note` 之上，追加溯源列：

```text
source,target,type,aliases,gender,reading,status,note,src_lang,tgt_lang,book
```

- **键** = `(src_lang, tgt_lang, NFKC(source))`——术语决策只在同一语言对内有效，避免跨语对串味。
- `book` 记录该条目的来源工作区 slug（溯源，可多书合并时保留首见）。
- 语言对来源：工作区 `publication.json.meta.language` / `target_language`；源语言为 `auto`
  未回写时，由 agent 用 `--src-lang` 显式声明（CLI 无法探测语义）。

### 3.3 跨书冲突（外置待裁决）

沿用工作区机制，不自动覆盖：

- `knowledge import` 合并工作区术语时，同一键出现**不同已确认译法** → 新条目落库为
  `conflict` 态，并把 `(source, src_lang, tgt_lang, existing_target, proposed_target, books)`
  追加进 `conflicts.jsonl`（按键去重，重复导入不重复记账）。
- 未裁决判定：某键在 `terminology.csv` 中仍有 **>1 个非空 target** 即为未裁决；
  agent 在 `terminology.csv` 上裁决（保留一个、删除/清空其余）后自动归零，无需改账本。
- 单 LLM 原则：CLI 只做确定性的合并/记账/计数，**裁决由 agent 完成**。

### 3.4 命令面（CLI，确定性零 token）

```bash
auto-epublizer knowledge path                 # 打印解析后的 store 目录与覆盖来源
auto-epublizer knowledge init [--remote URL] [--push]   # 建骨架 + git init + 首次提交（可选配置远端/首推）
auto-epublizer knowledge export [--workspace .] [--src-lang en] [--include-pending] [--force]
                                              # 同语对已确认术语 → preprocessing/terms.csv（agent 审阅后 import --terms）
auto-epublizer knowledge import [--workspace .] [--src-lang en] [--no-commit]
                                              # 工作区 glossary.csv → 统一库（合并 + 冲突外置 + 自动提交）
auto-epublizer knowledge status [--json]      # 条目/冲突/知识文件统计 + git 状态（是否仓库/脏/远端）
auto-epublizer knowledge push [--remote origin]         # 推送（跨设备同步；无远端/无网络时明确告警）
```

- **播种走显式命令**：`export` 写 `preprocessing/terms.csv`，agent 增删后 `import --terms`
  导入工作区（沿用现有闭环，确定性可见）；目标文件已有内容时拒绝覆盖，需 `--force`。
- **持续维护**：`import` 成功写库后自动 `git add -A && git commit`（store 仓库内，信息含
  工作区 slug 与计数）；git 不可用/失败仅告警不阻断。`init` 做首次提交。
- **跨设备**：`--remote` / 配置 `paths.knowledge_remote` / 环境变量 `AUTO_EPUBLIZER_REMOTE`
  指定远端；建仓与推送由 agent 用自身 git/gh 能力完成（CLI 只做本地确定性 git 操作 + push）。

### 3.5 agent 能力自检接入

「如果 agent 发现自己有文件权限和记忆权限」——落到 `preprocessing/capabilities.md` 自报：
新增一行「持久化统一库」，agent 自报是否可写持久化目录、是否使用统一库；`knowledge path`
输出 store 路径供 agent 判定。CLI 无法探测 agent 的跨会话记忆，故由 agent 自报。

## 4. 架构落点

| 层 | 文件 | 职责 |
|---|---|---|
| auto_common | `config.py` `PathsConfig` | `knowledge_dir` / `knowledge_remote` 配置项 |
| auto_translator | `glossary/store.py`（新） | 统一库 schema / 键 / 合并 / 导出 / 冲突账本（纯函数，无 git、无路径策略） |
| auto_epublizer | `knowledge.py`（新） | store 路径解析 + git 子进程（init/commit/push）+ 命令实现 |
| auto_epublizer | `cli.py` | `knowledge` 子命令组（typer） |
| docs / skills | 见 §6 | 双语同步 + i18n 盖章 |

边界不变：`auto_translator` 不依赖 `auto_epublizer`；`knowledge.py` 不导入 orchestrator；
全库无 LLM 调用符号。

## 5. 验收

- [ ] 单测覆盖：路径解析覆盖链、init 骨架 + git、import 合并/去重/冲突/幂等、export 过滤/
      拒覆盖/`--force`、status 统计、未裁决计数。
- [ ] `uv run pytest -q` 全绿；`ruff check` / `ruff format --check` 全绿。
- [ ] 双语文档改动的 i18n `--finalize` / `--check` / `--links` 全绿。
- [ ] 真实冒烟：`knowledge init` → `knowledge path/status`（在临时目录，不污染真实 home）。

## 6. 实施时须同步的文档

- `AGENTS.md` / `AGENTS.zh.md`：工作区契约（新增 `<store>/` 说明）、标准工作流（preprocessing
  与 translation 阶段接入 `knowledge export/import`）。
- `README.md` / `README.zh.md`：能力表 + 使用方式。
- `docs/configuration.md` / `.zh.md`：`paths.knowledge_dir` / `paths.knowledge_remote` + 环境变量。
- `docs/translation-flow.md` / `.zh.md`：术语闭环补「统一库」一环。
- `config.example.yaml`：新增配置项（示例）。
- `skills/auto-epublizer/SKILL.md` / `.zh.md`：命令总览。
- `skills/auto-epublizer/references/preprocessing.md` / `.zh.md`：`terms.csv` 播种来源 +
  capabilities 自报「持久化统一库」。
- `skills/auto-epublizer/references/translation.md` / `.zh.md`：三态闭环补写回统一库。
- `skills/auto-epublizer/references/workflow.md` / `.zh.md`：阶段路由补 `knowledge`。
- `skills/auto-epublizer/references/publishing.md` / `.zh.md`：统一库同为私有仓/跨设备同步。

## 7. 实施记录

已完成（`34d6d2b`）：

- 领域层 `auto_translator/glossary/store.py`：统一库 schema/键/合并/导出/冲突账本。
- 编排层 `auto_epublizer/knowledge.py`：目录解析 + git init/commit/push + 五个命令实现。
- CLI `knowledge` 子命令组（path/init/import/export/status/push）+ `paths.knowledge_dir` /
  `paths.knowledge_remote` 配置。
- 测试 `tests/test_knowledge_store.py`：17 例（解析覆盖链、git 骨架/提交/幂等、合并去重/
  跨书冲突、导出语对隔离/拒覆盖、未裁决自动归零、CLI 全链路）。
- 文档双语同步：AGENTS / README / configuration / translation-flow / SKILL / workflow /
  preprocessing / translation / publishing（i18n 9 对重盖戳）+ config 示例 + 本计划。

验证：`uv run pytest -q` **375 passed**；`ruff check .` / `ruff format --check .` 全绿；
`scripts/i18n.py --check/--links` OK；`knowledge init/status` 真实冒烟通过。

> 真实用户目录 `~/Documents/auto-epublizer/` 未创建（冒烟与测试均在 `/tmp` 与 `tmp_path`），
> 由 agent 首次运行 `knowledge init` 时按需建立。

### 后续增量

- **`3f3bd43`**：补 `knowledge import-csv <csv> --src-lang --book [--status]`（历史项目不是
  工作区时的确定性导入入口；自动识别旧案例 `category,source,target,note` 格式），并补全
  `_CATEGORY_TO_TYPE` 映射（专名/概念/职衔/机构/组织机构/政治派系）。
- **历史数据开荒**：真实目录 `~/Documents/auto-epublizer/` 已建立并入库 `~/work/translate/`
  的 6 份权威 `GLOSSARY.csv`（confirmed）+ morris 报告表外术语 1024 条（seed），
  共 **1199 条**（en→zh 1107 / es→zh 72 / ru→zh 20）；裁决 40 个跨章变体键后未裁决键归零；
  另写 4 篇 `knowledge/` 事实知识（项目索引 / 术语体例与裁决 / 源文缺陷模式 / OCR 勘误先例）。
