# 计划：扫描件 PDF 处理方式更新（MinerU 最优先）

> 状态：**已完成**（2026-09-05）。MinerU 后端落地（`ingest/mineru.py`）+ 路由优先级
> 反转 + 扫描页渲染图持久化 + skills/lessons 文档同步。

## 背景与决策

传统 OCR（tesseract/ocrmypdf/rapidocr）只能保证**字符**识别，无法识别**换行和插图**。
决策（用户拍板）：

1. **最优先方案 = MinerU 外部 API**（版面分析：换行/段落/插图/表格/公式全能识别）——
   key 未配置时 agent 必须先**询问用户**是否有 `MINERU_API_KEY`；
2. **次选方案 = 传统 OCR + agent 逐页阅读兜底**：agent 逐页阅读 OCR 产物
   （`raw/page-NNN.json`）补换行/段落，期间看 `raw/pages/pNNN.png` 页图找插图并提取。

MinerU 是外部解析 API（非 LLM），不违反唯一 LLM 原则
（`docs/plans/2026-09-04-remove-internal-llm.md` 已定「MinerU 保留」）；
默认 `model_version=pipeline`（确定性、零幻觉），`vlm` 仅显式配置可用。

## 实现

### API 契约（2026-09 真机探测定案，探测脚本 /tmp/opencode/mineru-probe）

`POST /file-urls/batch`（Bearer token，申请预签名 URL）→ `PUT` 原始字节（无
Content-Type）→ 轮询 `GET /extract-results/batch/{id}`（state: pending/running/done/
failed/converting）→ 下载 `full_zip_url`（full.md + `*_content_list.json` + images/）。

content_list（v1）关键 schema 与实测坑：

- 标题 = `type:text` + `text_level`（书名页常为单次最小层级，切章时自动跳过）；
- **紧随插图的正文行会被归为 `image_footnote`**——解析器必须把 caption/footnote
  文本吐回正文段，否则丢内容（实测已复现并处理）；
- 整页图版归类为 `type:chart`，与 `image` 同走图片路由；`page_idx` 为 0-based。

### 代码变更

- `ingest/mineru.py`（新）：`MineruClient`（transport 可注入，测试离线）+
  `read_mineru`（content_list → SourceDocument；媒体落 `raw/media/`、溯源记录
  `method="mineru"`、审计产物落 `raw/mineru/`）+ `aggregate_mineru_chapters`
  （标题层级切章，书名页前置内容归 frontmatter）。
- `orchestrator.py::_mineru_client_if_preferred`：`backend=mineru` 强制（缺 key 报错）、
  `pymupdf` 禁用、`auto`（默认）= 扫描件（嗅探）且 key 存在 → MinerU。
- `ingest/load.py`：PDF 分支 MinerU 优先于 pymupdf+OCR。
- `ingest/pdf_reader.py`：扫描页渲染图持久化 `raw/pages/pNNN.png`（原 tmp 用完即删）。
- `config.py::PDFConfig`：新增 `mineru_model`（默认 pipeline）/ `mineru_language`
  （默认 ch）；`mineru_effort` 标注未接线（v4 API 无此参数）。
- `doctor.py::probe_mineru` + `preprocess/facts.py::_ocr_routing`：优先级反转——
  MinerU 首选；无 key 时第一提示「询问用户是否有 MinerU API key」。

### 测试（全离线）

`tests/test_mineru.py`（13 个）：客户端四段流程（MockTransport 注入，断言 Bearer/
无 Content-Type 上传）、failed/超时/API 错误中文报错、content_list 映射
（footnote 吐回/表格 html 入 extra/缺图不悬空/header 剔除）、切章规则（书名页/
frontmatter/深层标题内联）、编排路由矩阵（强制/禁用/auto×扫描/缺 key 报错）、
e2e（fake client 走完 init → structured/units/raw 落盘断言）。
`test_preprocess.py` 路由断言按新优先级重写；`test_ingest.py` 增页图持久化回归。

## 验收

- `uv run pytest -q` 全绿（226 passed）+ ruff check/format 通过；
- 架构边界测试无新增禁用符号（MinerU 端点不含 LLM 调用符号）；
- skills（ingest/preprocessing）+ lessons（scanned-pdf-mineru-first）+
  docs/configuration + AGENTS.md 同步更新。
