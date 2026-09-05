# 计划文档目录（docs/plans/）

本目录专门存放**每次更新的计划文档**：每轮开发任务先在此立项（写计划），实施时以计划为
权威依据，完成后回写状态。规范类文档（如 `docs/pdf-content-spec.md`）与交接类文档
（如 `docs/workstate.md`）仍留在 `docs/`。

> **计划中的经验归位**：计划文档的验证记录是可复用经验的来源；经验本体沉淀到
> `skills/auto-epublizer/lessons/`（判据/处置/验证三段式，每篇一主题），计划文档保留
> 验证上下文并在完成后互相引用（见 `AGENTS.md`「文档地图」）。

## 命名与状态约定

- 文件名：`YYYY-MM-DD-<主题>.md`（立项日期前缀，便于按时间排序）。
- 文档头部状态行：`规划中` → `实施中` → `已完成（<提交号>）`；被取代的标 `已被 <new> 取代`。
- 实施时须同步的文档（`skills/`、`AGENTS.md`、`README.md`）在计划内列明；完成后一并提交。
- 完成后若验证记录含可复用经验，同步沉淀一篇 `lessons/` 并互相引用。

## 索引

| 文档 | 状态 | 内容 |
|---|---|---|
| [preprocessing-plan.md](preprocessing-plan.md) | 已被 v2 取代 | 预处理 v1（分类识别 + 分层理解 + 补充环节） |
| [preprocessing-plan-v2.md](preprocessing-plan-v2.md) | 已完成 | 预处理 v2（能力边界确认 + 计划 A OCR 路由 / B 网络搜索 / C PDF 内容提取） |
| [2026-09-04-skills-inserts-guidance.md](2026-09-04-skills-inserts-guidance.md) | 已完成 | skills 缺口：inserts 补全与判读指引（translation/qa + 审计源切换） |
| [2026-09-04-capabilities-status.md](2026-09-04-capabilities-status.md) | 已完成 | capabilities.md 接入 status 完整性检查 |
| [2026-09-04-pdf-dogfooding.md](2026-09-04-pdf-dogfooding.md) | 已完成 | 真书 dogfooding：新 PDF 管线实战验证与阈值回填（5 缺陷修复） |
| [2026-09-04-remove-internal-llm.md](2026-09-04-remove-internal-llm.md) | 已完成 | 移除内部 LLM 路径（唯一 LLM = agent 本身；代码 + 文档全库落地） |
| [2026-09-05-scanned-pdf-mineru.md](2026-09-05-scanned-pdf-mineru.md) | 已完成 | 扫描件 PDF 处理方式更新：MinerU 最优先（后端落地）+ 传统 OCR 逐页阅读兜底 |
