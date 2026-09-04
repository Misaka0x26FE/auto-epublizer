# PDF 内容提取规范（pdf-content-spec）

> 状态：**已实现**（P0–P2 随本规范同批落地；实现与规范的偏差已回写本文）。
> 本文档定义 PDF 内容提取（ingest 阶段，计划 C）的验收标准、数据契约与实现阶段。
> 战略背景见 `docs/pdf-parsing.md`；本规范是 `docs/plans/preprocessing-plan-v2.md`
> 计划 C 的落点。改动须同步回本规范与 `skills/`。

## 1. 定位与范围

PDF 是坐标定位指令，无语义结构；EPUB 是语义化文档。PDF 内容提取 = **从坐标重建语义结构**，
本规范聚焦六项缺口（对齐 `docs/pdf-parsing.md` §5）：

| 能力 | 现状 | 目标 |
|---|---|---|
| 书签切章 | `sniff_pdf` 已 `get_toc`，`aggregate_pdf_chapters` 未接入 | bookmark TOC 优先切章，字号启发式降级 fallback |
| 内嵌图提取 | 只抽文字层，图片 block 跳过 | `get_images` / `extract_image` → `raw/media/` + md 引用 |
| 多栏阅读顺序 | `get_text("dict")` 内部块序 | 列聚类（x）→ 列内 y → 列间 x，单栏流式 |
| 表格 | 无 | `find_tables`：纯文字 → md 表格；含图/公式 → 区域裁剪成图 |
| 公式 | 无 | 检测（特征）→ 标 `type=formula` + 描述文件；**latex 由 agent 手写** |
| 插入内容溯源 | 仅媒体 basename 对账 | 描述文件 + 原始地址 `{page,bbox,xref,method}` |

**能力分工**：CLI 只做确定性检测/提取/落盘（零 LLM 调用）；内容描述（`content_desc`）、
公式 LaTeX（`latex`）是语义判断，归 agent 补写。**不做公式的 LLM 自动转 LaTeX（FormulaAgent）**。

## 2. 数据契约

### 2.1 inserts 目录

每个识别出的插入内容（图 / 表 / 公式）生成一份描述文件 + 汇总索引：

```text
structured/raw/inserts/
├── p012-img01.json    # 单个插入内容（CLI 骨架 + agent 补语义）
├── p012-tbl01.json
├── p012-fml01.json
└── index.jsonl        # 汇总索引（每行一条，按 id 排序）
```

- id 命名：`p{page:03d}-{img|tbl|fml}{nn:02d}`（页内序号，确定性、稳定）。
- `index.jsonl` 每行一条记录（JSON），供 provenance 审计与审查。
- 目录生命周期同 `structured/raw/`：持久化供审查，可由源文件重建。

### 2.2 描述文件 schema

```jsonc
// p012-img01.json
{
  "id": "p012-img01",
  "type": "image",            // image | table | formula
  "source": {
    "page": 12,               // 源页号（1-based，必填）
    "bbox": [x0, y0, x1, y1], // 页内坐标（图/表/公式区域；整页图=整页 bbox）
    "xref": 34,               // PDF 对象号（内嵌图必填；区域/整页可为 null）
    "method": "embedded"      // embedded | full_page | crop | table | formula
  },
  "file": "media/p012-img01.png",  // 相对 structured/raw/ 的路径；纯文本表格为 null
  "markdown": null,               // 纯文本表格的 md（自包含）；其余为 null
  "content_desc": "",             // agent 补：这个插入内容讲什么（渲染目的/场景）
  "latex": null                   // formula 时 agent 手写 LaTeX；其余为 null
}
```

- `source`（page / bbox / xref / method）即「原始内容地址」，是溯源到源文件的唯一依据。
- CLI 生成确定性字段（id / type / source / file / markdown）；agent 补语义字段
  （content_desc / latex）。
- method 语义：
  - `embedded`：内嵌栅格图，`extract_image` 提取原始字节；
  - `full_page`：整页渲染成图（图版页/整页插图）；
  - `crop`：页内区域裁剪（表格含图/公式渲染图等）；
  - `table`：表格（md 或裁剪图，配合 file 区分）；
  - `formula`：公式（检测标记，latex 待 agent）。

### 2.3 页面块与 md 表示

`page-NNN.json` 的 `blocks[]` 扩展四种 type，保留 bbox：

```jsonc
{ "type": "text",  "bbox": [...], "text": "...", "font_size": 12.0 }
{ "type": "image", "bbox": [...], "file": "media/p012-img01.png", "xref": 34, "method": "embedded" }
{ "type": "table", "bbox": [...], "markdown": "| a | b |\n|---|---|", "file": null }
{ "type": "formula", "bbox": [...], "text": "E = mc2" }
```

结构化 md 中的表示（segment 的 source，按类型）：

| 类型 | md 表示 | 示例 |
|---|---|---|
| 图（embedded/crop/full_page） | 图片引用，alt=insert id | `![p012-img01](raw/media/p012-img01.png)` |
| 表格（纯文字） | markdown 表格 inline | `\| a \| b \|\n\|---|---\|` |
| 表格（含图/公式） | 图片引用（裁剪图） | `![p012-tbl01](raw/media/p012-tbl01.png)` |
| 公式 | `$$原始抽取文本$$`（草稿），latex 在 inserts 记录 | `$$E = mc2$$` |

> `![…](raw/media/…)` 与 pandoc 抽取媒体同一目录、同一解析路径，`collect_media`
> （build）与 `_img_refs`（provenance）自动兼容（前缀剥离 + basename 兜底）。

## 3. 插图路由（版面判据 + 文体加权）

**版面判据（确定性主判据）**：

| 判据 | 判定 | 动作 |
|---|---|---|
| 图 block 占页面积 ≥ 0.70、文字覆盖率 < 0.15、**且页面文字 < 200 字** | 整页插图/图版页 | `page.get_pixmap` 整页渲染 → `media/pNNN-page.png`，method=`full_page` |
| 其余图 block 面积 ≥ 32×32 px | 内嵌插图 | `extract_image` 提取原始字节 → method=`embedded` |
| 面积 < 32×32 px | 装饰（项目符号/分隔线） | 忽略，不产出记录 |

- **字数守卫（实现补充）**：带 OCR 文字层的扫描页字形覆盖率天然 < 0.15、整页扫描背景
  图占比 ≈ 1.0，仅凭面积判据会把每一页误路由为整页图版并丢失正文——故整页路由要求
  页面文字 < 200 字。同因，页面文字 ≥ 200 字时占页 ≥ 0.85 的图判为**扫描背景**直接跳过
  （不提取、不记录）；OCR 域的页（`ocr:true`）不做整页路由/表格/公式检测。
- 一页多图：按阅读顺序排序后页内序号递增；同一 xref 多矩形只提取一次原始字节。
- **文体加权**：阈值是 CLI 常量（见 §7 配置项）；agent 在 `plan.md` 按 `detect_genre`
  提示调整（如小说图版页阈值放松、教材内嵌小图标视为装饰）。CLI 不做文体判断。

## 4. 表格双路径

`page.find_tables()`（pymupdf ≥ 1.23）：

- **纯文字表格**：`table.extract()` 全单元格为文本且无图/公式 block 相交 → markdown 表格
  （首行表头 + 分隔行），`markdown` 字段保存自包含 md；
- **含图/公式表格**：表格 bbox 与 image block 相交（或单元格含公式特征）→ 区域渲染
  `page.get_pixmap(clip=table.bbox)` → `media/pNNN-tblNN.png`，method=`table`（crop 语义）。
- 跨页表格：pymupdf 表格对象按页切分，本规范不跨页合并（后续扩展点，`pdf-parsing.md` §2.1）。

## 5. 公式检测与标记

确定性检测（任一命中即标 `type=formula`）：

1. **符号特征**：文本短（≤200 字）且含 ≥2 个数学符号（`∫∑√∂∓±×÷≠≤≥∞∈∀∃∇·…` 或希腊字母）；
2. **字体特征**：span 字体名含 `Math` / `CMMI` / `CMSY` / `CMEX` / `Symbol` 等数学字体
   （**`CMR` 除外**——它是 TeX 正文默认字体，计入会使纯 TeX 排版的书全篇误判）；
3. **独立行特征**：单独成块的居中短文本（≤120 字、句末无标点），且含 ≥1 个数学符号。

处理：

- 公式块保留原始抽取文本为草稿，md 呈现 `$$原始文本$$`；
- 生成 `type=formula` 描述文件（`latex: null`），agent **手写 LaTeX** 填入 `latex` 字段
  （并同步更新 translation md）；CLI 不调 LLM、不产出 LaTeX 候选。

## 6. 多栏阅读顺序

`ingest/reading_order.py` 纯函数 `sort_reading_order(blocks) -> list[dict]`：

1. 任一 block 无 bbox（OCR 路径）→ 原序返回（OCR 文本本身是顺序的）；
2. 全页均为**宽块**（width ≥ 0.6 × 页宽，如标题）或块间无横向并存 → 单栏，按 y 排序；
3. 否则检测列界：合并窄块 x 区间成列簇，按 x0 排序得列序；
4. 按 y 流式合并：宽块在其 y 位置输出；窄块按其「所属列（x 中心）→ 列内 y」输出
   （行带内跨列按列序输出，实现「行内左→右、行间上→下」）。

## 7. 配置与常量

- 本规范实现不新增 config 段；阈值作为 `ingest/images.py` 模块常量
  （`FULL_PAGE_AREA_RATIO=0.70`、`TEXT_COVERAGE_MAX=0.15`、`MIN_IMAGE_SIZE=32`、
  `MAX_IMAGE_DIM=1800`、`RENDER_DPI=150`、`BACKGROUND_AREA_RATIO=0.85`）。
- agent 在 `plan.md` 覆盖阈值 = 直接以自身能力处理（不传 CLI 参数）。

## 8. 图片优化

- 渲染类（full_page / crop）：控制渲染 dpi/缩放使**最长边 ≤ 1800px**（`MAX_IMAGE_DIM`），
  纯 fitz、确定性；
- 内嵌图：保留 `extract_image` 原始字节（PNG 带 alpha 保留——EPUB 支持），不重压缩；
  Pillow 重采样/JPEG 量化留作扩展点（需新依赖，本轮不做）。

## 9. provenance 审计扩展

`qa/provenance.py::audit_provenance` 增加 inserts 审计（仅当 `raw/inserts/index.jsonl` 存在）：

| 代码 | 级别 | 条件 |
|---|---|---|
| E_INSERT_MISSING_FILE | error | record.file 非空但文件不存在于 `raw/<file>` |
| E_INSERT_BAD_SOURCE | error | source.page 非正整数 或 bbox 非 4 个有限数 |
| W_INSERT_NO_DESC | warning | `content_desc` 为空（agent 未补语义描述） |
| W_INSERT_NO_LATEX | warning | type=formula 且 `latex` 为空（agent 未手写 LaTeX） |

`ProvenanceResult` 新增字段：`inserts_total`、`inserts_missing_files`、`inserts_no_desc`、
`inserts_no_latex`。放行条件 `prov_ok` 纳入 `inserts_missing_files == 0`
（溯源完整 = 每个插入内容可回原始地址且文件在）；`report.json` 暴露
`inserts_missing_files` 字段，W 级发现经 `provenance_findings` 透出。

## 10. 分阶段实现（已全部完成）

| 阶段 | 内容 | 模块 |
|---|---|---|
| P0 ✅ | 书签切章 + 内嵌图提取 + inserts 基座 + 多栏排序 | `pdf_reader.py`、`images.py`、`inserts.py`、`reading_order.py` |
| P1 ✅ | 插图路由（整页/嵌入）+ 表格双路径 + 公式检测标记 | `images.py`、`tables.py`、`formula.py`、`inserts.py` |
| P2 ✅ | provenance 审计扩展 + 图片优化 | `qa/provenance.py`、`qa/report.py`、`images.py` |

## 11. 测试计划

- `tests/test_inserts.py`：描述文件 schema / id 命名 / index.jsonl 落盘与读取。
- `tests/test_reading_order.py`：单栏按 y；双栏（左列 top→bottom → 右列）；宽块标题穿插；
  OCR 无 bbox 原序。
- `tests/test_ingest.py`（扩展）：带书签 TOC 的 PDF 按 TOC 切章、无 TOC 字号降级；
  内嵌图提取落盘 `raw/media/` + md 引用；页序含图时阅读顺序正确。
- `tests/test_tables.py`：纯文字表格 → md；含图表格 → 裁剪图 + record。
- `tests/test_formula.py`：符号/字体/独立行三路检测；md 呈现 `$$…$$`；record.latex 为 null。
- `tests/test_provenance.py`（扩展）：inserts 审计各代码；`prov_ok` 纳入文件缺失。
- 全量 `uv run pytest -q`（基线 207）+ `ruff check .` + `ruff format --check .`。

## 12. 本轮不做

- 跨页表格合并、脚注/尾注专项（`pdf-parsing.md` §2.2 仍为扩展点）、竖排/繁体阅读顺序
- 公式 LLM 自动转 LaTeX（FormulaAgent）
- 内嵌图 Pillow 重采样/JPEG 量化（扩展点）
- marker-pdf / MinerU 本地引擎默认后端（可选外部 API，`plans/preprocessing-plan-v2` §3.4）
