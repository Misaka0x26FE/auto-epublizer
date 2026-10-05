> **中文** | [English](README.md)

# 任务卡（弱模型路径）

偏弱模型的推荐循环：先读一次 `references/workflow.md`，之后完全按 `status --json` 返回的
机器指针驱动。

1. 运行 `auto-epublizer status --json`，取 `next_tasks[0]`；
2. 打开与其中 `kind` 对应的任务卡（见下表）并执行；
3. 重跑 `status --json`，循环，直到 `next_tasks` 为空。

| `next_tasks[0].kind` | 任务卡 |
|---|---|
| `preprocess` | [preprocess.zh.md](preprocess.zh.md) |
| `write_preprocessing` | [write-preprocessing.zh.md](write-preprocessing.zh.md) |
| `repair` | [repair.zh.md](repair.zh.md) |
| `analyze` | [analyze.zh.md](analyze.zh.md) |
| `translate` | [translate-unit.zh.md](translate-unit.zh.md) |
| `import` | [import-unit.zh.md](import-unit.zh.md) |
| `review` | [review-unit.zh.md](review-unit.zh.md) |
| `build` / `qa` / `delivery` | [build-qa-delivery.zh.md](build-qa-delivery.zh.md) |

每张卡自包含（一屏以内）：重述现场 → 动作 → 完成判据 → 失败处置。`references/` 下的
阶段级文档仍是完整指南；任务卡是弱模型的最小路径。
