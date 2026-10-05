> **中文** | [English](build-qa-delivery.md)

# 任务卡：build / qa / delivery

阶段文档：`references/build.md`、`references/qa.md`、`references/delivery.md`。

**现场（从磁盘重述）**：所有单元均为 `reviewed`；`next_tasks[0].kind` 为 `build` / `qa` /
`delivery` 三者之一。

**动作**（按顺序，步与步之间重跑 `status --json`）：
- `build`：`auto-epublizer build [--bilingual] [--theme standard|compact|spacious]` → EPUB 落 `output/`。
- `qa`：`auto-epublizer qa` → epubcheck + 解包审计 + `report.json`。
- `delivery`：按 `references/delivery.md`（独立对账 + 抽样 + 人工核查）执行，并写
  `reviews/delivery-<ts>.md`。

**完成判据**：`next_tasks` 为空（没有更多条目）。

**失败处置**：读 `qa` 报告的错误码；修 `translation/` + `align/` 后重建——**绝不**手补
EPUB（成品不是真源）。
