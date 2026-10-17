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
   `python3 docs/build_ledger.py` 重算台账并按唯一 slug 保留人工列。
3. **身份以 `publication.json.meta.source_sha256` 为准**，不认文件名。入库前对源做过加工
   （注入书签、格式转换）时，用 `preprocess --original <原始件>` 归档未改动的交付原件。
4. **数字一律由命令重算**，绝不手维护。

## 告诉用户的话（可直接转述）

> 这是你的**长期工作区**：`inbox/` 放还没开工的原书；开工时复制到 `sources/<slug>.<ext>` 交给
> agent 处理；每本书成为 `workspaces/<slug>/` 下一个标准工作区；`docs/` 放过程文档与跨书台账；
> `references/` 放跨书共享资料。随时用 `auto-epublizer status --all` 看全部书的进度
> （已交付 / 已建未放行 / 仅预处理），`auto-epublizer ledger` 生成台账。源身份以 sha256 为准。

## 可直接运行的操作护栏（issue #47）

生成器同时复制 `docs/{pack_outbox,build_ledger,check_doc_links,check_tracked}.py`。
四者均为 Python 3.11+ 标准库脚本，不依赖原仓库、不联网、无 LLM，不自动 stage/push。
前两项调用已安装的真实 CLI，可通过 `--cli /绝对路径/auto-epublizer` 指定未激活环境中的
可执行文件；不会另算 QA 摘要或机器进度。默认工作根由脚本位置确定，显式相对路径参数按
shell 当前目录解释。复制或生成工作根后即可运行；无书籍时仍可运行空台账与文档检查。

```bash
python3 docs/build_ledger.py --workspace workspaces --output docs/工作台账.md
python3 docs/pack_outbox.py workspaces/book-a workspaces/book-b --batch 2026-10-17
python3 docs/check_doc_links.py --root .
python3 docs/check_tracked.py --repo workspaces/book-a
```

### 保守交付

打包位置参数显式列出**整批实际工作区**；嵌套布局应传包含 `publication.json` 的 `book/`。
整批先逐项调用真实 `status --json`，必须当前 `released=true`、`stale=false`、`reason=ok`，
再读对应 `report.artifacts_epub` 精确路径（相对路径按工作区解释）。不猜 output 文件，
不以有无译文判断合法源语言转换。任何预检失败时整批不复制；忽略大小写的文件名冲突也失败。

默认新批次位于 `outbox/<batch>/epub/`（`--outbox` 可改根）。已存在的完整批次和无
`MANIFEST.md` 的中断批次均拒绝覆盖，退出非零并明确未复制。复制后逐件重算源文件与
副本 SHA256，再检查真实状态及报告快照，全部一致才独占写入批次 `MANIFEST.md`。
中途失败会保留无清单现场；人工核证后用新批次名重试，不把残件当交付，不并发修改工作区。

### 机器台账与人工列

`build_ledger.py` 实际调用 `ledger --workspace … --output <临时文件>`，按表头与列数解析。
所有机器单元格保持真实 CLI 原值，只按唯一稳定 `slug` 保留四个人工列：
`批次/领域/摘要/最后修改`，缺列补上，转义 `\|` 原样保留。不会把词数当领域、因无译文而
降低放行状态、按书名或行号搬数据，也不额外手算放行计数。扫描范围内 slug 必须唯一且
保持稳定；重复/空 slug、列数错误、旧机器表头不兼容、CLI 失败均不覆盖旧台账。
成功时原子替换；生成期间旧台账被改也拒绝覆盖。改了 slug 时应人工核证迁移对应人工列。

### 本地文档引用

`check_doc_links.py` 只检查已知根 `AGENTS.md` 与 `docs/*.md`，覆盖普通 inline、
full/collapsed/shortcut reference links 及独立行内代码中的相对文档/脚本/目录路径。
断链和未定义显式引用给出文件与行号并退出非零。跳过外链、纯 fragment、围栏/缩进代码示例、
`<slug>`/花括号/通配等显式占位与 EPUB 内部成员；不请求网络、不验证锚点。
初次生成后先跑台账，否则 `AGENTS.md` 指向尚不存在的台账会如实失败。

### Git/磁盘/忽略对账

`check_tracked.py --repo <实际仓库根>` 读取 Git 跟踪、ignored、untracked 与磁盘文件，
列出 missing/无法归类并按顶层汇总 ignored。每本书有独立 Git 时逐本检查，不要求工作根
也必须入库；嵌套仓库内容需对其根单独检查。未跟踪、缺失、无法归类及意外忽略均失败。

独立的默认允许忽略规则**仅** `docs/__pycache__/**` 和 `outbox/*/epub/**`，
不把 `.gitignore` 自身当允许清单。故 `outbox/batch/secret.txt` 和 `.tr/draft.txt` 即使被
Git 忽略也会失败。核证后用可重复 `--allow '精确/模式'` 或 `--allow-file <独立规则文件>`
添加规则（一行一条、`#` 注释；`*` 不跨路径段、`**` 可跨层、尾 `/` 允许子树）。
不接受 `.gitignore` 作为独立规则文件。失败不等于应把文件入库：先检查内容与保密边界，
应忽略者添加精确允许规则，**绝不要为消警把 secret 加 Git**。工具不执行 `git add`。

这些脚本不替代逐书 QA 或内容核证；四项操作失败均退出非零，不自动修文件或制造放行证据。
