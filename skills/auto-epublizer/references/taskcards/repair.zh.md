> **中文** | [English](repair.md)

# 任务卡：repair

阶段文档：`references/repair.md`。

**现场（从磁盘重述）**：`next_tasks[0].kind=repair`——`facts` 标出
`repair_signals.units > 0`，且 `preprocessing/repairs.jsonl` 不存在。OCR / 扫描件路径必做。

**动作**：按 `references/repair.md`，对照原始证据（`structured/raw/`、页面图）核验
`structured/`，修复解析缺陷（断行、连字符、OCR 字符、乱码、页眉页脚、脚注标记、顺序）。
每修一处写一行 JSON 到 `preprocessing/repairs.jsonl`，`status` 取 `done` 或 `unresolved`。

**完成判据**：`preprocessing/repairs.jsonl` 存在。

**失败处置**：无法确认的一律记为 `unresolved`（附 `evidence`），绝不静默丢弃；`qa` 会把
未决项作为 warning 提示出来。
