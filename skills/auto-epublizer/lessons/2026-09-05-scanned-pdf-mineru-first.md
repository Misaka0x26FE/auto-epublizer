# 扫描件 PDF：MinerU 最优先，传统 OCR 逐页阅读兜底

> 日期：2026-09-05　来源：MinerU API 真机探测（/file-urls/batch 全流程实测）。
> 状态：MinerU 后端已落地（`ingest/mineru.py`）；本文留存路由决策依据与兜底工作流。

## 触发场景

输入是**扫描件 PDF**（嗅探 `scanned=true`：抽样页空文字层比例 ≥ 60%）。两条路径的
能力边界（2026-09 实测定案）：

| 路径 | 字符 | 换行/段落 | 插图 | 表格/公式 |
|---|---|---|---|---|
| MinerU 外部 API（最优先） | ✓ | ✓（实测 `## 标题`/空行分段） | ✓（实测整页图版也提取为 `chart` 类型） | ✓（latex/html） |
| 传统 OCR（tesseract/ocrmypdf/rapidocr） | ✓ | **✗** | **✗** | ✗ |
| 传统 OCR + agent 逐页阅读（次选） | ✓ | ✓（agent 重断段） | ✓（agent 看图找+裁） | 部分（agent 看图） |

**决策顺序**：`MINERU_API_KEY` 已配置 → 直接 MinerU；未配置 → **先询问用户是否有
key**（这是扫描件质量最优路径）；确认无 key 才退传统 OCR + 逐页阅读兜底。

## MinerU 路径（CLI 自动，agent 无需干预）

`pdf.backend=auto` + key 存在 + 扫描件 → init 自动走 MinerU；产物已全量落盘：

- `structured/raw/mineru/content_list.json` + `full.md`：审计对账 ground truth；
- `structured/raw/media/`：插图（含整页图版）；`raw/inserts/`：溯源记录
  （`source.method="mineru"`，page/bbox 齐全）；
- 正文按 MinerU 标题层级切章（书名页=单次最小层级，自动跳过）。

**实测坑（解析器已处理，审计时留意）**：紧随插图的正文行会被 MinerU 归为
`image_footnote`——CLI 已把 caption/footnote 文本吐回正文段，但翻译时若发现
「插图后紧跟的句子像图注」，先查 `raw/mineru/content_list.json` 原始归属再判断。

## 传统 OCR + agent 逐页阅读兜底（次选工作流）

1. **读 OCR 产物**：`raw/page-NNN.json` 的 `ocr:true` 文本块——OCR 文本无段落信息，
   按语义重断段落；
2. **看页图找插图**：`raw/pages/pNNN.png`（init 持久化的扫描页渲染图）逐页看图；
3. **提取插图**：含插图的页用 shell（pymupdf）按 bbox 裁图 → `raw/media/` +
   `raw/inserts/<id>.json`（补 content_desc）；
4. **改写 structured**：重断段落的正文 + `![<id>](raw/media/…)` 引用写回
   `structured/<unit>.md`，逐页对齐不丢原文。

## 复现 / 验证

```python
# 离线回归：tests/test_mineru.py（httpx.MockTransport 注入，零网络）
uv run pytest -q tests/test_mineru.py
# 真机探测脚本（含 key 才可跑）：/tmp/opencode/mineru-probe/probe.py 同型流程
```

## 关联

- 路由决策表：`references/ingest.md`；本计划：`docs/plans/`（扫描件处理方式更新）。
- MinerU API 契约注释：`src/auto_epublizer/ingest/mineru.py` 模块 docstring。
