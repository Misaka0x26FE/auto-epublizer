# 预处理阶段更新计划（v2）

> 状态：**已完成**（2026-09-04，S0–S5 落地：`57240ca`/`42eef38`/`a1b7306`/`d84fbcd`/
> `d14e6f4`/`e81fed2`；Plan C 规范见 `docs/pdf-content-spec.md`）。本文档是预处理阶段的
> v2 更新计划，取代同目录 `preprocessing-plan.md`
> （v1，已完成 2026-09，聚焦「分类识别 + 分层理解 + 补充环节」）。v2 在 v1 基础上：
>
> 1. **重新定义预处理的目的**——从「拆解分析文件」升级为「正式处理前的**能力边界确认**」；
> 2. 纳入两轮新计划：**A 扫描件 OCR 能力路由**、**B 网络搜索检测**、**C PDF 内容提取**
>    （插图 / 多栏 / 表格 / 公式 / 书签）。
>
> 本文档是后续开发的权威依据；实施时须同步更新 `skills/` 与 `AGENTS.md`（见 §八）。

---

## 一、预处理目的：能力边界确认

v1 把预处理定义为「翻译前的文件拆解与分析」。v2 明确其更根本的目的——**在正式处理前，
把「谁来做、用什么模型、在什么环境、能调什么外部 API、要干多少活」这五件事查清楚**，
据此确定处理方案，避免开工后才发现能力缺口。

### 1.1 能力边界五维模型

| 维度 | 探测者 | 现状 | v2 新增 |
|---|---|---|---|
| ① **Agent 身份与能力** | agent 自报（CLI 无法探测） | `doctor` 留 `multimodal=null`，agent 隐性自报 | 显式 `search` 留空 + 新增 `capabilities.md` 自报清单（看图 / 搜索 / 跑 shell / 写文件） |
| ② **Agent 使用的模型** | CLI 探测 `config.llm` + agent 自报 | `llm_key` / `llm_vision_model` / `llm_endpoint` | agent 自报实际模型 ID / 上下文窗口 / 是否多模态 |
| ③ **操作系统环境** | CLI `doctor`（本地确定性探测） | pandoc / pdftotext / tesseract / rapidocr / lxml / epubcheck / java | `ocrmypdf`、OS 平台信息、磁盘空间、内存 |
| ④ **可调用的外部 API 能力边界** | CLI 探测 key env + agent 自报 | `llm_endpoint`（`--ping`） | `mineru_api_key`（`MINERU_API_KEY`）、网络可达性（`--ping`） |
| ⑤ **处理待处理文件需要的工作** | CLI `facts` + agent 撰写 | sniff / 体检 / 规模 / 路由提示 | 插图 / 表格 / 公式 / 书签的提取工作 + 工作量估算 |

### 1.2 原则（沿用 AGENTS.md 分工）

- CLI 只做**确定性探测与事实收集**（零 token、零决策）；`usage.json` 不涉及预处理。
- **语义判断与方案决策归 agent**：读 facts + 能力边界，写 plan / capabilities / 理解产物。
- `multimodal`、`search`、agent 模型等** agent 自身属性**，CLI 探测不到，一律留空由 agent 自报，
  落盘到 `preprocessing/capabilities.md`（新），与 v1 的 `multimodal=null` 逻辑一致。

---

## 二、目录契约变更

在 v1 的 `preprocessing/` 基础上新增一份 agent 自报文件：

```text
preprocessing/
├── facts.json        # CLI 确定性事实（幂等，含能力边界快照）
├── facts.md          # 人类可读版 + agent 待办 + doctor 能力快照
├── todo.md           # 【新增】agent 写：逐细节任务清单（开工第一件，全程勾选）
├── capabilities.md   # 【新增】agent 自报：自身能力/模型/可调外部 API（五维 ①②④）
├── plan.md           # agent 写：处理方案决策（路由 + 依据）
├── global.md         # 全局理解
├── units/<id>.md     # 章节理解
├── terms.csv         # 术语预提取
├── risks.md          # 风险标注
└── report.md         # 汇总报告
```

`todo.md` 建议结构（agent 写，非 CLI 校验；模板见 `references/preprocessing.md` §2.0）：
把全书处理细化到「不用思考就能照做」的颗粒度——每单元一项（读 structured → 写
translation + align → import → g0）、每 3–5 单元一次 build 校验、审校/质检/交付
各阶段逐项；全程勾选并随进展追加。

`capabilities.md` 建议结构（agent 写，非 CLI 校验）：

```text
# 能力边界自报
## ① 本 agent
- 看图（multimodal）：是/否 + 说明
- 网络搜索工具：有/无 + 说明
- 跑 shell / 写文件：是
## ② 模型
- 模型 ID / 上下文窗口 / 是否多模态
## ④ 可调用的外部 API
- LLM 端点（doctor 探测）+ 自报是否持有调用工具
- MinerU / 其他解析 API：key 有无 + 是否可调
```

---

## 三、计划 A：扫描件 OCR 能力路由

> 目标：扫描件 PDF 的 OCR 手段由 agent 按能力边界自行判断，优先级固定：
> **传统 OCR → rapidocr → 多模态/识图 → MinerU 外部 API → 询问用户**。

### 3.1 CLI 变更（确定性探测）

- `src/auto_epublizer/doctor.py` `collect_capabilities` 新增：
  - `ocrmypdf`（`_probe_tool`）—— 传统 OCR 工具
  - `mineru`（探测 `MINERU_API_KEY` 环境变量）—— 外部解析 API key
  - `network`（可达性探测，仅 `--ping` 时执行，复用 `_ping_endpoint` 的超时/异常模式）
- `capabilities_summary` 增加 `"search": None`（与 `multimodal` 并列，agent 自报）。

### 3.2 facts 路由提示重排

`src/auto_epublizer/preprocess/facts.py::_route_suggestions` 对 `kind=="pdf"` 且 `scanned` 时，
按优先级输出提示：

1. `tesseract` 或 `ocrmypdf` 可用 → 首选传统 OCR
2. 否则 `rapidocr` → 离线 OCR
3. 否则 `llm_vision_model` 或 `multimodal` 自报 → 多模态 / 识图兜底
4. 否则 `mineru` key → 外部 API
5. 否则 → 明确请用户提供可用的 OCR / 解析手段

### 3.3 文档同步

- `skills/auto-epublizer/references/ingest.md`：重写「能力自检与路由」表为五档。
- `skills/auto-epublizer/references/preprocessing.md`：`plan.md` 增加「扫描件 OCR 方案决策」。

### 3.4 后续（本轮不做，Q1 定的最终形态）

- `ingest/ocr.py` 新增 `TesseractOcrBackend` / `OcrmypdfBackend` / `MineruBackend`（CLI 一等后端）
  + `config` 段 + 回归测试。
- `raw/page-NNN.json` 的 `ocr:true` 细化为 `method: text|rapidocr|tesseract|vision|mineru`。

---

## 四、计划 B：网络搜索检测

> 目标：翻译 / 整理过程中需要的背景知识（历史专著历史背景、日轻人物形象、专名译法、
> 文化梗等），由 agent 判断能否检索补齐；不能则询问用户提供参考信息。

### 4.1 CLI 变更

- `doctor.py` 增加 `network` 可达性探测（`--ping`，同计划 A）。
- `capabilities_summary` 增加 `"search": None`（agent 自报是否有搜索工具）。

### 4.2 agent 路由（写入 skills）

- `skills/auto-epublizer/references/preprocessing.md` 新增「背景知识补齐」小节：

| 条件 | 动作 |
|---|---|
| 有搜索工具 + `network` 可达 | 检索补背景知识 → 写 `references/web/*.md` + `index.jsonl`（带 URL + 检索时间，契约已有） |
| 无搜索工具 或 网络不可达 | 询问用户提供参考信息 → `references/user/` |

- 触发点落到 `global.md` / `units/` / `terms.csv` / `risks.md` 的撰写指引。

---

## 五、计划 C：PDF 内容提取规范

> 目标：补齐 PDF 内容提取的六大缺口（书签 / 内嵌图 / 多栏 / 表格 / 公式 / 溯源）。
> 决策已定：**插图按版面判据为主 + 文体加权；公式仅 agent 手写 LaTeX（不做 LLM agent）；
> 先写 spec 再实现**。战略背景见 `docs/pdf-parsing.md`。

### 5.1 分项验收 + 现状差距

| 能力 | 现状 | 目标 |
|---|---|---|
| 书签切章 | `sniff_pdf` 已 `get_toc` 但未接入 | `aggregate_pdf_chapters` 优先 bookmark TOC 边界，字号启发式降级 fallback |
| 内嵌图提取 | 只抽文字层，图片 block 跳过 | `get_images` / `extract_image` → `raw/media/` + md 写 `![](...)` |
| 多栏阅读顺序 | `get_text("dict")` 内部块序 | 列聚类（x）→ 列内 y → 列间 x，单栏流式 |
| 表格 | 无 | `find_tables`：纯文字 → md 表格；含图/公式 → 截区域成图 |
| 公式 | 无 | 检测（特殊字体/符号/独立行）→ 标 `kind=formula` + 描述文件，**latex 由 agent 手写** |
| 插入内容溯源 | 仅媒体 basename 对账 | 描述文件 + 原始地址 `{page,bbox,xref,method}` |

### 5.2 插图路由规则（版面判据 + 文体加权）

- **版面判据（确定性主判据）**：页面文字覆盖率低且图 block 占页面积大 → 整页渲染（`get_pixmap`）；
  图是小区域嵌入文字流 → 区域裁剪（bbox crop）。
- **文体加权（agent 提示）**：`detect_genre` 提示小说 vs 工具书/教材；agent 在 `plan.md` 可覆盖阈值。

### 5.3 数据契约：插入内容描述文件

每个图 / 表 / 公式识别后生成描述文件，保证可溯源到原始内容地址：

```text
structured/raw/inserts/
├── <id>.json     # 单个插入内容（CLI 骨架 + agent 补语义）
└── index.jsonl   # 汇总索引（复用 references/index.jsonl 模式）
```

```jsonc
// <id>.json（如 ch01-p012-fig01.json）
{
  "id": "ch01-p012-fig01",
  "type": "image | table | formula",
  "source": { "page": 12, "bbox": [x0, y0, x1, y1], "xref": 34,
              "method": "embedded | full_page | crop | table | formula" },
  "file": "media/ch01-p012-fig01.png",
  "content_desc": "",   // agent 补：这个插入内容讲什么
  "latex": null         // formula 时 agent 手写 LaTeX
}
```

- `source`（page / bbox / xref / method）即「原始内容地址」。
- CLI 生成确定性字段（type / source / file / method）；agent 补语义字段（content_desc / latex）。

### 5.4 分阶段实现

- **P0**：书签切章 + 内嵌图提取 + 描述文件基座（`ingest/inserts.py`）+ 多栏排序
  （`ingest/reading_order.py`）
- **P1**：插图路由（整页 vs 截取）+ 表格双路径（`ingest/tables.py`）+ 公式检测与标记
- **P2**：provenance 扩展（插入内容 ↔ 原始地址对账）+ 图片优化（借鉴 pdf2epub：
  最长边 1800px / RGBA→RGB / JPEG q85）

---

## 六、分阶段实施计划（A / B / C 合并）

| 阶段 | 内容 | 归属 |
|---|---|---|
| S0 | 写 `docs/pdf-content-spec.md`（计划 C 的验收标准 + 数据契约 + 实现计划） | C |
| S1 | doctor 扩探测（ocrmypdf / mineru / network）+ `search` 留空 + facts 路由重排 + skills 路由表（A/B） | A、B |
| S2 | C-P0：书签切章 + 内嵌图 + 描述文件 + 多栏排序 | C |
| S3 | C-P1：插图路由 + 表格 + 公式标记 | C |
| S4 | C-P2：溯源接入 + 图片优化 | C |
| S5 | OCR 一等后端（Tesseract / Ocrmypdf / Mineru）+ `method` 细化 | A 后续 |

> S1（计划 A/B）改动小（主要是 doctor 探测 + 文档），可独立先行或与 S2 并行。

---

## 七、测试计划

- `tests/test_doctor.py`：新增探测项断言（`ocrmypdf` / `mineru` / `network`）+ `search is None`。
- `tests/test_preprocess.py`：`_route_suggestions` 五档优先级；`capabilities.md` 待办出现在 facts 指引。
- 计划 C 各阶段：构造多页 PDF fixture（fitp，临时文件离线惯例）——
  书签切章 / 内嵌图提取 / 多栏排序 / 表格双路径 / 公式标记 / 描述文件溯源 各一最小回归。
- 全量 `uv run pytest -q`（基线 207）+ `ruff check .` + `ruff format --check .`。

---

## 八、验收标准

1. `uv run pytest -q` 全绿 + ruff 通过。
2. facts 明确呈现「能力边界五维」：doctor 快照（①②④ 的 CLI 可探测部分）+ 待办指引 agent
   自报 `capabilities.md`。
3. 扫描件 OCR 路由按五档优先级在 facts 提示 + skills 决策表一致落地。
4. 网络搜索检测：有搜索工具走 `references/web/`，无则询问用户 `references/user/`（skills 落地）。
5. 计划 C 按 P0→P2 实现，每个插入内容可溯源到 `{page,bbox,xref,method}`（S2–S4 验收）。
6. 文档与实现一致：`AGENTS.md`、`SKILL.md`、`ingest.md`、`preprocessing.md`、`workflow.md`
   逐项核对更新。

---

## 九、本轮不做

- marker-pdf / MinerU 本地引擎作为默认后端（重、离线不友好；仅作可选外部 API，见计划 A §3.4）
- 公式的 LLM 自动转 LaTeX（`FormulaAgent`）—— 已定「仅 agent 手写」
- 脚注/尾注专项提取（`docs/pdf-parsing.md` §2.2 的六阶段流水线，仍为后续扩展点）
- 竖排/繁体 PDF 阅读顺序
