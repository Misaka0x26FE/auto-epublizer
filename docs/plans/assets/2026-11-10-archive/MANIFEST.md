# 归档资产保全清单（2026-11-10）

来源：`~/Downloads/translate.tar.gz`（SHA-256 `c22235b4…9bc59a08`）内
`translate/auto-epublizer` 快照与 `translate/docs/tools/`。只保全**代码/补丁**，
不含书籍正文、译文或凭证。

| 文件 | SHA-256 | 内容 | 处置 |
|---|---|---|---|
| `pdf-running-font-770ae20.diff` | `312fb255…6eb838` | PDF 页眉/页码 TrueType 嵌入、字体栈、封面 h1/figcaption 剔除、colophon、span bbox redaction | **已重做**（E4；字体栈/字体文件、redaction、封面剔除/colophon 均有单测；仍无页面视觉比对） |
| `worktree-build-cover.diff` | `82c79b04…23cb5` | 主题去 `font-family`（2026-11-04 用户指令）+ `dossier` 封面意象 | **已采纳**（主题与规范/测试同步更新；dossier 已移植） |
| `cover_hanze_batch11.patch` | `624574eb…5487f` | 十款批量封面意象补丁 | **暂缓**：未逐项评估视觉与参数稳定性；需要时按单项 cherry-pick，不整体套用 |

未保全：`uv.lock` 镜像噪声（环境产物，不是功能）；归档中 3 个未推送提交的其余文件
（对象不完整，无法可靠重建；已在计划正文登记，待归档保留期再取）。

## 采纳边界

- 保全 ≠ 迁移成功：功能必须重新通过本仓测试与视觉检查；清单中的「已重做/已采纳」
  只表示对应能力已在本轮落地并有测试。
- 补丁保留原样，不修改；如与当前主线冲突，以本仓测试和规范为准并记录差异。
