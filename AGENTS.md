# auto-epublizer 仓库指南（面向 coding agent）

本文件是 agent 拿到本仓库后的唯一入口契约。按本文件即可完成：环境准备 → 配置 →
建工作区 → 解析 → 翻译 → 审校 → 封装 → 质检 的完整流程。

> 当前状态：方案设计阶段，源码尚未实现。本文件同时是"必须实现成什么样"的契约；
> 实现时若子目录出现更具体的 `AGENTS.md`，以更深层文件为准。

## 项目定位

`auto-epublizer`（Python CLI，包名待定）提供两项能力、一条共用管线：

1. **翻译**：外语文献 → 任意可配置目标语言。
2. **转 EPUB**：来源复杂文件（PDF/扫描 PDF/EPUB/DOCX/HTML/TXT/Markdown）→ 标准 EPUB 3。

- Python 3.12，包管理用 `uv`。
- 翻译引擎为 OpenAI 兼容 API（`base_url`/`api_key`/`model` 多 profile）。
- 工作区为 `publication.json` 权威索引 + 工作区目录（见下），不沿用旧 `split/` 流程。
- 质量检验五道关，重点参考 wenyi（`trans_novel`）的 Review 体系。
- **只负责交付质量**（准确 / 完整 / 一致 / 规范 / 结构正确 / 可复现），**不做内容的价值观 / 政治 / 思想性判断**。
- **自包含**：全部智能环节由 CLI 内部调用 LLM API 完成；使用本项目的 agent 只需读文件、跑 shell、写文件，无需 MCP / 子代理。
- **许可**：本项目自身代码采用 **AGPL-3.0**；第三方依赖保留各自许可证，并在 `THIRD_PARTY_LICENSES.md` 登记（AGPL 依赖可直接引入，与项目同许可兼容）。

## 处理一本著作的标准流程

```bash
# 1. 安装
uv sync

# 2. 配置（API Key 只从环境变量读取，见「配置与密钥」）

# 3. 建工作区并解析（源文件放入 source/，四层结构拆入 structured/；可选 --reference 导入参考材料）
auto-epublizer init <input> [--reference <path...>]

# 4. 解析（agent 理解：analysis/ 概要/全局/每单元/重点/术语表/人物表；网络检索写 references/web/）
auto-epublizer analyze

# 5. 翻译（读 analysis/，段落翻译返回句对，写 translation/ + align/ 对照表）
auto-epublizer translate [--target zh-CN] [--bilingual]

# 6. 审校（只读影子修订，五道关，产出质量报告）
auto-epublizer review

# 7. 封装输出
auto-epublizer build          # 纯译文 / 双语 EPUB → output/

# 8. 质检
auto-epublizer qa             # 结构审计 + epubcheck
auto-epublizer status --json  # 查看进度/状态机
```

仅转换不翻译：`auto-epublizer convert <input> -o output/book.epub`。

## 工作区目录契约

```text
<book-slug>/
├── source/           ① 待处理文件（原样，绝不改动）
├── structured/       ③ 按出版物四层结构拆分的源文（frontmatter/body/backmatter/media）
│                     + raw/（处理源文件的中间产物：OCR 页图、PDF→HTML，持久化供审查）
├── analysis/         ④ agent 理解：overview.md、global.md、units/<id>.md、
│                       keypoints.md、glossary.csv、characters.csv、glossary_conflicts.jsonl
├── translation/      ⑤ 译文（镜像 structured 树）+ align/<unit-id>.jsonl 句级对照表
├── references/       ⑦ 参考：user/（用户上传）+ web/（agent 网络检索）+ index.jsonl
├── reviews/          ⑥ 审校运行记录 review-<ts>/（每轮 issues/patches/summary/usage）
├── output/           ② 成品 EPUB（<title>.<lang>.epub / <title>.<lang>-bi.epub）
├── publication.json  权威索引（DC 元数据 + 内容树 + 状态机 + 配置快照）
├── .progress.json    断点续跑（可丢弃）
├── glossary.db       术语库内部索引（可选，SQLite）
├── events.jsonl      追加式行为账本
└── usage.json        token 用量账本（一次增量只合并一次）
```

单元状态机：`pending → split → analyzed → translated → aligned → reviewed → built`
（`reviewed`=通过审校，`built`=已封装；`convert` 路径跳过 analyze/translate/review，直接 split → built）。

目录生命周期：`source/`、`references/user/` 不可动；`structured/`（含 `raw/` 中间产物）
持久化保存供审查，可由源文件重建；`analysis/`、`translation/`、`reviews/`、`output/`
是智能产物；`.progress.json`、`events.jsonl`、`usage.json` 是追加式账本/断点；
`publication.json`、`glossary.db` 是权威真相。

术语表三态：`种子 → 候选 → 冲突 → 确认`。`analysis/glossary.csv` 是权威（人类/agent 可读），
冲突外置到 `glossary_conflicts.jsonl`；翻译 worker 只读快照 + 追加提案，由单线程合并器裁决后写回 CSV。

句级对照表 `translation/align/<unit-id>.jsonl` 每行一句：

```jsonl
{"seq": 1, "src": "原句", "tgt": "译句", "note": null}
```

`seq` 是双语排版、QA 定位、断点续跑的锚点；`note` 记录拆句/并句/漏译/存疑。

## 架构边界

依赖方向必须保持：

```text
CLI → Orchestrator（薄 façade）→ 领域服务（ingest/structure/analysis/translation/
      review/build/qa）→ agents / llm / glossary / workspace(RunStore)
```

- `orchestrator.py` 只装配与路由，不直接调用领域函数，不持有线程池。
- 下层不得反向导入 orchestrator。
- `agents/` 是**内部 LLM 调用服务**（翻译/审校/取证/仲裁/修订的提示词封装），不是子代理、也不是 MCP 服务；不得依赖编排、状态机或 RunStore。
- 并发属于具体领域服务；结果必须按稳定原文序合并，不得让线程完成顺序改变输出。
- 第三方依赖保留各自许可证并在 `THIRD_PARTY_LICENSES.md` 登记；AGPL 依赖可直接引入（项目自身为 AGPL）。

**自包含约束**：整个管线（解析 → 分析 → 翻译 → 审校 → 封装 → 质检）由 CLI 内部直接调用
OpenAI 兼容 API 完成。使用本项目的 agent 只需要**读文件、跑 shell 命令、写文件**这三种基础能力，
**不要求 MCP、子代理或任何特殊工具**。

## 状态与续跑不变量

- `publication.json` 是初始化成功的最终标志：派生状态先落盘，最后原子提交。
- JSON 状态经同目录临时文件 + `os.replace` 原子写；禁止直接覆盖。
- 状态用源文件 `source_sha256` 绑定内容；不得按同名静默复用不同内容。
- 已完成单元必须可安全跳过；改翻译/术语/解析/审校缓存时须覆盖中断后续跑。
- 导出从一致快照读取；审校只能改影子译文，正式 segment 只有显式 Autofix 可改。
- 用量账本追加式；一次审校增量只合并一次，重试/续跑不得重复计费。

## 质量检验流程（五道关）

1. **零 token 廉价校验**：对照表完整性、句数一致、长度比异常（<0.30 / >3.0 / 空）、标点/术语命中纯函数。
2. **逐批审校 Agent（cheap）**：missing/added/mistranslation/terminology/pronoun；宁缺毋滥；JSON 协议末尾必须 `reviewed_segments` + `complete:true`，违例整批重试。
3. **证据取证 Agent Loop（strong）**：候选先取证再裁决，禁止假设未取得的上下文；术语库与影子修订都是待核验材料。
4. **冲突仲裁 + 影子修订 + 盲复审**：跨块矛盾终局仲裁；Fixer 只在影子 overlay 改；下一轮盲审不传旧说明；连续 clean 确认或 max_rounds 收敛；振荡检测（摘要 SHA-256 循环）。
5. **EPUB 结构 QA**：epubcheck 零 error + 解包逐项审计（mimetype 首位、manifest/spine/nav 解析、封面、lang、每章一个 h1、脚注双向跳转、无残留）。

## 配置、密钥与 provider

- API Key 只从环境变量读取；禁止写入源码、测试、文档示例或提交。
- 通用 LLM 抽象不感知具体 provider 私有协议；重试由统一模块负责，关闭 SDK 内置重试避免嵌套。
- 测试默认用 `FakeClient`/mock，不调用真实 LLM 或网络。
- 用户可预期错误 → 明确异常 + 简洁中文提示；CLI 不打印 traceback。

## 开发与验证命令

```bash
uv sync                      # 安装
uv run pytest -q             # 全量测试（离线、确定、快速，不依赖真实书籍）
uv run ruff check .
uv run ruff format --check .
```

修复缺陷先添加能失败的最小回归测试；测试数据写 `tempfile`，不依赖仓库外的真实书籍。

## 代码与交付风格

- 中文领域命名与提示词；公共代码带类型提示与简短 docstring。
- 遵循 pyproject 的 Ruff 规则（目标 Python 3.12）。
- 提交信息用 Conventional Commits；只暂存本次任务修改的文件；不提交密钥与用户本地数据。
- 交付前运行受影响测试 + ruff check + ruff format --check。
