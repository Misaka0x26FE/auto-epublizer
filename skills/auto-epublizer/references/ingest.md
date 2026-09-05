# Ingest（文件解析）

`init` / `convert` 阶段把源文件归一化为 `Document → Unit → Segment` 结构，落 `structured/`，
中间产物落 `structured/raw/`。

## 能力自检与路由（开工前先看这里）

先跑 `auto-epublizer preprocess <input>`（新书）拿 `preprocessing/facts.md`——其中已含
源文件嗅探结果（类型/DRM/文字层/扫描件判定/乱码率）、doctor 能力快照与确定性路由提示；
再结合 **agent 自报 multimodal**（能否看图）与 **search**（是否有网络搜索工具，CLI 探测不到）
按此表定方案（写入 `preprocessing/plan.md`）：

| 输入 | 条件 | 路由 |
|---|---|---|
| TXT / MD | — | 直接读（`read_text`） |
| EPUB / DOCX / HTML | `pandoc` ✓ | pandoc → Markdown + 抽媒体 |
| EPUB / DOCX / HTML | `pandoc` ✗ | 请用户先转 PDF/TXT/MD |
| PDF 文字层 | `pymupdf` ✓ | 按页切片抽文字层 |
| PDF 扫描件 | `tesseract` / `ocrmypdf` ✓ | 传统 OCR 优先：扫描 PDF 先重建文字层再入库 |
| PDF 扫描件 | `rapidocr` ✓（`uv sync --extra ocr`） | 离线 OCR（`pdf.ocr: auto`） |
| PDF 扫描件 | 无 OCR，但 multimodal=true | 视觉兜底：你自行渲染难页看图理解（只转需要的页），结果按页写回 `page-NNN.json`（`ocr:true`） |
| PDF 扫描件 | `MINERU_API_KEY` 已配置 | MinerU 外部 API（复杂版面可选） |
| PDF 扫描件 | 以上皆无 | 明确告知无法处理；请用户提供可用 OCR / 手工 OCR 或换源 |

**OCR 路由优先级固定**：传统 OCR（tesseract/ocrmypdf）→ rapidocr → MinerU 外部 API →
询问用户；「视觉兜底」不在 CLI 路由内——它是你的自身能力（multimodal 自报），无多模态
即视为无此能力。facts.md 的「路由提示」给出确定性选择；agent 在 plan.md 记录最终路由
与依据。

`pdf.ocr: off` 可在 config 关闭自动 OCR；`pdf.ocr: <其他值>` 视为强制要求（不可用时报错）。

## 格式路由（doctor 探测通过后）

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
- 页面块支持四种 type：`text` / `image` / `table` / `formula`（保留 bbox）——插图/表格/公式
  的提取与 md 表示见 `docs/pdf-content-spec.md`；对应描述文件落 `raw/inserts/`。

## 中间产物

```text
structured/raw/
├── page-001.json ...   # PDF 逐页切片（文字层/OCR；blocks 含 text/image/table/formula）
├── inserts/            # 插图/表格/公式描述文件（<id>.json 为权威）+ index.jsonl（快照）
└── media/              # pandoc 抽取的图片 + PDF 提取的插图/裁剪图
```

`raw/` 持久化供审查，可由源文件重建。inserts 的 `index.jsonl` 只是 ingest 时的汇总
快照；**读取与审计一律以 `<id>.json` 单文件为准**——agent 补语义（content_desc/latex）
只需编辑对应单文件，见 `references/translation.md`「inserts 补全」。

## 注意事项

- `source/` 原样，绝不改动；源内容身份以 `publication.json.meta.source_sha256` 绑定。
- OCR 引擎懒加载：文字层 PDF 不付模型加载成本；`init` 遇扫描页自动调 RapidOCR。
- 难页视觉兜底是你的能力（multimodal 自报）：可自行渲染难页看图理解，结果按页写回
  `structured/raw/page-NNN.json`（`ocr:true`）。
- 常见错误：`不支持的格式`（换扩展名）、`该 PDF 没有可抽取的文字层`（扫描件，装 OCR extra 或用视觉兜底）。
