# source/ —— 源文件目录

把待处理文件**原样**放入本目录（主文件如 `the-great-gatsby.epub`，分卷/勘误/附图等辅助文件一并放入）。

- 主文件路径记录在 `publication.json` 的 `meta.source`。
- 内容身份用 SHA-256 绑定（`meta.source_sha256`），绝不改动源文件。
- 源文件随工作区**全量纳入 git 仓库**（默认私有；版权风险由用户负责，本项目不审查）。
