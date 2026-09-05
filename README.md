# auto-epublizer

一个 Python CLI，把来源复杂的文献**翻译**成任意目标语言，并生成**标准 EPUB 3**。

- **翻译**：外语文献 → 任意可配置目标语言（译文由使用本 CLI 的 AI agent 主进程完成，CLI 自身不做任何 LLM 调用）。
- **转 EPUB**：PDF（含扫描件）/ EPUB / DOCX / HTML / TXT / Markdown → 标准 EPUB 3，带目录导航、插图、封面。

两条能力共用同一条「归一化 → 结构化 → 翻译 → 封装」管线，避免两套解析。

项目由两大模块构成：**`skills/`**（指导 AI agent 用本项目完成任务 + 质量控制）与
**`src/auto_epublizer/`**（Python 代码：解析、清洗、中间文件处理、QC、EPUB 写出）。

---

## 快速开始

```bash
# 1. 安装（Python 3.12 + uv）
uv sync

# 2. 环境自检（工具链/OCR/epubcheck/MinerU 探测）
uv run auto-epublizer doctor [--ping]

# 3. 仅转换（不翻译）：源文件 → EPUB
uv run auto-epublizer convert <input> -o output/book.epub

# 4. 完整翻译流程（agent 主进程翻译 → import 登记 → 构建 → 质检）
uv run auto-epublizer preprocess <input>   # 预处理：init + 事实收集 → preprocessing/facts.*
uv run auto-epublizer import               # 登记 agent 手写的译文/对照表
uv run auto-epublizer build                # 封装 EPUB（纯译文 / --bilingual 双语）
uv run auto-epublizer qa                   # 结构审计 + epubcheck + 放行报告
uv run auto-epublizer status [--json]      # 进度 / 状态机 / 产物对账
```

配置项见 [docs/configuration.md](docs/configuration.md)（`config.yaml`，无密钥段；
可选外部解析 API 的 `MINERU_API_KEY` 只从环境变量读取）。

---

## 能力特性

| 能力 | 说明 |
|---|---|
| 输入格式 | TXT/Markdown、HTML、DOCX、EPUB、PDF（文字层）、扫描 PDF（OCR/MinerU） |
| 扫描件 PDF | **MinerU 外部 API 最优先**（版面/换行/插图识别），无 key 退传统 OCR + agent 逐页阅读兜底 |
| 输出 | 纯译文 / 双语对照两种；标准 EPUB 3（目录导航、插图、封面、脚注双向跳转） |
| 质量控制 | 六道关 G0–G5：静态校验 → 逐批审校 → 取证 → 仲裁/影子修订 → epubcheck+解包审计 → 交付放行 |
| 术语管理 | 三态术语表（种子→候选→冲突→确认）+ 冲突外置裁决，跨章/跨书一致 |
| 可复现 | 同一输入必得同一产物；断点续跑按单元状态跳过已完成单元 |

翻译流程细节见 [docs/translation-flow.md](docs/translation-flow.md)；
分文体优化（小说/学术/论文/诗歌/报刊）见 [docs/genre-style.md](docs/genre-style.md)；
PDF 解析难点与方案见 [docs/pdf-parsing.md](docs/pdf-parsing.md)。

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
├── output/          成品 EPUB（<slug>.epub / <slug>-bi.epub）
├── references/      用户上传 + agent 检索的参考材料
├── publication.json 权威索引（元数据 + 内容树 + 状态机 + 配置快照）
└── events.jsonl     行为账本
```

每单元状态机：`pending → split → analyzed → translated → aligned → reviewed → built`。

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [docs/configuration.md](docs/configuration.md) | 配置完整 schema（config.yaml） |
| [docs/development-plan.md](docs/development-plan.md) | 开发任务与里程碑 |
| [docs/translation-flow.md](docs/translation-flow.md) | 翻译流程设计 |
| [docs/quality-control.md](docs/quality-control.md) | 六道关 QC 规格（数据契约/验收阈值/收敛状态机） |
| [docs/epub-template-spec.md](docs/epub-template-spec.md) | EPUB 形态规范（无样式模板/有限主题/标准弹窗注释） |
| [docs/postprocessing-spec.md](docs/postprocessing-spec.md) | 后处理验收（内容溯源/媒体/目录层级） |
| [docs/pdf-content-spec.md](docs/pdf-content-spec.md) | PDF 内容提取规范（书签切章/插图路由/表格/公式/inserts 溯源） |
| [docs/pdf-parsing.md](docs/pdf-parsing.md) | PDF 解析难点与方案对比 |
| [docs/genre-style.md](docs/genre-style.md) + [docs/genres/](docs/genres/) | 分文体设计 |
| [docs/publishing-workflow.md](docs/publishing-workflow.md) | 传统三审三校编校流程映射 |
| [docs/reference-projects.md](docs/reference-projects.md) | 参考项目（wenyi）：借鉴与差异 |
| [docs/plans/](docs/plans/) | 计划文档目录（每轮任务立项/状态/索引） |
| [docs/testing-doubao.md](docs/testing-doubao.md) | 豆包云容器实测指南 |

面向 AI 的文档：
- **维护本仓库代码的 agent** → [AGENTS.md](AGENTS.md)（项目怎么实现、怎么验证）
- **用本 CLI 处理一本书的 agent** → [`skills/auto-epublizer/`](skills/auto-epublizer/SKILL.md)
  （每步怎么做、怎么判读结果、怎么修；含 `lessons/` 实战经验沉淀）

---

## 许可

项目自身代码采用 **AGPL-3.0**；第三方依赖保留各自许可证并在
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) 登记。
