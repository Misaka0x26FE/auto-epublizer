> **中文** | [English](build-qa-delivery.md)

# 任务卡：build / qa / delivery

阶段文档：`references/build.md`、`references/qa.md`、`references/delivery.md`。

**现场（从磁盘重述）**：所有单元均为 `reviewed`；`next_tasks[0].kind` 为 `build` / `qa` /
`delivery` 三者之一。

**动作**（按顺序，步与步之间重跑 `status --json`）：
- `build`：`auto-epublizer build [--theme standard|compact|spacious]` → EPUB 落 `output/`。
- `qa`：`auto-epublizer qa` → epubcheck + 解包审计 + 独立登记注释门 + `report.json`。
- `delivery`：按 `references/delivery.md`（内容/资源/登记/链接/回链独立对账 + 抽样 + 人工核查）执行，写 `reviews/delivery-<ts>.md`，并核对全部分发副本字节。无需桌面：不可用时记「阅读器未实测」；GUI 仅为有条件兼容抽查，不替代离线验收、不承诺弹窗。

**完成判据**：`next_tasks` 为空、强制离线验收与交付记录完整、全部分发副本字节核对通过；机器指针为空本身不是交付证据。

**失败处置**：读 `qa` 报告的错误码；修 `translation/` + `align/` 后重建——**绝不**手补
EPUB（成品不是真源）。
