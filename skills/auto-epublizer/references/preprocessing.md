# Preprocessing（预处理：事实收集 + agent 理解撰写）

预处理是**agent 任务**：CLI 只产出零 token 事实（`preprocessing/facts.json` / `facts.md`），
方案决策与分层理解由你（agent）用自身能力撰写。全部产物落在 `preprocessing/`。

## 1. 跑事实收集

```bash
# 新书（= init + 事实收集：嗅探/元数据/TOC/体检/规模）
auto-epublizer preprocess <input> [--reference <path...>] [--target zh-CN]
# 已有工作区（幂等刷新 facts）
auto-epublizer preprocess
```

`facts.md` 包含：源文件类型与嗅探结果（DRM/文字层/扫描件判定/乱码率）、DC 元数据、
目录 TOC、规模统计（单元/词数/句数/token 粗估）、内容体检、环境能力快照（doctor）、
确定性路由提示，以及 **agent 待办清单**。

## 1.1 能力自报（capabilities.md）

CLI 探测不到的五维能力边界，由你（agent）开工前自报，写 `preprocessing/capabilities.md`：

| 维度 | 自报内容 | 影响 |
|---|---|---|
| agent 自身能力 | multimodal（能否看图）、search（是否有网络搜索工具） | 扫描 PDF 视觉兜底 / 背景知识补齐路由 |
| agent 模型 | 模型 ID、上下文窗口、是否视觉模型 | 单次可处理的书内容量、是否可走多模态 |
| OS 环境 | 本机可达的 CLI 工具（doctor 已探测部分） | ingest/OCR 路由 |
| 外部 API 边界 | 可用外部解析 API（MinerU key）、网络可达 | 解析/检索可用性 |
| 待处理文件工作量 | 规模粗估（facts 有 token 粗估）、难点预估 | 切分与分阶段计划 |

`multimodal` / `search` 也可从 `facts.md` 的「环境能力快照」里确认（CLI 探测不到的显示
「待 agent 自报」）。

## 1.2 背景知识补齐（Plan B 路由）

翻译前若缺少背景知识（专名、史实、文化背景、可疑 OCR 文本），按此路由：

1. **有网络搜索工具**（自报 search=true）：自行检索，结果与来源记入 `references/web/`
   （URL、标题、时间），追加到 `references/index.jsonl`；
2. **无搜索工具**：明确询问用户，将用户提供的材料放 `references/user/`；
3. 两者都没有时不强行补；把缺口写进 `risks.md` 留待翻译/审校时处理。

## 2. 按待办依次撰写（全部写在 `preprocessing/`）

### 1.2 元数据核对（facts 待办首项；`meta` 命令写回）

facts 嗅探的元数据（title/creator/publisher/date/rights）只是**推断**——源文件自带
metadata 常错、常缺、常乱码。开工第一步：对照源文版权页/题录逐项核实（存疑处
询问用户），确认/补全后写回：

```bash
auto-epublizer meta --publisher "..." --date "..." --rights "..."
```

**译者署名默认规则**：用户无特殊说明时，译者 = 你的 agent 框架名称
（opencode 处理写 `OpenCode`，豆包处理写 `DouBao`，以此类推）；用户指定名优先。

```bash
auto-epublizer meta --translator OpenCode
```

署名随 build 进入 EPUB 元数据（`dc:creator` + `role=trl`）；QA 期的
`W_META_INCOMPLETE` 应在预处理期已被本步骤消化。

### 2.0 `todo.md`（任务细化清单——开工第一件，贯穿全程）

**要求**：读 facts 后、动手翻译前，把「处理这本书要做的每一个动作」细化成可勾选
任务清单。粒度要小到**不用思考就能照做**：每一单元一项（阅读 structured → 写
translation + align → import → g0）、每 3–5 单元一项 build 校验、审校/质检/交付
各阶段逐项列出。翻译全程**每完成一项就勾掉一项**，并随进展追加/修正。

模板（可在此基础按书增删，如按「部/章/行间」分组、附预计 token 或词数）：

```markdown
# todo.md（逐细节任务清单）

> 开工第一件产物。完成一项勾一项（- [x]）；新任务追加到对应阶段。
> 与 status --json / publication.json 状态机配合，杜绝「以为做了其实没做」。

## 0. 预处理理解（facts 之后）
- [ ] capabilities.md：自报五维能力边界
- [ ] plan.md：方案决策（路由 + 依据 + 工作量）
- [ ] global.md：全局理解
- [ ] units/<id>.md：逐章理解
- [ ] terms.csv：术语预提取 + import --terms
- [ ] risks.md + report.md

## 1. 单元翻译（每单元：读 structured → 写 translation + align → import --unit → g0 --unit）
- [ ] ch01 <标题>（约 N 段）
- [ ] ch02 <标题>
- [ ] …（按 48 单元 / 25 章逐一列出）

## 2. 过程校验（每译 3–5 单元一次）
- [ ] build 一次，验证格式契约（图片段 / 空行 / 转义 / 目录层级）
- [ ] 解包抽查：插图、目录、标题

## 3. 审校（G1–G3）
- [ ] 逐批审校，写 reviews/review-<ts>/{issues,patches,summary,result.json}
- [ ] 术语冲突外置 glossary_conflicts.jsonl 逐条裁决写回 glossary.csv
- [ ] 双语版 build（--bilingual）抽查，重点核省略号收尾段落

## 4. 封装与质检（G4–G5）
- [ ] build 全量 EPUB
- [ ] qa：epubcheck 0 error + 审计 pass + G0 术语命中清零
- [ ] 核对 status --json 无 stale、目录层级与源文一致
- [ ] 交付：产物落 output/ + 记录 events
```

### 2.1 `plan.md`（方案决策）

输入：facts.md（源类型/体检/能力快照/路由提示）+ `references/ingest.md` 决策表。
写明：选择的 ingest 路由（pandoc / 按页切片 / 扫描件路由：**MinerU API 最优先——
无 key 时先询问用户是否有**；无 key 才退传统 OCR/rapidocr + 逐页阅读兜底）及
**依据**；扫描件时明确 OCR 或逐页阅读的执行方式（含工作量估算：页数 × 逐页阅读
成本）；DRM/损坏等阻断问题在此升级给用户。

### 2.2 `global.md`（全局理解）

主要内容、中心思想、语言风格（语域/语气/句式偏好）、叙事结构（人称/时态/跨章依赖）、
文体判定（novel/academic/paper/poetry/newspaper，参照 `references/style.md`）。
这是翻译上下文的来源之一（agent 翻译时在 `analysis/` 缺失的情况下回退读本文件）。

### 2.3 `units/<id>.md`（章节理解）

每个单元一份：本章梗概/思想推进/登场人物/术语注意/与其他章的衔接。
同样作为 agent 翻译的章级上下文（fallback 顺序同上）。

### 2.4 `terms.csv`（术语预提取）

列格式与 `glossary.csv` 权威列一致：
`source,target,type,aliases,gender,reading,status,note`
覆盖：人名/地名/机构/专名、source-only 口癖/称谓/固定表达、缩写与已知勘误先例。
翻译前导入术语库：`auto-epublizer import --terms preprocessing/terms.csv`。

### 2.5 `risks.md`（风险标注）

多语片段/诗歌/双关/文化梗、长难句与术语密集段、预期术语冲突、
扫描件 OCR 难页清单。供翻译与审校重点关注。

### 2.6 `report.md`（汇总）

以上各件的提炼合并，是「翻译前输入锚点」：一张表回答
「用什么方案、全书讲什么、风格怎么定、术语怎么统一、风险在哪、规模多大」。

### 2.7 `catalog.csv`（可选：源内容盘点）

目录完整性契约：逐项声明源内容去向——`included`（已收录，unit_id 必填）、
`physical`（护封/腰封/书脊等实体元素，有意不进 EPUB）、`excluded`（有意排除，
note 必填理由）、`unresolved`（未决，**qa 阻断放行**）。与 provenance 互补：
catalog 管「源侧有没有漏收」，provenance 管「译侧有没有漏译」。
facts 待办有该项时建议写；不写则全部检查跳过。

## 3. 完成判据

- `auto-epublizer status --json` 的 `preprocessing_complete == true`
  （facts + todo.md + global.md + capabilities.md 四者齐备）
  且不再有 `preprocessing_plan_missing` stale 提示。
- **todo.md 必须生成**：逐细节任务清单已列出全部单元翻译项与阶段校验项
  （这是后续翻译/审校/交付的全程工作锚点）。
- capabilities/plan/global/units/terms/risks/report 七类产物齐备
  （小书可合并风险与报告，但 capabilities/plan/global/terms 必备）。

## 4. 与 analysis 的关系

- 理解层由你撰写：可写 `preprocessing/`（plan/global/units/terms/risks/report），
  也可写 `analysis/`（overview/global/units/keypoints/style/glossary，见
  `references/analysis.md`）——两者都作为翻译/审校的上下文读取源，`analysis/` 优先。
- `preprocess` 只产零 token 事实与待办清单；不做任何语义生成。

## 注意事项

- `preprocessing/facts.*` 由 CLI 幂等生成，**不要手工编辑**；其余文件是你写的智能产物。
- facts 里的「路由提示」是确定性结论，不是决策；最终方案以 plan.md 为准。
- 规模 token 为粗估（chars/2），仅用于规划，非计费依据。
