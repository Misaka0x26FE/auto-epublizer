# 学术史料整理方法论迁移：EPUB / 印刷 PDF 质量门改进计划

> 2026-11-20 首轮范围按新版计划调整为源页清洗漏失和等量源译块错配的只读诊断。原规划保留供追溯，首轮实现和验证见 §10。

状态：**新版首轮 P0 与后续四项改进已验证，原规划保留供追溯**　｜　立项：2026-11-19　｜　基线：当前 `main`
范围：只改 `auto-epublizer` 的确定性能力（预处理证据、构建、校验、报告）；不改译文、
不新增 LLM 调用、不改存量工作区结构。
来源材料：`~/Documents/学术文章整理工作流与提示词_图表与注释修订.md`（外部客户规范，
不复制进仓库）＋ `~/work/translate` 工作根（57 个工作区、654 个 per-book 工具脚本）的
现场证据。

> 一句话：把那篇文章从「Word 排版提示词」读成「学术史料的可验收方法」，把其中**可判定**
> 的部分落成 CLI 的检查与证据；不可判定的分类仍由 agent 完成。

## 0. 明确不做

用户 2026-11-19 决定：**本项目不做 DOCX 交付**，产出仍是 EPUB 与印刷 PDF。因此本计划
不包含、也不得顺手引入：

- Word/WPS 模板、`4，正文` 等 DOCX 样式名、14/12 磅字号体系、页边距与文档网格；
- DOCX 原生脚注/尾注对象、`python-docx` 或类似依赖；
- 在 EPUB 中设置 `font-family` 或内嵌字体（工作根既有红线，EPUB 由阅读器渲染）；
- 「自动重绘统计图」「自动判定引文边界」「自动给注释分类」等语义动作（单 LLM 原则）。

## 1. 文章里什么是可迁移的

该文是**一份面向 DOCX 的执行提示词**，但其结构是一条可复用的整理方法：

> 先建清单与映射 → 先做语义分类 → 只执行被授权的变换 → 逐项验收并如实标注未核对。

前两步与最后一步属于方法，与输出格式无关；中间一步的"授权变换"正好对应本项目的
`repairs.jsonl` / `errata.jsonl` / `terminology_exemptions.csv` 留痕模式。

| 文章内容 | 迁移判断 |
|---|---|
| WPS 模板、样式名、磅值、页边距、网格、DOCX 原生注释对象 | 不迁移（输出形态不同） |
| 字符级字体归属（数字宋体、拉丁/西里尔 TNR） | 只迁移**检查思路**：PDF 端已有逐字符脚本—字体对账，可扩到数字与西里尔；EPUB 端只查符号与空格 |
| 清单先行、稳定标识、对应关系表 | **迁移**（本项目已有 `catalog.csv` 模式，缺图表/引文两类对象） |
| 语义分类先于格式（书籍/期刊、逻辑表/表格对象/面板/截图、整段引用/行内引用、原生注/段落注） | **迁移**为结构化字段；分类由 agent 判定，CLI 只校验 |
| 逐格核对、一条逻辑记录一行、不新增派生列 | **迁移**为表格检查器（纯机械，可正则 + 表格模型） |
| 整块缩进引文识别、引文上下空行、同一引用合并为一个容器 | **迁移**为版面证据候选 + 渲染契约 |
| 注释右括号无空格、页码列表不互改、作者首字母保真、同上指向可解析 | **迁移**为确定性门 |
| 唯一授权规范化 + 禁止擅加符号 | **迁移**为「候选 → 授权 → 留痕」的规范化账本 |
| 逐表逐注的验收状态、未核对不得称完成 | **迁移**为 `qa` 的逐项验收矩阵，并接入 `released` 条件 |
| 长稿分批交接记录 | **迁移**为固定交接模板（低成本，收益在减少"凭记忆猜进度"） |

## 2. 现状证据（均为本次只读核对）

| 能力 | 现状证据 | 缺口 |
|---|---|---|
| 表格结构 | `src/auto_epublizer/build/html.py` 的 `_render_pipe_table` / `_render_simple_table` 只生成**单行表头**，无 `colspan/rowspan/tfoot` | 多级表头、纵向合并、表注/来源同框、跨页续表（PDF 依赖真正的 `thead`） |
| 引文容器 | 只有普通 `<blockquote>` 与 PDF 的 `blockquote` 缩放 | 无单列容器语义、无左侧竖线契约、无上下空段规则 |
| 注释语义 | `src/auto_epublizer/notes.py` 有 `scope_id/label/status`、双向锚点校验 | 无 `kind`（脚注/尾注/表注/译者注/解释注）、无书目 `citation` 类型、无页码列表/首字母/同上检查 |
| 术语 | `src/auto_translator/glossary/csv_io.py` 固定 8 列（G0 用） | 无首现状态、无括注密度、无 7 字段交付表、无西里尔回填候选 |
| 版面卫生 | `src/auto_epublizer/hygiene.py` 仅 6 类（残词/引号/重复/半句/长段/丢尾） | 无数字内空格、范围号、字形混淆、Markdown 残留 |
| PDF 字体 | `src/auto_epublizer/pdfdiagnostics.py` 已有 `W_PDF_FONT_LATIN_USES_CJK` / `W_PDF_FONT_CJK_USES_LATIN` | 无数字字体归属、无西里尔/拉丁同形字 |
| 逐项状态 | `qa/report.py` 输出聚合计数与放行原因 | 无表/图/引文块/注的逐项 `pass/fail/unverified` 矩阵 |
| 工具复用 | `~/work/translate` 有 **654** 个 `preprocessing/tools/*.py`；高频：`make_align.py`(34)、`assemble_unit.py`(17)、`dump_blocks.py`(15)、`guard.py`(11)、`check_unit_coverage.py`(11) | 每个高频脚本都是一次 CLI 缺口 |

现场阻塞（`docs/交付审计-批次B-20261119.md`）：批次 B 复核 54 本历史工作区，放行 46、
**仍阻塞 8**，原因集中在注释形态（`forced-labour-and-extermination` 2,074 条、`hans-frank`
800+ 条）、注码差额、标题与诗行结构（`matla-al-sadayn-1`）、对照表漂移、章节末尾注文列表
（`zhonghua-renmin-gongheguo-shi-2` 843 条无引用、`tamozhennaya-politika-rossii` 779 aside 混排）。
这些正是本计划 P0/P1 的靶子。

## 3. 七个方法论与落点

### M1 清单与映射先于加工

文章要求先建内容清单、稳定标识（如 `CH06-T001`）、"标识—原编号—锚点—全文—类型—目标位置"
映射，再动手。本项目已有 `catalog.csv`、`structure.csv`、`notes.json`、`repairs.jsonl`；
缺**表格**与**引文**两类对象。

落点：新增 `preprocessing/table-registry.jsonl`、`preprocessing/figure-registry.jsonl`
（可选，存在则参与门禁），字段与四态状态见 §5.2。CLI 只读取与校验，不写权威内容；
与 `catalog.csv` 一样属于"agent 写、CLI 校验"的契约。

### M2 语义分类是 agent 的活，校验是 CLI 的活

文章反复强调"分类错比格式错更严重"：书籍 vs 期刊、逻辑表 vs 表格对象 vs 多面板、
整段文件引用 vs 行内引用、原生脚注 vs 文末段落注。当前 `notes.json` 只到"是不是注"。

落点：`notes.json` 增加 `kind` 与 `citation`（§5.1）；表格注册表增加 `kind`
（`data|quote_container|continuation|panel`）。CLI 按 `kind` 选择校验分支，不做语义推断。

### M3 逐格核对与"一条逻辑记录一行"

文章最具体的规则：不得把多年数据塞进一个单元格靠段落排齐；国家名跨年纵向合并；
空白、`0`、`—`、星号不得互换；不得新增派生列。

落点：表格检查器（§6 检查码 `W_TABLE_*`），输入为结构化 md 表格或 sidecar 表格模型；
只报候选与位置，不改文本。配合 §4.2 的渲染升级，EPUB 出真正的合并单元格、PDF 出真正的
`thead` 续页表头。

### M4 从版面证据识别结构

文章判据：整块缩进的长引文（无引号也算）、原书整块内缩与块内首行缩进是两件事。
扫描件里这些是几何事实，本项目已有 `structured/raw/page-*.json` 的块字号与位置。

落点：`evidence layout`（新命令或 `evidence breaks` 的同族子命令）导出候选：
连续块左边界内缩、字号不大于正文、上下邻接正文 → `quote_candidate`；页面绘制线构成网格
→ `table_candidate`；图片块相邻短块 → `caption_candidate`。CLI 只给坐标与块号，agent 判定。

### M5 注释的"锚点—编号—类型"三向对账

项目已有前两层（`scope_id`/`note_id`/`ref_id` 双向对账），缺第三层与五个机械检查：

- 编号右括号后不得有空白（译文、EPUB、PDF 三处）；
- 连续范围与分列页码不得互改（`94、100` ≠ `94—100`）；
- 作者首字母序列多重集一致，西里尔/拉丁同形字告警；
- `同上` 指向可解析，且不是"一注多出处就机械指最后一条"；
- 注释类型覆盖：登记为 note 的条目必须能落到某个 `kind`。

落点：`notes.py` 校验 + `g0` 接线 + `qa` 成品对账；另加 `notes adopt --from-inline`
把历史 `注 N.` / `[N] 正文` 机械迁移为候选与原位标记（agent 复核），用于批次 B 的阻塞书。

### M6 唯一授权的规范化与符号保真

文章结构是"默认禁止新增符号；只有明确授权者可改，且逐条记录"。

落点：`hygiene` 扩检查项；所有改写走 `hygiene --apply`，每处写
`preprocessing/normalizations.jsonl`（位置、前值、后值、授权类型）。未授权的 diff
在交付审计里必须出现。

### M7 逐项验收状态，而不是汇总数字

文章的验收表逐表、逐注记录，并明确"数量相同不能代替核对"。

落点：`qa` 输出逐项矩阵，`report.json` 增加 `verification` 段；`released` 条件加一条：
**blocking 类对象不得存在 `unverified`**。这补上已经总结过的"假绿"教训
（`skills/auto-epublizer/lessons/2026-11-10-notes-nonempty-false-green.md`）。

## 4. 工作包与优先级

### P0 注释语义与机械门（先做）

理由：不碰渲染、不改存量结构，直接对批次 B 的阻塞；可在一个 PR 内完成并有正负样本。

1. `notes.json` schema v2：每条增加可选 `kind`、`citation`（向后兼容，缺省视为未分类）。
2. 五类检查接线到 `g0`（结构侧）与 `qa`（成品侧）。
3. `notes adopt --from-inline`：只做机械迁移与候选生成，输出 `preprocessing/note-adoption.jsonl`。
4. 文档：`skills/auto-epublizer/references/notes.md` 补类型与检查说明。

验收：合成样本覆盖五种命中与三种负样本；批次 B 的 `forced-labour-and-extermination`、
`hans-frank` 至少一本能推进到可登记；存量 46 本放行书重跑 `qa` 不出现新 blocking。

### P1 表格逻辑模型（结构级）

1. **sidecar**：`preprocessing/blocks/<unit>.json` 的 `tables[]`（字段见 §5.2）。没有 sidecar
   时退化到当前行为，保证存量不动。
2. **渲染**：`build/html.py` 消费 sidecar，输出 `caption/thead/tbody/tfoot`、
   `colspan/rowspan`、`class="data quote-container"`；无 sidecar 走原路径。
3. **PDF**：`pdfexport.py` 保证 `thead` 重复、`tfoot` 随末行、引文容器 `page-break-inside`
   按容器而非按段落。
4. **检查**：`W_TABLE_*` 见 §6；`E_TABLE_SPAN_OVERLAP` 为 blocking（模型自相矛盾）。
5. **候选提取**：`evidence layout` 产出 `table_candidate`（网格线 + 文本落格），降低手写
   sidecar 的成本。

验收：一本真实多级表头书（如 `tobacco-in-history`，台账记 15 张表）走通；回归样本中
`tobacco-in-history` 之外的存量书抽查 5 本，EPUB 字节变化仅限预期 class 与表格结构。

### P1 逐项验收矩阵

1. `qa` 为表/图/引文块/注输出 `verification[]`，每项 `pass|fail|unverified|not_covered` 与证据指针。
2. `released` 条件扩展；`report.json` 增 `verification_summary`。
3. `skills/auto-epublizer/references/delivery.md` 增加"逐项核对"要求。

验收：构造"表存在但未核对"的样本，`released` 必须为 false 且原因可读；46 本放行书在
未补状态时会新增 blocking——因此本项需提供迁移开关（默认 advisory 一版，下一版收紧），
避免一次把存量全部锁死。

### P2 版面证据

`evidence layout`：引文/表格/图注候选 + 页码与 bbox 证据；只读、零 token。
验收：对 3 本扫描件（`from-georges-sorel`、`matla-al-sadayn-1`、`pod-znakiem-krola-daniela`）
抽样，人工判定候选准确率与漏报，写入计划验证记录。

### P2 术语首现、括注密度与西里尔回填

1. `terms-export`：从 `analysis/glossary.csv` 生成 7 字段交付表（只读导出，不替代 G0 表）。
2. `analysis/first-mention.json`：章内首现状态机（agent 维护，CLI 校验一致性）。
3. 括注密度报告：两种口径（源词占比 3%–5%；每千译文字 6–9 处），advisory。
4. 西里尔回填候选：拉丁转写词 + 括注上下文 → `pending` 列表；查到依据才由 agent 填。

验收：对一俄文源书抽样，密度报告与人工计数误差可解释；不产生"猜造词形"的写回。

### P3 印刷档案与 PDF 字体对账扩展

1. `print-profile`（版本化 YAML/JSON）：字体族、字号、行距、表格与引文容器规则；取代散落
   在各书 `preprocessing/tools` 的打印参数。
2. `pdfdiagnostics` 扩：数字字体归属、西里尔/拉丁同形字、引文容器跨页连续性。
3. 验收：PDF 字体检查输出可复算清单；未嵌入/降级的字体如实列出，不写"通过"。

### P3 工具上游化（按复用次数）

先做 5 个：align 同步、assemble/重组、块偏移检查、覆盖检查、页眉页脚清洗。每上游化一个
即删除 per-book 副本（工作根红线：一份字节只属于一个仓库）。验收：654 → 500 量级的收敛
记录在计划验证节，不删任何工作区内容。

## 5. 数据结构草案

### 5.1 `structured/notes.json` / `translation/notes.json`（v2 增项）

```json
{
  "note_id": "n-000123",
  "scope_id": "ch03",
  "label": "17",
  "kind": "endnote",
  "citation": {
    "type": "book",
    "fields": {"author": "В.И.阿利金", "title": "国家安全与时代",
               "place": "莫斯科", "year": "2001"},
    "pages": [{"from": 131, "to": 131}]
  },
  "text": "……"
}
```

- `kind`：`footnote|endnote|table_note|figure_note|translator_note|explanatory|bibliographic`
- `citation.type`：`book|journal|collection|newspaper|archive|ibid|secondary|explanatory|unknown`
- `pages`：显式区分连续范围与分列页码；不合并、不推断。
- 缺省（旧文件）视为 `kind: null`，不阻断，只触发 `W_NOTE_KIND_MISSING`。

### 5.2 `preprocessing/blocks/<unit>.json`（可选 sidecar）

```json
{
  "unit": "ch03",
  "tables": [
    {"block_id": 12, "kind": "data", "label": "表2",
     "caption": ["产量增长速度（1950年＝100），%"],
     "header_rows": 2,
     "cells": [{"r": 0, "c": 0, "rowspan": 2},
               {"r": 0, "c": 1, "colspan": 3, "text": "电力工业"}],
     "source": "《……年鉴》，第54—55页",
     "notes": ["* 民主德国—1956—1965年"]}
  ],
  "quotes": [{"block_id": 20, "container": "table", "indent_em": 2, "turns": 3}]
}
```

约束：单元格用 `(r,c)` 定位，合并区域必须覆盖守恒；`kind=quote_container` 的表不参与
`W_TABLE_*` 数据检查。

### 5.3 `report.json` 增项

```json
{"verification": [{"object": "table:ch03:12", "status": "unverified",
                   "evidence": "preprocessing/blocks/ch03.json"}],
 "verification_summary": {"pass": 0, "fail": 0, "unverified": 1, "not_covered": 0}}
```

`released` 条件：`verification_summary.unverified == 0`（blocking 类），迁移期可配置为 advisory。

## 6. 检查码清单

| 码 | 级别 | 判据 |
|---|---|---|
| `E_NOTE_BRACKET_SPACE` | blocking | `[N]` 右括号后存在半角/全角/不间断空白或制表符 |
| `W_NOTE_PAGE_LIST` | advisory | 同一条注里连续范围与分列页码形态混用/疑似互改 |
| `E_NOTE_INITIALS_MISMATCH` | blocking | 源注与译注作者首字母序列多重集不一致 |
| `W_SCRIPT_CONFUSABLE` | advisory | 首字母/专名中拉丁与西里尔同形字混用（`B.`/`В.`） |
| `W_NOTE_IBID_UNRESOLVED` | advisory | `同上` 无可解析前项，或一注多出处时指向不唯一 |
| `W_NOTE_KIND_MISSING` | advisory | 已登记注文缺 `kind`（v2 迁移期） |
| `W_TABLE_CELL_MULTI_RECORD` | advisory | 单元格含 ≥2 组年份/数值，疑似多年挤在一格 |
| `W_TABLE_VMERGE_CANDIDATE` | advisory | 连续行首列同名，建议纵向合并 |
| `W_TABLE_NO_BASIS` | advisory | 表头含年份/指数但缺基期或单位 |
| `W_TABLE_SOURCE_MISSING` | advisory | 源件该表有来源/表注而注册表未登记 |
| `E_TABLE_SPAN_OVERLAP` | blocking | 合并区域重叠或覆盖不守恒 |
| `W_TABLE_COLUMN_ADDED` | advisory | 注册表列数多于源表（疑似新增派生列） |
| `W_QUOTE_INDENT_CANDIDATE` | advisory | 版面证据显示整块缩进而未标记为引文容器 |
| `W_NUM_INNER_SPACE` | advisory | 同一数值内部出现空白（`1 936`、`0. 5`、`[ 1 ]`） |
| `W_RANGE_DASH` | advisory | 数字之间用 `-`/`–`/`=` 且语义疑似范围（排除负号、复合词、URL/DOI） |
| `W_MARKDOWN_RESIDUE` | advisory | 成品或译层出现 `]{#`、`$$`、缩进标题等字面残留 |
| `W_FIRST_MENTION_MISSING` | advisory | 强制括注项（书名、`tâbûr` 等）章内首现未附原文 |

所有 advisory 默认不阻断；`config.yaml` 可按书把子集提为 blocking（与现有
`terminology_exemptions.csv` 的粒度一致）。

## 7. 测试与验收

- 单测：每个检查码至少 1 正 1 负样本；侧挂表格的 span 守恒用性质测试
  （Hypothesis 生成随机矩形覆盖）。
- 集成：合成工作区（`tempfile`）跑 `import → g0 → build → qa`；PDF 用现有
  `pdf-verify` 链路加字体断言。
- 回归：存量 46 本放行书重跑 `qa`，除新 advisory 外不得新增 blocking；EPUB 字节变化
  必须可归因（class/表格结构）。
- 文档：`skills/auto-epublizer/references/{notes,translation,qa,delivery}.md` 同步；
  `AGENTS.md` 的 QC 条目补新门；完成后按目录约定沉淀 `lessons/`。

## 8. 风险与边界

| 风险 | 处置 |
|---|---|
| 侧挂 JSON 手写负担重 | 先上 `evidence layout` 与 `W_TABLE_*` 候选，让 CLI 给骨架、agent 只做判定 |
| EPUB 字节大范围变化 | sidecar 缺省退化到原路径；只对显式登记的表启用新渲染 |
| 逐项矩阵一次锁死存量 | 先 advisory 一版，下一版收紧；迁移记录写在 `report.json` |
| 注释类型误判 | 类型由 agent 判定并留痕；CLI 不推断，只校验字段完备性 |
| WPS/Word 渲染差异 | 不在本项目范围（不做 DOCX）；PDF 以 Chromium 实测为准，字体缺失如实列 |

## 9. 待定决策

1. `notes adopt` 是否允许写回 `structured/*.md`（当前结构层被视为源保真基线）——建议只写
   `translation/*.md` + `align/`，源层不动。
2. 逐项矩阵的 blocking 收紧时点：P1 落地后一版，还是与下一批次打包。
3. 术语 7 字段表是否进 `output/`（当前 `output/` 只放 EPUB/PDF）——建议放
   `analysis/` 或交付包，不进成品目录。

## 10. 实施记录

### 2026-11-20 首轮验证

- `evidence partition --json` 增加 `cleanup_candidates`，记录疑似页眉后未匹配行与字号突出的未匹配短块及其原页定位。RSS 返工前结构备份的试验副本命中第 47、69 页第 4 块的两个小节标题，当前结构对这两处无候选。全书候选分别为 406 和 435 条，说明仍需原页核证，不宜按候选数量设置硬门。
- `align-propose` 增加 `offset_candidates`，列出邻域数字锚点支持的连续偏移区间。`pod` 可取得的 `fdf2f34` 快照为 158 对 158 块，当前快照为 53 对 53 块，两者均无偏移候选。在前者的译文副本内重排 4 块后，命中译文第 6–8 块对应源文第 7–9 块，偏移 +1。历史记录中的 159 对 159 块坏快照未复现。
- 这两条输出供逐项人工核证。清洗报告受 OCR 和源层阅读顺序影响，偏移报告依赖可区分的数字锚点。两条诊断维持原放行逻辑和原工作区格式。
- 历史样本只读抽查：《布拉格之春及其余波》《俄国关税史》《俄国铁路史》分别列出 144、13、334 条清洗待核候选。《烟草史》原始分区证据不可用，报告 `unknown`。四书各抽查 3 个已译单元，未发现连续数字偏移候选。此处记录候选数量，未逐条回查底本。
- 全量回归 1,514 项通过、5 项跳过。随后新增单数字块边界用例，分区和对齐定向测试合计 24 项通过。Ruff、双语戳、文档链接与 diff 空白检查通过。

### 2026-11-20 后续四项验证

| 项目 | 试点证据 |
|---|---|
| 旧注码定位 | `evidence notes --unit ch04` 在 `hans-frank` 第四章列出 222 处旧注码，其中 94 处有原页上下文匹配。两处 `[1]` 分别位于第 7、129 行，原页匹配为空。同号还见于其他单元，书末第 3 行的定义仅供回查。 |
| EPUB 表格核对 | 目视核查《苏联机车技术》源 PDF 第 238 页的表 B，独立录入预期单元格，与 `OEBPS/back-appendix.xhtml` 第 2 张表逐格对账。包括空白和注记在内的 125 格一致。交换同一行两个数字的合成反例定位到第 3 行、第 1 和第 2 列。表外来源另行查看。 |
| 印刷 PDF | Chromium 的百行多级表头回归验证了续页表头、全部数据行和唯一表尾。最终版实书表 B 在试验字号下跨第 385–386 页，两页均有表头，首行、末行和来源可从文本层读回。《俄国关税史》重渲 686 页，更新 22 个目录页码，25 个书签均落在有效页范围内。抽查前五个已更新条目，页码与书签一致。79 条目录项仍标为原版页码、未定位。两份派生件的字节清单校验通过。 |
| 清洗候选 | RSS 原页第 10、50、407 页确认页码和页眉位于同一原始块。第 89、245 页的章名已与章号合并写入结构层，第 284 页的附录标题跨原始行。缩小清洗候选范围后条目从 435 降至 49，分区账本仍有 8,587 个未决原行。剩余候选需要原页核证。 |

同一 Chromium 版本渲染常规样本册，修复表尾规则前后均为 21 页，纸张尺寸和文本摘要一致。打印 CSS 字节基线已更新。全量测试发现的 Markdown 裸标签回归已增加固定用例，Pandoc 分片 SVG 封面也已通过定向回归。

最终全量回归 1,520 项通过、5 项跳过。跳过项涉及外部工具检查、RapidOCR、Pandoc 与 Calibre 集成，以及 Chromium 版本绑定的 PDF 基线。Ruff、双语戳、文档链接与 diff 空白检查通过。
