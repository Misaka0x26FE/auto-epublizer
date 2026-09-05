# Ingest（文件解析）

`init` / `convert` 阶段把源文件归一化为 `Document → Unit → Segment` 结构，落 `structured/`，
中间产物落 `structured/raw/`。

## 能力自检与路由（开工前先看这里）

先跑 `auto-epublizer preprocess <input>`（新书）拿 `preprocessing/facts.md`——其中已含
源文件嗅探结果（类型/DRM/文字层/扫描件判定/乱码率）、doctor 能力快照与确定性路由提示；
再结合 **agent 自报 multimodal**（能否看图）与 **search**（是否有网络搜索工具，CLI 探测不到）
按此表定方案（写入 `preprocessing/plan.md`）：

**扫描件 PDF 路由（2026-09 优先级更新：MinerU 最优先）**——传统 OCR 只能识别字符，
**无法识别换行和插图**；MinerU 是版面分析服务，换行/段落/插图/表格/公式全能识别：

| 顺序 | 输入 | 条件 | 路由 |
|---|---|---|---|
| ① 最优先 | PDF 扫描件 | `MINERU_API_KEY` 已配置 | **MinerU 外部 API**（`pdf.backend=auto` 时 init 自动走；强制用 `pdf.backend: mineru`）。版面/换行/插图/表格/公式全部由 MinerU 识别 |
| ① 最优先 | PDF 扫描件 | key 未配置 | **先询问用户是否有 MinerU API key**（facts 路由提示含此指引）——这是扫描件质量最优路径，值得多问一句 |
| ② 次选 | PDF 扫描件 | 无 key，`tesseract`/`ocrmypdf` ✓ | 传统 OCR 重建文字层再入库 + **agent 逐页阅读兜底**（见下方工作流） |
| ② 次选 | PDF 扫描件 | 无 key，`rapidocr` ✓（`uv sync --extra ocr`） | 离线 OCR（`pdf.ocr: auto`，init 自动）+ **agent 逐页阅读兜底**（见下方工作流） |
| 兜底 | PDF 扫描件 | 以上皆无 | 明确告知无法处理；请用户提供 MinerU key / 其他 OCR / 手工 OCR 或换源 |

| 输入 | 条件 | 路由 |
|---|---|---|
| TXT / MD | — | 直接读（`read_text`） |
| EPUB / DOCX / HTML | `pandoc` ✓ | pandoc → Markdown + 抽媒体 |
| EPUB / DOCX / HTML | `pandoc` ✗ | 请用户先转 PDF/TXT/MD |
| PDF 文字层 | `pymupdf` ✓ | 按页切片抽文字层（离线、零成本；auto 模式下即使有 MinerU key 也走此路径） |

**OCR 路由优先级固定**：**MinerU 外部 API（询问用户拿 key）→ 传统 OCR/rapidocr
+ agent 逐页阅读兜底 → 询问用户**。facts.md 的「路由提示」给出确定性选择；
agent 在 plan.md 记录最终路由与依据（含「是否已询问用户 MinerU key」）。

`pdf.backend: mineru` 强制 MinerU（无 key 明确报错）；`pdf.backend: pymupdf` 禁用；
`auto`（默认）= 扫描件且 key 存在 → MinerU，文字层 PDF → pymupdf。
`pdf.ocr: off` 可关闭自动 OCR；`pdf.ocr: <其他值>` 视为强制要求（不可用时报错）。

## 传统 OCR 的 agent 逐页阅读工作流（次选方案）

传统 OCR（tesseract/ocrmypdf/rapidocr）只保证**字符**识别；换行（段落边界）与插图
需要 agent 逐页阅读补齐：

1. **读 OCR 产物**：`structured/raw/page-NNN.json` 每页的 `ocr:true` 文本块——OCR 文本
   无段落信息（常连成整页一串），你需要按语义重断段落/换行；
2. **看页图找插图**：init 已把扫描页渲染图持久化到 `structured/raw/pages/pNNN.png`——
   逐页看图（multimodal 自报），找出插图位置；
3. **提取插图**：对含插图的页，用 shell（pymupdf）按 bbox 裁图落
   `structured/raw/media/`，并补 inserts 记录（`raw/inserts/<id>.json`，含
   content_desc）；
4. **改写 structured**：把重断段落后的正文 + `![<id>](raw/media/…)` 插图引用写回
   `structured/<unit>.md`（按页对齐，不要丢 OCR 原文语义）。

> 逐页阅读是 token 密集型工作：先用 facts 的规模估算（页数/字符数）评估工作量，
> 写入 plan.md；页数很多且无 MinerU key 时，优先再次向用户要 key。

## 格式路由（doctor 探测通过后）

| 格式 | 处理 |
|---|---|
| `.txt` `.md` `.markdown` | 直接读文本，识别章节标题、按空行切段 |
| `.html` `.htm` `.xhtml` `.docx` `.epub` | 走 pandoc → Markdown 纯文本 + `--extract-media` 抽媒体 |
| `.pdf`（有文字层） | pymupdf 按页切片抽文字层，逐页写 `structured/raw/page-NNN.json` |
| `.pdf`（扫描件，MinerU） | MinerU API 整本解析：`raw/media/` 插图 + `raw/mineru/`（content_list.json + full.md 审计产物）+ `raw/inserts/` 记录；正文按 MinerU 标题层级切章 |
| `.pdf`（扫描件，无 key） | OCR 兜底：逐页渲染为图片 → OCR → 作为该页文本块（`ocr:true`）；渲染页图持久化 `raw/pages/pNNN.png` |

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
├── pages/              # 扫描页渲染图 pNNN.png（传统 OCR 路径；agent 逐页阅读找插图的素材）
├── mineru/             # MinerU 路径：content_list.json + full.md（审计对账 ground truth）
├── inserts/            # 插图/表格/公式描述文件（<id>.json 为权威）+ index.jsonl（快照）
└── media/              # pandoc 抽取的图片 + PDF 提取的插图/裁剪图 + MinerU 插图
```

`raw/` 持久化供审查，可由源文件重建。inserts 的 `index.jsonl` 只是 ingest 时的汇总
快照；**读取与审计一律以 `<id>.json` 单文件为准**——agent 补语义（content_desc/latex）
只需编辑对应单文件，见 `references/translation.md`「inserts 补全」。

## 注意事项

- `source/` 原样，绝不改动；源内容身份以 `publication.json.meta.source_sha256` 绑定。
- MinerU 是**外部解析 API（非 LLM）**：整本上传（≤200MB/200 页）、异步轮询，
  每天有免费高优先级页数额度；网络失败会以中文错误明确报出。
- OCR 引擎懒加载：文字层 PDF 不付模型加载成本；`init` 遇扫描页自动调 RapidOCR。
- 难页视觉兜底是你的能力（multimodal 自报）：可自行渲染难页看图理解，结果按页写回
  `structured/raw/page-NNN.json`（`ocr:true`）。
- 常见错误：`不支持的格式`（换扩展名）、`该 PDF 没有可抽取的文字层`（扫描件，
  装 OCR extra / 配 MinerU key / 用逐页阅读兜底）、`未配置 MINERU_API_KEY`（强制
  mineru 后端但缺 key——询问用户）。
