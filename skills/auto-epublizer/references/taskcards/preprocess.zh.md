> **中文** | [English](preprocess.md)

# 任务卡：preprocess

阶段文档：`references/preprocessing.md`、`references/ingest.md`。

**现场（从磁盘重述）**：`status --json` 显示 `has_preprocessing=false`；工作区可能尚无
`publication.json`。

**动作**：新书运行 `auto-epublizer preprocess <input> [--reference <path>...] [--target <lang>]`；
既有工作区运行 `auto-epublizer preprocess` 刷新 facts。此步仅做零 token 事实收集——**不要**
开始写理解产物。

**完成判据**：`status --json` 显示 `has_preprocessing=true`。

**失败处置**：先跑 `auto-epublizer doctor --json`（工具链 / MinerU / 网络），再读中文报错；
不支持的源或加密源是真实阻塞——见 `references/ingest.md`。
