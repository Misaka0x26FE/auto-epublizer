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
python3 docs/build_ledger.py                     # 保留人工列后重算，见下
```

**数字列永远由命令重算，绝不手维护。**

## 约定

本工作根与每本书分别管理；下面的工具直接随模板复制，无需原仓库脚本路径：

- 根目录只允许一个 `.md`（`AGENTS.md`），过程文档一律进 `docs/`；
- 每书一个独立 git 仓库（工作区内 `git init`、全量入库，默认私有远端）；
- `inbox/` 与 `sources/` 只做暂存，不入库。

## 四个离线操作工具

四个脚本只用 Python 3.11+ 标准库。`pack_outbox.py`、`build_ledger.py` 还需安装真实
`auto-epublizer` CLI；未激活环境时用 `--cli /绝对路径/auto-epublizer`。不接 LLM、不联网，
不自动 stage/push。脚本默认路径按**脚本所在工作根**确定，与当前 shell 目录无关；
显式相对参数则相对于当前 shell 目录。先生成台账，再检查引用它的文档：

```bash
python3 docs/build_ledger.py --workspace workspaces --output docs/工作台账.md
python3 docs/pack_outbox.py workspaces/book-a workspaces/book-b --batch 2026-10-17
python3 docs/check_doc_links.py --root .
python3 docs/check_tracked.py --repo workspaces/book-a
```

- **打包**：位置参数是本批全部实际工作区（包含 `publication.json`；嵌套布局传到 `book/`）。
  真实 `status --json` 必须逐件报告当前 `released=true`、`stale=false`、`reason=ok`；
  只复制对应 `report.artifacts_epub`，不猜 output 文件，也不因合法源语言转换无译文而拒绝。
  全批预检失败不创建批次。默认交付到 `outbox/<batch>/epub/`（可用 `--outbox` 改根）；
  同名（忽略大小写）产物冲突失败，既有完整/中断批次均拒绝覆盖，不谎报复制成功。
  复制后逐件对源和副本 SHA256、真实状态、报告快照再次核对，全部一致才通过临时文件
  原子发布 `outbox/<batch>/MANIFEST.md`。清单写失败不得留下完成标记；中途失败可能留下
  **无清单**目录。人工核证后换新批次，不要把残件当交付，操作期间不要并发修改工作区。
- **台账**：真正调用 `ledger`，保留机器单元格原值，仅按唯一稳定 `slug` 搬回
  `批次/领域/摘要/最后修改` 四个人工列（不存在的列补上；转义 `\|` 原样保留）。
  不按书名/行序、不重新计算放行数、不猜旧表列位。`slug` 应稳定且在扫描范围内唯一；
  表头不兼容、列数错误、重复 slug 或 CLI 失败均退出非零，旧文件不覆盖。
  台账成功时以临时文件原子替换；生成期间修改旧台账也会拒绝覆盖。
  CLI 会转义书名/slug 中的反斜线与竖线、把换行转为空格；工具保留该机器值，不猜拆列。
- **文档**：只查已知 `AGENTS.md` 和 `docs/*.md` 的相对链接与独立行内代码路径，
  覆盖 inline、full/collapsed/shortcut reference links；诊断包含文档路径与行号。
  跳过外链、纯 fragment、围栏/缩进代码示例、显式 `<slug>`/花括号/通配占位、
  EPUB 内部成员；不校验锚点、不请求网络。缺失引用和未定义显式引用均失败。
  Markdown 脚注正文中的真实链接和普通 HTML 文档链接也须核对，不把注文文本当路径。
  刚生成时台账未创建，`AGENTS.md` 对它的引用会如实报断链；先运行台账工具。
- **Git 对账**：`--repo` 必须是实际 Git 根；每本书独立 Git 时逐本运行，工作根有仓库也可
  单独检查。只读核对跟踪文件、磁盘、ignored、untracked 与 missing，并按顶层汇总 ignored。
  未跟踪、跟踪但缺失、无法归类及意外 ignored 都退出非零。默认独立忽略允许规则只有
  `docs/__pycache__/**`、`outbox/*/epub/**`，**不是照抄 `.gitignore`**；
  `outbox/batch/secret.txt`、`.tr/draft.txt` 不会因顶层目录被忽略而放过。
  经核证后可用重复 `--allow '相对/精确模式'` 或 `--allow-file <独立规则文件>` 扩展
  （一行一条、`#` 注释；`*` 不跨目录、`**` 跨层，尾 `/` 表示子树）。
  不得以 `.gitignore` 作为允许清单。失败时先核证保密边界，**绝不要为消警把 secret 加 Git**。

这四项检查是操作护栏，不替代逐书 QA 或内容核证；失败均返回非零，不会自动修文件或放行。
