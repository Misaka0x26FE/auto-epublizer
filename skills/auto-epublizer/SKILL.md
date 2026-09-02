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

**分工**：CLI 内部调用 LLM 完成**确定性触发的生成与初筛**——分析生成（`analysis/`）、术语播种、
翻译（`translation/`）、审校报 issue（G1）、取证裁决（G2）、仲裁与影子修订（G3）。而**内容理解、
语义判断、质量把关、术语终局裁决、未收敛处置、修复与放行决策**由使用本 Skill 的 agent 用自身能力
（读文件、判断、写文件）完成。agent 只需基础能力，无需 MCP/子代理。

## Route Before Acting

先读本 Skill 目录的 `manifest.json`，再按当前阶段只读需要的 reference（路径相对本 Skill 目录）。

| 场景 | 读 |
|---|---|
| 全新任务 / 状态路由 / 多阶段请求 / 命令总览 | `references/workflow.md` |
| 文件解析：PDF / 扫描 PDF / EPUB / DOCX / HTML / TXT / MD / OCR | `references/ingest.md` |
| 四层结构归类、清洗、页眉页脚/页码剔除、溯源 | `references/structure.md` |
| 分层理解、术语播种、语言/体裁检测 | `references/analysis.md` |
| 切片翻译、句级对齐、术语三态闭环 | `references/translation.md` |
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
auto-epublizer init <input> [--reference <path...>]     # 建工作区 + 解析
auto-epublizer analyze                                    # 分层理解 + 术语播种
auto-epublizer translate [--target zh-CN] [--bilingual]   # 翻译 + 句对齐
auto-epublizer review                                     # 审校（G0–G3）
auto-epublizer build [--bilingual]                        # 封装 EPUB → output/
auto-epublizer qa                                         # epubcheck + 解包审计
auto-epublizer status --json                              # 查看进度/状态机
```

仅转换不翻译：`auto-epublizer convert <input> -o output/book.epub`。
