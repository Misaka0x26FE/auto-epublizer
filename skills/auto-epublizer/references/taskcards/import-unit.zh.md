> **中文** | [English](import-unit.md)

# 任务卡：import-unit

阶段文档：`references/translation.md`、`references/review.md`。

**现场（从磁盘重述）**：`next_tasks[0].kind=import`，带 `unit` id——译文和/或对齐表已落盘
但状态未推进（stale）。

**动作**：运行 `auto-epublizer import --unit <unit>`（若有工作区术语表，加
`--terms preprocessing/terms.csv`）。该命令登记产物并执行 G0 结构校验。

**完成判据**：命令退出码为 0，且 `status --json` 不再把该单元列为 stale。

**失败处置**：读 G0 错误码/提示，修 `translation/` + `align/` 后重跑
`import --unit <unit>`。绝不手改 `publication.json`。
