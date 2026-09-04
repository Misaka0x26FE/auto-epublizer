---
name: auto-epublizer
description: Orchestrates the auto-epublizer translation and EPUB workflow. Use for publication.json workspaces, init/analyze/translate/review/build/qa/status/convert stage routing, glossary.csv three-state terminology, translation/align/ sentence tables, structured/ four-layer content, or EPUB output.
compatibility: opencode
metadata:
  suite: auto-epublizer
  workspace_model: publication.json
---

# auto-epublizer

`auto-epublizer` 是一个 Python CLI，提供两项能力、一条共用管线：**翻译**（外语文献 → 任意目标语言）与
**转 EPUB**（复杂文件 → 标准 EPUB 3）。工作区以 `publication.json` 为权威索引。

**分工**：CLI 内部调用 LLM 完成**确定性触发的生成与初筛**（分析生成、术语播种、翻译、
审校报 issue、取证裁决、仲裁与影子修订）；**LLM 是可选加速器**——无 API Key 的环境里
`analyze` 确定性降级，翻译由 agent 用自身能力手写 `translation/`+`align/` 后经
`auto-epublizer import` 登记。**内容理解、语义判断、质量把关、术语终局裁决、未收敛处置、
修复与放行决策**由使用本 Skill 的 agent 用自身能力（读文件、判断、写文件）完成。
agent 只需基础能力，无需 MCP/子代理。

## Route Before Acting

先跑 `auto-epublizer doctor --json` 做能力自检（工具链/依赖/LLM Key/MinerU/网络），并**自报
multimodal / search**（能否看图、有无搜索工具，CLI 无法探测）——据此选择 ingest 路由
（见 `references/ingest.md` 的能力-路由决策表）。然后读本 Skill 目录的 `manifest.json`，
按当前阶段只读需要的 reference。

| 场景 | 读 |
|---|---|
| 全新任务 / 状态路由 / 多阶段请求 / 命令总览 | `references/workflow.md` |
| 预处理：读 facts → 撰写 plan/global/units/terms/risks/report | `references/preprocessing.md` |
| 文件解析：PDF / 扫描 PDF / EPUB / DOCX / HTML / TXT / MD / OCR | `references/ingest.md` |
| 四层结构归类、清洗、页眉页脚/页码剔除、溯源 | `references/structure.md` |
| 分层理解、术语播种、语言/体裁检测 | `references/analysis.md` |
| 切片翻译、句级对齐、术语三态闭环、agent 手写翻译路径 | `references/translation.md` |
| 六道关 QC（G0–G5）操作指引 | `references/review.md` |
| EPUB 封装、确定性构建 | `references/build.md` |
| epubcheck + 解包审计、质量报告 | `references/qa.md` |
| 文体档案（novel/academic/paper/poetry/newspaper）应用 | `references/style.md` |

## Boundary（不可违背）

1. `source/`、`references/user/` 只读，绝不改动；源文件内容以 `publication.json.meta.source_sha256` 绑定。
2. `publication.json` 是唯一真相，**禁止手工编辑**；所有状态变更走 CLI 命令。
3. `structured/`（含 `raw/` 中间产物）持久化供审查，可由源文件重建；`analysis/`、`translation/`、
   `reviews/`、`output/` 是智能产物。
4. 审校只改影子译文（`reviews/review-<ts>/shadow_overlay.json`）；正式 `translation/` 只有显式 Autofix 可改。
5. API Key 只从环境变量读取，绝不写入源码、配置、文档示例或提交。
6. 只处理公有领域或已获授权文本；不提交受版权保护的正文与用户本地数据。

## Command Discipline

- 机器决策用 `status --json` 或 `--json` 输出，不要解析彩色终端文本。
- 命令失败看错误码与中文提示，修复工作区/输入后重试；已完成单元可安全跳过。
- 同一工作区一次只跑一条长流程命令，避免并发写 `publication.json`。
- 改术语表/理解/解析后，须重跑受影响单元的后续阶段（状态机 `split → analyzed → translated →
  aligned → reviewed → built`）。

## 标准流程

```bash
auto-epublizer doctor --json                              # 能力自检（开工前；multimodal/search 自报）
auto-epublizer preprocess <input>                         # 预处理：init + 零 token 事实 → preprocessing/facts.*
#   agent 读 facts.md，撰写 capabilities/plan/global/units/terms/risks/report（见 references/preprocessing.md）
auto-epublizer analyze                                    # 分层理解 + 术语播种（无 Key 时降级，可省略）
auto-epublizer translate [--target zh-CN] [--force]       # 路径 A：CLI 内部翻译
#   路径 B：agent 读 structured/ 手写 translation/ + align/，然后：
auto-epublizer import [--unit <id>] [--terms preprocessing/terms.csv]  # 登记手写产物
auto-epublizer g0                                         # 静态校验（advisory）
auto-epublizer review                                     # 审校（G1–G3，无 LLM 时 agent 自行审校）
auto-epublizer build [--bilingual] [--theme standard|compact|spacious]  # 封装 EPUB → output/
auto-epublizer qa                                         # epubcheck + 解包审计
auto-epublizer status --json                              # 查看进度/状态机/产物-状态对账
```

仅转换不翻译：`auto-epublizer convert <input> -o output/book.epub`。
