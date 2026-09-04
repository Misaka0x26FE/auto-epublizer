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
| 外部 API 边界 | 可用 LLM provider、MinerU key、网络可达 | 翻译/解析/检索可用性 |
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

### 2.1 `plan.md`（方案决策）

输入：facts.md（源类型/体检/能力快照/路由提示）+ `references/ingest.md` 决策表。
写明：选择的 ingest 路由（pandoc / 按页切片 / OCR 五档：传统 OCR→rapidocr→视觉 LLM→
MinerU API→询问用户）及**依据**；扫描件时明确 OCR 或视觉兜底的执行方式；
DRM/损坏等阻断问题在此升级给用户。

### 2.2 `global.md`（全局理解）

主要内容、中心思想、语言风格（语域/语气/句式偏好）、叙事结构（人称/时态/跨章依赖）、
文体判定（novel/academic/paper/poetry/newspaper，参照 `references/style.md`）。
这是翻译上下文注入的来源之一（`translate` 在 `analysis/` 缺失时读本文件）。

### 2.3 `units/<id>.md`（章节理解）

每个单元一份：本章梗概/思想推进/登场人物/术语注意/与其他章的衔接。
同样作为 translate 的章级上下文（fallback 顺序同上）。

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

## 3. 完成判据

- `auto-epublizer status --json` 的 `preprocessing_complete == true`（facts + global.md 齐）
  且不再有 `preprocessing_plan_missing` stale 提示。
- capabilities/plan/global/units/terms/risks/report 七类产物齐备
  （小书可合并风险与报告，但 capabilities/plan/global/terms 必备）。

## 4. 与 analyze 的关系

- 无 LLM Key 环境：跳过 `analyze`，你的 preprocessing/ 产物即理解层（translate/review
  的上下文 fallback 自动读取）。
- 有 LLM Key 环境：`analyze` 生成 `analysis/`（优先级更高）；也可仅用 preprocessing/
  走纯 agent 路径——两者共存时 `analysis/` 胜出。

## 注意事项

- `preprocessing/facts.*` 由 CLI 幂等生成，**不要手工编辑**；其余文件是你写的智能产物。
- facts 里的「路由提示」是确定性结论，不是决策；最终方案以 plan.md 为准。
- 规模 token 为粗估（chars/2），仅用于规划，非计费依据。
