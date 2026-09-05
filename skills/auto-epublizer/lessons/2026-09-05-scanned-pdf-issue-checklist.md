# 扫描件 PDF 全流程问题清单（豆包 JS 权威指南 15 问题实录）

> 日期：2026-09-05　来源：豆包云端 agent 实测《JavaScript 权威指南》第 6 版
> 扫描件（1018 页，中文版）→ EPUB 全程，15 个问题的根因与处置。
> 状态：经验留存；其中**主仓库缺口已逐条核实**（下述 ✅/❌）。

## 触发场景

扫描件 PDF（尤其代码/技术书）用传统 OCR 与 MinerU 两条路走完的完整问题集。
本清单是「同一任务」的两份 lessons 的补充：`scanned-pdf-operations.md`
（方案选择/分批/拆分）与 `agent-translation-workflow.md`（翻译工作流）。

## 问题分类分析

### A 类：真实主仓库缺口（已核实，可合入修复）

| # | 问题 | 主仓库现状（2026-09-05 核实） |
|---|---|---|
| 7 | `markdown_to_xhtml` 只支持行内反引号，不支持 ``` 围栏代码块 | ❌ `html.py` 仅 `_CODE_RE`（行内）；围栏代码会整块进 `<p>` |
| 8 | `_inline` 不支持 `\[` 转义（先链接后转义，转义无效） | ❌ 无转义处理 |
| 11 | 链接正则 `\[([^\]]+)\]\(([^)]+)\)` 不校验 URL，`[9](1个数字元素)` 误判为链接 → epubcheck RSC-007 | ❌ `_LINK_RE` 匹配任意 `[x](y)` |
| 9 | 代码块占位符用 `\x00` → XML 非法字符 FATAL | ⚠️ 主仓库**尚无**代码块占位符（同上）；将来实现围栏支持时**禁止用控制字符作占位符** |
| 12 | 手工建 publication.json 时 units.status 设 "built" → build 跳过 | ✅ 是使用陷阱，非代码 bug；状态机由 CLI 管，手工建工作区必须 `pending` |
| 13 | 手工建 publication.json 时 units.meta 缺 `rel_path`/`region`/`level` → build 找不到源 | ✅ 使用陷阱；应让 CLI `init` 生成而非手写 |

> 封面（豆包报告#2 说「不支持」）：**主仓库现已支持** `cover_media` +
> `<meta name="cover">` + spine `linear="no"`（cover 单元自动识别）。豆包当时
> 是旧仓库状态 + 扫描件整页图难自动判定封面，手动注入的 spine/playOrder
> 修补（报告#14/#15）在新仓库不再需要。

### B 类：MinerU/OCR 方案性教训（与前两份 lessons 一致，此处聚焦新细节）

- **#1 换行未处理**：OCR 逐块落盘时每行一个文本块 → 每行独立 `<p>`。传统 OCR
  必然要段落合并（v1 无效 / v2 合并过度 / v3 保守阈值，反复调）——**直接换 MinerU**。
- **#3 单单元构建丢 nav**：整本 markdown 作单单元 → nav 只有 1 项。必须按章拆单元。
- **#4 标题层级不一致**：MinerU 输出同一本书 `#`/`##` 混用（第1章 `#`、第2章 `##`、
  第6章 `## 第6章`）；`build` 以单元 `title` 生成目录、structured md 首行 `#` 为标题。
  → 统一每章首行为 `# 第X章 标题`。
- **#5/#6 手动拆分**：第1章标题页是整页大图、无"第1章"前缀 → 目录页码定位失败；
  拆分时写入路径错位覆盖原 ch01。→ 拆章**先写临时文件再从后往前重命名**，
  且标题判定归 agent 手动（见 `scanned-pdf-operations.md` §3）。
- **#10 代码块前后无空行**：占位符与文本同 block 无法被 `re.match` 识别 →
  markdown 清理必须保证代码块前后有空行。

### C 类：epubcheck 错误码 → 根因对照（调试速查）

| epubcheck 错误 | 通常根因 | 处置 |
|---|---|---|
| FATAL "invalid XML character (Unicode: 0x0)" | 占位符/内容含控制字符 | 清理空字符；占位符用可打印串 |
| RSC-007 "Referenced resource … could not be found" | 方括号被误解析为链接；资源路径错 | 链接正则校验 URL；核对 href |
| "Element type spine must be followed by attribute" | XML 注入时标签拼接错 | 只改标签内容不改结构 |
| "playOrder value not 1 / gaps" | 手动插封面后未重排 NCX | 重新连续编号 |

## 处置清单（合入主仓库时的修复建议）

1. **围栏代码块**：`html.py` block 级预处理——``` 块提取 → `<pre><code class="language-xxx">`；
   占位符用可打印标记（如 `__AUTOEPUBLIZERCODEBLOCK__`），**禁用控制字符**。
2. **`_inline` 转义顺序**：先处理 `\[`/`\]` 转义再链接匹配，或链接正则先排除转义。
3. **`_LINK_RE` URL 校验**：仅 http/https/#/mailto 等合法协议才当链接，否则按纯文本
   （`[9](1个数字元素)` 不是链接）。参考 `_DANGEROUS_URL` 的写法。

> 修复后须补回归：围栏代码块渲染、`\[` 转义不产生链接、`[x](非URL)` 不生成 `<a>`。

## 复现 / 验证

```bash
# 当前主仓库：`[9](1个数字元素)` 会被渲染成 <a>（RSC-007 源头）
uv run python -c "from auto_epublizer.build.html import _inline; print(_inline('[9](1个数字元素)'))"
# 围栏代码块当前会原样进 <p>：
uv run python -c "from auto_epublizer.build.html import render_document; print('```' in render_document('T','```js\nlet a=1\n```', lang='zh-CN'))"
```

## 关联

- 方案选择/拆分/分批：`2026-09-05-scanned-pdf-operations.md`
- 翻译工作流：`2026-09-05-agent-translation-workflow.md`
- MinerU 后端：`2026-09-05-scanned-pdf-mineru-first.md`、`src/auto_epublizer/ingest/mineru.py`
