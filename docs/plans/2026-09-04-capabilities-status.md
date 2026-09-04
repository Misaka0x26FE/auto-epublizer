# 计划：capabilities.md 接入 status 完整性检查

> 状态：**规划中**（2026-09-04 立项）。前置：preprocessing-plan-v2 §capabilities 契约；
> S1 已让 doctor 输出 `search: null` 自报位并更新 skills，但 **CLI 状态机不认
> capabilities.md**。

## 1. 背景与问题

v2 契约把 `preprocessing/capabilities.md` 定为预处理必备产物（agent 自报五维能力边界：
multimodal/search/模型/外部 API/工作量），skills/preprocessing.md 的完成判据也已写
「七类产物齐备（capabilities/plan/global/units/terms/risks/report）」。但：

- `orchestrator.status` 的 `preprocessing_complete` 只查 `global.md`
  （orchestrator.py:590），capabilities.md 缺失时状态机仍显示 complete；
- `facts.py` 的 `agent_todo` 清单（6 项）没有 capabilities.md 项——agent 读 facts.md
  的待办清单根本不会去写它。

## 2. 已定决策

- `preprocessing_complete` = facts 落盘 **且 `global.md` 存在 且 `capabilities.md` 存在**。
- stale 机制不加新 reason（保持最小改动）：capabilities 缺失直接体现为
  `preprocessing_complete == false`；skills 已把 capabilities.md 列为必备，判据闭环在
  文档侧。
- `agent_todo` 首位插入 capabilities 项（先自报能力，再做方案决策——顺序即依赖）。

## 3. 任务清单

| # | 文件 | 改动 |
|---|---|---|
| 1 | `src/auto_epublizer/orchestrator.py` | `preprocessing_complete` 增加 `(preprocessing_dir / "capabilities.md").is_file()` 条件（约 :590） |
| 2 | `src/auto_epublizer/preprocess/facts.py` | `agent_todo` 列表首位插入「preprocessing/capabilities.md：自报五维能力边界（multimodal/search/模型/外部 API/工作量），见 references/preprocessing.md §1.1」 |
| 3 | `skills/auto-epublizer/references/workflow.md` | 命令总览处 agent 理解一行的产物清单加 capabilities（capabilities/plan/global/…，与 preprocessing.md 一致；若 S5 已改则核对即可） |
| 4 | `tests/test_preprocess.py` | `test_collect_facts_and_write`：agent_todo 数量 6→7、首项含 capabilities；`test_status_reports_preprocessing_state`：补 capabilities.md 前后 complete 翻转的断言 |
| 5 | `tests/test_e2e.py` 等 | 全局搜索依赖 `preprocessing_complete` 或 agent_todo 数量的断言，逐个更新 |

## 4. 验收标准

- `status --json`：无 capabilities.md → `preprocessing_complete == false`；补齐后 true。
- facts.md 的 agent 待办首位是 capabilities 自报项。
- 全量回归通过 + ruff 双检；`uv run pytest -q` 中所有 preprocessing/status 相关断言更新。

## 5. 本轮不做

- capabilities.md 的 schema 校验（自由 markdown；CLI 只查存在性）
- 把 plan.md/terms.csv 纳入 complete 判据（v2 契约里它们是「齐备」项但非状态机门，
  与现状一致）
