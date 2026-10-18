> **中文** | [English](README.md)

# auto-epublizer

[![skills.sh](https://skills.sh/b/Misaka0x26FE/auto-epublizer)](https://skills.sh/Misaka0x26FE/auto-epublizer)

一个 Python CLI，把来源复杂的文献**翻译**成任意目标语言，并生成**标准 EPUB 3**。

- **翻译**：外语文献 → 任意可配置目标语言（译文由使用本 CLI 的 AI agent 主进程完成，CLI 自身不做任何 LLM 调用）。
- **转 EPUB**：PDF（含扫描件）/ EPUB / DOCX / HTML / TXT / Markdown → 标准 EPUB 3，带目录导航、插图、封面。

两条能力共用同一条「归一化 → 结构化 → 翻译 → 封装」管线，避免两套解析。

项目由两大模块构成：**`skills/`**（指导 AI agent 用本项目完成任务 + 质量控制）与
**`src/auto_epublizer/`**（Python 代码：解析、清洗、中间文件处理、QC、EPUB 写出）。

---

## 使用方式（Agent 协作模式）

本项目**不面向命令行人类用户**，而面向 **AI 编程 agent**：把本仓库地址和待处理文件
交给支持联网执行的 agent（如 OpenCode / DouBao / Cursor），先选定工作根。agent 按
[`references/work-root.md`](skills/auto-epublizer/references/work-root.zh.md) 的可复制步骤，
在 `<工作根>/auto-epublizer/` clone 官方 GitHub 最新 **main**，用项目 `uv` 环境准备
Python CLI，再用现有 `work-root` 命令无覆盖生成骨架（不加 `--force`）。
**安装 Skill 只安装文档，不安装 Python 引擎。** 书籍输入、工作区和交付物与源码仓库分离。
已有 checkout 必须先检查根/origin/main 与 tracked+untracked dirty，再 fetch/只快进；
ahead/divergent、错误分支/来源均停止，不 reset/stash/clean/覆盖用户内容。

你需要做的只有三件事：

1. 把本地址发给 agent（或用 Git UI / 命令行让任何 agent 能访问到本项目：
   `https://github.com/Misaka0x26FE/auto-epublizer.git`，Gitee 镜像：
   `https://gitee.com/misaka0x26fe/auto-epublizer.git`）。
2. 提供待处理文件（书源 PDF/EPUB/DOCX/HTML/TXT/MD 等）。
3. 可选：提供目标语言、元数据（标题/作者/版权页信息）、参考材料或备注。

> **版权与发布**：本项目**不审查处理对象是否包含版权风险**（源文件、插图等），权属由
> 你负责。处理过程产生的工作目录（含 `source/` 源文件）**全量纳入 git 仓库**，默认作为
> **私有仓库**上传到指定的 git 托管平台（默认 GitHub）；如需转为公开仓库，请自行处理
> 或显式声明。

> **扫描件 PDF 提示**：如果待处理文件是扫描件 PDF（无文字层），agent 会优先走
> MinerU 外部解析 API（版式/插图识别最好）。此时请配合提供 **MinerU API Key**
> （`MINERU_API_KEY` 环境变量，只在运行时读取，不写入任何文件）；无 key 时，
> agent 会改用传统 OCR + 逐页阅读兜底，效果略差但可用。

### 提示词（复制粘贴给你的 agent）

```text
你是译书助手。请严格按以下步骤工作：

1. 先与我确定工作根（即使只处理一本书），读
   skills/auto-epublizer/references/work-root.md 并整体执行其安全 bootstrap：
   <工作根>/auto-epublizer 为官方 GitHub 最新 main + 项目 uv 环境，
   书籍在同级 inbox/sources/workspaces，不放进源码。只用现有 work-root 命令，
   不加 --force；已有 checkout 脏/分支来源错误/ahead/divergent 就停止。
2. bootstrap 成功后，用导出的 "$AEP_CLI" version 对照 Skill 最低版本，
   再 "$AEP_CLI" doctor --ping 自检，并告知 multimodal/search 能力。
   此后所有 auto-epublizer 命令均用 "$AEP_CLI" 执行，不依赖全局同名程序。
3. 向我收集：待处理文件路径、目标语言（可选，默认 zh-CN）、元数据（标题/作者/版权页字段）。
   - 若文件是扫描件 PDF：请我提供 MINERU_API_KEY（写入环境变量，仅运行时读取，
     不写入源码/配置文件/提交历史）；无 key 则说明你会改走传统 OCR 兜底。
4. 严格按仓库内 skills/auto-epublizer/SKILL.md 的路由表执行：
   doctor → preprocess（CLI 零 token 事实收集）→ 我撰写理解/计划/术语 →
   meta（元数据核对写回）→ 我逐单元翻译+句对齐 → import/g0 登记查验 →
   我审校（G1–G3）→ build → qa（G4+epubcheck+G5 放行）。遵守其中的全部红线与协议。
5. 完成后告诉我成品 EPUB 路径。交付或遇到问题时，按 workflow 的反馈贡献流程，
   询问是否提供脱敏 issue（症状/合成复现）和/或实际修复 PR。先在工作根 docs/
   留草稿并给我看全部正文/补丁，获明确同意才 issue create/fork/push/pr create；
   未授权或缺认证/权限就停在本地草稿，不上传书籍内容、身份、路径或历史。
```

---

## 快速开始

先执行[首次使用与安全续用](skills/auto-epublizer/references/work-root.zh.md) 的完整 Bash
步骤（Git + Python 3.12 + `uv`），成功后已有 `AEP_ROOT` / `AEP_CLI`。以下是**阶段命令
语法示例**（`<input>`、`<slug>` 等须替换），相对路径以工作根为当前目录；不是独立安装流程。
不要从源码 checkout 处理书籍。新 shell 先安全续用，不把安装 Skill 当作安装引擎。

```bash
# 1. 骨架已由 bootstrap 无覆盖生成；先核对版本，再自检环境
"$AEP_CLI" version
"$AEP_CLI" doctor [--ping]

# 2. 仅转换（不翻译）：源文件 → EPUB
"$AEP_CLI" convert <input> --workspace "$AEP_ROOT/workspaces" -o "$AEP_ROOT/outbox/book.epub"

# 3. 完整翻译流程（preprocess 在 workspaces 下生成 <slug> 工作区）
"$AEP_CLI" preprocess <input> --workspace "$AEP_ROOT/workspaces"
"$AEP_CLI" meta --workspace "$AEP_ROOT/workspaces/<slug>" --translator OpenCode
# agent 理解/计划/翻译/对齐/审校遵循 Skill，以下只列 CLI 阶段
"$AEP_CLI" import --workspace "$AEP_ROOT/workspaces/<slug>"
"$AEP_CLI" build --workspace "$AEP_ROOT/workspaces/<slug>"
"$AEP_CLI" qa --workspace "$AEP_ROOT/workspaces/<slug>"
"$AEP_CLI" status --workspace "$AEP_ROOT/workspaces/<slug>" [--json]
```

配置项见 [docs/configuration.md](docs/configuration.zh.md)（`config.yaml`，无密钥段；
可选外部解析 API 的 `MINERU_API_KEY` 只从环境变量读取）。

### 反馈与贡献（默认仅本地草稿）

交付或遇到技术问题时可选择**issue**（症状与最小合成复现）和/或 **PR**（实际修复、
合成回归测试、文档改进）。完整流程见
[workflow「反馈贡献」](skills/auto-epublizer/references/workflow.zh.md)。
先在工作根 `docs/` 写脱敏草稿，展示完整标题/正文/补丁并获用户同意，才执行
issue create、fork、push、pr create。只用虚构夹具，禁止真实书名/作者、文件/工作区名、
原文/译文、真实路径、凭据、敏感报告元数据或用户/书籍 Git 历史；不盲目 `git add -A`。
使用用户自己的 GitHub 账户，不索要 token；未授权或缺认证/权限就保留本地草稿，不实际提交。

---

## 能力特性

| 能力 | 说明 |
|---|---|
| 输入格式 | TXT/Markdown、HTML、DOCX、EPUB、PDF（文字层）、扫描 PDF（OCR/MinerU） |
| 扫描件 PDF | **MinerU 外部 API 最优先**（版面/换行/插图识别），无 key 退传统 OCR + agent 逐页阅读兜底 |
| 输出 | 标准 EPUB 3（目录导航、插图、封面、脚注双向跳转） |
| 质量控制 | 六道关 G0–G5：静态校验 → 逐批审校 → 取证 → 仲裁/影子修订 → epubcheck+解包审计 → 交付放行 |
| 术语管理 | 三态术语表（种子→候选→冲突→确认）+ 冲突外置裁决；**跨书统一库**（`knowledge export/import`，默认 `~/Documents/auto-epublizer`，私有 git 仓库）复用术语与知识 |
| 可复现 | 同一输入必得同一产物；断点续跑按单元状态跳过已完成单元 |

翻译流程细节见 [docs/translation-flow.md](docs/translation-flow.zh.md)；
分文体优化（小说/学术/论文/诗歌/报刊）见 [docs/genre-style.md](docs/genre-style.zh.md)；
PDF 解析难点与方案见 [docs/pdf-parsing.md](docs/pdf-parsing.zh.md)。

---

## 工作区（每本书一个目录）

```text
<book-slug>/
├── source/          源文件（原样，绝不改动）
├── structured/      按四层结构拆分的源文 + raw/（OCR 页图、MinerU 产物等中间件）
├── analysis/        对源文的理解（翻译上下文）
├── preprocessing/   CLI 事实（facts.*）+ agent 撰写的理解/计划/术语/风险
├── translation/     译文 + align/ 句级对照表
├── reviews/         审校运行记录
├── output/          成品 EPUB（<slug>.epub）
├── references/      用户上传 + agent 检索的参考材料
├── publication.json 权威索引（元数据 + 内容树 + 状态机 + 配置快照）
└── events.jsonl     行为账本
```

每单元状态机：`pending → split → analyzed → translated → aligned → reviewed → built`。

> **统一术语库/知识库（工作区之外）**：默认 `~/Documents/auto-epublizer/`，跨书持久化、
> 由 agent 自行维护、本身是**私有 git 仓库**（`knowledge push` 可跨设备同步）；
> 开工 `knowledge export` 播种、定稿 `knowledge import` 回写。

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [docs/architecture.md](docs/architecture.zh.md) | 当前组件架构、agent/CLI 数据流、权威存储与实现边界 |
| [docs/configuration.md](docs/configuration.zh.md) | 配置完整 schema（config.yaml） |
| [docs/development-plan.md](docs/development-plan.zh.md) | 开发任务与里程碑 |
| [docs/translation-flow.md](docs/translation-flow.zh.md) | 翻译流程设计 |
| [docs/quality-control.md](docs/quality-control.zh.md) | 六道关 QC 规格（数据契约/验收阈值/收敛状态机） |
| [docs/epub-template-spec.md](docs/epub-template-spec.zh.md) | EPUB 形态规范（无样式模板/有限主题/标准弹窗注释） |
| [docs/postprocessing-spec.md](docs/postprocessing-spec.zh.md) | 后处理验收（内容溯源/媒体/目录层级） |
| [docs/pdf-content-spec.md](docs/pdf-content-spec.zh.md) | PDF 内容提取规范（书签切章/插图路由/表格/公式/inserts 溯源） |
| [docs/pdf-parsing.md](docs/pdf-parsing.zh.md) | PDF 解析难点与方案对比 |
| [docs/genre-style.md](docs/genre-style.zh.md) + [docs/genres/](docs/genres/) | 分文体设计 |
| [docs/publishing-workflow.md](docs/publishing-workflow.zh.md) | 传统三审三校编校流程映射 |
| [docs/reference-projects.md](docs/reference-projects.zh.md) | 参考项目（wenyi）：借鉴与差异 |
| [docs/plans/](docs/plans/) | 计划文档目录（每轮任务立项/状态/索引） |
| [docs/testing-doubao.md](docs/testing-doubao.zh.md) | 豆包云容器实测指南 |

面向 AI 的文档：
- **维护本仓库代码的 agent** → [AGENTS.md](AGENTS.zh.md)（项目怎么实现、怎么验证）
- **用本 CLI 处理一本书的 agent** → [`skills/auto-epublizer/`](skills/auto-epublizer/SKILL.zh.md)
  （每步怎么做、怎么判读结果、怎么修；含 `lessons/` 实战经验沉淀）

---

## 许可

项目自身代码采用 **AGPL-3.0-only**（SPDX 表达式；源码文件带
`SPDX-License-Identifier: AGPL-3.0-only` 与版权行；分发元数据见 `pyproject.toml` 的
`license`）；第三方依赖保留各自许可证并在
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) 登记。

**来源可识别、不追踪**：程序不含遥测/心跳/部署识别；工作区在 `publication.json`
记录 `meta.producer`（如 `auto-epublizer@0.1.0`）并在 `events.jsonl` 的
`run_initialized` 事件给出同一标识，`build` 日志固定带工具名 + 许可证 + 源码地址——
第三方可据此指回源码，工具不做任何出网行为。（issue #40 §5）
