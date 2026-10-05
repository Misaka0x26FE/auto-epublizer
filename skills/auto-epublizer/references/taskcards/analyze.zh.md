> **中文** | [English](analyze.md)

# 任务卡：analyze

阶段文档：`references/analysis.md`。

**现场（从磁盘重述）**：`next_tasks[0].kind=analyze`，带 `unit` id；`analysis/` 层尚无
`overview.md` / `global.md`。

**动作**：读 `structured/<unit>` 与 `preprocessing/facts.md`，写
`analysis/units/<unit>.md`（摘要 / 出场人物 / 术语注意点）。对指针列出的单元逐个完成
（每批最多 5 个）。

**完成判据**：被点名的 `analysis/units/<unit>.md` 存在。

**失败处置**：保持事实、简短；若该单元源文可疑，那是 `repair` 的事——不要杜撰理解。
