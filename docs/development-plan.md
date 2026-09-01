# auto-epublizer 项目开发计划

本文件是接下来完成项目开发的**任务文档**。它把会话中已定型的全部设计（工作区、管线、翻译、
QC、文体、PDF、许可证）收敛成可执行的两大模块 + 其他事项，并给出现有参考材料索引。

---

## 一、项目定位

一个 Python CLI，两项能力、一条共用管线：

1. **翻译**：外语文献 → 任意可配置目标语言。
2. **转 EPUB**：来源复杂文件（PDF/扫描 PDF/EPUB/DOCX/HTML/TXT/Markdown）→ 标准 EPUB 3。

**对外契约**：用户把仓库地址发给一个**只有基础能力**的 agent（读文件、跑 shell、写文件，
无 MCP、无子代理），agent 仅凭仓库内 `AGENTS.md` + `skills/` + `docs/` 即可完成一本书的
完整高质量处理。所有智能环节由 CLI 内部调用 OpenAI 兼容 API 完成。

**许可**：自身代码 AGPL-3.0；第三方依赖保留各自许可并登记。

---

## 二、两大模块

### 模块一：`skills/` —— 面向 agent 的指引

- 职责：**教 agent 怎么用本项目完成任务、怎么做质量控制**。
- 形态：一个 Skill（`SKILL.md` 入口 + `references/` 分主题文档），可安装到 opencode 等 agent。
- 参照：wenyi 的 `traditional-translation` Skill、epub-builder 的 `skills/epub-builder/`。

### 模块二：`src/auto_epublizer/` —— Python 代码

- 职责：文件解析、清洗、中间文件处理、质量控制、EPUB 写出。
- 形态：Python 3.12 CLI，`uv` 管理，`typer` + `pydantic` + `rich`。
- 参照：epub-builder（稳定 ID、内容树、验证门禁、原图优先、分阶段验证）+ wenyi
  （RunStore、LLM 抽象、术语库、段级对齐、Review 体系）。

---

## 三、仓库结构（目标形态）

```text
auto-epublizer/
├── skills/                        # 模块一：agent 指引
│   └── auto-epublizer/
│       ├── SKILL.md               # agent 入口：按状态路由到各 references
│       └── references/
│           ├── workflow.md        # 阶段路由 + 命令总览
│           ├── ingest.md          # 文件解析（pandoc / PDF / OCR）
│           ├── structure.md       # 清洗 + 结构重建 + 溯源
│           ├── analysis.md        # 分层理解（overview/global/units/keypoints/glossary）
│           ├── translation.md     # 切片翻译 + 句对齐 + 术语表
│           ├── review.md          # 六道关 QC 操作指引
│           ├── build.md           # EPUB 封装
│           ├── qa.md              # epubcheck + 解包审计
│           └── style.md           # 文体档案应用
│
├── src/auto_epublizer/            # 模块二：Python 代码
│   ├── __init__.py
│   ├── cli.py                     # typer CLI + 阶段入口
│   ├── config.py                  # pydantic 配置 + 默认 config.yaml
│   ├── workspace/                 # publication.json + RunStore（原子写/锁/sha256/快照）
│   ├── ingest/                    # 文件解析 → structured/（pandoc/pymupdf/RapidOCR/视觉LLM）
│   ├── structure/                 # 清洗 + 四层结构重建 + 插入元素提取 + 溯源
│   ├── analysis/                  # 分层理解（LLM）：overview/global/units/keypoints + 术语播种
│   ├── translation/               # 切片翻译 + 句级对齐 + align/ 对照表
│   ├── review/                    # 六道关 QC：g0 纯函数 + g1 审校 + g2 取证 + g3 仲裁/影子修订
│   ├── build/                     # EPUB 3 直写（opf/nav/ncx/封面/DC 元数据/epub:type）
│   ├── qa/                        # 结构审计 + epubcheck 集成
│   ├── glossary/                  # 术语表三态（CSV 权威 + conflicts + 可选 SQLite）
│   ├── llm/                       # LLM 抽象（complete/complete_json + tiers + 重试 + 用量）
│   └── genre/                     # 文体档案（声明式 genre profile）
│
├── docs/                          # 设计文档（会话已定型的参考材料）
├── template/                      # 工作区模板（每本书一个目录）
├── tests/                         # 离线测试（FakeClient + tempfile fixture）
├── pyproject.toml                 # uv + Ruff + pytest
├── config.example.yaml            # 配置示例
├── AGENTS.md                      # agent 入口契约
├── README.md
├── LICENSE                        # AGPL-3.0
└── THIRD_PARTY_LICENSES.md        # 第三方依赖许可登记
```

---

## 四、模块一开发任务：`skills/`

| # | 任务 | 内容 | 验收 |
|---|---|---|---|
| S1 | `SKILL.md` 入口 | 按工作区状态路由（无 publication.json → 全新流程；有 → 续跑）；列出阶段命令 | agent 按路由能推进 |
| S2 | `references/workflow.md` | 阶段路由表 + `status --json` 用法 + 故障排查 | 覆盖全部子命令 |
| S3 | `references/ingest.md` | 各格式 → pandoc/PDF/OCR 的选择规则；"非 PDF 走 pandoc，处理不了转 PDF，难页转图" | agent 能判断路由 |
| S4 | `references/structure.md` | 四层结构 + 插入元素提取 + 溯源（source_page）约定 | 对齐工作区契约 |
| S5 | `references/analysis.md` | overview/global/units/keypoints + glossary/characters 播种 | 对齐 analysis/ 契约 |
| S6 | `references/translation.md` | 切片 + 分层上下文 + 句对齐 + 术语三态 | 对齐 translation/ + align/ |
| S7 | `references/review.md` | **六道关 QC 操作指引**（G0-G5 何时跑、怎么看报告、怎么修） | 覆盖 quality-control.md |
| S8 | `references/build.md` + `qa.md` | 封装 + epubcheck 零 error + 解包审计 | 对齐 build/qa |
| S9 | `references/style.md` | 文体档案选择 + 各文体特殊优化 | 对齐 genres/ |
| S10 | 安装脚本 | `scripts/install-skills.sh --target opencode` | 可安装 |

> skills 是**纯文档**，不写业务逻辑；它把 docs/ 里的设计翻译成"agent 照抄就能干"的步骤。

---

## 五、模块二开发任务：`src/auto_epublizer/`

按依赖顺序（下层先做）：

| # | 领域服务 | 任务 | 借鉴来源 | 验收 |
|---|---|---|---|---|
| C1 | `workspace/` | publication.json schema（DC 元数据 + 内容树 + 状态机 + 配置快照）；RunStore：tmp+`os.replace` 原子写、`source_sha256` 绑定、多级 flock、导出快照、`events.jsonl`/`usage.json` 账本 | wenyi runstore | schema 单测覆盖 |
| C2 | `llm/` | `complete`/`complete_json` + tiers（strong/cheap/fast）+ 统一重试 + 用量账本 + 宽松 JSON 解析 + FakeClient | wenyi llm | 离线可测 |
| C3 | `ingest/` | pandoc 归一化（非 PDF）+ PDF 按页切片（pymupdf）+ OCR（RapidOCR）+ 页转图视觉 LLM 兜底 | epub-builder + pdf-parsing.md | 样例文件抽对结构 |
| C4 | `structure/` | 四层结构归类、标题层级、页眉页脚/页码剔除、分栏阅读顺序、脚注配对、表格保形、插入元素提取、source_page 溯源 | 出版物规范 + epub-builder | 复杂 PDF 样例 |
| C5 | `analysis/` | 分层理解生成（overview/global/units/keypoints）+ 术语播种 + 源语言检测 + 网络检索写 references/web/ | wenyi preparation + synopsis | 生成文件契约正确 |
| C6 | `translation/` | 切片（段→批）+ 分层上下文组装 + 段落翻译返回句对 + 句级 align/ 对照表 + 术语注入/提案 | wenyi translator + segmenter | 句对齐 1:1 |
| C7 | `glossary/` | 三态：CSV 权威 + `glossary_conflicts.jsonl` + worker 只读/单线程合并 + 可选 SQLite 索引 | wenyi glossary | 冲突追踪正确 |
| C8 | `review/` | 六道关：G0 纯函数（标记守恒/段落1:1/长度比/残留/标点/术语命中/URL安全）+ G1 逐批审校 + G2 取证 + G3 仲裁/影子修订/盲复审收敛 | wenyi review + quality-control.md | 收敛状态机正确 |
| C9 | `build/` | EPUB 3 直写：opf/nav.xhtml/NCX/封面/DC 元数据/epub:type/lang/landmarks/脚注双向跳转/原图优先+补充层 | epub-builder | 确定性构建 + epubcheck 零 error |
| C10 | `qa/` | 解包逐项审计 + epubcheck 集成 + release 四必需组件门禁 + 质量报告 | epub-builder + epub-qa | 零 error 放行 |
| C11 | `genre/` | 文体档案声明式加载（novel/academic/paper/poetry/newspaper）+ langprofile | wenyi langprofile + genres/ | 各文体注入正确 |
| C12 | `cli.py` | 子命令 init/analyze/translate/review/convert/build/qa/status + `--json` + exit code + 中文错误提示 | wenyi cli | `--help` + 状态查询可跑 |

**实现顺序**：C1→C2（地基）→ C3/C4（解析）→ C5/C11（理解+文体）→ C6/C7（翻译+术语）→
C8（QC）→ C9/C10（封装+审计）→ C12（CLI 贯穿）。

---

## 六、其他需要的内容

| # | 事项 | 说明 |
|---|---|---|
| O1 | `pyproject.toml` | uv 管理；依赖：typer/pydantic/rich/httpx/pymupdf/rapidocr-onnxruntime/lxml/pyyaml；dev：pytest/ruff |
| O2 | Ruff 规则 | 目标 Python 3.12；行宽、E/W/F/I；中文 prompt 忽略 E501 |
| O3 | `config.example.yaml` | 对齐 docs/configuration.md 的完整 schema |
| O4 | 测试策略 | 全部离线：FakeClient/mock，不调真实 LLM/网络；数据写 tempfile；`test_architecture_boundaries.py` 固定依赖边界 |
| O5 | `THIRD_PARTY_LICENSES.md` | 登记 PyMuPDF(AGPL)/pymupdf4llm/RapidOCR/MinerU(如用)/pandoc 等许可 |
| O6 | 工作区模板 | 已有 `template/`；实现后由 `init` 按它生成，保持同步 |
| O7 | `.gitignore` | 排除 output/、glossary.db、OCR 页图、__pycache__ |
| O8 | 环境中立 | 不写绝对路径/用户路径；密钥只从环境变量读 |
| O9 | 打包发布 | `uv build` 可装；EPUB 成品走 GitHub Releases |

---

## 七、里程碑（更新后）

| # | 里程碑 | 覆盖任务 | 验收 |
|---|---|---|---|
| M1 | 脚手架 + 配置 + LLM 地基 | C1(workspace) + C2(llm) + O1/O2/O3 | `--help` 可跑，FakeClient 可用 |
| M2 | 工作区模型 | C1 完整 + O6/O7 | schema 单测覆盖 |
| M3 | 归一化 + 结构重建 | C3 + C4 | 各格式样例抽对结构 |
| M4 | 理解 + 文体 | C5 + C11 | analysis/ + style 契约正确 |
| M5 | 翻译 + 术语 + 对齐 | C6 + C7 | 句对齐 1:1 + 术语冲突 |
| M6 | 质量控制 | C8 | G0-G3 收敛正确 |
| M7 | EPUB 封装 + QA | C9 + C10 | epubcheck 零 error + 确定性 |
| M8 | CLI 贯穿 + 测试 | C12 + O4/O5 | pytest 全绿 + ruff |
| M9 | skills + 文档 | S1-S10 + O8/O9 | agent 照 skills 跑通端到端 |

---

## 八、参考材料索引（本会话已保存的有效内容）

所有设计文档已在 `docs/` 落盘，实现时以此为准：

| 文档 | 内容 |
|---|---|
| `README.md` | 总纲：决策/管线/目录/模块/QC/里程碑/命令 |
| `AGENTS.md` | agent 入口契约 |
| `docs/configuration.md` | 配置完整 schema |
| `docs/translation-flow.md` | 切片翻译流程（分层理解 + 句对齐 + 术语闭环） |
| `docs/quality-control.md` | 六道关 QC 规格（数据契约/阈值/收敛/配置） |
| `docs/quality-lessons.md` | 历史实践提炼的正向目标 + 负面限制 |
| `docs/publishing-workflow.md` | 传统三审三校映射 |
| `docs/pdf-parsing.md` | PDF 方案（按页切片 + 溯源 + 页转图） |
| `docs/genre-style.md` + `docs/genres/*.md` | 文体优化（小说/学术/论文/诗歌/报刊） |
| `template/` | 工作区目录模板 |
| `LICENSE` | AGPL-3.0 |

**参考外部项目**：`~/github/epub-builder`（稳定 ID / 内容树 / 验证门禁 / 原图优先）、
`~/github/wenyi`（RunStore / LLM 抽象 / 术语库 / Review 体系）、`~/work/translate`（11 本书实战规范）。
