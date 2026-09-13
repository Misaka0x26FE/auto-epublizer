---
name: auto-epublizer
description: Orchestrates the auto-epublizer translation and EPUB workflow. Use for publication.json workspaces, init/preprocess/import/g0/build/qa/status/convert stage routing, glossary.csv three-state terminology, translation/align/ sentence tables, structured/ four-layer content, or EPUB output. The only LLM is the agent using the CLI (no internal LLM calls).
compatibility: opencode
metadata:
  suite: auto-epublizer
  workspace_model: publication.json
---

# auto-epublizer

`auto-epublizer` 是一个 Python CLI，提供两项能力、一条共用管线：**翻译**（外语文献 → 任意目标语言）与
**转 EPUB**（复杂文件 → 标准 EPUB 3）。工作区以 `publication.json` 为权威索引。

**唯一 LLM 原则**：本项目中**唯一的 LLM 就是操作本 CLI 的 agent 本身**。CLI 只做确定性、
零 token 的计算（解析/切片/检测/校验/构建/审计）；**内容理解、翻译、审校判断、术语终局
裁决、公式 LaTeX、内容描述、修复与放行决策**全部由使用本 Skill 的 agent 用自身能力
（读文件、判断、写文件）完成。agent 只需基础能力，无需 MCP/子代理。

## 不可协商红线

1. **不手编 `publication.json`**——状态只经 CLI 命令推进（import/g0/qa/meta）。
2. **`source/` 与 `references/user/` 绝不改动**。
3. **结构（切章/标题层级）翻译前定稿**；中途改动必须重走受影响单元（重 ingest +
   重译），旧译文不作数。
4. **G0 术语命中/标记守恒/脚注守恒/源保真/表格形状是缺陷不是建议**，放行前必须
   清零；长度比才是 advisory。
5. **EPUB 不是真相源**——发现成品问题改 `translation/` + `align/` 后重新 build，
   不手补成品文件。
6. **`qa` released ≠ 可发布**：发布前必须过 `references/publishing.md` 的
   权属+隐私 gate。
7. **唯一 LLM 原则**：CLI 零 token；语义判断全由你完成，禁止引入任何 LLM API 调用。
8. **译者署名默认=你的 agent 框架名**（OpenCode/DouBao…），用户指定名优先
   （经 `meta --translator` 写入）。

## Route Before Acting

先跑 `auto-epublizer version`，若低于本目录 `manifest.json` 的
`minimum_cli_version`，停止并提示用户升级 CLI（skill 与 CLI 契约不兼容）。
再跑 `auto-epublizer doctor --json` 做能力自检（工具链/依赖/MinerU/网络），并**自报
multimodal / search**（能否看图、有无搜索工具，CLI 无法探测）——据此选择 ingest 路由
（见 `references/ingest.md` 的能力-路由决策表）。然后读本 Skill 目录的 `manifest.json`，
按当前阶段只读需要的 reference。

| 场景 | 读 |
|---|---|
| 全新任务 / 状态路由 / 多阶段请求 / 命令总览 | `references/workflow.md` |
| 预处理：读 facts → 撰写 todo/capabilities/plan/global/units/terms/risks/report | `references/preprocessing.md` |
| 文件解析：PDF / 扫描 PDF / EPUB / DOCX / HTML / TXT / MD / OCR | `references/ingest.md` |
| 语义整备：解析缺陷修复 / OCR 修正 / 结构重切（信号触发；OCR 必做） | `references/repair.md` |
| 四层结构归类、清洗、页眉页脚/页码剔除、溯源 | `references/structure.md` |
| 分层理解、术语播种、语言/体裁检测 | `references/analysis.md` |
| 切片翻译、句级对齐、术语三态闭环、agent 手写翻译路径 | `references/translation.md` |
| 六道关 QC（G0–G5）操作指引 | `references/review.md` |
| 交付前全量校验（qa 之后、交付之前，强制） | `references/delivery.md` |
| EPUB 封装、确定性构建 | `references/build.md` |
| epubcheck + 解包审计、质量报告 | `references/qa.md` |
| 文体档案（novel/academic/paper/poetry/newspaper）应用 | `references/style.md` |
| 放行条件全集 / 错误码速查 / 排障判读 | `references/invariants.md` |
| 发布/分发成品（GitHub release / 私有分发）、权属与隐私 | `references/publishing.md` |
| 源站/脏源/边界情况的实战经验（Baka-Tsuki 插图段、epubcheck 离线等） | `lessons/`（按主题匹配，仅命中才读） |

> **传统工作区指纹**：目录含 `split/`、`split_translated/`、`.progress`、根
> `GLOSSARY.csv`、`_analysis.md`、`_understanding.md` 等 → **停下**：这是
> traditional-translation skill 的文件式工作区；换用该 skill 续跑，或与用户确认
> 迁移。迁移 = 以 `source/` 原文件重新 `init`/`preprocess` 的**语义重做**；legacy
> 译文只作对照证据，**禁止**拷进本工作区或当 canonical ID 使用。

## Boundary（不可违背）

1. `source/`、`references/user/` 只读，绝不改动；源文件内容以 `publication.json.meta.source_sha256` 绑定。
2. `publication.json` 是唯一真相，**禁止手工编辑**；所有状态变更走 CLI 命令。
3. `structured/`（含 `raw/` 中间产物）持久化供审查，可由源文件重建；`analysis/`、`translation/`、
   `reviews/`、`output/` 是智能产物。
4. 审校产物只写 `reviews/review-<ts>/`（影子译文、result.json）；正式 `translation/` 只在
   agent 明确修复后覆盖。
5. 只处理公有领域或已获授权文本；不提交受版权保护的正文与用户本地数据。

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
#   agent 读 facts.md，撰写 todo/capabilities/plan/global/units/terms/risks/report（见 references/preprocessing.md）
#   理解层 analysis/*.md 同样由 agent 撰写（见 references/analysis.md）
auto-epublizer meta --translator OpenCode                             # 元数据核对写回 + 译者署名（默认=agent 框架名）
auto-epublizer import [--unit <id>] [--terms preprocessing/terms.csv]  # 登记 agent 手写翻译产物
auto-epublizer import --reviewed                                    # 审校通过后：aligned → reviewed
auto-epublizer g0                                         # 静态校验（术语命中=真实缺陷须清零；长度比=advisory）
#   agent 写审校产物 reviews/review-<ts>/（含 result.json，见 references/review.md）
auto-epublizer build [--bilingual] [--theme standard|compact|spacious]  # 封装 EPUB → output/
auto-epublizer qa                                         # epubcheck + 解包审计
auto-epublizer status --json                              # 查看进度/状态机/产物-状态对账
```

仅转换不翻译：`auto-epublizer convert <input> -o output/book.epub`。
