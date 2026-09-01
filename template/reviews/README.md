# reviews/ —— 审校运行记录

每次全书审校生成一个独立目录 `review-<ts>/`，其中保存：

- `issues/`：审校发现的问题清单
- `patches/`：影子修订的补丁记录
- `summary.json`：本轮摘要（轮数、问题数、收敛原因）
- `usage.json`：本轮 token 增量

审校只读影子译文，正式译文只有显式 Autofix 才会更新；历史记录保留用于审计与回溯。
