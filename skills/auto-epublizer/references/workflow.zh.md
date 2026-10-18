> **中文** | [English](workflow.md)

# Workflow（阶段路由 + 命令总览）

## 状态路由

工作区是 `<workspaces_dir>/<book-slug>/`，权威索引是 `publication.json`。

**任何 CLI 之前**：先按 `references/work-root.md` 完成用户选定工作根、官方 GitHub main
checkout、项目 `uv` 环境与无覆盖骨架生成；安装 Skill 不等于安装引擎。本页所有
`auto-epublizer …` 示例运行时都写作 `"$AEP_CLI" …`（该变量由 bootstrap 导出）；
相对书籍路径以工作根为当前目录，源码 checkout 不存书。
然后 `"$AEP_CLI" version` 对照 Skill `manifest.json` 的最低版本，不兼容即停止；
`"$AEP_CLI" doctor --json` 自检环境（pandoc/pymupdf/OCR/epubcheck/MinerU/网络），
并自报 multimodal / search——按 `references/ingest.md` 的能力-路由决策表选路。

```text
无 publication.json               -> 全新流程：先 preprocess <input>（= init + 事实收集）
有 publication.json              -> 续跑：status --json 看状态机与对账（stale / preprocessing）
  preprocessing_complete=false   -> 按 facts.md 待办完成 agent 理解产物（todo.md 逐细节清单 + capabilities/plan/global/...）
  单元 status 全 built           -> 已完成，跳过对应阶段
  有 structured/ 无 analysis/ 且无 preprocessing/global.md -> agent 写 global.md（理解层）
  有 translation/ 但 status 未推进（stale） -> 运行 import 登记
  有 translation/ 无 reviews/    -> agent 写审校产物 reviews/review-<ts>/
  有 output/*.epub               -> 已封装，qa 或重新 build
```

### 机器「下一任务」指针（弱模型路径）

`status --json` 还会返回 `next_tasks: [{kind, unit?, hint, done_when}]`，由现有状态机
**派生**（不新增第二份状态源）。**只取首条执行**，完成后重跑 `status --json` 刷新——
不要自行规划整条流程。`done_when` 是完成判据的机器表述（某条 CLI 命令或某个工作区
文件），因此无需依赖模型自评即可核对。

遇到**源站/脏源/边界情况**（如 Baka-Tsuki 插图段不渲染、epubcheck 离线装 jar、
MediaWiki 卷导航垃圾混入 structured），先查 `lessons/` 目录——里面是真实工作沉淀的
「判据 + 处置 + 验证」，命中即按它处理；未命中再自行排查。

## 标准阶段

```text
bootstrap（工作根 + 官方 main + uv + 无覆盖骨架） -> version（兼容性门）
doctor（能力自检：工具链 + 自报 multimodal/search）
  -> preprocess （CLI：嗅探/元数据/TOC/体检/规模 -> preprocessing/facts.*，零 token）
  -> agent 理解 （读 facts.md 撰写 capabilities/plan/global/units/terms/risks/report；
                 analysis/*.md 也由 agent 撰写）
  -> 语义整备 （可选/条件：facts 可疑信号触发；OCR/扫描件路径必做——按
                 references/repair.md 对照 raw 证据修复 structured/ 并写
                 preprocessing/repairs.jsonl 留痕）
   -> 注释结构化（有注书必做：notes candidates 导出候选 → agent 逐条核证
                 disposition=note|not_note → 写 structured/notes.json + 正文原位标记
                 [^ref-…] → notes register；详见 references/notes.md）
  -> 术语播种  （knowledge export：同语对已确认术语 -> preprocessing/terms.csv；
                 agent 审阅增删后 import --terms 导入工作区）
  -> 翻译      （agent 手写 translation/ + align/，然后 import 登记）
  -> g0        （静态校验：术语命中=真实缺陷须清零；长度比=advisory）
  -> review    （QC G1–G3，agent 语义审校后写 reviews/review-<ts>/result.json）
  -> 统一库回写（knowledge import：工作区已确认术语合并进统一库并自动 git 提交；
                 knowledge push 推送远端跨设备同步；远端地址已固化为公共库
                 auto-epublizer-knowledge，init 无需 --remote）
  -> build     （EPUB 封装 -> output/）
  -> qa        （epubcheck + 解包审计 + G5 放行 -> report.json）
  -> delivery  （交付审计：按 references/delivery.md 全量校验 + 写
                 reviews/delivery-<ts>.md；强制，全部单元 built 后 qa 会以
                 W_DELIVERY_AUDIT_MISSING 提示）
```

仅转换不翻译：

```text
convert <input>   -> 归一化 + 结构 + EPUB + QA
```

## 交付或遇到问题：反馈贡献（可选，issue + PR）

交付收尾或遇到技术问题时询问用户是否愿意贡献：**issue 报告症状与最小合成复现；
PR 提交实际修复、回归测试或文档改进**。可只选其一，也可 issue 与关联 PR 都做；
不再把完整修复补丁塞进 issue 来替代 PR。问题处理与书籍交付不以公开贡献为前提。

### 默认只留本地脱敏草稿

1. 先在工作根 `docs/feedback-issue.md` 和/或 `docs/feedback-pr.md` 写草稿（按需创建，
   不自动提交到任何仓库）。issue 草稿含：通用症状、最小虚构输入、明确命令、
   预期/实际结果、可公开的工具版本；根因未知就写未知。PR 草稿含：修复原因、
   精确变更范围、合成回归夹具、实际执行的检查及结果；未执行就明说。
2. **禁止外发**真实书名/作者、文件名/工作区名、原文/译文/引用、真实路径、凭据、
   敏感报告元数据与用户/书籍 Git 历史（包括日志、补丁上下文、附件、分支名、提交信息）。
   用完全虚构的 `sample.md`、`sample-workspace` 与自写短句重建最小复现；
   不从真实书籍截取「看似无害」片段，不贴原始 facts/report/events 或 format-patch。
   保留公开项目名称/仓库地址及原作者归属，不把用户资料伪装为公开夹具。
3. 给用户展示**完整脱敏标题、正文、所有拟发附件/补丁及目标仓库**。明确询问 issue、
   fork、push、PR 各项拟执行的网络写操作是否获准；一个明确覆盖这些操作的批准即可，
   不把「可反馈建议」当作授权。未批准时只保留本地草稿，**绝不执行** issue create、
   fork、push 或 pr create；批准后如内容/操作范围变化，重新展示并取得同意。
4. 批准后先 `gh auth status` 核对使用**用户自己的账户**。未登录/权限不足则停在草稿，
   由用户自行通过 `gh auth login` 浏览器/设备码流程解决；不索要密码或 token，
   不借用维护者/agent 身份，不以权限失败为由改发别处。

### 经批准的 issue

下面是**仅在上述批准与认证完成后**手动执行的模板；先把标题替换为已批准的脱敏标题：

```bash
gh issue create --repo Misaka0x26FE/auto-epublizer \
  --title 'Synthetic input: concise symptom' \
  --body-file "$AEP_ROOT/docs/feedback-issue.md"
```

issue 仅含症状/复现/建议；有实际修复时走下面 PR，可在两份草稿中互链已创建的公开 URL。
不得自动创建 Release、上传书籍产物，或修改现有在线 issue/PR。

### 实际修复或文档改进的 PR

使用**从官方 main 新 clone 的独立贡献 checkout**（例如
`$AEP_ROOT/docs/contribution-source`），不要在运行书籍任务的源码 checkout 切分支，
更不要 fork/push 书籍仓库、用户 Git 历史或任务历史。保留官方公开历史和作者归属。
在新 checkout 创建单主题分支，只重做脱敏的真实修复/文档与合成回归夹具，
按仓库维护规范执行相应检查，在草稿中记录实际证据。
逐文件审阅内容与 diff，**只 `git add -- <明确审核的文件...>`，禁止盲目 `git add -A`**；
检查 staged diff 与提交信息不含隐私后，用 Conventional Commit 本地提交。
展示最终补丁和 PR 草稿后取得上述批准；没有实际变更就不制造空 PR。

以下网络写模板仅适用于**已批准的实际提交**；其中分支名须与本地已审阅分支一致，
贡献 checkout 必须有官方 `origin`，且尚无 `fork` remote：

```bash
contribution="$AEP_ROOT/docs/contribution-source"
account=$(gh api user --jq .login)
gh repo fork Misaka0x26FE/auto-epublizer --clone=false --remote=false
git -C "$contribution" remote add fork "https://github.com/$account/auto-epublizer.git"
git -C "$contribution" push fork HEAD:refs/heads/fix/synthetic-example
gh pr create --repo Misaka0x26FE/auto-epublizer --base main \
  --head "$account:fix/synthetic-example" \
  --title 'fix: concise synthetic regression repair' \
  --body-file "$AEP_ROOT/docs/feedback-pr.md"
```

认证/权限或任一步失败就停止并保留草稿，不自动重试写操作。仅在工具确认创建成功后
回报真实 URL；未提交就明确说「仅本地草稿」，不得把草稿说成已上游反馈。

## 命令总览

```bash
# 能力自检（开工前必做；multimodal/search 由 agent 自报补填）
auto-epublizer doctor [--json] [--ping]

# 预处理（新书：init + 零 token 事实收集 → preprocessing/facts.*；已有工作区：幂等刷新）
auto-epublizer preprocess <input> [--reference <path...>] [--original <path>] [--progress] [--target zh-CN] [--workspace <dir>]
#   --force（省略 input）：从 source/ 原地重建 structured/ 与 facts（误中断恢复；单元状态重置 split）
#   --original <path>：把未改动的交付原件归档到 references/user/（issue #30 §4.6）
#   --progress：长任务（PDF 逐页）进度到 stderr（issue #30 §4.4）
# （agent 读 facts.md 撰写 capabilities/plan/global/units/terms/risks/report，见 references/preprocessing.md）
# init <input> 等价于 preprocess 的建工作区子集（不产 facts；仍可用于仅需拆解的场景）

# agent 手写翻译后的登记入口（G0 结构校验 + 状态推进 + 术语冲突外置）
auto-epublizer meta [--translator X] [--publisher P] [--date D] [--rights R] [--workspace <dir>]
auto-epublizer import [--unit <id>] [--terms <csv>] [--reviewed] [--force] [--workspace <dir>]
#   --force：对 reviewed/built 单元重跑全套阻断校验（交付后修订译文的重登记，issue #13）；
#            通过保持原状态，失败回退 aligned

# 统一术语库/知识库（跨工作区持久化 + git 持续维护；默认 ~/Documents/auto-epublizer）
#   远端已固化为公共库 https://github.com/Misaka0x26FE/auto-epublizer-knowledge
#   （内容 CC BY-SA 4.0）；init 无需 --remote，自建库/fork 用 --remote 或
#   AUTO_EPUBLIZER_REMOTE / paths.knowledge_remote 覆盖
auto-epublizer knowledge init [--remote <url>] [--push] [--dir <dir>]  # 建骨架 + git 初始化（写 CC BY-SA 4.0 LICENSE）
auto-epublizer knowledge export [--workspace <dir>] [--src-lang en]    # 同语对已确认术语 → preprocessing/terms.csv
auto-epublizer knowledge import [--workspace <dir>] [--src-lang en]    # 工作区 glossary.csv → 统一库（合并 + 自动提交）
auto-epublizer knowledge status [--json] | push [--remote <name|url>] | path
auto-epublizer knowledge import-csv <csv> --src-lang en --book <slug>  # 历史/任意术语 CSV（旧案例格式自动识别）

# 单元边界重建登记（agent 重切/合并后；preprocessing/structure.csv → publication.json）
auto-epublizer restructure [--workspace <dir>]

# G0 零 token 静态校验（翻译/导入后立即跑；术语命中是放行硬门，长度比 advisory）
auto-epublizer g0 [--unit <id>] [--workspace <dir>]

# 注释结构化与绑定（有注书；N 阶段：候选盘点 → 登记 → 成品门；详见 references/notes.md）
auto-epublizer notes candidates [-o <jsonl>] [--workspace <dir>]  # 导出候选（零 token；重跑保留处置）
auto-epublizer notes register [--workspace <dir>]                 # 分离登记门：校验并写 publication.json.notes
auto-epublizer notes status [--json] [--workspace <dir>]          # 摘要 / stale / 候选处置进度

# 封装（译文缺省回退源文；--theme 选排版主题）
auto-epublizer build [--theme standard|compact|spacious] [-o <out.epub>] [--workspace <dir>]

# 质检（epubcheck 零 error + 解包审计 + 溯源审计 + G5 放行判定）
auto-epublizer qa [--epub <path>] [--workspace <dir>]

# 仅转换不翻译
auto-epublizer convert <input> [--theme standard|compact|spacious] [-o <out.epub>] [--workspace <dir>]

# 进度 / 状态机 / 产物-状态对账
auto-epublizer status [--workspace <dir>] [--json]
#   --all：总览 base 目录下所有工作区（多书汇总；issue #32）
auto-epublizer status --all [--json] [--workspace <work-root>]

# 跨书台账（markdown）：机器可重算列 + 待填领域/摘要
auto-epublizer ledger [-o <ledger.md>] [--workspace <work-root>]
```

## 状态机与 `status --json`

单元状态机：`pending → split → analyzed → translated → aligned → reviewed → built`。

```bash
auto-epublizer status --workspace <dir> --json
# {"slug":"book","title":"...","target_language":"zh-CN","units_total":N,
#  "units":[{"id":"ch01","kind":"chapter","title":"...","status":"built",
#            "has_translation":true,"has_align":true}, ...],
#  "has_preprocessing":true,"preprocessing_complete":false,
#  "stale":[{"id":"preprocessing","status":"facts_written","reason":"preprocessing_plan_missing"}],
#  "next_tasks":[{"kind":"translate","unit":"ch01","hint":"...","done_when":{"cmd":"import","unit":"ch01"}}]}
```

- `stale`：agent 手写了 translation/align 但尚未 `import` 登记，或预处理 facts 已产但
  理解产物（capabilities/global）未完成——状态机与产物脱节的信号。
- agent 手写产物必须跑 `import` 状态才会推进；`import` 会校验
  seq 连续性/空译文（阻断）与长度比/术语命中（告警）。

## 多工作区工作根（长期多书项目）

无论单书还是多书都先按 `references/work-root.md` 安全 bootstrap；
骨架由现有 `"$AEP_CLI" work-root "$AEP_ROOT"` 生成（不加 `--force`）。
每书一个独立工作区，`status --all` 与 `ledger` 是跨书索引。

```text
<work-root>/
├── auto-epublizer/    # 官方 main 源码与 .venv；不放书，不切贡献分支
├── AGENTS.md          # 本目录怎么工作（根目录只保留这一个 .md）
├── config.yaml        # workspaces_dir / qc.epubcheck.jar / pdf.*
├── inbox/ sources/    # inbox：尚未开工的源；sources：按 <slug>.<ext> 命名的送审副本
├── workspaces/<slug>/ # 每书一个工作区（标准 11 项顶层）
├── docs/              # 过程文档（计划 / 规范 / 审计）
└── references/        # 跨书共享基准（只读）
```

- 源身份一律以 `publication.json.meta.source_sha256` 为准，不认文件名；
- 入库前对源做过加工（注入书签、格式转换）时，用 `preprocess --original` 把**未改动的
  交付原件**存进 `references/user/`，与 `source/` 的 ingest 副本并存；
- `status --all --json` 重算每本的 `progress`（`released` / `built_not_released` /
  `preprocessing`）、单元数与词数；`ledger` 渲染成表，领域/摘要两列由 agent 填。
  **数字绝不手维护**——可随时重算核对。

## 故障排查

| 现象 | 处理 |
|---|---|
| `工作区尚未初始化` | 先 `init`；或 `--workspace` 指向错误的目录 |
| `输入文件内容与工作区不一致` | 源文件被替换；用原始源文件或重新 `init` |
| `成品不存在：...请先 build/convert` | `qa` 前先 `build` |
| `epubcheck errors: -1` | 未装 epubcheck jar（`~/.cache/epubcheck.jar`）；G4 审计仍可跑，`released_reason=epubcheck_not_run` |
| `导入失败`（import 阻断） | 按 `--unit` 输出的错误清单修 align（断号/空译文/缺文件）后重试 |
| `pandoc` 缺失 | `doctor` 已提示；装 pandoc 或先把文件转为 PDF/TXT/MD |
| 扫描 PDF 处理不了 | 按 OCR 路由（`doctor` + multimodal 自报）：**MinerU 外部 API 最优先**（无 key 先询问用户）→ 传统 OCR（tesseract/ocrmypdf）/rapidocr + agent 逐页阅读兜底 |
| 单元状态停在中间态 / stale | `status --json` 定位，从对应阶段续跑（手写产物跑 `import`） |
