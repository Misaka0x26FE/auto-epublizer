# Ingest（文件解析）

`init` / `convert` 阶段把源文件归一化为 `Document → Unit → Segment` 结构，落 `structured/`，
中间产物落 `structured/raw/`。

## 格式路由

| 格式 | 处理 |
|---|---|
| `.txt` `.md` `.markdown` | 直接读文本，识别章节标题、按空行切段 |
| `.html` `.htm` `.xhtml` `.docx` `.epub` | 走 pandoc → Markdown 纯文本 + `--extract-media` 抽媒体 |
| `.pdf`（有文字层） | pymupdf 按页切片抽文字层，逐页写 `structured/raw/page-NNN.json` |
| `.pdf`（扫描件无文字层） | OCR 兜底：逐页渲染为图片 → OCR（RapidOCR，可选 `[ocr]` extra） |

不支持的其他格式：先转 PDF/TXT/Markdown，或 `pandoc` 处理后转 PDF 兜底。

## PDF 按页切片

- 每页独立处理、独立落盘 `page-NNN.json`（`{page_idx, blocks:[{type,bbox,text}], source}`），
  可单独重跑——断点续跑粒度 = 页。
- 每页文本块保留 `bbox` 与页号，是后续结构聚合与对账的 ground truth。
- 无文字层的扫描件：`page.get_pixmap(dpi)` 渲染 PNG → OCR → 作为该页文本块（`ocr:true`）。

## 中间产物

```text
structured/raw/
├── page-001.json ...   # PDF 逐页切片（文字层/OCR）
└── media/              # pandoc 抽取的图片等媒体
```

`raw/` 持久化供审查，可由源文件重建。

## 注意事项

- `source/` 原样，绝不改动；源内容身份以 `publication.json.meta.source_sha256` 绑定。
- OCR 是可选 extra（`uv sync --extra ocr`）；未装时扫描 PDF 会报错提示走 OCR 路径。
- 难页降级到多模态 LLM（页面转图）为后续扩展点，当前未实现。
- 常见错误：`不支持的格式`（换扩展名）、`该 PDF 没有可抽取的文字层`（扫描件，装 OCR 或转图）。
