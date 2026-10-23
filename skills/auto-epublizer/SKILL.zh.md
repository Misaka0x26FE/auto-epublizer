---
name: auto-epublizer
description: Orchestrates the auto-epublizer translation and EPUB workflow. Use for publication.json workspaces, init/preprocess/import/g0/build/qa/status/convert stage routing, glossary.csv three-state terminology, translation/align/ sentence tables, structured/ four-layer content, or EPUB output. The only LLM is the agent using the CLI (no internal LLM calls).
license: AGPL-3.0-only
compatibility: 需要具备文件读写和 shell 执行能力的 agent，以及 Git、uv、Python 3.12+ 和访问 GitHub 与 Python 包索引的网络。
metadata:
  suite: auto-epublizer
  workspace_model: publication.json
---
> **中文** | [English](SKILL.md)

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
4. **G0 的 blocking 术语/标记/脚注/源保真/表格结构违例是缺陷不是建议**，放行前须清零；长度比、前向缺块和经取证登记的 `terminology_exempt` 是 advisory，处理见 `references/translation.md`、`references/review.md`。
5. **EPUB 不是真相源**——发现成品问题改 `translation/` + `align/` 后重新 build，
   不手补成品文件。
6. **`qa` released ≠ 可发布**：发布前必须过 `references/publishing.md` 的
   权属+隐私 gate。
7. **唯一 LLM 原则**：CLI 零 token；语义判断全由你完成，禁止引入任何 LLM API 调用。
8. **译者署名默认=你的 agent 框架名**（OpenCode/DouBao…），用户指定名优先
   （经 `meta --translator` 写入）。
9. **标准 EPUB 验收不依赖桌面**：注释语义/内容/链接/回链/资源/有效登记绑定、独立注释门、epubcheck、独立交付对账与分发字节核对均为强制项。阅读器 GUI 仅作有条件兼容抽查；无桌面/阅读器记「阅读器未实测」，不阻塞标准交付、不保证普遍弹窗。见 `references/delivery.md`、`references/publishing.md`。
10. **EPUBCheck 必须有真实进程通过证据**：发布要求 `report.epubcheck.ran == true`、实际 `returncode == 0` 且 `errors == 0`；仅 jar 存在、Java 启动或旧 `ran` 字段不证明通过，进程失败/FATAL 不得当作零错误。完整发行包须保留 jar 相邻 `lib`，headless Java 即可运行。未执行的 `returncode` 为 `null`，未知不能猜 0；缺此证据的旧 released 报告由 status 标 stale，须重新 `qa`，不得手改旧 `released`。

## Route Before Acting

**先 bootstrap，后调用 CLI**：安装 Skill 只安装指引，不安装 Python 引擎。先读
`references/work-root.md`，确定用户选定的工作根，在 `<工作根>/auto-epublizer/`
安全 clone/快进官方 GitHub **main**，用项目 `uv` 环境准备 CLI，再通过现有
`work-root` 命令生成骨架（不加 `--force`）。书籍工作区在源码目录之外。
已有 checkout 必须通过仓库根/origin/main 与 tracked+untracked dirty 护栏；
ahead/divergent、错误分支/来源均停止，绝不 reset/stash/clean/覆盖。

成功后用其中导出的 `"$AEP_CLI" version`，对照本 Skill `manifest.json` 的
`minimum_cli_version`；不兼容则停止。再运行 `"$AEP_CLI" doctor --json` 自检
工具链/依赖/MinerU/网络，并**自报 multimodal / search**（能否看图、有无搜索工具，
CLI 无法探测），据此选 ingest 路由（见 `references/ingest.md`）。
本 Skill 及其 references 中所有 `auto-epublizer …` 示例都须以 `"$AEP_CLI" …`
执行；新 shell 先按 work-root 指引安全续用，禁止碰巧调用全局同名 CLI。
然后只读当前阶段需要的 reference。

| 场景 | 读 |
|---|---|
| 首次使用 / 安全续用（必须先于 version/doctor） | `references/work-root.md` |
| 全新任务 / 状态路由 / 多阶段请求 / 命令总览 | `references/workflow.md` |
| 弱模型路径：机器「下一任务」指针（`status --json`）+ 原子任务卡 | `references/taskcards/` |
| 长期多书：工作根生成、批次 SHA256 交付、台账人工列保留、断链/忽略对账工具 | `references/work-root.md` |
| 预处理：读 facts → 撰写 todo/capabilities/plan/global/units/terms/risks/report | `references/preprocessing.md` |
| 文件解析：PDF / 扫描 PDF / EPUB / DOCX / HTML / TXT / MD / OCR | `references/ingest.md` |
| 语义整备：解析缺陷修复 / OCR 修正 / 结构重切（信号触发；OCR 必做） | `references/repair.md` |
| 四层结构归类、清洗、页眉页脚/页码剔除、溯源 | `references/structure.md` |
| 分层理解、术语播种、语言/体裁检测 | `references/analysis.md` |
| 切片翻译、纯标题空 align、`unit,source,reason` 术语豁免及三入口 advisory | `references/translation.md` |
| 注释结构化与绑定、稳定 ref、注号碰撞/孤注宿主、完整注文与代码字面量边界 | `references/notes.md` |
| 六道关 QC（G0–G5）、blocking/advisory 处理 | `references/review.md` |
| 交付前全量校验（qa 之后、交付之前，强制） | `references/delivery.zh.md` |
| 证据范围、审计诚实性、索引/结构批量修复工具的安全契约（自己写审计或批量修复脚本前必读） | `references/quality-evidence.zh.md` |
| EPUB 封装、代码/raw HTML、SVG/媒体身份、软件指纹、制作页署名与 nav/NCX 入口 | `references/build.md` |
| epubcheck + 解包审计、正文/注文独立对账、注释分段疑点 advisory、报告失效 | `references/qa.md` |
| 文体档案（novel/academic/paper/poetry/newspaper）应用 | `references/style.md` |
| 放行条件全集 / 错误码速查 / 排障判读 | `references/invariants.md` |
| 发布/分发成品（GitHub release / 私有分发）、权属与隐私 | `references/publishing.md` |
| 交付或遇到问题：经同意提供脱敏 issue / 修复 PR（默认仅本地草稿） | `references/workflow.md`「反馈贡献」 |
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
5. 本项目**不审查处理对象的版权风险**（权属由用户负责）；工作区（含 `source/` 源文件
   与全部处理产物）**全量纳入 git 仓库**，默认作为**私有仓库**上传到指定托管平台
   （默认 GitHub）；转公开需用户显式声明或自行处理。

## Command Discipline

- 机器决策用 `status --json` 或 `--json` 输出，不要解析彩色终端文本。
- 命令失败看错误码与中文提示，修复工作区/输入后重试；已完成单元可安全跳过。
- 同一工作区一次只跑一条长流程命令，避免并发写 `publication.json`。
- 改术语表/理解/解析后，须重跑受影响单元的后续阶段（状态机 `split → analyzed → translated →
  aligned → reviewed → built`）。

## 标准流程

完整命令总览与阶段列表见 `references/workflow.md`（此处不重复——入口刻意保持精简）。

```text
bootstrap → version → doctor → preprocess → agent 理解/分析 → (整备) → 翻译 → import
       → g0 → 审校 → build → qa → delivery → 询问是否贡献脱敏 issue / PR
```

按机器指针驱动：取 `status --json` → `next_tasks[0]`，做该任务（见
`references/taskcards/`），重跑 `status --json`，循环。

仅转换不翻译：`"$AEP_CLI" convert <input> -o output/book.epub`。

## 反馈贡献（交付或遇到问题时提醒）

**症状/最小合成复现用 issue，实际修复/文档变更用 PR，两者都支持。**
先在工作根 `docs/` 留脱敏草稿，给用户看完整标题、正文与拟提交补丁并请求明确同意，
才可 issue create / fork / push / pr create；未授权仅保留本地草稿。
不得上游提交真实书名/作者、文件或工作区名、原文/译文、真实路径、凭据、敏感报告元数据
或 Git 历史，改用虚构夹具；禁止盲目 `git add -A`。以用户账户认证，不索要 token；
缺认证/权限就停在草稿。完整步骤见 `references/workflow.md`。
