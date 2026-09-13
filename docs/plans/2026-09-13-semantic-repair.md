# 2026-09-13 语义整备（Agent 语义任务）：信号层 + 修复留痕 + 结构重建登记

状态：规划中

## 背景与问题

「依赖 agent 语言能力的处理」散落各处但从未系统化：

- 原则已定（`docs/agent-vs-code.md`：理解/权衡/判断归 agent），但**没有场景清单**——
  agent 遇到换行/OCR/结构问题时不知道「这该我自己干，不该写脚本」。
- 实战两头翻车：要么写「智能修复脚本」（豆包实测：`merge_paragraphs` v1/v2/v3 反复
  调阈值烂尾、MinerU 拆分脚本反复翻车，最终结论「别脚本了，你自己手动拆分不行吗」，
  见 `lessons/2026-09-05-scanned-pdf-operations.md` §3、`agent-translation-workflow.md` §6）；
  要么手动修了但**无留痕、无校验**（修了什么、凭什么证据、有没有吞内容，全靠记忆）。
- 单元边界重建（重切/合并）没有登记入口——「禁止手改 publication.json」与「必须手动
  重切」矛盾，豆包只能手改状态文件并踩坑（`scanned-pdf-issue-checklist.md` #12/#13）。

目标：把「agent 语义任务」做成项目的一等公民——**CLI 出信号 + agent 修 + 契约留痕 +
CLI 校验/登记**，与现有「CLI 给信号、agent 做终审」的架构完全同构。

## 已定决策（默认值；实施中可推翻，推翻须回写本节）

| # | 决策 | 理由 |
|---|---|---|
| D1 | 留痕契约 = `preprocessing/repairs.jsonl`，**操作级**记录（非逐字） | OCR 逐字修正可达千处，逐字记录不可持续；操作级（动了哪个单元/哪些页、做了什么、证据在哪）足以审计 |
| D2 | `status=unresolved` 修复 = **W 级告警，不阻断放行** | 区别于 catalog：catalog unresolved ≈ 可能漏内容（阻断合理）；repair unresolved ≈ 文本疑点（风险线索，类似 risks.md）。实战证伪再升级为门禁 |
| D3 | 语音转写 = 前瞻条目（清单 B9），本轮不新增音频 ingest | 当前无音频输入路径；先闭环文本类场景 |
| D4 | 确定性修复原语（已有 `repair_missing_hyphens`）**不接线「自动动手」命令** | 修复是否适用取决于上下文（语义判断）；CLI 只出信号指路，避免边界模糊 |
| D5 | 信号集 = 6 类保守计数，全部 advisory，不进任何放行门 | 信号是给 agent 指路（哪些单元值得看），不是缺陷判定；误报代价 = 多看一眼 |
| D6 | 结构重建 = `restructure` 命令 + `preprocessing/structure.csv` 显式清单 | 对齐 catalog.csv 先例（显式、可校验、agent 可控 id）；「扫描 structured/ 自动推导」会把「哪个是章」的语义判断偷回 CLI |

## 场景总清单（agent 语义任务，按处理窗口）

> 完整清单同时落 `docs/semantic-repair.md`（规范）与 `skills/.../references/repair.md`
> （操作手册）。「现有支撑」列标注已有机制，避免重复建设。

### 窗口 A：解析后的文本流修复（改 structured/，翻译前）

| # | 场景 | 典型症状/信号 | agent 动作（证据 → 产物） | 现有支撑 |
|---|---|---|---|---|
| A1 | 硬换行/段落重组 | 行尾断句、句中断行、段落粘连、每行一段 | 按语义重断/合并；对照 `raw/page-NNN.json` 或页图 | 信号 hard_wrap_lines；OCR 工作流已有「改写 structured」指引 |
| A2 | 跨页续段 | 页尾句被页眉脚截断、下页首行续句 | 用 `source_page` 定位页边界，合并续段 | raw 逐页产物 |
| A3 | 页眉/页脚/页码误清漏清 | 奇偶页不同、章首页不同、无规律页眉；短对话行被误清 | 逐页看图判定保留/剔除 | `clean_header_footer`（50% 频率法，仅兜标准情况） |
| A4 | 脚注/尾注/边注归属 | 正文与注区混排、注号对不上、编号格式不一 | 分离注区，建立注码↔注文对应 | 脚注守恒（G0/G4）兜住数量，归属判断归 agent |
| A5 | 多栏/异形版式阅读顺序 | 带框、嵌套栏、通栏标题、图片环绕导致整段错位 | 看页图按版面语义重排 | `reading_order.py`（几何法，复杂版面失效） |
| A6 | 跨页表格/图 | 被页边界切开、表头只在首页 | 合并或调整呈现 | spec 已标「跨页表格」为扩展点 |
| A7 | 语义标记丢失 | 上标注号、上下标、斜/粗体强调丢失 | 恢复 markdown 语义标记 | — |
| A8 | 重复/隐藏文本层 | PDF 白字重复层、OCR 重叠扫描 | 去重并对照页证据 | — |
| A9 | 混合型 PDF | 部分页文字层坏、部分扫描 | 逐页判定哪些页改走 OCR/看图 | `sniff` 全书级判定，页级归 agent |

### 窗口 B：OCR / 转写噪声修复

| # | 场景 | 典型症状 | agent 动作 | 现有支撑 |
|---|---|---|---|---|
| B1 | 字符混淆 | `l/1/I`、`O/0`、`rn/m`、`己/已/巳`、`日/曰`、`未/末` | 按语言与上下文校正 | 信号 garbled_marks（部分） |
| B2 | 西文粘连/拆词 | `delos`→`de los`、断词连字符 | 恢复词边界 | 信号 hyphen_eol / long_latin_run |
| B3 | 中文误识/异体字 | 生僻字、旧字形、繁简混杂 | 按上下文校正 | — |
| B4 | 标点错误 | 全半角混用、引号方向、省略号/破折号 | 套用出版标点规范（quality-lessons F） | 信号 ascii_punct_cjk |
| B5 | 乱码/mojibake | 葡语 `Ã©`、`\ufffd` | 按语言还原 | 信号 garbled_marks；sniff 全书乱码率 |
| B6 | 版面噪声成字符 | 装订线、污点、框线变成乱串 | 剔除并对照页图 | — |
| B7 | OCR 段落合并 | 每行独立成段（传统 OCR 必然） | 语义重断——**明令禁止写阈值脚本** | 信号 hard_wrap_lines；`raw/pages/` 页图 |
| B8 | 多语混排 | 一书多语言、注音/原文夹注 | 判定语言分而治之 | `analysis/detect.py`（启发式参考） |
| B9 | 语音转写（前瞻） | 同音字、无标点、说话人分段、口语冗余 | 转写文本清洗与分段 | 本轮不做（D3） |

### 窗口 C：结构与归类判断

| # | 场景 | 典型症状 | agent 动作 | 现有支撑 |
|---|---|---|---|---|
| C1 | 标题判定 | 大字正文误判、代码/图注被当标题、漏判 | 按语义定标题 | `_is_chapter_heading`（启发式，仅兜底） |
| C2 | 层级推导 | MinerU `#`/`##` 混乱、PART 启发式失手、无书签书 | 重排目录层级（`level`） | `_derive_heading_levels`；重切走 restructure |
| C3 | 单元边界 | 碎片单元、单单元丢 nav、整页图章无前缀 | 重切/合并单元 + **restructure 登记** | S3 新命令 |
| C4 | 四层归类 | 「序/跋/附录」语义因书而异、多序言 | 纠正 region/kind | `_classify_title`（关键词表，仅兜底） |
| C5 | 垃圾内容 | 广告、书评页、空白页、腰封、重复目录页 | 识别剔除，去向记 catalog（excluded） | catalog.csv 契约 |
| C6 | 标题残留 | 装饰符、页码、转换器标记 | 清理 | `clean_pandoc_residue` / E_RESIDUE |
| C7 | 目录一致性 | 源 TOC 与实际单元标题/层级不符 | 对账修正 | `W_TOC_MISSING` / `_toc_missing_from_facts` |

### 窗口 D：媒体与插入元素

封面判定（多候选择一）、插图归属（整页图版 vs 内嵌 vs 装饰 vs 扫描背景）、图注/表注
与图序、表格结构恢复（无框线/合并单元格/跨页/表头）、公式与行内公式、非线性 spine 项
内联位置、媒体缺失对位。现有支撑：`images.py`/`tables.py` 几何路由 + inserts
`content_desc`/`latex` agent 语义层；归属/表头/合并单元格判断归 agent。

### 窗口 E：元数据与外部知识（已有流程，纳入清单统一管理）

元数据核对（`meta` 命令）、术语预提取/风险标注（terms/risks）、源文勘误先例
（`corr:` 留痕）、TOC 对账、背景知识补齐（search → `references/web/`）。

### 窗口 F：翻译/审校中发现的源缺陷（回流）

语义不通/缺句/重复段、引文与参考文献残缺、数字/年代/专名矛盾——定位到源页核对后：
要么回写 structured（走重译 + repairs 留痕），要么走现有 `corr:` 机制（只改 tgt、
align note 留痕，不动 src）。判据：影响单点措辞 → `corr:`；影响段落/结构 → 回写
structured 并重译该单元。

## 三层机制总览

```text
信号层（CLI，零 token）          修复层（agent）                登记层（CLI）
─────────────────────          ─────────────────────         ─────────────────────
facts 可疑信号（每单元）   →     读 raw 证据（页图/页 JSON/     →   repairs.jsonl 校验
  hard_wrap/hyphen/dup/           MinerU full.md/源文件）           （qa：字段/路径/单元）
  garbled/ascii_punct/            修 structured/（内容级）      →   restructure（边界级）：
  latin_run                       写 repairs.jsonl（操作级）        structure.csv 校验 +
                                  抽样自查（首/中/尾 × 页证据）      publication.units 更新
```

## 实施设计

### S0 顺手修复（并入 S1 提交）

`src/auto_common/workspace/models.py` `PublicationMeta` 中 `translator` 字段
**重复定义**（约 66/68 行，pydantic 静默取后者）——删除重复行，回归跑
`test_build.py::test_build_epub_translator_creator_role`。

### S1 信号层 + 规范文档（Batch A）

#### S1.1 信号纯函数：新模块 `src/auto_epublizer/preprocess/signals.py`

```python
def repair_signals(text: str) -> dict[str, int]:
    """对一份 structured md 统计可疑信号（跳过 # 标题行；全部为保守计数）。

    返回键（0 = 无信号）：
    - hard_wrap_lines：段内非末行且行尾无终止标点（。！？；…!?）——疑似硬换行/断行
    - hyphen_eol：行尾连字符（西文断词）
    - duplicate_paras：完全重复的非空段落数（多余份数）
    - garbled_marks：\ufffd 与常见 mojibake 序列（Ã/â€/ï¿½）
    - ascii_punct_cjk：CJK 字符紧邻 ASCII 引号/逗号/句号等（中西标点混用）
    - long_latin_run：无空格拉丁长串（≥20 字符，OCR 粘连）
    """
```

实现要点：按空行分段；段内逐行扫描（末行天然豁免 hard_wrap）；重复段用
`Counter`（`sum(c - 1 for c in Counter(paras).values() if c > 1)`）；纯函数、
无 IO、确定性。

#### S1.2 facts 接线：`src/auto_epublizer/preprocess/facts.py`

- `_unit_facts`（读 structured md 处）：`"signals": repair_signals(text)` 并入每单元
  dict（文件缺失 → 全零 dict）。
- `collect_facts`：聚合 `repair_signal_units = [u for u in units if any(...)]`，写入
  facts 顶层键 `"repair_signals": {"units": N, "kinds": {各信号的全书总计数}}`；
  `agent_todo` **条件追加**（有信号时）：
  `"语义整备：体检检出可疑信号（见 facts.md「可疑信号」表；信号是线索非缺陷）——按 references/repair.md 对照 raw 证据修复 structured/ 并写 preprocessing/repairs.jsonl 留痕；OCR/扫描件路径无论有无信号都必做一遍"`。
- `render_facts_md`：体检节后新增「可疑信号（语义整备线索）」表——
  `| id | 硬换行 | 断词 | 重复段 | 乱码 | 中西标点 | 拉丁长串 |`，仅列非全零行；
  表后加一行说明（advisory + 指向 repair.md）。
- 测试锚点：`tests/test_preprocess.py` 既有 facts 断言风格。

#### S1.3 规范文档：新 `docs/semantic-repair.md`

内容：定位（agent-vs-code 的场景展开）→ 场景总清单（A–F 全表，即本计划 §场景）→
三层机制 → 判据（每类场景「为什么脚本不行」一句话）→ 契约（信号字段语义、
repairs.jsonl schema（S2）、structure.csv schema（S3））→ 反模式（见下）→
决策记录（D1–D6）。

#### S1.4 操作手册：新 `skills/auto-epublizer/references/repair.md`

内容（「照抄就能干」）：
- **何时进入**：facts 检出信号 / OCR 与扫描件路径（必做）/ MinerU 层级乱 / 翻译审校
  回流（窗口 F）；
- **证据在哪**：`raw/page-NNN.json`、`raw/pages/pNNN.png`、`raw/mineru/full.md`、
  `source/`——先看证据再动手；
- **逐类操作**：A–F 压缩表（症状 → 证据 → 修法 → 自查），指向 docs 规范；
- **留痕**：repairs.jsonl 写法 + 示例（S2 落地后生效，文档先行描述契约）；
- **边界重建**：structure.csv 写法 + `restructure` 命令（S3 落地后生效）；
- **自查三件事**：① 修复后 grep 标记/脚注/图片引用数量未变（守恒）② 抽首/中/尾
  对照页证据 ③ 无法确定的写 `status: unresolved` 别硬修。

#### S1.5 路由与模板接线

- `skills/auto-epublizer/SKILL.md` 路由表加一行：
  `| 语义整备（解析缺陷/OCR 修正/结构重切） | references/repair.md |`；
- `skills/auto-epublizer/manifest.json` `references` 数组加 `"repair"`；
- `skills/.../references/workflow.md` 标准阶段在「agent 理解」与「翻译」之间加
  `语义整备（可选：信号触发；扫描件必做）`；
- `skills/.../references/preprocessing.md` 新增「§2.0b 语义整备 pass」+ todo.md
  模板加「0.5 语义整备」节（勾选项：逐单元修复 + repairs.jsonl）；
- `docs/agent-vs-code.md`：归 agent 表加「语义整备」行 + 文末链接规范文档；
- `AGENTS.md`：文档地图表加 `docs/semantic-repair.md` 行。

### S2 修复留痕契约（Batch B）

#### S2.1 契约：`preprocessing/repairs.jsonl`（agent 手写，每行一个操作）

```json
{"unit": "ch03", "kind": "line_join", "pages": [12, 13], "count": 18,
 "summary": "OCR 每行成段，按语义重断合并", "method": "逐页看图 + 手动重排",
 "evidence": "structured/raw/pages/p012.png", "status": "done"}
```

字段契约：
- `unit`：必填，须存在于 `publication.json.units`；
- `kind`：必填，枚举 `line_join|hyphen|ocr_char|mojibake|punct|header_footer|footnote|
  order|heading|boundary|classification|garbage|media|metadata|other`（对齐场景 A–F）；
- `pages`：可选 `list[int]`（源页号）；`count`：可选 int（影响处数，供汇总）；
- `summary`：必填非空（做了什么）；
- `method`：可选（怎么做：逐段判断/确定性批量操作+抽检）；
- `evidence`：可选，**工作区相对路径**且必须存在（页图/页 JSON/MinerU 产物）；
- `status`：必填，`done|unresolved`。

#### S2.2 读取与校验：`orchestrator.read_repairs(store)`

仿 `read_catalog`（orchestrator.py，catalog 模式）：
- 文件不存在 → `None`（全部检查跳过，零破坏——老工作区/convert 路径无感）；
- JSON 行解析失败 / 必填缺失 / 枚举非法 / unit 不存在 / evidence 路径不存在 →
  `OrchestrationError`（中文提示，带行号）。

#### S2.3 qa / report 接线

- `orchestrator.qa`：`repairs = read_repairs(store)`；
  `repairs_unresolved = sum(status == "unresolved")`；传
  `repairs_total=..., repairs_unresolved=...` 给 `generate_report`；
- `qa/report.py`：`QaResult` 加字段 `repairs_total: int = 0`、
  `repairs_unresolved: int = 0`；`generate_report` 加同名 kw 参数（**不进 released
  判定**，D2）；
- unresolved > 0 时 `orchestrator.qa` 仿 `W_TOC_MISSING` 追加
  `provenance_findings` 项：`{"level": "warning", "code": "W_REPAIR_UNRESOLVED",
  "message": "语义整备有未决修复：…（unit 列表，见 repairs.jsonl）"}`；
- skills `qa.md` 判读节 + `invariants.md` W 级表加 `W_REPAIR_UNRESOLVED` 行。

### S3 结构重建登记（Batch C）

#### S3.1 契约：`preprocessing/structure.csv`（agent 手写）

列：`id,region,kind,title,level,rel_path`（顺序固定，utf-8-sig 容 BOM）。

- `id`：`^[A-Za-z][A-Za-z0-9_-]*$`，全书唯一（建议沿用 `ch01`/`front-preface`/
  `back-index` 惯例）；
- `region`：`cover|frontmatter|body|backmatter`，且与 `rel_path` 前缀一致
  （cover → `cover.md`；其余 → `<region>/….md`）；
- `kind`：`cover|titlepage|copyright|dedication|foreword|preface|toc|afterword|
  appendix|notes|bibliography|index|glossary|chapter`；
- `title`：必须等于该文件首个 `# ` 标题文本（容忍 `{#id}` 锚点后缀；不一致 = 清单与
  文件脱节，报错）；
- `level`：1–6 整数（目录嵌套层级，epub-template-spec §3）；
- `rel_path`：`structured/` 内相对路径，禁止 `..`/绝对路径，文件必须存在。

**孤儿校验**：`structured/**/*.md`（排除 `raw/`）与清单 `rel_path` 集合相等——
漏登 = 内容会静默丢出 spine，报错。

#### S3.2 `store.replace_units(units: list[Unit])`

`src/auto_common/workspace/store.py` `set_units` 之后新增：整体替换单元清单，
**状态由调用方给定**（与 set_units 的「按 id 保留状态」不同），同锁 +
`atomic_write_json`。

#### S3.3 `orchestrator.restructure(store) -> dict`

流程：读 `preprocessing/structure.csv` → 逐项校验（S3.1 全部规则，错误中文带行号）
→ 与现有 `publication.units` 对账构建新 `Unit` 列表：
- id 存在且 `(rel_path, title, level, kind, region)` 全未变 → **保留原状态与 meta**
  （meta 更新 rel_path/region/level）；
- id 存在但任一字段变 → 状态回退 `split`（翻译/align 已失效，需重译重 import；
  旧产物保留不删，输出提示「需重译」）；
- 新 id → 状态 `split`、`meta = {rel_path, region, level}`；
- 消失的 id → 不入清单，输出「孤儿产物」提示（translation/align/analysis 残留）。

→ `store.replace_units` → `log_event("restructured", units=N, reset=[...],
added=[...], removed=[...])` → 返回摘要 dict（CLI 展示）。

#### S3.4 CLI：`auto-epublizer restructure [--workspace] [--config]`

输出：登记单元数 / 重置（需重译）列表 / 新增列表 / 消失列表 / 提示先跑
`preprocess` 刷新 facts。错误路径仿 `meta`/`import` 命令
（`typer.Exit` + 中文提示，不打 traceback）。

#### S3.5 状态机语义（写进 skills 与 AGENTS）

`restructure` 是继 `import` 之后第二个「agent 手写产物 → CLI 登记」的入口：
内容级修复（窗口 A/B/D）改 `structured/` 文件本身（无需登记，build/provenance 直接
读）；**边界级重建**（窗口 C3/C2）改文件集合，必须 `restructure` 登记才能进
build。两条路径都以 repairs.jsonl 留痕（kind=`boundary`/`heading`）。

### S4 收尾

全量 `uv run pytest -q` + `ruff check .` + `ruff format --check .`；CLI 冒烟
（构造含信号的书 → facts 出表 → 修 structured + repairs.jsonl → qa 出
`repairs_total` → 重切 + structure.csv → restructure → status 确认状态语义）；
计划状态回写 + `plans/README.md` 索引更新；如实战沉淀出可复用判据，另写 lessons。

## 与既有机制的关系（防冲突）

| 机制 | 分工 |
|---|---|
| `catalog.csv` | 管「源内容**收没收**」（included/physical/excluded/unresolved）——漏收阻断 |
| `repairs.jsonl` | 管「收进来的文本**对不对**」（修复留痕）——unresolved 仅告警（D2） |
| `corr:` 勘误 | 翻译期发现的单点源错——只改 tgt + align note 留痕，**不动 src**；影响段落/结构时改走语义整备（回写 structured + 重译） |
| G0 守恒 / fidelity | 修复后的自动防线：标记/脚注/表格形状守恒 + align src↔structured 源保真——修复吞内容/改写源文会被 import 阻断 |
| provenance 覆盖率 | structured 修改后旧翻译段落对不上 → coverage < 1.0 → 放行阻断（天然防「修了结构不重译」） |
| `risks.md` | 预判的风险（未发生）；repairs 是已执行的动作（发生了） |

## 反模式（写入 docs/semantic-repair.md 与 repair.md）

1. **禁止写「智能修复/合并/拆分脚本」**——阈值/正则永远差一点（merge_paragraphs
   v1/v2/v3、MinerU 拆分脚本实证）。语义判断（哪是标题/哪里断段/哪个字错）由 agent
   读源文完成；
2. agent 写脚本**只允许做确定性检索/统计/搬运**（找线索、数数、批量替换已由 agent
   逐处确认的确定模式），不允许做语义判断；
3. **批量修复必须抽首/中/尾对照 raw 页证据**（防批量清洗静默吞内容——ingest.md
   「批量改写后抽查」既有纪律的强化）。

## 测试设计

- `tests/test_signals.py`（新）：`repair_signals` 纯函数——六类信号各正例 + 干净文本
  全零 + 标题行豁免 + 段末行豁免。
- `tests/test_preprocess.py`（扩展）：含可疑内容的 structured → facts.json `signals`
  字段与 `repair_signals` 聚合、facts.md 渲染「可疑信号」表、agent_todo 出现整备项；
  干净书 → 无该待办项。
- `tests/test_repair.py`（新）：`read_repairs`——不存在 → None；合法 done/unresolved；
  非法 kind/status/unit/evidence/缺必填/坏 JSON → OrchestrationError（带行号）；
  qa report 含 `repairs_total`/`repairs_unresolved` + `W_REPAIR_UNRESOLVED` 追加。
- `tests/test_restructure.py`（新）：合法登记（新 id → split；变更 id → 回退 split；
  未变 id → 状态保留）；错误——列缺失/重复 id/id 非法/文件缺失/孤儿 md/标题不匹配/
  region 与路径不符/level 越界/`..` 路径；CliRunner 冒烟（输出含登记与重置摘要）。
- 回归：S0 的 translator 字段（`test_build.py`）。

## 文档同步清单

| 文件 | 动作 |
|---|---|
| `docs/semantic-repair.md` | 新建（规范：清单/判据/契约/反模式/决策） |
| `docs/agent-vs-code.md` | 归 agent 表加「语义整备」行 + 链接 |
| `AGENTS.md` | 文档地图加行；标准流程加 restructure 可选步骤 |
| `skills/.../references/repair.md` | 新建（操作手册） |
| `skills/.../SKILL.md` + `manifest.json` | 路由表 + references 数组 |
| `skills/.../references/workflow.md` | 阶段图加语义整备；命令总览加 restructure |
| `skills/.../references/preprocessing.md` | 语义整备节 + todo 模板 |
| `skills/.../references/structure.md` | 「单元边界重建」节（structure.csv + 命令） |
| `skills/.../references/qa.md` / `invariants.md` | W_REPAIR_UNRESOLVED 判读 |
| `docs/plans/README.md` | 索引 |

## 验证要求

每批：`uv run pytest -q` 全绿 + `ruff check .` + `ruff format --check .` +
Conventional Commits 单批一提交。S4 全链路 CLI 冒烟（信号 → 修复留痕 → qa 字段 →
重切登记 → 状态语义）。

## 已知边界与后续扩展点

- **EPUB 源重切**：入库时内部链接已按旧单元 id 重写（`structure/links.py`），重切会
  使锚点指向旧单元——restructure 场景主要面向 PDF/OCR/MinerU 源；EPUB 源重切须 grep
  检查内部链接指向并人工修复（repair.md 写明）。
- **重置单元的旧翻译**：restructure 不删除旧 translation/align（防误删），以状态回退
  + 提示驱动重译；孤儿文件由 agent 清理。
- 信号集可按实战迭代（新增检波器只是纯函数 + facts 字段扩展）；语音转写（B9）等音频
  ingest 到位后再入正式清单。
- unresolved 修复若实战证明是放行级风险，D2 可升级为门禁（加 `released_reason=
  repair_open`，仿 catalog）。
