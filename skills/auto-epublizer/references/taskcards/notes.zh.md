> **中文** | [English](notes.md)

# 任务卡：notes（注释核证 / 登记）

阶段文档：`references/notes.md`。

**现场（从磁盘重述）**：`next_tasks[0].kind` 为 `notes_verify` 或 `notes_register`——
书里确实出现注文候选：`preprocessing/note_candidates.jsonl` 有未决条目，或
`structured/notes.json` 尚未登记 / 已因源文或结构变更而失效。

**动作（`notes_verify`）**：逐条回看源件（页底 / 边注 / 对页证据）核证候选，把
`disposition=note|not_note` 写回 `preprocessing/note_candidates.jsonl`；判定为 note 的写进
`structured/notes.json`（注文内容 + 源引用位置/证据），并在正文**原引用位置**保留
`[^ref-…]` 原位标记（ref_id → note_id 由源 JSON 记录）。

引用候选显式绑定同单元且唯一的 `ref_id`；注文候选显式绑定 `note_id`，并在该
注文 `source_locations` 中逐条写对应 `candidate_id`（可保留 PDF page/bbox；
另列 unit/line 时须匹配候选）。跨页多候选可合并同一注，混合附录尾注可由正文引用；
合法孤儿注用 `orphan_ok`/`orphan_reason`，不得伪造引用或删除续文。
完整绑定示例见阶段文档；不得按同号/文本前缀猜配。重跑候选导出保留身份绑定。

**动作（`notes_register`）**：运行 `auto-epublizer notes register` 登记
`structured/notes.json`——分离登记门做契约校验 + 正文标记双向对账 + 摘要写入
`publication.json`。

**完成判据**：`status --json` 的 `notes` 段显示已登记且摘要在盘上一致；翻译阶段把同
`note_id` 的完整译注写入 `translation/notes.json`，由 `import` 的翻译导入门（标记守恒 +
译注齐全 + 摘要绑定）校验。

**失败处置**：契约错误按提示逐条修正（**不要手改** `publication.json`）；候选未决时不得
跳过——有注而零语义节点、部分遗漏、错目标/错内容、坏回链都会在成品门以 `notes_open`
阻断放行（E_NOTES_* 定位到具体 ref/文件）。
