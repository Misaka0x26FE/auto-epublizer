# 结构化文档技术栈升级

状态：已完成（`ad1461f`，已推送 GitHub/Gitee `main`）；基线 `96c73d1`。

## 目标与边界

按技术栈评估推进：Markdown token 解析、EPUBCheck JSON、OCR 坐标/置信度、
Pandoc AST 导入试点、性质测试和固定外部工具 CI。保留单 LLM、工作区 Markdown、
来源证据、注释登记与确定性 EPUB 契约。原工作树的两项文档改动不纳入提交。

## 实施顺序

1. 先以四个真实最小反例固定 Markdown 缺陷，再用 markdown-it-py 替代通用语法；
   保留代码字面内容、Pandoc raw/属性、诗行、原注号及跨文件注释。
2. EPUBCheck JSON 严格读取，损坏报告和进程失败不得放行；真实 Java 集成验证。
3. OCR 返回结构化文本行，像素坐标转换到 PDF 页面坐标并保存置信度；
   新版 RapidOCR 只有对照证据支持才替换默认后端。
4. 复杂 DOCX/HTML 试点 Pandoc JSON AST，明确 opt-in 边界及不变的下游工作区。
5. Hypothesis 可重复生成边界样本；CI 固定工具版本并禁止必需集成测试静默跳过。
6. 同步中英文技能路由与阶段文档，全套测试、Ruff、i18n 后原子提交、推送核对。

## 验收

- 嵌套强调、引用链接、嵌套列表、带括号图片路径正确；既有媒体、代码、注释、
  nav、QA 和确定性测试不降低要求。
- EPUBCheck 成功/错误/损坏 JSON/非零退出均有覆盖。
- OCR 原始证据保留每行坐标、置信度、来源页；无坐标不虚构。
- AST 试点真实运行 Pandoc，结构与内容对账。
- 不引入内部 LLM 或生成式 VLM。Docling 暂为后续实测候选，不作为默认依赖。

## 实施记录

### 1. Markdown token 解析（`build/html.py`）

- 通用行内/块级语法改用 `markdown-it-py` 4.2（`commonmark` + `table`，禁用把正文下划线
  猜成标题的 `lheading`）；出版扩展保留专用处理：
  - `_protect_code`：代码跨度先换占位符，`<code>` 内容**逐字**保留（含换行、`*`、`#`、
    `[]{#id}`）；markdown-it 默认会把代码内换行折成空格，故不交给它改写。
  - `_publication_inline`：`[]{#id}` → 空锚点、`{[]}` 空属性块丢弃；普通 Markdown 交回
    标准规则。
  - 块分流：围栏、raw HTML、管道/网格表、诗行、有序列表、ATX 标题走既有专用分支；
    其余块批量交给 token 渲染器，嵌套列表/引用链接/括号图片路径不再被拍平。
  - 图片段落：单图 + 非空 alt → `figure.imgfig` + `figcaption`；多图段落 → `p.imgp`。
- 移除手写 `_inline_text`、`_BOLD_RE`/`_ITALIC_RE`/`_LINK_RE`/`_IMG_RE` 与重复的图注分支。
- 注文门（`qa/notes_audit.py`）与渲染器同口径：CommonMark 自动链接 `<http://…>` 渲染后
  不保留尖括号，比对侧同步剥离；撇号不再强制数字实体（成品保留字面撇号，审计反转义）。

### 2. EPUBCheck 结构化报告（`qa/epubcheck.py`、`qa/report.py`）

- 命令固定 `--locale en --quiet --json -`（`--quiet` 阻止 Java 进度行污染 stdout）。
- 严格解析 `messages`（ID/severity/message/locations），`checker.nFatal/nError/nWarning`
  与逐条消息取较大值（官方会截断重复消息），诊断明细进 `report.json`
  → `epubcheck.diagnostics`。
- 缺 `messages`、坏 JSON、未知 severity、缺 ID/消息、非法位置、非法计数、非零退出
  → 一律 fail closed（记 error）。

### 3. OCR 结构化（`ingest/ocr.py`、`ingest/pdf_reader.py`）

- `OcrLine(text, bbox, confidence)`；后端可实现 `ocr_lines`（结构化）或仅 `ocr_image`
  （旧约定，退化为单块、无坐标——不虚构几何）。
- `lines_from_engine_result` 同时适配新版 `rapidocr` 3.x（`txts/boxes/scores`）与旧版
  `rapidocr_onnxruntime`（`([box, text, score], elapsed)`）；四点框归一为 `(x0,y0,x1,y1)`，
  置信度限定在 `[0,1]`。
- `_ocr_page` 按行距（行高中位数 × 0.6）与横向重叠合并段落，坐标按 `72/dpi` 换算为
  PDF 页面点；块带 `ocr_confidence`（均值）、`ocr_lines`、`ocr_source`，segment meta
  同步 `ocr_confidence`/`ocr_source`。
- 只重写 `ocr_image` 的自定义后端（测试替身、自有引擎）优先于基类结构化实现，避免被
  静默绕过；页面渲染图仍落 `structured/raw/pages/pNNN.png`。

### 4. Pandoc JSON AST 试点（`ingest/pandoc_ast.py`）

- opt-in：`pandoc.ast_check: true`（默认关闭，多一次 pandoc 进程）。
- `run_pandoc_ast` + `ast_blocks` 拍平标题/段落/代码块；`compare_with_units` 按**词序列
  子序列**对账（对 `**强调**` 等标记不敏感），计数与缺失块写入
  `SourceDocument.meta["ast_check"]`。
- 工作区仍是 `pandoc -t markdown` 的 Markdown（agent 可编辑），AST 只做核验，不替换、
  不丢行内格式；缺口由 agent 判断是否 `preprocess --force` 或逐块修复。

### 5. 测试与 CI

- `tests/test_markdown_tokens.py`：嵌套强调、引用链接、嵌套列表、带括号图片、代码内注号、
  多行行内代码逐字、自动链接、图注。
- `tests/test_epubcheck_json.py`：位置保留、六类坏报告、空报告 + 退出码、FATAL。
- `tests/test_ocr_structure.py`：坐标换算/段落合并/置信度/来源、纯文本后端退化、
  segment meta、两种引擎结果解析、结构化优先。
- `tests/test_pandoc_ast.py`：合成 AST 拍平/引用、缺失块检出、真实 DOCX `ast_check`
  对账且 Markdown 标记保留、真实 AST 合法 JSON。
- `tests/test_markdown_properties.py`：Hypothesis 任意文本渲染良构 + 确定性、代码跨度
  逐字、标题不被吞。
- `.github/workflows/ci.yml`：固定 pandoc 3.1.3、EPUBCheck 5.2.1、Java 21、uv 0.11.32；
  `AUTO_EPUBLIZER_REQUIRE_EXTERNAL=1` 下 `tests/test_external_tools_required.py` 在工具
  缺失时**失败而非 skip**；另跑 ruff、`scripts/i18n.py --check` 与全量 pytest。

### 6. 技术决策与证据

- **采纳 markdown-it-py**：四类手写解析缺陷有先失败测试；通用语法成熟、可扩展自定义
  rule；出版扩展仍由本项目控制，EPUB 契约不变。
- **采纳 EPUBCheck JSON**：官方 5.2.1 实测输出含 `checker` 计数与 `locations`，比文本
  正则更可靠；保留退出码校验。
- **RapidOCR 升级到 3.10（`rapidocr`，onnxruntime 1.31）**：在隔离 venv 实测
  Python 3.13 + onnxruntime 1.31.1 可用，默认模型为 PP-OCRv6（det/rec small），
  返回 `txts/boxes/scores`；旧包 `rapidocr-onnxruntime` 最后发布 2025-01-17，
  `rapidocr` 3.10.0 发布 2026-10-08。故 `[ocr]` extra 改为
  `rapidocr>=3.10,<4` + `onnxruntime>=1.17`，运行时仍兼容旧包。
- **Pandoc AST 仅试点**：AST 输出会丢行内标记，不能作为工作区真相；作为独立对账源
  成本低、能发现整段被吞/误判标题。
- **Docling 不引入**：无本仓库实测证据表明其版面/表格收益超过现有 PyMuPDF + MinerU +
  OCR 路径；保持“有证据再推进”的口径。

## 验证

- 基线（`96c73d1`）：975 passed / 1 skipped。
- 本任务：`uv run pytest -q` → **1009 passed / 3 skipped**（3 skip = 2 个 CI 强制外部工具
  门在本地未开、1 个真实 RapidOCR 用例未装 OCR extra）；`ruff check`、
  `ruff format --check`、`scripts/i18n.py --check` 全部通过。
- 真实外部工具：EPUBCheck 5.2.1（Java 21，`--quiet --json -`）与 Pandoc 3.1.3 的集成
  测试**实际执行**（非 stub）；`AUTO_EPUBLIZER_REQUIRE_EXTERNAL=1` 下工具缺失即失败。
- RapidOCR 3.10 真实推理在隔离 venv 验证（Python 3.13 + onnxruntime 1.31.1，PP-OCRv6
  模型，返回 `txts/boxes/scores`，结构化读取器正确换算出 PDF 点坐标与段落块）；
  CI 不装 OCR extra，体积/模型下载成本不进入常规流水线。
- 已知边界：扫描件段落边界仍建议 agent 逐页复核；`ast_check` 只报计数与缺失块，不自动
  修复；Docling 仍为未验证候选。

## 证据与决策（立项时）

- 前轮已实测四组手写渲染缺陷；环境中 markdown-it-py 是 Rich 的间接依赖。
- 最新远端较原工作树多 29 个提交，含新审校门和 PDF 导出；本任务基于最新远端。
