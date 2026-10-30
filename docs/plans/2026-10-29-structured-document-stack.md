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
  - `literal_code`：注册在标准 `backticks` 之前的行内 token 规则，`<code>` 内容**逐字**
    保留（含换行、`*`、`#`、`[]{#id}`）；markdown-it 默认会把代码内换行折成空格，故不交给
    它改写。代码是 token 而不是文本占位符（2026-10-30 复核改法，见文末审查）。
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
- `run_pandoc_ast` + `ast_blocks` 拍平标题/段落/代码块（`Div` 取 `c[1]` 的 blocks）；
  `compare_with_units` 按源序**消费**词序列对账（对 `**强调**` 等标记不敏感，重复段落须
  各消费一次），计数与缺失块写入 `SourceDocument.meta["ast_check"]`，并由
  `write_structured` 落到 `structured/raw/pandoc-ast-check.json`（关闭试点时删除旧报告）。
- 它是**文本覆盖探针**：只回答「AST 里的可见文字是否还在工作区、顺序是否被打乱」，
  不校验标题层级、段落边界或块顺序。
- 工作区仍是 `pandoc -t markdown` 的 Markdown（agent 可编辑），AST 只做核验，不替换、
  不丢行内格式；缺口由 agent 判断是否 `preprocess --force` 或逐块修复。

### 5. 测试与 CI

- `tests/test_markdown_tokens.py`：嵌套强调、引用链接、嵌套列表、带括号图片、代码内注号、
  多行行内代码逐字、自动链接、图注；代码进 alt/图注只贡献文字、私用区字符不与代码碰撞、
  链接地址里的反引号不是代码、出版专用块共享 `env` 解析引用式链接。
- `tests/test_epubcheck_json.py`：位置保留、六类坏报告、空报告 + 退出码、FATAL。
- `tests/test_ocr_structure.py`：坐标换算/段落合并/置信度/来源、纯文本后端退化、
  segment meta、两种引擎结果解析、结构化优先。
- `tests/test_pandoc_ast.py`：合成 AST 拍平/引用、缺失块检出、`Div` 正文、重复段落
  逐次消费、报告落盘与关闭后清理、真实 DOCX `ast_check` 对账且 Markdown 标记保留、
  真实 AST 合法 JSON。
- `tests/test_build.py` / `tests/test_provenance.py`：alt 含行内代码时媒体照常收集、
  行内代码里的图片语法不被收集、成品段落探针按整篇 `env` 解析引用式链接。
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
- GitHub Actions（`.github/workflows/ci.yml`，run 40827116263）绿：固定 pandoc 3.1.3 /
  EPUBCheck 5.2.1 / Java 21 / uv 0.11.32，真实外部工具集成测试实际执行；
  印刷 PDF 端到端测试在 CI 需 CJK 字体（已加入字体安装步骤）。
- RapidOCR 3.10 真实推理在隔离 venv 验证（Python 3.13 + onnxruntime 1.31.1，PP-OCRv6
  模型，返回 `txts/boxes/scores`，结构化读取器正确换算出 PDF 点坐标与段落块）；
  CI 不装 OCR extra，体积/模型下载成本不进入常规流水线。
- 独立复核：干净克隆 `0795d4c` 全量 1009 passed / 3 skipped；手写冒烟脚本 29 项覆盖渲染、
  epubcheck 好/坏包、坏 JSON、OCR 坐标/置信度、AST 对账。复核发现并修复一个真实缺陷：
  混合后端下**无坐标 OCR 行会被丢弃**——现按原顺序保留为独立无坐标块（不借用相邻坐标），
  回归见 `test_coordinate_less_line_keeps_text_between_located_blocks`；修复后全量
  1010 passed / 3 skipped，CLI 端到端（init→import→build→qa）`released=True`、
  独立 epubcheck 0 error/0 warning、`report.epubcheck.diagnostics` 为空数组。
- 已知边界：扫描件段落边界仍建议 agent 逐页复核；`ast_check` 只报计数与缺失块（文本
  覆盖探针，不校验结构），不自动修复；Docling 仍为未验证候选。

## 证据与决策（立项时）

- 前轮已实测四组手写渲染缺陷；环境中 markdown-it-py 是 Rich 的间接依赖。
- 最新远端较原工作树多 29 个提交，含新审校门和 PDF 导出；本任务基于最新远端。

## 审查与修复（2026-10-30）

审查对象：`96c73d1..951b849` 的本轮升级（markdown-it 渲染、EPUBCheck JSON、OCR 结构化、
Pandoc AST 试点、性质测试与 CI）。方式：先按 `ocr delegate preview` 圈定 16 个可审文件
（其余 26 个测试/文档文件按需核对断言），逐文件读实现 → 写最小反例 → 先失败再修复；
最后用真实 CLI 端到端复核。共确认 7 类缺陷，全部有失败回归测试与修复。

### 缺陷与修复

1. **代码占位符污染图片 alt / 图注，并与正文私用区字符碰撞**（`build/html.py`）。
   `_protect_code` 把代码换成 `U+E000<序号>U+E000`，但 alt/figcaption 经
   `renderInlineAsText` 先把占位符当文字取出，渲染后再把 `<code>` 塞回属性，得到
   `alt="<code>x &lt; y</code>"`（XML 非法）；正文出现 `U+E000` 时占位符正则命中正文，
   `codes[int(...)]` 直接 `IndexError`；链接地址里的反引号也先被抽成代码，href 变成
   `%EE%80%80…`。回归：`test_code_in_image_alt_is_text_not_markup`、
   `test_private_use_text_cannot_collide_with_code`、
   `test_backticks_in_link_destination_are_not_code`。修复：改注册 markdown-it 行内规则
   `literal_code`（`before("backticks")`），代码是 token 而不是文本占位符；alt/图注走
   `_inline_text` 只取文字；删除 `_CODE_SENTINEL`/`_protect_code`/`_restore_code`。

2. **出版专用块不共享 `env`，引用式链接失效**（`build/html.py`）。
   标题、诗行、引用、表格、有序列表分支各自调用 `_inline()`，未传 `env`（默认空字典），
   文档级 `[标签][ref]` 定义不可见，原样漏进成品。回归：四参数化用例
   `test_reference_links_resolve_in_publication_blocks`。修复：`_inline(text, env)` 贯穿
   全部分支；`markdown_to_xhtml` 显式接受预置 `env`。

3. **alt 含行内代码时媒体被静默漏收**（`build/__init__.py`）。
   `![图注 `a & b`](media/pic.png)` 不进 EPUB，`dropped` 也为空，只在 qa 报
   `E_IMG_SRC` / `E_MEDIA_EPUB_LOST`。根因是 `collect_media` 先按 `inline_code_chunks`
   切文本再匹配图片，alt 里的代码把 `![` 与 `](…)` 切到两个片段。回归：
   `test_collect_media_image_with_code_in_alt`。修复：文本块内先整体匹配媒体引用，只跳过
   起点落在行内代码跨度内的匹配。

4. **成品段落探针与 build 口径不一致，误报段落丢失**（`qa/provenance.py`）。
   `_probe_missing` 逐段渲染 `markdown_to_xhtml(block)`，没有整篇 `env`，`[标签][ref]`
   在探针里留成字面量，成品里已是链接文字 → `E_EPUB_PARA_LOST` 误报（CLI 复核时
   `epub_coverage=0.333`）。回归：`test_probe_renders_reference_links_with_document_env`。
   修复：整篇 md 预解析出 `env` 再逐段渲染；同时剔除 `^` 前缀的链接定义——旧记法脚注
   定义 `[^7]: …` 在 CommonMark 里也是合法链接定义，不能把 `[^7]` 解成普通链接
   （既有 `test_provenance_legacy_note_numbers_are_not_labels` 守住该回归）。

5. **nav/`<title>` 泄漏 `[ref]`**（`build/html.py`）。`plain_label` 只剥内联链接语法，
   标题里的引用式链接把 `[ref]` 带进目录与页面标题。回归：
   `test_reference_link_in_heading_keeps_only_visible_label`。修复：先按
   `_LABEL_REF_LINK` 剥掉引用标签。

6. **Pandoc AST 对账两处漏检 + 报告不落盘**（`ingest/pandoc_ast.py`、
   `structure/rebuild.py`）。`Div` 只遍历 `c` 的属性表，正文整段隐身；重复段落用
   `it = iter(haystack)` 子序列判定，只要出现过一次就通过；报告只写
   `SourceDocument.meta`，CLI 的 `init` 路径读完即丢。回归：
   `test_div_contents_are_checked`、`test_repeated_paragraph_requires_each_occurrence`、
   `test_ast_report_survives_workspace_ingest_and_is_removed_when_disabled`。修复：
   `Div` 取 `c[1]`；`_match_end` 按源序消费词序列；`write_structured` 原子写
   `structured/raw/pandoc-ast-check.json`，关闭试点重建时删除旧报告。

7. **无坐标 OCR 丢失行数/来源/置信度**（`ingest/pdf_reader.py`）。纯无坐标路径返回
   `{type,bbox,text,ocr}`，与「不虚构几何、但保留证据」的契约不符。回归：
   `test_unlocated_structured_lines_keep_confidence_and_source`（既有
   `test_plain_text_backend_keeps_previous_single_block` 期望同步更新）。修复：单块输出
   同样带 `ocr_lines`/`ocr_source` 与置信度均值（无置信度时不写该字段）。

8. **文档口径纠正**：原实施记录称 AST 能发现「正文被误判成标题」，实际它只是**文本
   覆盖探针**（按源序消费可见词序列，不校验标题层级、段落边界、块顺序）。已同步修正
   本文件、模块 docstring、`docs/configuration*.md` 与 `config.example.yaml`，并补上
   结果文件位置。

### 验证（2026-10-30）

- 全量：`AUTO_EPUBLIZER_REQUIRE_EXTERNAL=1 uv run pytest -q` → **1026 passed / 1 skipped**
  （真实 pandoc 与 EPUBCheck 集成测试实际执行）。
- 静态：`ruff check`、`ruff format --check`、`scripts/i18n.py --check` 全部通过。
- CLI 端到端（新工作区，`/tmp/opencode/review-stack-e2e.py`）：
  `init → 手写 translation+align → import --reviewed → build → qa`，2 个单元全部
  `reviewed`（无「跳过」），`released=True`、`g4_epubcheck_errors=0`、
  `epubcheck.returncode=0`、`diagnostics=[]`；成品断言 `<code>x &lt; y</code>`、
  `alt="图注含代码 a &amp; b"`，标题/表格/有序列表/引用/诗行里的引用式链接均为 `<a>`。
- AST 报告 CLI 复核：`pandoc.ast_check: true` 的 `init` 生成
  `structured/raw/pandoc-ast-check.json`（headings=2 / paragraphs=2 / missing=0）；
  同工作区用关闭配置 `preprocess --force` 重建后该文件被删除。

### 本次未覆盖

- AST 探针不校验结构（见缺陷 8），「正文被误判成标题」只要文字仍在就不会报出。
- 扫描件段落边界仍需 agent 逐页复核；RapidOCR 真实推理不在 CI（体积/模型下载成本）。
- 测试与文档逐行内容不在本次审查清单内，只核对其断言是否覆盖既有契约；CI workflow
  只核对固定版本与「必需工具缺失即失败」的门。
- 契约未变：单 LLM、可编辑 Markdown 工作区、注释/媒体/Pandoc 扩展/XHTML-EPUB 保真、
  确定性 ZIP。
