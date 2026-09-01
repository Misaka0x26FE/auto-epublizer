# auto-epublizer

一个 Python CLI 工具，提供两项能力、一条共用管线：

1. **翻译**：把外语文献翻译到任意可配置的目标语言。
2. **转 EPUB**：把来源复杂的文件（PDF/扫描 PDF/EPUB/DOCX/HTML/TXT/Markdown）完整、规则地转换为标准 EPUB 文件。

两条能力共享同一条"归一化 → 结构化 → 翻译 → 封装"管线，避免两套解析。

项目分为两大模块：**`skills/`**（教 agent 如何用本项目完成任务 + 做质量控制）与
**`src/auto_epublizer/`**（Python 代码：文件解析、清洗、中间文件处理、质量控制、EPUB 写出）。
开发任务与里程碑见 [docs/development-plan.md](docs/development-plan.md)。

## 已锁定决策

| 项目 | 决策 |
|---|---|
| 形态 | Python 3.12 CLI，`uv` 管理依赖，`typer` + `pydantic` + `rich` |
| 翻译引擎 | OpenAI 兼容 API（`base_url`/`api_key`/`model` 多 profile），目标语言任意可配 |
| 输出样式 | 纯译文 / 双语对照两种，命令参数切换 |
| 输入格式 | TXT/Markdown、HTML、DOCX、EPUB、PDF（文字层）、扫描 PDF（OCR） |
| 架构模型 | 全新 `publication.json` 工作区 + 工作区目录（不沿用传统 `split/` 流程） |
| 句级对照表 | JSONL；**段落翻译 + 模型返回句对 JSON** |
| EPUB 写出 | 纯 Python 直写 EPUB 3，不依赖 pandoc/calibre；内置审计 + 可选 epubcheck |
| OCR | RapidOCR 离线默认 + 同一 OpenAI 兼容端点视觉模型兜底 |
| 双语排版 | 段落级上下对照 |
| 校验 | epubcheck 自动拉 jar 到 `~/.cache`，零 error 才放行 |
| 许可 | 项目自身代码 **AGPL-3.0**；第三方依赖保留各自许可证并登记 |

## 管线

```text
source/ ──ingest──▶ structured/（四层结构拆分）
                        │
                        ▼
                    analysis/（agent 解析：概要/全局/每章/重点/术语表/人物表）
                        │
                        ▼
                    translation/（读 analysis/ 翻译 → 句级 align/ 对照表）
                        │
                        ▼
                    output/（EPUB：纯译文 / 双语）
```

每单元状态机：`pending → split → analyzed → translated → aligned → reviewed → built`，记入
`publication.json` + `.progress.json`。其中 `reviewed` = 通过 G1–G3 审校（影子修订/autofix 后），
`built` = 已封装进 EPUB；`convert` 路径跳过 `analyzed/translated/reviewed`，直接 `split → built`。

翻译流程详细设计（切片 → 分层理解注入 → 句对 → 术语表闭环）见 [docs/translation-flow.md](docs/translation-flow.md)；
分文体特殊优化（小说/学术专著/论文/诗歌/报刊）见 [docs/genre-style.md](docs/genre-style.md)，
每种文体的专门文档在 [docs/genres/](docs/genres/) 下；
PDF 解析难点与方案见 [docs/pdf-parsing.md](docs/pdf-parsing.md)；
配置项完整 schema 见 [docs/configuration.md](docs/configuration.md)。

## 工作区目录结构

```text
<book-slug>/                     # 每本书一个工作区目录，init <input> 生成
├── source/                      # ① 源文件目录：待处理文件原样存放，绝不改动
│   ├── book.pdf                 # 主文件（publication.json 的 meta.source 指向它）
│   └── supplement…              # 可选辅助文件（分卷、勘误、附图等）
│
├── structured/                  # ③ 中间文件目录：按出版物结构拆分的源文 + 处理源文件的中间产物
│   ├── cover.md + cover.jpg     # 外观（封面文字 + 封面图）
│   ├── frontmatter/             # 正文前（前置辅文）
│   │   ├── titlepage.md         # 书名页
│   │   ├── copyright.md         # 版权页（ISBN/CIP）
│   │   ├── dedication.md        # 献词
│   │   ├── foreword.md          # 他序
│   │   ├── preface.md           # 自序/前言
│   │   ├── toc.md               # 目录（源书目录）
│   │   └── …
│   ├── body/                    # 正文：部/篇/章/节
│   │   ├── ch01.md
│   │   ├── ch01/s01.md          # 节（可选嵌套）
│   │   └── …
│   ├── backmatter/              # 正文后（后置辅文）
│   │   ├── afterword.md         # 后记/跋
│   │   ├── appendix/a.md        # 附录
│   │   ├── notes.md             # 尾注
│   │   ├── bibliography.md      # 参考文献
│   │   └── index.md             # 索引
│   ├── media/                   # 抽取的图片/表格资产（文件名与单元引用一致）
│   └── raw/                     # 处理源文件的中间产物（OCR 页图、PDF→HTML 等），持久化供审查
│
├── analysis/                    # ④ 解析目录：agent 对源文的理解（翻译的强制输入）
│   ├── overview.md              # 内容概要（整书）
│   ├── global.md                # 全局理解（主题/论证脉络/文体/跨章依赖/风险）
│   ├── units/                   # 每单元理解（与 structured 所有单元对应，含 front/back matter）
│   │   ├── ch01.md
│   │   └── …
│   ├── keypoints.md             # 重点内容（难点段落/复杂排版/多语片段/高风险处）
│   ├── glossary.csv             # 术语表（人类可读视图，由 glossary.db 导出）
│   └── characters.csv           # 人物表（person/角色、别名、身份、出现章节）
│
├── translation/                 # ⑤ 翻译中间目录：译文 + 句级对照表
│   ├── frontmatter/…            # 镜像 structured 的目录树（纯译文文件）
│   ├── body/ch01.md
│   ├── backmatter/…
│   └── align/                   # 句级对照表（每个单元一个）
│       ├── ch01.jsonl
│       └── …
│
├── references/                  # ⑦ 参考目录：用户上传 + agent 网络检索的参考信息
│   ├── user/                    # 用户上传（原样保留，绝不改动）
│   ├── web/                     # agent 检索整理后的笔记（必须带来源 URL 与检索时间）
│   └── index.jsonl              # 条目索引：{id, path, origin, url?, sha256, retrieved_at, note}
│
├── reviews/                     # ⑥ 审校运行记录：review-<ts>/ 每轮 issues/patches/summary/usage
│
├── output/                      # ② 输出目录：成品（二进制，走 Release，不入 git）
│   ├── <书名简写>-<作者简写>.epub     # 纯译文版（全 ASCII 文件名）
│   └── <书名简写>-<作者简写>-bi.epub  # 双语版
│
├── publication.json             # 权威索引：DC 元数据 + 内容树 + 状态机 + 配置快照
├── .progress.json               # 断点续跑（可丢弃）
├── glossary.db                  # 术语库内部权威（SQLite + 冲突表）
├── events.jsonl                 # 追加式行为账本（翻译/审校/产物对账）
├── usage.json                   # token 用量账本（追加式，一次增量只合并一次）
├── .gitignore                   # 自动生成：排除二进制（OCR 页图、output/、glossary.db 等）
└── README.md                    # 工作区说明：元数据、来源、复现方式、许可提示
```

### 目录生命周期

| 类别 | 目录/文件 | 处置 |
|---|---|---|
| 不可动 | `source/`、`references/user/` | 用户原始材料，绝不改动 |
| 中间产物（持久化） | `structured/`（含 `raw/`） | 源文拆分 + 处理源文件的中间文件，持久化保存供审查；可由源文件重建 |
| 智能产物 | `analysis/`、`translation/`、`reviews/`、`output/` | 管线产出，有状态、可续跑 |
| 账本/断点 | `.progress.json`、`events.jsonl`、`usage.json` | 追加式，保留用于审计与续跑 |
| 权威 | `publication.json`、`glossary.db` | 唯一真相，原子写 |

### 参考目录（references/）

- **`references/user/`**：用户上传的参考材料（既有术语表、官方译名表、相关译本、风格指南等），原样保留、与 `source/` 同级待遇。`init <input> --reference <path...>` 导入，或用户直接放入。
- **`references/web/`**：agent 在 `analyze` 阶段检索网络后整理的笔记（人物译名来源、领域术语规范、消歧依据等）。**每条必须带来源 URL 与检索时间**，保证可追溯。
- **`references/index.jsonl`**：权威清单，记录每条参考的 `origin`（user/web）、路径、URL、SHA-256、用途。

参考信息的定位是**待核验证据，不是事实**：

- `analyze` 阶段用它播种术语库、消歧人物/术语、补充风格指南；
- `review` 取证 Agent 可引用，但和术语库、影子修订一样属于"待核验材料"，来源不明或与原文语义冲突时不得采信；
- 不要求仓库内的参考目录成为任何私有缓存的必需依赖。

### 元数据与源语言

- **元数据（DC 15 项）**：`init` 时从源文件自动提取（EPUB 的 OPF / PDF 的 info / DOCX 属性 / HTML meta），
  写入 `publication.json.meta`；缺项或存疑的由用户/agent **确认而非猜测**（借鉴传统"Confirm, rather than infer"）。
  映射：title/creator/publisher/date/identifier(isbn,doi)/language/rights/description/subject…
- **源语言**：`language.source: auto` 时，`analyze` 阶段用 cheap 档检测主要语言；失败则要求显式指定
  ISO 639-1 代码（借鉴 wenyi `detect_language_ai`）。目标语言始终显式指定（任意可配）。
- **多目标语言**：一个工作区 = 一本书 × 一个目标语言；同一本书翻多个目标语言则建多个工作区（`--target` 不同）。

### 辅文五类 → 目录映射

| 辅文类型 | 功能 | 落位 |
|---|---|---|
| 识别性辅文 | 识别与著录 | cover / titlepage / copyright |
| 介绍性辅文 | 推广与导读 | preface（简介）/ foreword |
| 说明性辅文 | 说明体例与缘起 | preface / foreword / afterword / notes |
| 检索性辅文 | 检索定位 | toc / index |
| 参考性辅文 | 补充参考 | notes / bibliography / appendix / glossary |

即出版物"外观 ＋ 正文前 ＋ 正文 ＋ 正文后"四层骨架的直接落地。

## 句级对照表设计

`translation/align/<unit-id>.jsonl` 每行一句：

```jsonl
{"seq": 1, "src": "The quick brown fox jumps.", "tgt": "敏捷的棕狐跳起。", "note": null}
{"seq": 2, "src": "It never looks back.",    "tgt": "它从不回头。",      "note": null}
```

- `seq`：单元内句序号，是双语排版、QA 定位、断点续跑的锚点。
- `note`：对齐异常标记（拆句/并句/漏译/存疑）。
- **纯译文**构建只用 `tgt` 列；**双语对照**构建用 `src`↔`tgt` 成对渲染；QA 逐句 diff 也基于它。
- **译者注 vs 作者注**：脚注/尾注翻译时，原书作者的注释（作者注）与翻译时新增的说明（译者注）必须区分——
  译者注统一标注「——译者注」，作者注保留原样式；EPUB 里两者样式可辨、双向跳转（对应传统 epub 规范）。

翻译过程硬约束：

1. 每单元翻译前必须读取 `analysis/` 对应文件（overview + global + 该章理解 + keypoints + glossary + characters），作为上下文注入。
2. 翻译输出必须是**对齐的句对**，不能只吐一段译文——这是对照表成立的唯一来源。
3. 翻译策略：按段落输入保上下文连贯，但要求模型返回对齐句对 JSON。

## 模块划分

| 模块 | 技术 | 说明 |
|---|---|---|
| CLI / 配置 | `typer` + `pydantic` + `rich`；YAML 配置 | `uv` 管理 |
| 工作区 | `pydantic` schema + JSON 原子写 | publication.json + 工作区目录 + 状态机 |
| 状态与续跑（RunStore） | 借鉴 wenyi：tmp+`os.replace` 原子写、`source_sha256` 绑定、多级 flock、manifest 最后原子提交、`events.jsonl` 账本、导出快照 | 断点续跑与一致性核心 |
| 数据模型 | Document → Chapter → Segment（pydantic v2） | Segment 是最小可翻译/对齐单元，带 `anchor`/`resource_href`/`cont`；meta 记 `source_page` 溯源 |
| PDF（文字层） | `pymupdf` + `pymupdf4llm`（AGPL，与本项目同许可兼容）| 按页切片抽文字层 + 版面块 → Markdown，逐页落 `structured/raw/` |
| 扫描 PDF（OCR） | 可插拔：默认 `rapidocr_onnxruntime`；难页走视觉模型 | 复杂排版可选 MinerU（Apache 2.0）本地后端 |
| EPUB 输入 | `pandoc` 统一 → Markdown（纯文本）+ 抽取媒体 | 非 PDF 一律先走 pandoc |
| DOCX / HTML | `pandoc` 统一 → Markdown + 媒体 | 同上 |
| TXT/MD | 原生解析 + 标题推断（pandoc 兜底） | 最简路径 |
| 非 PDF 兜底 | pandoc 处理不了 → 转 PDF → 走 PDF 管线 | 统一兜底路径 |
| 结构重建 | 自研 `structure/` | 四层结构归类、层级、页眉页脚/页码剔除、分栏、脚注配对、表格保形 |
| LLM 抽象 | 借鉴 wenyi：`complete`/`complete_json` + 档位 tiers（strong/cheap/fast）+ 统一重试 + 用量账本 + 宽松 JSON 解析 | 多 provider 可插拔 |
| 翻译引擎 | OpenAI 兼容 API，段落翻译返回等长数组，失败逐段兜底 | 目标语言任意可配 |
| 术语表 | CSV 权威 + `glossary_conflicts.jsonl` 冲突外置 + 可选 SQLite 索引；worker 只读+追加提案、单线程合并裁决；逐批按出现过滤注入 | 三态生命周期，灵活可插拔 |
| EPUB 写出 | `zipfile` + `lxml` 直写 | opf + nav.xhtml + NCX + 封面 + DC 元数据 |
| QA | 内置审计 + 可选 epubcheck | 零 error 放行 |

## 参考项目：wenyi

参考 [wenyi](https://github.com/BigDawnGhost/wenyi)（包名 `trans-novel`）——面向长篇文本的多阶段翻译工具。它实现了很多我们想要的能力，以下记录**借鉴**与**差异**。

### 借鉴（直接采用其模式）

1. **数据模型**：`Document → Chapter → Segment`。Segment 是最小可翻译/可对齐单元（通常一段），带 `anchor`（EPUB 回填占位符）、`resource_href`、`cont`（超长段拆分后的续段标记，回填时并回原段）。
2. **状态与续跑（RunStore）**：
   - 同目录临时文件 + `os.replace` 原子写；
   - `source_sha256` 绑定源内容，拒绝"同名不同内容"静默复用状态；
   - 多级文件锁（run/state/event/assemble）隔离长流程与短状态读写；
   - `manifest.json` 最后原子提交，作为初始化完成标志（"派生状态先落盘，manifest 最后"）；
   - `events.jsonl` 追加式行为账本，用于审计与批次检查点恢复；
   - 导出前冻结一致快照（ExportSnapshotStore），避免读到 manifest 与章节文件的混合时刻。
3. **LLM 抽象**：`complete` / `complete_json` 统一接口 + 档位 tiers（strong/cheap/fast）+ 传输层统一重试（关闭 SDK 内置重试避免嵌套）+ 用量账本 + 畸形 JSON 宽松解析。
4. **段级对齐策略**：一批 N 段整体发给模型，要求返回**等长 JSON 数组**；数量不符重试（align_retry_limit），仍不符则逐段兜底翻译——从结构上杜绝整段漏译。我们在此之上再加**句级对照表**（见上文）。
5. **术语库**：SQLite 存储 + `term_conflicts` 冲突表；同 source 出现不同 target 时保留当前译法、记录候选待人工裁决；逐批按正文实际出现过滤注入 prompt；按 rowid 排序稳定前缀缓存。
6. **提示词工程**：system 模板保持全静态（命中 DeepSeek 等前缀缓存）；user 模板按"静态→动态"排列（风格/全书概览 → 章梗概 → 术语表 → 前文译文 → 待译正文）；标点统一规范（PUNCT_RULE）。
7. **全书理解**：风格分析（叙事人称/语气/语域/对话风格 + 人物/术语种子）→ 并行逐章梗概 → 全书概览，全部注入每个翻译批次。这正是我们 `analysis/` 目录的自动化来源。
8. **架构边界**：`CLI → Orchestrator（薄 façade）→ 领域服务 → agents/ingest/glossary/assemble`，下层不得反向导入上层，并发只属于领域服务、结果按稳定顺序合并；用 `test_architecture_boundaries.py` 固定契约。
9. **配置与续跑**：YAML 配置（language/llm/segment/pipeline/paths/output），同一命令幂等续跑。

### 差异（我们做不同 / 更强）

| 维度 | wenyi | auto-epublizer |
|---|---|---|
| 目标语言 | 仅简体中文 | 任意语言可配 |
| 对齐粒度 | 段级等长数组 | 段级对齐 + **句级 JSONL 对照表** |
| 结构模型 | 全部按章处理 | 显式出版物**四层结构**（frontmatter/body/backmatter + 外观） |
| 核心功能 | 翻译为主 | **转换（convert）为一等功能**，翻译可选 |
| PDF | 依赖 MinerU 外部 API | 本地 OCR（RapidOCR）+ 可选视觉 LLM |
| 工作区 | `state/<slug>/` | `publication.json` + 工作区目录 |

## 目录结构改进（六项缺口解决方案）

对照 wenyi 实战，上一版目录有六处缺口，均已解决：

| # | 缺口 | 解决方案 |
|---|---|---|
| 1 | 运行痕迹无处安放 | 新增 `events.jsonl`（行为账本）、`usage.json`（token 用量）、`reviews/`（每轮审校记录） |
| 2 | `analysis/` 只覆盖正文 | 改为 `analysis/units/`，front/back matter（序、后记等散文单元）同样有理解文件 |
| 3 | 术语表单一 CSV 扛不住复杂性 | 见下节「术语表（灵活方案）」：CSV 权威 + 冲突外置 + 存储可插拔 |
| 4 | 处理源文件的中间产物无处安放 | 归入 `structured/raw/`（OCR 页图、PDF→HTML 等），持久化保存供审查 |
| 5 | 续跑无配置快照 | `publication.json` 固化本次运行配置（目标语言/引擎/双语开关），续跑一致 |
| 6 | 输出命名无约定 | `output/<title>.<lang>.epub`（纯译文）、`<title>.<lang>-bi.epub`（双语） |

## 术语表（灵活方案）

翻译术语管理复杂（多类别、别名、同词异译、语气化称呼），不绑定某一种存储，采用
**三态 + CSV 权威 + 冲突外置 + 存储可插拔**。

### 三态生命周期

```text
种子(seed，analysis 播种 / references 导入)
  → 候选(proposed，翻译中抽取)
  → 冲突(conflict，同词异译待裁决)
  → 确认(confirmed，写回 glossary.csv，注入翻译)
```

### 权威文件（人类/agent 可读，git 友好）

`analysis/glossary.csv`（扩展 schema）：

```csv
source,target,type,aliases,gender,reading,status,note
```

- `type` ∈ person / place / org / term / work / event / appellation / honorific / speech / fixed_expr；
- `aliases` 用 `|` 分隔（同一 source 的其它写法/简称/拼写变体）；
- `status` ∈ confirmed / pending。

`characters.csv` 是**人物档案**（`source,target,aliases,gender,role,first_chapter,note`），比 glossary 的
`person` 类更细（含角色身份、出现章节）；`glossary.csv` 的 `person` 类只存译名用于翻译注入。两者同源
（`analyze` 生成），characters 是 person 类术语的详细视图。

冲突外置到 `analysis/glossary_conflicts.jsonl`（追加式）：

```jsonl
{"source":"…","existing_target":"…","proposed_target":"…","type":"…","chapter":1,"status":"open"}
```

### 并发策略（关键）

- 翻译 worker **只读**术语表快照 + **追加提案**，绝不并发写术语表；
- 提案由**单线程合并器**归并进 conflicts，人工/agent 裁决后才写回 CSV；
- 并发安全因此不依赖数据库，CSV 始终是单一权威真相。

### 存储可插拔

- **默认**（短书 / agent 友好）：纯 CSV + conflicts.jsonl；
- **可选**（长书 / 高并发）：`glossary.db`（SQLite）作内部查询索引，CSV 仍为导出视图；
- 术语注入翻译 prompt 时按正文实际出现过滤（借鉴 wenyi 的 `terms_in_text`）；称谓/敬称/口癖/固定表达只按完整 source 精确匹配，避免裸名 alias 误注入。

## Agent 友好设计

目标：用户把仓库地址发给一个 agent，agent 仅凭仓库内的 `AGENTS.md` + 文档即可对一本著作完成完整、高质量的处理，无需逐页阅读源码。

**硬性约束——只依赖 agent 基础能力**：使用本项目的 agent 只需要
**读文件、跑 shell 命令、写文件**这三种基础能力。**不需要 MCP、不需要子代理、不需要任何
特殊工具**。所有"智能环节"（解析理解、翻译、审校、取证、仲裁、修订）都由 CLI 内部直接
调用 OpenAI 兼容 API 完成，**不是**把调用方 agent 当作子代理或经 MCP 编排。

设计要点：

1. **`AGENTS.md` 作为唯一入口契约**：写明安装（`uv sync`）、配置（环境变量密钥）、阶段命令、状态目录、不变量、验证命令与故障排查。
2. **CLI 子命令映射管线阶段**，agent 按阶段推进、每步可验证：

   ```text
   auto-epublizer init <input>      # 建工作区：source/ + publication.json + 四层结构拆分（--reference 导入参考）
   auto-epublizer analyze           # 生成 analysis/（概要/全局/每单元/重点/术语表/人物表）+ references/web/ 检索
   auto-epublizer translate         # 翻译 → translation/ + align/ 对照表
   auto-epublizer review            # 审校（只读影子修订）→ 质量报告
   auto-epublizer convert <input>   # 仅转换（不翻译）→ EPUB
   auto-epublizer build             # 封装 EPUB（纯译文 / 双语）
   auto-epublizer qa                # 结构审计 + epubcheck
   auto-epublizer status [--json]   # 进度 / 状态机查询
   ```

3. **幂等与续跑**：同一命令中断后重跑即可续；已完成单元安全跳过。
4. **机器可读输出**：`status --json`、`qa --json`、`review --json` 输出稳定 JSON 报告；明确 exit code；用户可预期错误给清晰中文提示，不打印 traceback。
5. **离线可验证**：测试用 `FakeClient`/mock，不调用真实 LLM 或网络；agent 改完代码跑 `uv run pytest -q` 即可自证。
6. **确定性输出**：同一输入必得同一产物；并发结果按稳定原文序合并，不随线程完成顺序变化。

## 质量检验体系（重点参考 wenyi）

分五道关，前一道不花 token、后几道逐步加重，成本与质量按需平衡。

**范围边界**：只负责**交付质量**（准确 / 完整 / 一致 / 规范 / 结构正确 / 可复现），
**不做内容的价值观 / 政治 / 思想性判断**。

传统「三审三校」编校流程与我们的映射见 [docs/publishing-workflow.md](docs/publishing-workflow.md)；
六道关的**详细规格（数据契约 / 验收阈值 / 收敛状态机 / 配置项）**见 [docs/quality-control.md](docs/quality-control.md)；
从历史实践提炼的**质量控制办法（正向目标 + 负面限制）**见 [docs/quality-lessons.md](docs/quality-lessons.md)。

### 第 0 道：无模型廉价校验（零 token）

- 对照表完整性：每句原文都有 `src↔tgt` 映射，句数一致；
- 长度比异常：`译文/原文` 字符比 < 0.30（疑似漏译）或 > 3.0（疑似失控/增译）或译文为空；
- 标点规范化、术语命中、章节编号连续性等确定性纯函数检查。

### 第 1 道：逐批审校 Agent（cheap 档）

逐句比对原文/译文，只报确凿问题：`missing`（漏译）/ `added`（增译）/ `mistranslation`（误译）/ `terminology`（术语违例）/ `pronoun`（人称错误）。

- **宁缺毋滥**：合理的语序调整、自然意译、风格润色不算问题，拿不准就不报；
- **严格 JSON 协议**：每条问题带可采纳的 `suggestion`；对象末尾必须依次是 `reviewed_segments` 与 `complete:true` 完整性回执，协议违例整批重试（缩小输入再试），防止坏字段被静默当作"无问题"。

### 第 2 道：证据取证 Agent Loop（strong 档，按需）

初审候选不直接采信，先选择性取证再裁决。只读工具：

- `glossary_term`：按术语查术语库条目；
- `term_occurrences`：术语在全书的命中位置取证；
- `segment_context`：段落附近的跨章上下文；
- `book_context`：风格指南 / 全书概览 / 章梗概。

每轮最多 4 个请求、最多 N 轮取证，禁止假设未取得的上下文；术语库与影子修订都是**待核验材料，不是不可推翻的事实**；互相矛盾时驳回候选或保留基线。

### 第 3 道：冲突仲裁 + 影子修订 + 盲复审状态机

- **冲突仲裁**：不同审校块对同一术语/人称/固定表达给出矛盾建议时，做终局仲裁（suggested / unresolved）；
- **影子修订**：Fixer 只在内存 overlay 上生成"最小修改的完整单段替换"，**正式章节、manifest、术语库全程只读**；
- **盲复审**：下一轮审校不传旧问题说明，只读修订后的影子译文，防止"按说明书打勾"；
- **收敛条件**：连续 N 轮（`review_clean_confirmations`）未发现问题 → `clean_confirmed`；超过 `review_fix_max_rounds` → `max_rounds`；无进展 → `no_progress`；修复失败积压 → `unresolved_fixes`；
- **振荡检测**：影子译文整体摘要（SHA-256）出现 A↔B 循环时判定无进展；
- **Autofix（可选）**：先写可恢复索引，再更新正式 segment `target`；其余历史保留在 Review 目录。

### 第 4 道：EPUB 结构 QA

- `epubcheck` 零 error；
- 直接解包逐项审计（对应传统 `epub-qa.md`）：`mimetype` 首位且不压缩、`container.xml` 指向 OPF、manifest href 全部解析、spine idref 全部存在、封面 `properties="cover-image"`、nav 链接全部可解析、每个内容文档 `xml:lang` 正确且恰好一个 `h1`、脚注引用↔定义双向可跳、无 HTML 残留/提取注释/占位符。

### 关键原则（从 wenyi 提炼）

- 审校**只读正式译文**，影子修订不经确认绝不落正式；
- **证据驱动而非投票**：不因多个 worker 重复出现就确认；
- **确定性**：结果按稳定原文序合并，与并发完成顺序无关；
- **幂等续跑**：内容摘要 + 审校配置指纹 + 术语表指纹三者一致才复用已完成的 Review 结果；
- **用量账本追加式**：一次 Review 增量只合并一次，重试/续跑不得重复计费；
- **终止条件明确**，修复最多三轮，三轮后剩余阻塞项带证据上报。

## 发布与分发

- **工作区即 git 仓库**：文本产物（`structured/` 的 md、`analysis/` 的 md/csv/jsonl、`translation/` 的 md/jsonl、
  `publication.json`、`events.jsonl`、`usage.json`）入库；二进制走 `.gitignore`（OCR 页图、`output/`、`glossary.db`）。
- **成品走 GitHub Releases**：EPUB 是 zip 二进制，不进 git，通过 Release 发布；命名
  `<书名简写>-<作者简写>[-bi].epub`（全 ASCII slug，便于 release）。
- **发布前核对**：版权（仅公有领域/已授权）、署名与译者、元数据完整、epubcheck 零 error、封面可再分发。
- **隐私**：`source/`、`references/user/` 里的私有材料不提交；不发布受版权保护的正文与私密书籍。

## 里程碑

| # | 里程碑 | 交付物 | 验收 |
|---|---|---|---|
| M1 | 脚手架 + CLI + 配置 | `uv` 项目、`convert`/`translate` 命令、config 加载 | `--help` 可跑 |
| M2 | 工作区模型 | publication.json schema + 稳定 ID + 工作区目录 + 状态机 | 单测覆盖 schema |
| M3 | 归一化层 | MD/TXT → HTML → DOCX → EPUB → PDF 文字层 → structured/ | 样例文件抽对结构 |
| M4 | 结构重建 + 清洗 | 层级/页眉页脚/分栏/脚注/表格 | 复杂 PDF 样例通过 |
| M5 | EPUB 直写器 + QA | opf/nav/ncx/封面/DC 元数据 + 内置审计 + epubcheck | epubcheck 零 error |
| M6 | 扫描 PDF OCR | RapidOCR + 视觉 LLM 兜底 | 扫描样张转出正确结构 |
| M7 | 翻译 | analysis 生成 → 段落翻译返回句对 → JSONL 对照表 → 双语构建 | 译后 EPUB 术语一致 |
| M8 | 测试 + README + 打包 | 端到端 fixture 测试、`uv` 可安装 | `pytest` 全绿 |

## 命令形态（目标）

```bash
# ── 完整翻译管线 ─────────────────────────────────────────────
auto-epublizer init <input> [--reference <path...>]   # 建工作区：source/ + structured/ + publication.json
auto-epublizer analyze                                # 生成 analysis/ + references/web/ 检索
auto-epublizer translate [--target zh-CN] [--bilingual] [--no-build]
auto-epublizer review [--autofix]                     # 审校（只读影子修订）
auto-epublizer build                                  # 封装 EPUB（纯译文 / 双语）
auto-epublizer qa                                     # 结构审计 + epubcheck

# ── 仅转换（不翻译）─────────────────────────────────────────
# convert = init(ingest + structure) + build 的快捷路径，跳过 analyze/translate/review
auto-epublizer convert <input> -o output/<书名简写>-<作者简写>.epub

# ── 状态 ────────────────────────────────────────────────────
auto-epublizer status [--json]
```

## 文档索引

| 文档 | 内容 |
|---|---|
| [docs/development-plan.md](docs/development-plan.md) | **开发任务文档**：两大模块（skills + code）+ 里程碑 |
| [docs/configuration.md](docs/configuration.md) | 配置完整 schema |
| [docs/translation-flow.md](docs/translation-flow.md) | 切片翻译流程 |
| [docs/quality-control.md](docs/quality-control.md) | 六道关 QC 规格 |
| [docs/quality-lessons.md](docs/quality-lessons.md) | 历史实践提炼的正向目标 + 负面限制 |
| [docs/publishing-workflow.md](docs/publishing-workflow.md) | 传统三审三校映射 |
| [docs/pdf-parsing.md](docs/pdf-parsing.md) | PDF 方案 |
| [docs/genre-style.md](docs/genre-style.md) + [docs/genres/](docs/genres/) | 文体优化 |
| [template/](template/) | 工作区目录模板 |
