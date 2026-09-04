# 工作状态交接（workstate）

> 用途：**会话压缩交接**。本文件记录预处理 v2 三份计划（A/B/C）落地任务的状态。
> **截至 2026-09-04 该任务已全部完成**（S0–S5 全部提交推送），保留供追溯与后续任务参考。
> 权威计划见 `docs/preprocessing-plan-v2.md`；Plan C 规范见 `docs/pdf-content-spec.md`。

## 1. 目标与路线

开发 `auto-epublizer`（Python 三包 monorepo）。当前任务：**把预处理 v2 计划的三份新计划
（A OCR 路由 / B 网络搜索 / C PDF 内容提取）全部落地**。阶段：

- **S0** 写 `docs/pdf-content-spec.md`（Plan C 规范）— ✅ **已完成**
- **S1** doctor 扩探测 + facts 五档路由 + skills 路由表（Plan A/B）— ✅ **已完成**（42eef38）
- **S2** C-P0：书签切章 + 内嵌图提取 + inserts 基座 + 多栏排序 — ✅ **已完成**（a1b7306）
- **S3** C-P1：插图路由 + 表格双路径 + 公式检测标记 — ✅ **已完成**（d84fbcd）
- **S4** C-P2：provenance inserts 审计 + 放行门接入 — ✅ **已完成**（d14e6f4）
- **S5** 文档同步（AGENTS/README/SKILL/workflow/postprocessing-spec/spec 回写）— ✅ **已完成**

**每阶段：回归测试 + ruff + 单阶段一提交**。提交信息用 Conventional Commits；只暂存本阶段文件。

## 2. 已定决策（用户拍板，勿再问）

- OCR 后端优先级固定：**传统 OCR（tesseract/ocrmypdf）→ rapidocr → 视觉 LLM/多模态 → MinerU API → 询问用户**。
- 插图「整页 vs 截取」判据：**版面判据为主 + 文体加权**（agent 在 plan.md 覆盖阈值，CLI 只出常量）。
- 公式 → LaTeX：**仅 agent 手写**（不做 FormulaAgent/LLM 调用）；CLI 只检测 + 标 `type=formula` + 留 `latex:null`。
- 交付节奏：**先 spec 再实现**（spec 已写）。
- 预处理目的 = **能力边界确认**：agent 自身能力 / agent 模型 / OS 环境 / 外部 API 边界 / 待处理文件工作量。
- `.progress.json`：文档诚实化（预留未落盘）；断点 = publication.json 单元级跳过。
- **marker-pdf / MinerU 本地引擎不引入**（重、离线不友好）；MinerU 仅作可选外部 API（`MINERU_API_KEY`）。

## 3. 当前 git 状态（关键！未提交）

```
 M src/auto_epublizer/doctor.py             # S1：新增 ocrmypdf probe + probe_mineru + probe_network + summary 加 search
 M src/auto_epublizer/preprocess/facts.py   # S1：新增 _ocr_routing 五档路由
?? docs/pdf-content-spec.md                 # S0 产物（全新文件）
```

- **207 tests 全绿**（在当前含改动的树跑过）；ruff/format 未跑。
- 这两处改动**尚无回归测试覆盖**，S1 完成前必须补测试。
- 不要 `git stash pop` 之后再 commit——当前改动直接接着做。

## 4. 已完成（S1 代码半程）

### doctor.py（`src/auto_epublizer/doctor.py`）
- `_probe_tool` 新增 `ocrmypdf`。
- 新增 `probe_mineru()`：读 `MINERU_API_KEY` 环境变量（本地只读，无网络）。
- 新增 `probe_network(timeout=5.0)`：`httpx.get` 探测 baidu/github，任一可达判有网；仅在 `--ping` 时调用。
- `collect_capabilities` 加入 `probe_mineru()`；`if ping: caps.append(probe_network())`。
- `capabilities_summary` 增加 `"search": None`（与 multimodal 并列，agent 自报）。

### facts.py（`src/auto_epublizer/preprocess/facts.py`）
- 新增 `_ocr_routing(capabilities) -> list[str]`：五档提示（tesseract/ocrmypdf → rapidocr → llm_vision_model → mineru → 请用户）。
- `_route_suggestions` 的 scanned 分支改调 `_ocr_routing`。
- `render_facts_md` **未改**（还差 search 自报行 + 路由提示呈现，待补）。

## 5. 下一步（S1 剩余 + S2）

### S1 收尾
1. `render_facts_md`：capabilities 快照区补 `search：待 agent 自报（是否有网络搜索工具）` 行。
2. `skills/auto-epublizer/references/ingest.md`：能力自检与路由表改五档（见 §2 决策）。
3. `skills/auto-epublizer/references/preprocessing.md`：新增 `capabilities.md` 产物（agent 自报五维中
   CLI 探测不到的：multimodal/search/模型 ID/上下文/外部 API 工具）+「背景知识补齐」路由小节
   （有搜索→`references/web/`，无→询问用户→`references/user/`）。
4. 测试：
   - `tests/test_doctor.py`：断言新 probe 存在（ocrmypdf/mineru/network）；`search is None`；
     `probe_network` 用 monkeypatch 控 httpx（离线确定）。
   - `tests/test_preprocess.py`：`_ocr_routing` 五档优先级（fake caps dict）。
5. `uv run pytest -q` + `ruff check .` + `ruff format --check .` → **提交 S1**。

### S2（C-P0，改动集中在 ingest）
- `src/auto_epublizer/ingest/pdf_reader.py`：
  - `aggregate_pdf_chapters` 增加 `toc` 参数：`doc.get_toc()`（simple，`[[level,title,page]]`）优先切章，
    level-1 条目为边界；无有效 toc 回落字号启发式（现有逻辑）。边界处理：首个 toc 条目前的页 → frontmatter
    （kind=frontmatter）；末条后 → backmatter。page_range meta。
  - `read_pdf` 传入 `doc.get_toc()`；图片/表格/公式提取接线（见下）。
- 新 `src/auto_epublizer/ingest/inserts.py`：`InsertSource`/`InsertRecord` pydantic（id/type/source{page,bbox,xref,method}/file/markdown/content_desc/latex）
  + `write_inserts(raw_dir, records)` → `raw/inserts/<id>.json` + `index.jsonl`（按 id 排序）+ `read_inserts()`。
- 新 `src/auto_epublizer/ingest/images.py`：常量（`FULL_PAGE_AREA_RATIO=0.70`/`TEXT_COVERAGE_MAX=0.15`/`MIN_IMAGE_SIZE=32`/`MAX_IMAGE_DIM=1800`）；
  内嵌图提取 `page.get_images(full=True)` + `page.get_image_rects(xref)` + `doc.extract_image(xref)` → `raw/media/pNNN-imgKK.<ext>`。
- 新 `src/auto_epublizer/ingest/reading_order.py`：纯函数 `sort_reading_order(blocks)`（见 spec §6）。
- md 表示（spec §2.3）：图 `![<id>](raw/media/<file>)`；表格 md inline；公式 `$$原始文本$$`。
- `page-NNN.json` blocks 扩展 `image`/`table`/`formula` type。

### S3（C-P1）
- 插图路由（整页 get_pixmap vs 内嵌 extract_image vs <32px 忽略）。
- `ingest/tables.py`：`page.find_tables()` 纯文字→md；含图→区域裁剪图。
- 公式检测（符号/字体/独立行三特征）+ 标 `type=formula`。

### S4（C-P2）
- `qa/provenance.py` `audit_provenance`：读 `raw/inserts/index.jsonl`（存在时）审计：
  E_INSERT_MISSING_FILE / E_INSERT_BAD_SOURCE / W_INSERT_NO_DESC / W_INSERT_NO_LATEX；
  `ProvenanceResult` 加 `inserts_total/inserts_missing_files/inserts_no_desc/inserts_no_latex`；
  `prov_ok` 纳入 `inserts_missing_files == 0`（qa/report.py 无需改字段，prov dict 自动进 findings）。
- 图片优化：渲染类控 dpi 使最长边 ≤1800（纯 fitz）；内嵌图保留原始字节（Pillow 留扩展点，**不引依赖**）。

## 6. 关键代码事实（省去重新读源码）

- 架构：`auto_common`（config/llm/workspace）← `auto_translator` ← `auto_epublizer`，依赖方向由
  `tests/test_architecture_boundaries.py` 固定。orchestrator 只装配不直接调领域函数。
- **media 管线**：pandoc 抽媒体到 `structured/raw/media/`；build 的 `collect_media` 解析 md 图片引用
  （前缀剥离 + basename 兜底）→ EPUB 内 `media/`。PDF 图片写 `raw/media/` + md 引用 `raw/media/...` 自动兼容，
  provenance `_img_refs` 也吃同格式。
- `read_pdf(path, raw_dir=None, ocr_backend=None, page_dpi=150)`；`load_document` 里
  `raw_dir = store.structured_dir/"raw"`。OCR 只有 `OcrBackend` Protocol + RapidOcrBackend + FakeOcrBackend。
- `SourceSegment.meta` 是自由 dict（已用 source_page/source_bbox/source_font_size）；segment 的 `source` 文本直接进 md
  （`_render_markdown`：heading→`##`，text→段落）。
- classify_units/clean_unit 会再处理单元 kind/title；aggregate 的 kind 可被覆盖。
- qa report.py 从 provenance dict 映射特定键（coverage/units_missing/media_lost/toc_flat/findings）进 report.json；
  `prov_ok` = coverage≈1 且无缺失单元/媒体/toc 不扁平。新增 E_INSERT_* finding 只进 findings，不改 report schema。

## 7. 环境与验证

- 验证命令：`uv run pytest -q`（基线 207）、`uv run ruff check .`、`uv run ruff format --check .`。
- **LSP 报 pytest/fitz/pydantic/typer/httpx「无法解析」是 venv 未指向的误报**，以 `uv run` 为准；
  `fitz` deprecation warning 已知。**不因 LSP 报错改 import**。
- 用 `uv` 装包（禁 pip）；测试写 `tempfile` fixture，不依赖真实书。
- 测试里构造 PDF 用 fitz（`pdf.new_page()` + `page.insert_text(...)` + `page.insert_image(...)`）；
  造图可直接 `insert_image`（需要一个真实 png bytes，可用 1x1 或小型 png 常量）。

## 8. 已知问题 / 注意

- `render_facts_md` 尚未渲染 `search` 自报行 → S1 补。
- `_ocr_routing` 只对 `scanned` 触发；非扫描 PDF 的 mineru/network 是加分项，当前静默（已留空分支）。
- `aggregate_pdf_chapters` 现有 C9 测试依赖字号/关键词启发式——**加 toc 参数必须向后兼容**（无 toc 时行为不变），
  否则现有 test_ingest 会挂。
- inserts id 命名 `p{page:03d}-{img|tbl|fml}{nn:02d}`；index.jsonl 按 id 排序（确定性）。
- spec §9 的 E_INSERT_BAD_SOURCE 检查 bbox 为 4 个有限数。
