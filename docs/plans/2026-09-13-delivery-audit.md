# 2026-09-13 交付审计：交付前全量完整性与可靠性校验

状态：规划中

## 背景：一次真实交付的手动完整性检验（案例复盘）

来源：《俄国铁路史》中译任务（外部工具链执行，本项目复盘）。流程已结束、工具 QA
全过后，agent 手动做了全量完整性检验，发现**重大缺陷**：EPUB 仅含 34/72 张正文引用
图片——根因是 translation body 文件丢失 38 处图片引用段与部分脚注标记，而 align
对照表是完整的（脚本回填过），工具的「标记守恒」校验（查 align）全部通过，缺陷
直达成品。修复：从 align（经校验的权威对照）重建 body → 重 build → QA → 同步
三个分发产物（本地/云盘/仓库）。

### 四条教训（逐条映射到本项目）

| # | 教训 | 在本项目的现状 |
|---|---|---|
| 1 | **校验对象错位**：工具校验 align（它知道的契约），build 消费的是 translation md——两者脱节，无对账 | 同样存在：G0 标记/脚注守恒是 align 行级；`import` 只校验 align（seq/空译文），不校验 translation md 与 align 的一致性 |
| 2 | **静默降级**：媒体解析失败被静默跳过，成品缺图无信号 | 同样存在：`collect_media`「找不到的文件对应引用被移除」（build/__init__.py:417）——无事件、无告警 |
| 3 | **成品对账缺失**：没有「structured/translation 引用 ↔ EPUB 实际包含」的独立对账；目录/段落/脚注呈现同理 | 同样缺失：`E_MEDIA_LOST` 只对 structured↔translation md 的**引用**；EPUB 包内 `<img>`/`<aside>`/正文段落与 md 无对账 |
| 4 | **快照时效**：facts.md 是重建前的旧统计，对账以当前产物为准 | `_toc_missing_from_facts` 读 facts 快照；重切/修复后 facts 过期 |

### 案例检查项 → 本项目覆盖矩阵

| 案例中的检查 | 本项目现状 | 结论 |
|---|---|---|
| publication 状态机 / stale | `status --json` | ✅ 已有 |
| structured 完整性（单元/媒体/段落/inserts） | facts 规模 + `_media_facts` + inserts 审计 | ✅ 已有 |
| inserts content_desc 空（案例发现 80 空 → EPUB alt 缺失） | `W_INSERT_NO_DESC`（W 级，常被忽视） | ⚠️ 需清单强制处置 |
| 译文镜像 + 标记/媒体/脚注守恒 | align 级守恒 ✅；md 级：媒体 ✅（E_MEDIA_LOST）/表格 ✅（S4.2）/**脚注 ✗ / 插入标记 ✗** | ⚠️ 盲区 1 |
| md 与 align 是否同一份内容 | **无任何检查** | ⚠️ 盲区 2（本案根因的通式） |
| EPUB 图 ↔ 引用对账（案例主缺口 34/72） | **无**；且 collect_media 静默丢弃 | ⚠️ 盲区 3 |
| EPUB 正文段落探针（案例译文探针 4/4） | **无**（provenance coverage 是 structured↔align，非 EPUB） | ⚠️ 盲区 4 |
| EPUB 脚注呈现（数量/内容） | `E_FN_BACKLINK` 只查「存在的 aside」的回链；aside 整个缺失不查 | ⚠️ 盲区 5 |
| 目录/元数据/层级 | E_TOC_COVERAGE / W_TOC_MISSING / W_META_INCOMPLETE / toc_depth | ✅ 已有（人工复核进清单） |
| 产物同步与归档 | publishing.md（发布分发） | ⚠️ 缺交付审计环节串联 |

## 目标与原则

1. **双保险**：确定性对账自动化（CLI，S1）+ agent 独立审计清单（skills，S2）——工具
   对账消盲区；人工清单防「工具本身校验错位」（本案核心教训：成品校验必须独立做
   「源引用 ↔ 成品包含」对账，不能只依赖工具 QA）。
2. **交付定义升级**：交付 = `qa` released（工具门）**且** 交付审计记录完成（agent 门）。
3. **修复循环标准化**：发现缺陷 → 修复（留痕）→ `import`/`g0` → `build` → `qa` →
   重新执行审计清单 → 更新交付记录。

## 已定决策（默认值；实施中可推翻，推翻须回写本节）

| # | 决策 | 理由 |
|---|---|---|
| D1 | 新对账检查（md↔align 一致性、EPUB 媒体/脚注/段落呈现）全部 **error 级** | 三者任一失配 = build 输入或成品缺内容，是真实缺陷；经现有 `prov_error_findings → released=False` 路径阻断，无需新增 released_reason |
| D2 | 正文段落探针**全量**（非抽样） | md→XHTML 是我们自己的确定性渲染器，变换可控（脚注替换/figure/verse/表格均可归一化匹配）；跳过规则显式列出并用测试锁定 |
| D3 | 交付审计记录 = `reviews/delivery-<ts>.md`（agent 手写清单，不进状态机）；qa 以 `W_DELIVERY_AUDIT_MISSING` 提示（W 级不阻断） | 与 review-<ts> 同风格；agent 门靠 skills 强制，机器只提醒不代管 |
| D4 | 双语 EPUB（`-bi` 或 XHTML 含 `class="src"/"tgt"`）跳过媒体对账，段落探针改「tgt 文本包含」 | 现状双语渲染不含图（后续扩展点）；探针仍可对 tgt 段落生效 |
| D5 | 交付审计第一步强制重跑 `preprocess`（幂等刷新 facts） | 教训 4：对账以当前产物为准，不用旧快照 |
| D6 | inserts `content_desc` 空值维持 W 级，但交付清单要求**逐项补全或显式接受**并记入交付记录 | 直接升 E 会阻断大量合理场景（无 alt 的装饰图）；显式接受留痕即可审计 |

## S1 CLI 对账增强（qa / provenance / import）

### S1.1 md↔align 全文一致性（盲区 2，本案根因的通式）

- 新纯函数 `auto_translator/review/g0.py::md_align_drift(md_text: str, rows: list[dict]) -> list[str]`：
  - md 侧：去掉 `#` 标题行（build 的 h1 来自 title 参数，不在 align 行内）；
  - align 侧：`tgt` 按 `seq` 升序拼接为全文；
  - 双侧归一化：复用 `fidelity.norm_text`，另剥离 `[^…]` 脚注标记与 `{fig:NNN}`
    插入标记（渲染期会变换）；
  - 不相等 → 返回差异摘要（双侧归一化长度、首处分歧位置——提示「translation md
    与 align tgt 不一致，一侧缺内容」）；相等 → `[]`。
- 接线一（登记时拦截）：`orchestrator.import_translations` 每单元 drift 非空 →
  阻断该单元（中文清单），错误码级同现有结构性校验；
- 接线二（兜底复核）：`audit_provenance` 对每单元复跑 drift → `align_md_drift`
  列表 + error finding（防 import 后 md 又被单独改动）。
- 导出：`review/__init__.py` 导出 `md_align_drift`。

### S1.2 EPUB 呈现对账（盲区 3/4/5，provenance 扩展）

`qa/provenance.py` 新增私有工具（均在已打开的 `zf` 上工作）：

- `_epub_doc_map(zf) -> dict[basename, zip_path]`：spine 文档 basename → 包内路径；
- `_doc_text(zf, path) -> str`：读 XHTML、剥全部标签得纯文本；
- `_doc_imgs(zf, path) -> list[str]`：`<img src>` 的 basename 列表；
- `_doc_footnotes(zf, path) -> int`：`<aside epub:type="footnote"` 计数；
- `_is_bilingual(text) -> bool`：含 `class="src"` 判定（D4）。

三个对账（对 `expected` 每单元，构建用 md = 译文优先回退源文，与 build 一致）：

1. **`E_MEDIA_EPUB_LOST`**：md `_img_refs` Counter vs XHTML `<img>` basename Counter；
   md 有而 XHTML 无 → error（条目 `unit:名称`）。双语文档跳过 img 对账。
   ——直接封堵「collect_media 静默丢弃」与「渲染丢图」两类成品缺口。
2. **`E_FN_EPUB_LOST`**：md 脚注定义数（`^\[\^…\]:` 行数）vs XHTML aside 数；
   不等 → error（附两侧数量）。
   ——封堵「md 丢脚注定义 → 成品无注」。（md 引用无定义的残留已有 `W_RESIDUE`
   兜底，互补。）
3. **`E_EPUB_PARA_LOST` + `epub_coverage`**：md 段落（跳过：独立图片段——alt 文本
   非空时会以 figcaption 出现，但仍跳过以避免空 alt 假阴性；表格段——已有形状
   守恒；标题行——build 单独渲染；脚注定义行——由检查 2 专责）归一化后必须为
   XHTML 剥标签归一化全文的子串；缺失 → error + `epub_coverage_missing` 清单
   （`unit:段序`，截断展示）；`epub_coverage = covered / total`。
   双语文档：段落探针改查 tgt 段落文本包含（src/tgt 均在 XHTML 中）。

`ProvenanceResult` 新字段：`epub_media_missing: list[str]`、
`epub_footnotes_missing: list[str]`、`epub_coverage: float | None`、
`epub_coverage_missing: list[str]`、`align_md_drift: list[str]`（含进 `to_dict` →
report）。`qa/report.py`：`QaResult` 加聚合字段 `epub_coverage`、
`epub_media_missing: int`、`epub_footnotes_missing: int`、`align_md_drift: int`；
`generate_report` 的 `prov_ok` 判定纳入新 error findings（走既有
`provenance_incomplete` 阻断路径）。

### S1.3 构建期静默丢弃信号（教训 2）

`collect_media` 返回值增加被丢弃的引用清单（`(md, media, dropped)`——或独立返回）；
`orchestrator._render_and_pack` 对 `dropped` 非空调 `store.log_event("media_dropped",
refs=[…])`。主对账由 S1.2-1 兜底，事件用于排查定位（events.jsonl 可查）。

### S1.4 交付审计存在性提示（D3）

`orchestrator.qa`：全部单元 `built` 且 `reviews/` 不存在 `delivery-*.md` →
`provenance_findings` 追加
`{"level": "warning", "code": "W_DELIVERY_AUDIT_MISSING", "message": "全部单元已构建但缺少交付审计记录（reviews/delivery-*.md）；交付前按 references/delivery.md 执行全量校验"}`。

## S2 交付审计清单（skills，agent 强制门）

### S2.1 新 `skills/auto-epublizer/references/delivery.md`

内容骨架（照抄就能干）：

0. **前置**：重跑 `auto-epublizer preprocess`（幂等刷新 facts——对账以当前产物为准，
   不用旧快照，教训 4）；`qa` 确认 released。
1. **工具对账复核**：report 核读——`epub_coverage ≈ 1.0`、
   `epub_media_missing/epub_footnotes_missing/align_md_drift == 0`、
   `W_INSERT_NO_DESC`/`W_REPAIR_UNRESOLVED` 清单过目。
2. **解包抽查**（首/中/尾 + 高风险章：图表/脚注/多语密集）：
   - 正文探针：抽译文代表句 3–5 句 grep 解包 XHTML（工具已全量对账，**人工复核
     是防工具自身错位的第二道保险**——本案核心教训）；
   - 图片：EPUB 图数 = 引用数（工具）；**看 2–3 张图**（multimodal）确认图的内容
     与上下文位置语义正确（防「图在但放错位置/张冠李戴」）；
   - 脚注：抽 3 条注码 → 注文**内容**正确（不只回链存在）。
3. **人肉核对**：目录层级 vs 原书目录（toc 单元/源 TOC，注意 facts 已刷新）；
   封面/元数据 vs 版权页；landmarks 指向。
4. **inserts content_desc 空值**：逐项补全或显式接受并记录（影响 EPUB alt；本案
   80 空的先例）。
5. **阅读器实测**（可选）：Foliate/Apple Books 翻首中尾（目录跳转/脚注弹窗/图片渲染）。
6. **修复循环**：发现缺陷 → 修复（structured/translation 修改走语义整备
   `repairs.jsonl` 留痕，见 `2026-09-13-semantic-repair.md`）→ `import` → `g0` →
   `build` → `qa` → **重新执行本清单**。
7. **交付记录**：写 `reviews/delivery-<ts>.md`（模板见 S2.2）。
8. **产物同步**：output/ 成品清单 + 分发字节核对（本地/备份/云盘/仓库，按
   `references/publishing.md`）；分发副本全部更新（本案三处同步的先例）。
9. **经验沉淀**：新判据（如「成品校验必须独立对账」「修复后必须全量重验」）写
   `lessons/` 并在交付记录中互引。

### S2.2 交付记录契约 `reviews/delivery-<ts>.md`（模板）

```markdown
# 交付审计 <YYYYMMDD-HHMMSS>

- 审计对象：<slug>.epub（qa released，reason=…）；facts 刷新时间 …
- 工具对账：epub_coverage=…；epub_media_missing=0；epub_footnotes_missing=0；align_md_drift=0
- [ ] 正文探针 N/N 命中（抽样章节：首/中/尾/高风险）
- [ ] 图片语义抽查 M 张正确（图清单）
- [ ] 脚注内容抽查 3 条正确
- [ ] 目录/封面/元数据核对（结论）
- [ ] inserts desc 空值处置：补全 X / 显式接受 Y
- 发现与处置：（缺陷 → 根因 → 修复 → 复验；或「无」）
- 修复循环轮次：0（或 N）
- 产物清单与同步：本地/云盘/仓库（字节核对结果）
```

### S2.3 路由接线

- `SKILL.md` 路由表加一行：`| 交付前全量校验（qa 之后、交付之前） | references/delivery.md |`；
- `manifest.json` `references` 加 `"delivery"`；
- `workflow.md` 标准阶段 `qa` 之后加 `delivery audit（交付审计，强制）`；「已完成」
  判据补「交付审计记录存在」；
- `qa.md` 判读节加 `W_DELIVERY_AUDIT_MISSING` 与新 error 码处置；
- `review.md`（G5 语义）与 `publishing.md`（分发前引用 delivery.md）交叉引用；
- `AGENTS.md`：处理一本著作的标准流程加「交付审计」步骤 + 文档地图行。

## S3 文档同步

| 文件 | 动作 |
|---|---|
| `docs/quality-control.md` | G4/G5 描述补：md↔align 一致性、EPUB 呈现对账（媒体/脚注/段落）、交付审计门 |
| `docs/postprocessing-spec.md` | §2 验收标准与 §3 数据契约补新检查与 ProvenanceResult/QaResult 字段 |
| `skills/.../references/invariants.md` | 错误码表加 `E_MEDIA_EPUB_LOST`/`E_FN_EPUB_LOST`/`E_EPUB_PARA_LOST`/`W_DELIVERY_AUDIT_MISSING` 行 |
| `skills/.../references/qa.md`、`workflow.md`、`SKILL.md`、`manifest.json`、`publishing.md` | 见 S2.3 |
| `AGENTS.md` | 流程 + 文档地图 |
| `docs/plans/README.md` | 索引 |

## 测试设计

- `tests/test_provenance.py`（扩展）：
  - `E_MEDIA_EPUB_LOST`：正常书全绿；重写 zip 删某章 `<img>` → 报错含 `unit:名称`；
    双语文档（构造 class=src/tgt）跳过；
  - `E_FN_EPUB_LOST`：删一个 aside → 报错（附两侧数量）；
  - `E_EPUB_PARA_LOST` / `epub_coverage`：删一段 `<p>` → 报错 + coverage < 1.0；
    干净书 coverage == 1.0；脚注/图片/表格段跳过规则锁定（构造含三类的单元不误报）；
  - `align_md_drift`：md 删一段 → error finding。
- `tests/test_import.py`（扩展）：md 与 align tgt 不一致 → 阻断（中文提示）；一致 →
  通过（回归）。
- `tests/test_qa.py`（扩展）：report 聚合字段；全部 built 且无 delivery 记录 →
  `W_DELIVERY_AUDIT_MISSING`；放置 `reviews/delivery-x.md` → 消失。
- `tests/test_build.py` 或 e2e：媒体文件缺失 → `collect_media` 丢弃进
  `events.jsonl`（`media_dropped`）。
- CLI 冒烟：小书全链路 → 删 raw/media 一图 → build（引用被移除）→ qa 报
  `E_MEDIA_EPUB_LOST`（封堵「静默丢图」路径的端到端证明）。

## 实施顺序与提交切分

1. **S1.1** md_align_drift + import 阻断 + provenance 兜底（一提交，含测试）；
2. **S1.2 + S1.3** EPUB 三对账 + report 字段 + media_dropped 事件（一提交）；
3. **S1.4 + S2** delivery.md 清单与记录契约 + 全部路由/文档接线（一提交）；
4. **S3 + 收尾**：计划状态回写、plans/README 索引、CLI 冒烟记录。

每批 `uv run pytest -q` 全绿 + `ruff check .` + `ruff format --check .` +
Conventional Commits。

## 与同日「语义整备」计划的关系

- `2026-09-13-semantic-repair.md`（规划中）管**输入侧**：解析缺陷/OCR/结构重切的
  agent 修复与留痕（repairs.jsonl、restructure）；
- 本计划管**输出侧**：成品完整性与可靠性对账 + 交付前强制审计（delivery 记录）；
- 交点：交付审计发现缺陷 → 修复走语义整备的留痕机制（delivery.md §6 引用
  repairs.jsonl）；两者共同构成「修有痕、验有据」的闭环；
- 建议实施顺序：**先本计划 S1**（对账自动化，立刻封堵成品缺口类缺陷），语义整备
  随后。

## 已知边界与后续扩展点

- 双语版媒体渲染缺失是 build 现状（`render_bilingual_document` 无图路径）；本计划
  先跳过对账并提示（D4），双语补图作为后续扩展点单独评估。
- 段落探针的归一化跳过规则靠测试锁定；若实战出现渲染变换导致的假阳性，按 lessons
  修正规则（而非降级为 W）——漏检代价（本案 38 图）远大于假阳性代价。
- 阅读器实测（S2.1 §5）无法 CLI 化，属 agent 能力（multimodal/本地环境）。
- 案例中「从 align 重建 body」的修复手法可在 repair.md 补一节「成品缺内容的标准
  修复路径」（align 是经 import 校验的权威对照）——随语义整备计划 S2 一并落。
