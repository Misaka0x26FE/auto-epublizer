# 2026-09-18 i18n：文档英文版（英文默认）与中英同步契约

状态：已完成（8226135 / deb26a5 / 8a3d9e0 / 072d6f8 / da52a03 / 11553dc / 293b03b / 5f59985 + 收尾回写；立项 bf0d3cf）

## 背景与目标

当前全部文档（README/AGENTS/skills/docs）为中文，CLI 输出与领域命名亦为中文。
本任务为**文档**增加英文版，并让**英文成为默认展示**（`README.md` 等默认名为英文），
以服务非中文使用者与国际 contributor。

**目标**

1. 根文档 2 份 + `skills/` 26 份 + `docs/` 22 份，共 **50 份**产出英文版；
2. 约定「英文默认 `X.md` / 中文 `X.zh.md`」的命名与语言切换横幅；
3. 建立**中英同步契约**（sha256 戳 + 测试强制），防止单侧改动导致文档漂移；
4. 全量相对链接在两种语言下均可解析。

**非目标（本轮不改）**

- CLI 提示词/输出、`--help` 文案、代码注释与领域命名（保持中文，遵循 `AGENTS.md` 风格约定）；
- `docs/plans/*.md`（14 份历史计划，保持中文单语；仅修复其中指向被改名文档的链接）；
- `template/`（生成用户工作区的模板，属产品行为，保持中文）；
- `THIRD_PARTY_LICENSES.md`（许可证登记表，单语 canonical）、`LICENSE`、`config.example.yaml`；
- 不做运行时 i18n：不引入语言配置项，CLI 不输出英文。

## 已定决策（用户确认）

| # | 决策 | 说明 |
|---|---|---|
| D1 | 范围 = T1+T2+T3 全量 | 根 2 + skills 26 + docs 22，见附录 A 清单 |
| D2 | 英文作默认 | 英文占 `X.md`（GitHub 默认展示），中文移入 `X.zh.md` |
| D3 | 中文仍为权威源 | 现有内容全为中文、维护者中文优先；英文为**派生译文**，戳记录中文源 sha256。工具方向中立（戳内声明 `source=`，可随时互换） |
| D4 | 同步强制 | `scripts/i18n.py`（check/stamp/links/audit）+ `tests/test_i18n.py` 强制 |
| D5 | 同语言互链 | 英文文档链英文默认名（`X.md`）；中文文档链 `X.zh.md`；跨语言经顶部横幅切换 |
| D6 | `docs/i18n.md` 为双语例外 | 政策 + 术语对照表单文件双语（中英并列），不设 `.zh.md` 孪生 |
| D7 | 翻译由 agent 完成 | 唯一 LLM 原则：无新增 LLM 调用；agent 读中文源、按术语表写英文 |
| D8 | 一跳一提交 | 每批（子阶段）一提交，Conventional Commits，完成后双推 |

## 命名、默认与同步契约

**命名**：英文默认 `X.md`，中文 `X.zh.md`（同目录并列，如 `README.md` / `README.zh.md`、
`skills/auto-epublizer/references/qa.md` / `.../qa.zh.md`）。

**语言横幅**（每份文件顶部，紧随 i18n 注释）：

```markdown
<!-- i18n: source=README.zh.md sha256=<64hex> -->
> **English** | [中文](README.zh.md)
```

中文侧：

```markdown
> **中文** | [English](README.md)
```

**戳规则**：仅**派生侧**带 `<!-- i18n: source=<对侧文件名> sha256=<对侧文件内容 sha256> -->`；
`--check` 读取 `source=` 命名的文件并重算哈希比对，方向中立（D3 可互换而无需改工具）。

## 工作分解

### S1 i18n 契约与工具（先做；后续每批依赖其校验）

1. `docs/i18n.md`（D6 双语例外）：命名/默认/权威/横幅/戳格式 + **术语对照表** + 豁免清单。
2. `scripts/i18n.py`（纯标准库，离线确定性）：
   - `--stamp`：对给定文件（或全量）按对侧内容重算并写入/更新 i18n 注释；
   - `--check`：扫描全部 `*.zh.md` → 要求存在对应 `X.md` 与 i18n 注释，
     校验 `sha256(source)` 与当前内容一致；不一致列清单并 `exit 1`；
   - `--links`：解析全部 md 的相对 `.md` 链接（跳过 http/https/mailto/纯锚点）；
     - 解析失败（断裂）→ `exit 1`；
     - 语言错配（中文文档链到已译文档的非 `.zh.md` 名，或英文文档链到 `.zh.md`）→ `exit 1`；
   - `--audit`：列出无孪生的 `.md`（供人工复核豁免，不失败）。
3. `tests/test_i18n.py`：`test_stamps_fresh` / `test_banners_present` / `test_links_resolve`
   （均直接调用脚本函数，仓库内文件为输入，离线快速）。
4. `AGENTS.md`（中文侧）：新增「文档 i18n 同步」条目（改中文源 → 必更新英文并 `--stamp`；
   新增文档须登记进 `docs/i18n.md` 清单）。

### S2 根文档（1 提交）

- `git mv README.md README.zh.md` → 新建英文 `README.md`（含横幅 + 戳）；
- `git mv AGENTS.md AGENTS.zh.md` → 新建英文 `AGENTS.md`（含横幅 + 戳；注明中文为权威源）；
- `pyproject.readme = "README.md"` 不变（翻转后即英文默认）。

### S3 skills 全套（26 份，分 3 提交）

| 批次 | 文件 | 备注 |
|---|---|---|
| S3a | `SKILL.md` + `references/workflow.md`、`invariants.md`、`preprocessing.md`、`ingest.md`、`repair.md`、`structure.md` | 入口 + 核心操作链 |
| S3b | `references/analysis.md`、`translation.md`、`review.md`、`build.md`、`qa.md`、`delivery.md`、`style.md`、`publishing.md` | 其余 references |
| S3c | `lessons/README.md` + 10 篇 lessons | 经验沉淀 |

- 同一提交内完成对应文件的 `git mv` + 英文写作 + 链接改指 + `--stamp`；
- `manifest.json` 评估是否补 `"languages": ["en","zh"]`（不改 references 列表语义）；
- `scripts/install-skills.sh` 整目录复制，无需改动（`.zh.md` 随附）。

### S4 docs/ 规格（22 份，分 3 提交）

| 批次 | 文件 | 备注 |
|---|---|---|
| S4a 规范 | `pdf-content-spec`、`pdf-parsing`、`epub-template-spec`、`postprocessing-spec`、`semantic-repair`、`configuration` | 被代码注释引用的核心规范 |
| S4b 流程/质量 | `quality-control`、`quality-lessons`、`agent-vs-code`、`translation-flow`、`publishing-workflow`、`development-plan`、`testing-doubao`、`reference-projects` | |
| S4c 文体/交接 | `genre-style` + `genres/{novel,academic,paper,poetry,newspaper}`、`workstate`、`progress-snapshot-2026-09-01` | 历史快照按需保留双语 |

- 代码注释/文档字符串中对 `docs/*.md` 的**文字引用**不改（路径仍有效，指向英文默认）；
  如需中文引用可在后续单独议题处理（非本任务）。

### S5 收尾（1 提交）

1. `docs/plans/*.md`（中文单语）里指向被改名文档的链接改指 `.zh.md`（`--links` 暴露后逐一修）；
2. 全量 `uv run python scripts/i18n.py --check` + `--links` 通过；
3. `uv run pytest -q` + `uv run ruff check .` + `uv run ruff format --check .` 全绿；
4. 本计划状态回写 + `docs/plans/README.md` 索引更新。

## 术语对照表（起始版，完整表落在 `docs/i18n.md`）

| 中文 | English |
|---|---|
| 工作区 | workspace |
| 权威索引 | authoritative index |
| 单元 | unit |
| 辅文 / 正文 / 后置 | frontmatter / body / backmatter |
| 句级对照表 | sentence-level alignment (`align/`) |
| 术语表（种子/候选/冲突/确认） | glossary (seed / candidate / conflict / confirmed) |
| 六道关 G0–G5 | quality gates G0–G5 |
| 源保真 | source fidelity |
| 溯源 | provenance |
| 插入元素 | inserts |
| 登记（import） | register |
| 结构重建 | restructure |
| 语义整备 | semantic repair |
| 交付审计 | delivery audit |
| 收敛 / 影子修订 / 仲裁 | convergence / shadow revision / arbitration |
| 封装（build） | build |
| 质检（qa） | QA |
| 目录导航 / 导航深度 | navigation / nav depth |
| 页眉 / 页脚 | running head / footer |

## 风险与对策

| 风险 | 对策 |
|---|---|
| **链接断裂**（改名 + 双语互链，最大风险） | `scripts/i18n.py --links` 每批跑；S5 全量兜底 |
| 中英漂移 | sha256 戳 + `tests/test_i18n.py`（CI/本地 `pytest` 即拦） |
| 术语不一致（跨 50 份） | `docs/i18n.md` 术语表 + 每批判读一份参考译文风格 |
| 翻译量 (~5,660 行) 导致批次过大 | 按 S2–S5 的 8 个批次推进，每批可独立验证/回滚 |
| 英文默认影响中文维护者阅读习惯 | 中文孪生同目录 + 顶部一键切换；戳由工具维护 |

## 验证计划

```bash
uv run python scripts/i18n.py --check    # 50 对戳全部与中文源一致
uv run python scripts/i18n.py --links    # 全部相对 md 链接可解析且语言一致
uv run pytest -q                         # 含 tests/test_i18n.py
uv run ruff check . && uv run ruff format --check .
```

## 提交计划

| 提交 | 信息 |
|---|---|
| C1 | `chore(i18n): 建立中英同步契约与校验工具（#i18n）`（S1） |
| C2 | `docs(i18n): 根文档英文默认化（README/AGENTS）`（S2） |
| C3–C5 | `docs(i18n): skills 英文版（入口+核心/其余 references/lessons）`（S3a–c） |
| C6–C8 | `docs(i18n): docs 规格英文版（规范/流程质量/文体交接）`（S4a–c） |
| C9 | `docs(i18n): 收尾——plans 链接修正 + 全量校验 + 状态回写`（S5） |

## 附录 A：可译文件清单（50 对）

**根（2）**：`README.md`、`AGENTS.md`

**skills（26）**：`SKILL.md`；references 14：`workflow` `preprocessing` `ingest` `repair`
`structure` `analysis` `translation` `review` `build` `qa` `delivery` `style` `invariants`
`publishing`；lessons 11：`README` + `2026-09-05-agent-translation-workflow`
`2026-09-05-baka-tsuki-html-figures` `2026-09-05-dogfooding-pdf-lessons`
`2026-09-05-scanned-pdf-issue-checklist` `2026-09-05-scanned-pdf-mineru-first`
`2026-09-05-scanned-pdf-operations` `2026-09-06-conservation-total-only`
`2026-09-11-epub-nonlinear-spine-tables` `2026-09-12-epub-internal-links-anchors`
`2026-09-13-delivery-integrity`

**docs（22）**：`agent-vs-code` `configuration` `development-plan` `epub-template-spec`
`genre-style` `pdf-content-spec` `pdf-parsing` `postprocessing-spec`
`progress-snapshot-2026-09-01` `publishing-workflow` `quality-control` `quality-lessons`
`reference-projects` `semantic-repair` `testing-doubao` `translation-flow` `workstate`
+ `genres/academic` `genres/newspaper` `genres/novel` `genres/paper` `genres/poetry`

**双语例外（1）**：`docs/i18n.md`（政策 + 术语表，单文件双语）

**豁免**：`docs/plans/*`、`template/**`、`THIRD_PARTY_LICENSES.md`、`LICENSE`、
`config.example.yaml`、`参考/**`、`dist/**`

## 验证记录

- 范围：**50 对全部产出**（根 2 + skills 26 + docs 22）；`docs/i18n.md` 双语例外。
- 工具：`scripts/i18n.py`（`--check`/`--links`/`--relink`/`--finalize`/`--audit`）
  + `tests/test_i18n.py`（11 个测试：工具临时树自测 + 仓库实时戳/横幅/链接/孪生数）。
- 结果：`--check` OK、`--links` OK；`uv run pytest -q` **344 passed**；
  `ruff check` / `ruff format --check` 全绿。
- 提交（每阶段一提交，GitHub/Gitee 双推）：
  - 立项 `bf0d3cf`；S1 工具契约 `8226135`；S2 根文档 `deb26a5`
  - S3a `8a3d9e0`（SKILL + 核心 references）；S3b `072d6f8`（其余 references）；
    S3c `da52a03`（lessons）
  - S4a `11553dc`（docs 规范）；S4b `293b03b`（docs 流程/质量）；
    S4c `5f59985`（docs 文体/交接）
  - S5 收尾（本条回写：全局 relink + 50 对重盖章 + 实时链接测试 + 状态回写）
- 抽查：英文文件残留中文仅为 CLI 字面消息/专有名词示例（各文件 1–8 行）。

## 实施偏差

- **新增 `scripts/i18n.py --relink`（计划外工具增强）**：按语言把相对 markdown
  链接改指孪生，避免 50 份逐一改链。期间发现并修复其误改语言横幅的缺陷
  （横幅标签 中文/English 跳过），并补回归测试 `test_relink_skips_language_banner`。
- 内联代码中的路径提及（如 `SKILL.zh.md` 路由表的 `` `references/workflow.md` ``）
  不是 markdown 链接，`--relink`/`--links` 不处理，保持指向英文默认；中文读者可经
  顶部横幅切到 `.zh.md`。如需按语言改写内联提及，列为后续扩展点。
- `docs/i18n.md` 按 D6 保持双语单文件（不设 `.zh.md`）。
- 代码注释/文档字符串中对 `docs/*.md` 的**文字引用**按计划保持原样（指向英文默认，
  路径有效，属非目标）。
- 历史计划 `docs/plans/*.md` 保持中文单语；其指向被译文档的链接仍为裸 `.md`
  （指向英文默认，`--links` 存在性校验通过）。
- `skills/auto-epublizer/manifest.json` 未改：references 列表语言中立，安装脚本
  整目录复制（`.zh.md` 随附），无需新增字段。
