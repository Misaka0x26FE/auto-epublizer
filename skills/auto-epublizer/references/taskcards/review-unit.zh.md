> **中文** | [English](review-unit.md)

# 任务卡：review-unit

阶段文档：`references/review.md`。

**现场（从磁盘重述）**：`next_tasks[0].kind=review`，带 `unit` id；该单元为 `aligned`，
尚未 `reviewed`。

**动作**：用你自己的判断对该单元做 G1–G3 语义审校（漏译 / 增译 / 误译 / 术语 / 代词），
把审校产物写到 `reviews/review-<ts>/`（含 `result.json`）。然后用
`auto-epublizer import --unit <unit> --reviewed` 登记通过。

逐句查看源译对应，抽查相邻段落的归属。重点核对否定、数字、专名、引文和诗行。源区间完整或段数相等时仍可能错挂。发现错挂或漏译时，记下影响的源区间、译文位置和原页依据。

**完成判据**：`import --unit <unit> --reviewed` 把该单元推进到 `reviewed`。

**失败处置**：把真实问题写进 `result.json` 并修影子译文；没有登记就不要声称完成。若单元
反复震荡，见 `references/review.md` 的收敛规则。
