# translation/ —— 译文目录

镜像 `structured/` 的目录树存放译文，并额外提供 `align/` 句级对照表：

- 每个源文单元 `<id>.md` 对应一个译文 `<id>.md`（纯译文）。
- `align/<id>.jsonl` 记录句级 `src ↔ tgt` 映射，是双语排版、QA 定位、断点续跑的锚点。
- 翻译前必须读取 `analysis/` 对应文件作为上下文；输出必须是**对齐的句对**。
