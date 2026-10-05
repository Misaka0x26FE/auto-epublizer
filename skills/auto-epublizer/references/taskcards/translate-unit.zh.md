> **中文** | [English](translate-unit.md)

# 任务卡：translate-unit

阶段文档：`references/translation.md`。

**现场（从磁盘重述）**：`next_tasks[0].kind=translate`，带 `unit` id；该单元状态为
`pending` / `split`，且无已登记译文。先读 `analysis/glossary.csv`（或
`preprocessing/terms.csv`）取已确认术语。

**动作**：读 `structured/<unit>`，把译文写入 `translation/<rel_path>`，并写句级对照表
`translation/align/<unit>.jsonl`（每行一句：
`{"seq","src","tgt","note"}`）。只做这一单元——指针一次只给一个。

**完成判据**：`auto-epublizer import --unit <unit>` 成功且单元状态推进（卡内 `done_when`
为 `{"cmd":"import","unit":<unit>}`）。

**失败处置**：跑 `auto-epublizer g0 --unit <unit>`；术语命中 / 标记 / 脚注 / 标题守恒都是
真实缺陷——修好后重新 import（G0 修法见 `references/review.md`）。
