# auto-epublizer 仓库指南（面向开发/维护本项目的 coding agent）

本文件是**维护本仓库代码**的 agent 的入口契约：讲清项目是什么、怎么实现、怎么验证。

> 若你的任务是**用本 CLI 处理一本书**（翻译/转 EPUB），请改读 `skills/auto-epublizer/`——
> 那是把设计翻译成「照抄就能干」步骤的可安装指引（见「skills/ 目录」）。

> 本文件同时是"必须实现成什么样"的契约；若子目录出现更具体的 `AGENTS.md`，以更深层文件为准。

## 项目定位

`auto-epublizer`（Python CLI，三包 monorepo）提供两项能力、一条共用管线：

1. **翻译**：外语文献 → 任意可配置目标语言。
2. **转 EPUB**：来源复杂文件（PDF/扫描 PDF/EPUB/DOCX/HTML/TXT/Markdown）→ 标准 EPUB 3。

- Python 3.12，包管理用 `uv`。
- **唯一 LLM 原则（硬约束）**：本项目中**唯一的 LLM 就是操作本 CLI 的 agent 本身**——
  CLI 只做确定性、零 token 的计算（解析/切片/检测/校验/构建/审计）；一切语义工作
  （理解、翻译、审校判断、术语裁决、公式 LaTeX、内容描述）由 agent 用自身能力完成。
  **禁止新增任何 LLM API 调用**（新依赖、新端点、任何包扩展均不许）；存量内部
  LLM 路径（`auto_common/llm/`、`agents/` 包、translate/analyze/review 命令）**已移除**，
  见 [docs/plans/2026-09-04-remove-internal-llm.md](docs/plans/2026-09-04-remove-internal-llm.md)，
  由 `test_architecture_boundaries.py` 的 `test_no_llm_api_calls_anywhere` 强制回归。
  判据不变：「同样输入必须得到同样输出 → Python；需理解/权衡/判断 → agent」，
  完整版见 [docs/agent-vs-code.md](docs/agent-vs-code.md)。
- 工作区为 `publication.json` 权威索引 + 工作区目录（见下），不沿用旧 `split/` 流程。
- 质量检验六道关（G0–G5），重点参考 wenyi（`trans_novel`）的 Review 体系。
- **只负责交付质量**（准确 / 完整 / 一致 / 规范 / 结构正确 / 可复现），**不做内容的价值观 / 政治 / 思想性判断**。
- **能力分工**：CLI 负责确定性计算与校验放行；**内容理解、语义判断、
  质量把关、术语裁决、修复决策**由使用本项目的 agent 用自身能力（读文件、判断、写文件）完成。
  agent 只需基础能力，无需 MCP / 子代理。
- **产物规范**：EPUB 形态规范（无样式模板 / 有限主题 / 标准弹窗注释）见
  [docs/epub-template-spec.md](docs/epub-template-spec.md)；后处理验收与实现计划
  （内容溯源 / 媒体 / 目录层级）见 [docs/postprocessing-spec.md](docs/postprocessing-spec.md)。
- **许可**：本项目自身代码采用 **AGPL-3.0**；第三方依赖保留各自许可证，并在 `THIRD_PARTY_LICENSES.md` 登记（AGPL 依赖可直接引入，与项目同许可兼容）。

## 处理一本著作的标准流程

```bash
# 0. 能力自检（agent 开工前必做：判断自身能力边界 + 环境工具链）
auto-epublizer doctor [--ping]   # 工具链/依赖/MinerU/网络探测；multimodal/search 由 agent 自报补填

# 1. 安装
uv sync

# 2. 配置（无密钥段；可选外部解析 API 的 MINERU_API_KEY 只从环境变量读取，见「配置与密钥」）

# 3. 预处理（零 token 事实收集 + agent 理解）：
auto-epublizer preprocess <input>   # 新书：init + 嗅探/元数据/TOC/体检/规模 → preprocessing/facts.*
#    agent 读 facts.md，按待办清单撰写：todo.md（逐细节任务清单，全程勾选）/ capabilities.md
#    （自报五维）/ plan.md（方案决策）/ global.md（全局理解）/ units/<id>.md /
#    terms.csv / risks.md / report.md
auto-epublizer preprocess           # 已有工作区：幂等刷新 facts

# 4. 理解（agent 任务）：analysis/*.md 与术语表由 agent 自身能力撰写
#    （概述/全局/每单元/重点；上下文也可只来自 preprocessing/）

# 5. 翻译（agent 任务）：agent 读 structured/ 自己翻译，写 translation/ + align/，
#    然后「import」登记：G0 校验 + 状态推进 + 术语冲突外置（terms.csv 可经 --terms 导入）
auto-epublizer import [--unit <id>] [--terms preprocessing/terms.csv]
auto-epublizer g0                # 翻译/导入后立即静态校验（术语命中为真实缺陷须逐条核验；长度比才是 advisory）

# 6. 审校（agent 任务）：agent 按 G1–G3 语义自行审校，写 reviews/review-<ts>/
#    （issues/patches/summary/result.json；qa 从 result.json 读 g1/g2/g3 计数）

# 7. 封装输出
auto-epublizer build          # 纯译文 / 双语 EPUB → output/（--theme 选排版主题）

# 8. 质检（G0 静态校验 + G4 审计 + G5 汇总放行 → report.json）
auto-epublizer qa             # 结构审计 + epubcheck
auto-epublizer status --json  # 查看进度/状态机/产物-状态对账
```

仅转换不翻译：`auto-epublizer convert <input> -o output/book.epub`。

**状态不变式**：语义产物由 agent 手写，`publication.json` 状态只经 CLI 命令推进
（`import` 登记入口；审校产物 `result.json` 由 agent 手写、状态推进参照其契约），
agent 不手工编辑；所有产物汇入同一套 G0 校验、状态机、术语闭环、构建与质检。

## skills/ 目录（面向下游 agent 的可安装指引）

`skills/auto-epublizer/` 是**模块一**：把 `docs/` 里的设计翻译成「下游 agent 照抄就能完成
一本书」的步骤。它与本文件（`AGENTS.md`）分工如下：

| 文档 | 受众 | 回答的问题 |
|---|---|---|
| `AGENTS.md`（本文件） | 开发/维护本项目的 agent | 项目是什么、怎么实现、怎么验证 |
| `skills/auto-epublizer/` | 使用本 CLI 处理一本书的 agent | 每一步怎么做、怎么判读结果、怎么修 |

`skills/` 结构（纯文档，不写业务逻辑）：

```text
skills/auto-epublizer/
├── SKILL.md               # 入口：按工作区状态路由（无 publication.json → 全新流程；有 → 续跑）
├── manifest.json          # 元数据 + references 清单
└── references/            # 分主题操作指引（按需只读当前阶段的一份）
    ├── workflow.md        # 阶段路由 + 命令总览 + status --json 判读 + 故障排查
    ├── preprocessing.md   # 预处理：读 facts → agent 撰写 plan/global/units/terms/risks/report
    ├── ingest.md          # 文件解析（pandoc / PDF 按页切片 / OCR 兜底）
    ├── structure.md       # 四层结构归类 + 清洗 + 溯源
    ├── analysis.md        # 分层理解（overview/global/units/keypoints）+ 术语播种
    ├── translation.md     # 切片翻译 + 句对齐 + 术语三态闭环
    ├── review.md          # 六道关 QC 操作指引（G0–G5 何时跑、怎么看报告、怎么修）
    ├── build.md           # EPUB 封装 + 确定性
    ├── qa.md              # epubcheck + 解包审计
    └── style.md           # 文体档案（novel/academic/paper/poetry/newspaper）+ langprofile
```

- 每个 reference 只覆盖一个阶段，SKILL.md 用「Route Before Acting」路由表让 agent 按当前
  阶段只读一份，不一次加载全部。
- 文档以**实际 CLI 能力**为准：未实现项（如 G0 自动接入、网络检索）
  显式标注「后续扩展点」，避免 agent 照未实现功能操作。
- 安装：`scripts/install-skills.sh --target opencode` 复制到 agent 的 skills 目录。

> 维护本仓库时，改了 CLI 命令/工作区契约/QC 行为，须同步更新对应 reference 与 SKILL.md 路由表。

## 文档地图（docs/ 四类文档各归其位）

| 目录 | 定位 | 内容 | 何时新增/更新 |
|---|---|---|---|
| `docs/` 根 | **规范 / 交接 / 测试指南** | 设计规范（`pdf-content-spec` / `epub-template-spec` / `postprocessing-spec`）、交叉文档（`agent-vs-code` / `quality-control` / `quality-lessons` 规范表 / `configuration` / `translation-flow` / `publishing-workflow`）、交接（`workstate`）、豆包环境测试指南（`testing-doubao`） | 改设计/接交流程时 |
| `docs/plans/` | **每次任务的计划文档** | `YYYY-MM-DD-<主题>.md`，立项→实施→回写状态（完成标提交号）；README 索引 | 每轮开发任务立项时 |
| `skills/auto-epublizer/references/` | **面向「用 CLI 处理书」的 agent 常规操作指引** | 每个阶段一份（workflow/preprocessing/ingest/…/style） | 改 CLI 命令/工作区契约/QC 行为时 |
| `skills/auto-epublizer/lessons/` | **真实工作沉淀的特定情况经验** | 判据/处置/验证三段式，每篇一主题；索引含来源与去向 | 遇到并解决一个特定源站/脏源/边界情况时 |

**经验教训的归位规则**：计划文档的验证记录（如 `pdf-dogfooding` §6）是可复用经验的
**来源**，但经验本体**沉淀到 `lessons/`**（计划文档保留验证上下文，lessons 提供
「同型情况怎么判/怎么修」）；规范表（如 `quality-lessons.md` 的正向目标/负面限制）
留在 `docs/` 作为 QC 设计依据。新教训一律写 `lessons/`，不往 plans 里塞经验正文。

## 工作区目录契约

```text
<book-slug>/
├── source/           ① 待处理文件（原样，绝不改动）
├── output/           ② 成品 EPUB（<slug>.epub / <slug>-bi.epub）
├── structured/       ③ 按出版物四层结构拆分的源文（frontmatter/body/backmatter/media）
│                     + raw/（处理源文件的中间产物：OCR 页图、PDF→HTML、
│                     pages/（扫描页渲染图）、mineru/（MinerU 解析产物），持久化供审查）
├── analysis/         ④ 分层理解（agent 产物：overview/global/units/keypoints/glossary 等）
├── translation/      ⑤ 译文（镜像 structured 树）+ align/<unit-id>.jsonl 句级对照表
├── reviews/          ⑥ 审校运行记录 review-<ts>/（issues/patches/summary/result.json）
├── references/       ⑦ 参考：user/（用户上传）+ web/（agent 网络检索）+ index.jsonl
├── preprocessing/    ⑧ 预处理层：facts.json/facts.md（CLI 零 token 事实）+
│                       agent 撰写的 todo.md（逐细节任务清单）/ plan/global/units/terms/risks/report
├── publication.json  权威索引（DC 元数据 + 内容树 + 状态机 + 配置快照）
├── .progress.json    （预留）批次级断点；当前未落盘，断点=单元级跳过
├── glossary.db       术语库内部索引（可选，SQLite）
└── events.jsonl      追加式行为账本
```

单元状态机：`pending → split → analyzed → translated → aligned → reviewed → built`
（`reviewed`=通过审校，`built`=已封装；`convert` 路径跳过理解/翻译/审校，直接 split → built）。

目录生命周期：`source/`、`references/user/` 不可动；`structured/`（含 `raw/` 中间产物）
持久化保存供审查，可由源文件重建；`preprocessing/facts.*` 由 CLI 幂等生成，其余
`preprocessing/` 产物、`analysis/`、`translation/`、`reviews/`、`output/` 是智能产物；
`events.jsonl` 是追加式账本；`.progress.json` 为预留断点文件（当前未落盘，
实际断点续跑 = 按 `publication.json` 单元状态跳过已完成单元）；
`publication.json`、`glossary.db` 是权威真相。

**预处理分工**：`preprocess` 命令只产出零 token 事实（嗅探/元数据/TOC/体检/规模）；
**方案决策与分层理解是 agent 任务**——读 facts.md 与 docs 决策表写 `plan.md`，
用自身能力完成全局理解/章节理解/术语预提取/风险标注。理解上下文的读取优先级：
`analysis/`（agent 直写）→ `preprocessing/`（agent 预处理产物）。

术语表三态：`种子 → 候选 → 冲突 → 确认`。`analysis/glossary.csv` 是权威（人类/agent 可读），
冲突外置到 `glossary_conflicts.jsonl`；翻译 worker 只读快照 + 追加提案，由单线程合并器裁决后写回 CSV。

句级对照表 `translation/align/<unit-id>.jsonl` 每行一句：

```jsonl
{"seq": 1, "src": "原句", "tgt": "译句", "note": null}
```

`seq` 是双语排版、QA 定位、断点续跑的锚点；`note` 记录拆句/并句/漏译/存疑，
`corr:wrong→right` 前缀 = 源文勘误先例留痕（translate/import 两路径自动写入）。

## 架构边界

三包 monorepo，依赖方向必须保持（`test_architecture_boundaries.py` 固定）：

```text
auto_common（基础设施：config/workspace）
      ▲
auto_translator（确定性领域逻辑：glossary/genre/analysis(detect)/translation(align)/review(g0/models/convergence)）
      ▲
auto_epublizer（转 EPUB + 编排：ingest/structure/build/qa + orchestrator/cli）
```

逻辑分层（跨包不变）：

```text
CLI → Orchestrator（薄 façade）→ 领域服务 → glossary / align / g0 / workspace(RunStore)
```

- `auto_common` 是叶子，不得依赖 `auto_translator` / `auto_epublizer`。
- `auto_translator` 只依赖 `auto_common`，不得依赖 `auto_epublizer`。
- `orchestrator.py` 只装配与路由，不直接调用领域函数，不持有线程池。
- 下层不得反向导入 orchestrator。
- 全库不得有任何 LLM 模块/调用（唯一 LLM 原则，由架构边界测试强制）。
- 并发属于具体领域服务；结果必须按稳定原文序合并，不得让线程完成顺序改变输出。
- 第三方依赖保留各自许可证并在 `THIRD_PARTY_LICENSES.md` 登记；AGPL 依赖可直接引入（项目自身为 AGPL）。

**能力分工**：CLI 只做确定性计算与校验放行——解析/切片/检测（语言体裁启发式、PDF 插图/
表格/公式）、G0 静态校验、import 登记、构建、qa 审计。**语义判断类工作全部由 agent
自身完成**：理解层（`analysis/` 与 `preprocessing/`）、翻译（`translation/`+`align/`）、
审校（G1–G3，写 `reviews/review-<ts>/result.json`）、术语冲突终局裁决
（`glossary_conflicts.jsonl` → 写回 `glossary.csv`）、inserts 语义（content_desc/latex）、
未收敛情形（`max_rounds`/`no_progress`/`unresolved_fixes`）的处置、源文勘误、复杂结构
判断、修复与放行决策。agent 只需**读文件、跑 shell、写文件**三种基础能力，
**不要求 MCP、子代理或任何特殊工具**。

**能力自检先行**：agent 开工前先跑 `auto-epublizer doctor` 判断环境工具链（pandoc/pymupdf/
OCR（tesseract/ocrmypdf/rapidocr）/epubcheck/MinerU/网络），并**自报 multimodal 与
search**（能否看图、有无搜索工具，CLI 无法探测）——据此按
skills 的能力-路由决策表选择 ingest 路由（pandoc / 按页切片 / 扫描件档：
**MinerU 外部 API 最优先（无 key 时先询问用户）→ 传统 OCR + agent 逐页阅读兜底**；
「看」是 agent 自身能力）。PDF 内容提取
（插图/表格/公式/多栏/书签切章）规范见 [docs/pdf-content-spec.md](docs/pdf-content-spec.md)。

## 状态与续跑不变量

- `publication.json` 是初始化成功的最终标志：派生状态先落盘，最后原子提交。
- JSON 状态经同目录临时文件 + `os.replace` 原子写；禁止直接覆盖。
- 状态用源文件 `source_sha256` 绑定内容；不得按同名静默复用不同内容。
- 已完成单元必须可安全跳过；改翻译/术语/解析/审校缓存时须覆盖中断后续跑。
- 导出从一致快照读取；审校只能改影子译文，正式 segment 只有显式 Autofix 可改。
- 用量账本追加式；一次审校增量只合并一次，重试/续跑不得重复计费。

## 质量检验流程（六道关）

1. **零 token 廉价校验**：对照表完整性、句数一致、长度比异常（<0.30 / >3.0 / 空）、标点/术语命中纯函数。
2. **逐批审校 Agent（cheap）**：missing/added/mistranslation/terminology/pronoun；宁缺毋滥；JSON 协议末尾必须 `reviewed_segments` + `complete:true`，违例整批重试。
3. **证据取证 Agent Loop（strong）**：候选先取证再裁决，禁止假设未取得的上下文；术语库与影子修订都是待核验材料。
4. **冲突仲裁 + 影子修订 + 盲复审**：跨块矛盾终局仲裁；Fixer 只在影子 overlay 改；下一轮盲审不传旧说明；连续 clean 确认或 max_rounds 收敛；振荡检测（摘要 SHA-256 循环）。
5. **EPUB 结构 QA**：epubcheck 零 error + 解包逐项审计（mimetype 首位、manifest/spine/nav 解析、封面、lang、每章一个 h1、脚注双向跳转、无残留）。
6. **交付验收**：汇总 G0–G4 + 溯源审计生成 `report.json`（g0_flags/g1_issues/g2_confirmed/
   g3_termination/error_rate/provenance_coverage/units_missing/media_lost/released/
   released_reason），放行条件为 **G0 术语命中清零（`terminology` 是真实缺陷，非 advisory）**、
   `g2_confirmed == 0` 或全部已修订、`g4_epubcheck_errors == 0`、
   `g4_audit == "pass"`、溯源完整（`provenance_coverage ≈ 1.0`（无翻译产物为 null）、
   三边对账/媒体溯源零缺失、目录层级不扁平；详见 docs/postprocessing-spec.md §5）。

> 翻译期间的过程校验（QC 落实，豆包实测教训）：每译 3–5 个单元 build 一次，格式契约
> 问题当轮暴露（图片段缺 `<img>` 行、空行破坏）；每单元写完 `import --unit <id>` +
> `g0 --unit <id>` 当场处理术语告警；标题开工前一次性定稿进 plan.md。

## 配置、密钥与 provider

- 配置**无任何 LLM/密钥段**（唯一 LLM 原则）；可选外部解析 API 的 `MINERU_API_KEY`
  只从环境变量读取，禁止写入源码、测试、文档示例或提交。
- 测试全部确定性离线：不调用任何 LLM、不依赖外部网络。
- 用户可预期错误 → 明确异常 + 简洁中文提示；CLI 不打印 traceback。

## 开发与验证命令

```bash
uv sync                      # 安装
uv run pytest -q             # 全量测试（离线、确定、快速，不依赖真实书籍）
uv run ruff check .
uv run ruff format --check .
```

修复缺陷先添加能失败的最小回归测试；测试数据写 `tempfile`，不依赖仓库外的真实书籍。

## 代码与交付风格

- 中文领域命名与提示词；公共代码带类型提示与简短 docstring。
- 遵循 pyproject 的 Ruff 规则（目标 Python 3.12）。
- 提交信息用 Conventional Commits；只暂存本次任务修改的文件；不提交密钥与用户本地数据。
- 交付前运行受影响测试 + ruff check + ruff format --check。
