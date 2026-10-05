> **中文** | [English](write-preprocessing.md)

# 任务卡：write-preprocessing

阶段文档：`references/preprocessing.md`。

**现场（从磁盘重述）**：`has_preprocessing=true` 但 `preprocessing_complete=false`；
`next_tasks[0].done_when.file` 指出缺失的产物（如 `preprocessing/capabilities.md`）。

**动作**：读 `preprocessing/facts.md`，按 `references/preprocessing.md` 的结构撰写被点名的
文件。只依据 facts 与自己的阅读来写——绝不杜撰内容。按顺序逐份完成
（`capabilities.md` → `global.md` → `todo.md`）。

**完成判据**：被点名的文件存在，且 `status --json` 推进到下一份缺失文件。

**失败处置**：若确有一项事实缺失，把缺口写进 `risks.md`，不要杜撰；若源不可读，回到
`preprocess` 卡。
