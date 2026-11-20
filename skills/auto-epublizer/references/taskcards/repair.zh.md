> **中文** | [English](repair.md)

# 任务卡：repair

阶段文档：`references/repair.md`。

**现场（从磁盘重述）**：整备指针 `kind=repair` 带单元 ID 和可疑信号。OCR / 扫描件路径必做。
如指针提示 QA 未放行，先查看 `report.json` 中对应的诊断，再按指针处理。

PDF 原页疑点可用 `auto-epublizer evidence partition --save-tasks` 生成任务快照。
出现 `source_evidence` 时，按提示刷新快照。可用 `evidence source --json` 的 `page_routes`
定位多栏、OCR 和缺坐标页，`boundaries` 查看跨页两端。单栏按原页阅读顺序核对，索引和书目还需核对跨栏续项。无法查看原页时记录缺件。
带 `candidate_id` 的任务同时给出原始页文件、块号、原文范围与相邻块。查原页后，在
`repairs.jsonl` 写入该 ID、受影响单元和存在的工作区相对证据路径。需要补证时写
`unresolved` 并说明缺件。修改结构稿后重跑分区取证，确认内容在正确位置收录。

**动作**：按 `references/repair.md`，对照原始证据（`structured/raw/`、页面图）核验
`structured/`，修复解析缺陷（断行、连字符、OCR 字符、乱码、页眉页脚、脚注标记、顺序）。
每修一处写一行 JSON 到 `preprocessing/repairs.jsonl`，`status` 取 `done` 或 `unresolved`。

**完成判据**：按原始证据核对该单元，并在 `preprocessing/repairs.jsonl` 为本单元写入有效留痕。

**失败处置**：无法确认的一律记为 `unresolved`（附 `evidence`），绝不静默丢弃；`qa` 会把
未决项作为 warning 提示出来。
