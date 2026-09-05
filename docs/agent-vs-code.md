# Agent 与 Python 代码的分工边界

本文回答一个架构根本问题：**哪些工作归 Python 代码，哪些工作归 agent。**
它是 `AGENTS.md` 中「能力分工」条目的展开，是维护与使用本项目的共同判据。

## 一条主判据

> **「同样输入必须得到同样输出」→ Python；「需要理解内容、做权衡、下判断」→ agent。**

三条辅助判据：

1. **状态一致性归 Python**——原子写、锁、状态机、幂等；agent 手工维护状态必然出错。
2. **外部世界归 Python**——跑 pandoc / epubcheck / OCR，是确定性工具调用，不该让 agent 手搓；
   而**任何「理解」都归 agent**（唯一 LLM 原则：本项目中唯一的 LLM 就是操作 CLI 的 agent）。
3. **验收判读归 agent**——机器只能给信号，判断（怎么修、放不放行）是 agent 的事。

一句话：**Python 负责「不错」，agent 负责「对」。**
确定性、一致性、可复现交给代码；理解、权衡、终审交给 agent。
CLI 是 agent 的手，不是 agent 的脑。

## 归 Python（工具：不会骗你）

| 类别 | 具体 |
|---|---|
| 确定性转换 | ingest（pandoc / PDF 按页切片 / OCR / 插图 / 表格 / 公式检测）、structure（四层归类 / 清洗 / 稳定 ID）、align（句对齐）、build（EPUB 封装）、preprocess facts（嗅探 / 元数据 / TOC / 体检 / 规模）、PDF 内容提取（书签切章 / 多栏阅读顺序 / inserts 描述文件） |
| 状态与一致性 | publication.json 原子写 / 多级锁 / source_sha256 绑定 / 状态机推进 |
| 外部工具调用 | pandoc / epubcheck / OCR / MinerU API（外部解析） |
| 确定性校验 | G0 静态检查、G4 解包审计、epubcheck、inserts 溯源审计——**只出信号，不出裁决** |

## 归 agent（判断者：懂内容）

| 类别 | 具体 |
|---|---|
| 方案决策 | `preprocessing/plan.md`（ingest 路由选择 + 依据）——CLI 给事实与提示，决策永远是 agent 的 |
| 语义理解 | `preprocessing/` 与 `analysis/` 的 global / units / terms / risks / overview / keypoints；「中心思想 / 风格 / 风险」的提炼 |
| 翻译 | `translation/` + `align/`（CLI 只负责 import 时的结构校验） |
| 审校 | G1–G3 语义审校（读 align 找漏译/误译/术语违例）、修订、收敛判定 → `reviews/review-<ts>/result.json` |
| 判读与处置 | g0 告警怎么修、`report.json` 怎么判、未收敛（max_rounds / 振荡 / unresolved_fixes）怎么办、放不放行 |
| 术语终局裁决 | `glossary_conflicts.jsonl` → 裁决写回 `glossary.csv` |
| 插入内容语义 | `raw/inserts/<id>.json` 的 `content_desc`（内容描述）与 `latex`（公式手写 LaTeX） |
| 源文勘误 | 按先例修正（如 IDG→IDF 类） |
| agent 元能力自报 | multimodal（能否看图）、search（有无搜索工具）——CLI 原理上探测不到，只能 agent 自己说 |

## 两个灰色区

**① `analysis/` 的理解产物算谁的？**
归 agent。`analysis/*.md` 与术语表由 agent 用自身能力撰写（读 `preprocessing/` 事实与
`references/style.md` 文体档案）；CLI 只提供确定性助手（语言/体裁启发式、`render_style_md`）。

**② G1 审校的 issue 算谁的？**
归 agent。issue 内容是 agent 的语义判断，但「宁缺毋滥」约束、G0 静态信号、取证流程
（G2 先证据后裁决）的规则与契约是代码的。机器给信号，规则管流程，agent 做终审。

## 一条架构推论

从这个边界自然推出本项目的解耦方式：**agent 的产物总是「文件」，Python 的工作是
「验证文件 + 推进状态 + 消费文件」**。两边只通过文件契约（schema）耦合。这解释了：

- agent 只需「读文件、跑 shell、写文件」三种能力，不需要 MCP / 子代理 / 特殊工具；
- CLI 无任何 LLM 调用，一切语义工作由 agent 手写产物完成，经 `import` / 审校产物登记；
- agent 不手工编辑 `publication.json`——状态推进只走 CLI 命令（`import` / `build` / `qa`…）。
