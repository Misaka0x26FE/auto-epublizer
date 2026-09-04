# 预处理阶段开发计划（本轮执行稿）

> 状态：**已完成**。本文档是本轮（预处理）的实施计划与验收依据；完成后按实际落地情况回填「验收结果」。
>
> ⚠️ 已被 **`preprocessing-plan-v2.md`** 取代：v2 重新定义预处理目的为「能力边界确认」，
> 并纳入 OCR 能力路由 / 网络搜索检测 / PDF 内容提取三份新计划。后续开发以 v2 为准。

## 一、背景与架构观

豆包两轮实测确立了一个根本事实：**是 agent 使用我们的程序，而不是 AI 运行在程序里**。
CLI 的价值在于确定性工具（解析/状态机/校验/构建/质检）与落盘契约；理解与决策本来就是
agent 的活。上轮已把翻译做成双路径（A: CLI LLM / B: agent 手写 + import 登记）并让
LLM 降为可选；本轮把同一原则推进到**正式翻译之前的全部工作**——预处理。

预处理 = 在正式翻译工作前，拆解并分析待处理文件：

1. **分类识别与方案决策**：识别输入类型（流式 EPUB / 网页 / DOCX / 有文字层 PDF /
   扫描件 / 混合型等），结合环境能力（doctor）与文档决策表，确定转入标准工作仓库的方案。
2. **分层理解**：提取目录结构、主要内容、中心思想、语言风格等全局内容，以及按章节的
   主要内容与思想——对齐后续翻译的上下文需求。
3. **补充环节**（传统出版「收稿齐清定 → 制订编辑方案 → 术语表先行」的映射）：
   内容体检、元数据提取、媒体资产清单、术语与命名实体预提取、翻译难度与风险标注、
   工作分解与规模估算。

## 二、职责划分（核心设计原则）

| 环节 | 执行者 | 产出 |
|---|---|---|
| 能力自检（工具链/LLM） | CLI（`doctor`，已有） | 快照嵌入 facts |
| 文件类型 + 内容嗅探（DRM / 文字层 / 扫描件 / 乱码率） | CLI 新增（确定性） | `facts.json` |
| 元数据提取（EPUB 读 OPF、DOCX 读 docProps、PDF 读 metadata、HTML 读 `<title>`） | CLI 新增 | `facts.json`（title/lang 可回填 publication meta） |
| TOC 提取（EPUB nav/NCX、PDF bookmark→页→章、其余标题推断） | CLI 新增 | `facts.json` |
| 内容体检（空文字层页比例、乱码率、空壳单元、版权残句） | CLI 新增 | `facts.json` |
| 规模统计（单元数/词数/句数/总字符/token 粗估） | CLI 新增 | `facts.json` |
| 媒体清单（插图数、封面候选） | CLI 新增 | `facts.json` |
| **方案决策**（读 doctor + facts + docs 决策表定 ingest 路由） | **agent** | `plan.md` |
| **全局理解**（主要内容/中心思想/语言风格/叙事结构） | **agent** | `global.md` |
| **章节理解**（每章梗概/思想/登场人物/术语注意） | **agent** | `units/<id>.md` |
| **术语预提取**（人名/地名/机构/source-only 口癖/勘误先例） | **agent** | `terms.csv` |
| **风险标注**（多语/诗歌/双关/文化梗/术语冲突预判） | **agent** | `risks.md` |
| 汇总报告（翻译前输入锚点） | agent（CLI 产框架） | `report.md` |

CLI 全程零 LLM 调用（`usage.json` 不涉及）；agent 产物不经 CLI 校验（与 analysis/ 同级契约，
后续 G0/translate 自然检验）。

## 三、目录契约（新增独立目录）

```text
preprocessing/
├── facts.json     # CLI 确定性事实（preprocess 命令生成，幂等可刷新）
├── facts.md       # 人类可读版 + agent 待办清单 + doctor 能力快照
├── plan.md        # agent 写：处理方案决策（路由选择 + 依据）
├── global.md      # agent 写：主要内容/中心思想/语言风格/叙事结构
├── units/<id>.md  # agent 写：每章梗概/思想/人物/术语注意
├── terms.csv      # agent 写：术语预提取（列格式 = glossary.csv 权威列）
├── risks.md       # agent 写：难度与风险
└── report.md      # agent 写：汇总报告（翻译前输入锚点）
```

## 四、CLI 变更

- 新增 `auto-epublizer preprocess [input]`：
  - 带 input = `init`（含 OCR 自动路由，工作区已存在则报错，与 init 语义一致）+ 事实收集落盘；
  - 无 input（已有工作区）= 只收集/刷新 facts；
  - 输出 facts 摘要 + agent 待办提示。
- 新模块 `src/auto_epublizer/preprocess/`：`sniff.py`（按格式探测）+ `facts.py`（收集与落盘）。
- translate 上下文 fallback：`analysis/` 缺失时读 `preprocessing/`（global/units）。

## 五、既有代码适应性更新清单

### 必须项（A）

| # | 位置 | 改动 |
|---|---|---|
| A1 | `auto_common/workspace/store.py` `ensure_skeleton()` | 目录清单加 `"preprocessing"` |
| A2 | 同上 `RunStore` | 加 `preprocessing_dir` 属性 |
| A3 | `auto_translator/translation/service.py` `_read_analysis()` | fallback：`analysis/` 缺失时读 `preprocessing/global.md`、`preprocessing/units/<id>.md`（analysis/ 优先，两者共存不冲突） |
| A4 | `auto_epublizer/cli.py` | 新增 `preprocess` 命令；translate/analyze help 补上下文来源说明 |
| A5 | `auto_epublizer/orchestrator.py` | 新增 `preprocess()` 编排函数（复用 init 的 OCR 路由；不动 init/convert） |
| A6 | `skills/auto-epublizer/manifest.json` | references 加 `"preprocessing"` |
| A7 | 文档 7 份 | `AGENTS.md`（工作区树 + 标准流程 + 能力分工）、`SKILL.md`（路由表 + 标准流程）、`workflow.md`（阶段表/命令总览/状态路由/排查）、`ingest.md`（决策表先跑 preprocess 拿 facts）、`translation.md`（上下文来源加 preprocessing/）、`analysis.md`（注明 agent 预处理路径产 preprocessing/，analysis/ 为 LLM 路径）、`review.md`（上下文 fallback 说明） |

### 建议项（B，本轮一并做）

| # | 位置 | 改动 |
|---|---|---|
| B1 | `auto_translator/review/service.py` `_load_book_context()` | 同 A3：加 `preprocessing/global.md` fallback |
| B2 | `orchestrator.status` | 顶层加 `has_preprocessing`；stale 增加「facts 有但 plan/global 缺 → preprocessing_plan_missing」 |
| B3 | `tests/test_workspace.py` | skeleton 断言固化 `preprocessing/` |

### 重构项（R，防循环依赖）

| # | 位置 | 改动 |
|---|---|---|
| R1 | `_unit_heading` / `_skip_empty_unit` | 从 `orchestrator.py` 移到 `structure/rebuild.py`（结构语义归位），orchestrator 与 preprocess 统一 import，避免 preprocess → orchestrator 反向依赖 |

### 明确不改

`analyze`/`analysis/`（路径 A LLM 加速器原样保留，优先级高于 preprocessing/）、`import`
（`--terms preprocessing/terms.csv` 已零代码对接）、ingest 各 reader（嗅探直读源文件）、
`build`/`qa`/`doctor`/`glossary`/`config.py`（本轮无新配置项）。

## 六、测试计划

- `tests/test_preprocess.py`：
  - EPUB 嗅探（手写最小 EPUB：OPF 元数据 + nav TOC；DRM 假书加 `META-INF/encryption.xml`）
  - PDF 嗅探（fitz 造带文字层与空页假书；metadata / get_toc / 空文字层页比例）
  - DOCX / HTML 元数据；TXT 规模
  - `collect_facts`：units 统计 / scale / 体检 / 落盘 facts.json+facts.md；幂等刷新
  - orchestrator.preprocess 无 input 模式；工作区缺失报错
- fallback 测试：`_read_analysis` 与 review `_load_book_context` 读 preprocessing/；
  B2 status 对账（facts 有 plan 缺 → stale）。
- 全量回归：现有 168 测试不受影响（ensure_skeleton 纯增量）。

## 七、验收标准

1. `uv run pytest -q` 全绿（168 + 新增）；`ruff check .` / `ruff format --check` 通过。
2. CLI：`preprocess` 命令对 MD/EPUB/PDF/HTML 各跑通，facts.json/facts.md 落盘且幂等。
3. agent 待办闭环：facts.md 明确指引 agent 依次产出 plan/global/units/terms/risks/report。
4. 无 LLM Key 环境全链路：preprocess → agent 填 preprocessing/ → import（--terms）→
   translate（上下文来自 preprocessing/）→ build → qa。
5. 文档与实现一致（A7 清单逐项核对）。

## 八、本轮不做

- web 检索、多栏/脚注/表格保形、图内文字 OCR、媒体尺寸优化（保持 docs 扩展点标注）
- review 上下文优先级反转、analyze 语义合并（保留两目录并存，analysis/ 优先）
- preprocess 的 `--json` 输出细化（facts.json 已是机器可读权威）

## 九、验收结果（执行后回填）

- [x] 测试：182 passed；ruff check / format 通过
- [x] CLI 实测（md 冒烟通过；EPUB/PDF/DOCX/HTML 由 13 个嗅探测试覆盖）
- [x] 文档核对（A7 七份 + manifest 全部同步）
