# 语义整备（Agent 语义任务）

> **定位**：把「依赖 agent 语言能力的处理」系统化——CLI 出信号、agent 修复、契约留痕、
> CLI 登记。它是 `docs/agent-vs-code.md` 主判据（「需理解/权衡/判断 → agent」）在
> 解析缺陷、OCR 噪声、结构判断上的展开。
> **操作手册**：`skills/auto-epublizer/references/repair.md`（照抄就能干）；
> **计划**：`docs/plans/2026-09-13-semantic-repair.md`。

## 1. 原则与反模式

1. **禁止写「智能修复/合并/拆分脚本」**——阈值/正则永远差一点（真实教训：
   `merge_paragraphs` v1/v2/v3 反复调参烂尾、MinerU 拆分脚本反复翻车）。
   语义判断（哪是标题/哪里断段/哪个字错）由 agent 读源文完成。
2. agent 写脚本**只允许做确定性检索/统计/搬运**（找线索、数数、批量替换已逐处确认
   的确定模式），不做语义判断。
3. **批量修复必须抽首/中/尾对照 raw 页证据**（防批量清洗静默吞内容）。
4. 修复必须留痕（`preprocessing/repairs.jsonl`）；无法确定的写 `unresolved`，不硬修。

## 2. 场景清单（按处理窗口）

### 窗口 A：解析后的文本流修复（改 structured/，翻译前）

| # | 场景 | 典型症状/信号 | agent 动作（证据 → 产物） |
|---|---|---|---|
| A1 | 硬换行/段落重组 | 行尾断句、句中断行、段落粘连 | 按语义重断/合并；对照 `raw/page-NNN.json` 或页图 |
| A2 | 跨页续段 | 页尾句被截断、下页首行续句 | 用 `source_page` 定位，合并续段 |
| A3 | 页眉/页脚/页码误清漏清 | 奇偶页不同、章首页不同；短对话行被误清 | 逐页看图判定保留/剔除 |
| A4 | 脚注/尾注/边注归属 | 正文与注区混排、注号对不上 | 分离注区，建立注码↔注文对应 |
| A5 | 多栏/异形阅读顺序 | 带框、嵌套栏、通栏标题导致错位 | 看页图按版面语义重排 |
| A6 | 跨页表格/图 | 被页边界切开、表头只在首页 | 合并或调整呈现 |
| A7 | 语义标记丢失 | 上标注号、下划线/斜粗体强调丢失 | 恢复 markdown 语义标记 |
| A8 | 重复/隐藏文本层 | PDF 白字重复层、OCR 重叠 | 去重并对照页证据 |
| A9 | 混合型 PDF | 部分页文字层坏、部分扫描 | 逐页判定哪些页改走 OCR/看图 |

### 窗口 B：OCR / 转写噪声修复

| # | 场景 | 典型症状 | 现有信号/支撑 |
|---|---|---|---|
| B1 | 字符混淆 | `l/1/I`、`O/0`、`rn/m`、`己/已/巳`、`日/曰` | —（agent 判断） |
| B2 | 西文粘连/拆词 | `delos`→`de los`、断词连字符 | `hyphen_eol` / `long_latin_run` |
| B3 | 中文误识/异体字 | 生僻字、旧字形、繁简混杂 | —（agent 判断） |
| B4 | 标点错误 | 全半角混用、引号方向、省略号/破折号 | `ascii_punct_cjk` |
| B5 | 乱码/mojibake | `Ã©`、`\ufffd` | `garbled_marks`；sniff 全书乱码率 |
| B6 | 版面噪声成字符 | 装订线、污点、框线变成乱串 | —（对照页图） |
| B7 | OCR 段落合并 | 每行独立成段（传统 OCR 必然） | `hard_wrap_lines`；`raw/pages/` |
| B8 | 多语混排 | 多语言、注音/原文夹注 | `analysis/detect.py`（参考） |
| B9 | 语音转写（前瞻） | 同音字、无标点、说话人分段 | 本轮不做（见计划 D3） |

### 窗口 C：结构与归类判断

| # | 场景 | 现有兜底 | agent 动作 |
|---|---|---|---|
| C1 | 标题判定 | `_is_chapter_heading`（字号/关键词） | 按语义定标题 |
| C2 | 层级推导 | `_derive_heading_levels`（PART/编号） | 重排 `level`（重切走 restructure） |
| C3 | 单元边界 | — | 重切/合并 + `restructure` 登记 |
| C4 | 四层归类 | `_classify_title`（关键词表） | 纠正 region/kind |
| C5 | 垃圾内容 | — | 剔除；去向记 catalog（excluded） |
| C6 | 标题残留 | `clean_pandoc_residue` / `E_RESIDUE` | 清理 |
| C7 | 目录一致性 | `W_TOC_MISSING` / `W_TOC_DEPTH` | 对账修正 |

### 窗口 D：媒体与插入元素

封面判定（多候选择一）、插图归属（整页图版 vs 内嵌 vs 装饰 vs 扫描背景）、图注/表注与
图序、表格结构恢复（无框线/合并单元格/跨页/表头）、公式 LaTeX（`inserts` 语义层）、
非线性 spine 项内联位置、媒体缺失对位。

### 窗口 E：元数据与外部知识（已有流程）

`meta` 元数据核对、`terms.csv` 术语预提取、`risks.md` 风险、`corr:` 勘误先例、
背景知识补齐（search → `references/web/`）。

### 窗口 F：翻译/审校中发现的源缺陷（回流）

定位源页核对后：影响单点措辞 → 现有 `corr:` 机制（只改 tgt + align note 留痕）；
影响段落/结构 → 回写 structured 并重译该单元（走 repairs 留痕）。

## 3. 三层机制

```text
信号层（CLI，零 token）          修复层（agent）                登记层（CLI）
─────────────────────          ─────────────────────         ─────────────────────
facts 可疑信号（每单元）   →     读 raw 证据（页图/页 JSON/     →   repairs.jsonl（留痕契约）
  hard_wrap/hyphen/dup/           MinerU full.md/源文件）           结构内容修复无需登记，
  garbled/ascii_punct/            修 structured/（内容级）           直接进 build/provenance
  latin_run                       抽样自查（首/中/尾 × 页证据）  →   restructure（边界级）：
                                                                  structure.csv 校验 +
                                                                  publication.units 更新
```

### 3.1 信号层（已接线）

`preprocess/signals.py::repair_signals` 对每单元 structured md 统计六类保守计数
（`hard_wrap_lines`/`hyphen_eol`/`duplicate_paras`/`garbled_marks`/`ascii_punct_cjk`/
`long_latin_run`），进 `facts.json`（`structure.units[].signals` + `repair_signals`
聚合）、`facts.md`「可疑信号」表；有信号时 `agent_todo` 追加「语义整备」项。
**信号是线索不是缺陷**，不进任何放行门。

### 3.2 修复留痕契约（已接线）

`preprocessing/repairs.jsonl`（agent 手写，操作级）：`{unit, kind, pages?, count?,
summary, method?, evidence?, status}`；`status ∈ done|unresolved`；`unit` 必须存在、
`kind` 枚举见 `references/repair.md`、`summary` 非空、`evidence` 为工作区相对路径
且必须存在（防杜撰）。CLI 校验（`orchestrator.read_repairs`，文件不存在零破坏；
非法 → `OrchestrationError` 带行号）；`unresolved` 进 `report.json`
（`repairs_total`/`repairs_unresolved`）并触发 `W_REPAIR_UNRESOLVED` 提示
（W 级，不阻断放行）。

### 3.3 结构重建登记（已接线）

agent 重切/合并单元后写 `preprocessing/structure.csv`（`id,region,kind,title,level,
rel_path`），运行 `auto-epublizer restructure` 登记：CLI 校验（文件在、每 md 恰一 h1
且 title 一致、无孤儿、region 与路径一致、id 唯一合法）后更新
`publication.json.units`；同 id 未变保留状态、变更单元回退 `split` 待重译；消失 id
输出孤儿产物提示。契约与操作见 `references/repair.md` / `references/structure.md`。

## 4. 与既有机制的关系

| 机制 | 分工 |
|---|---|
| `catalog.csv` | 管「源内容**收没收**」（漏收阻断） |
| `repairs.jsonl` | 管「收进来的文本**对不对**」（修复留痕；unresolved 仅告警） |
| `corr:` 勘误 | 翻译期单点源错——只改 tgt + align note 留痕，不动 src |
| G0 守恒 / fidelity | 修复后的自动防线：标记/脚注/表格守恒 + align↔structured 源保真 |
| 交付审计（`references/delivery.md`） | 修复后的全量复验：`E_ALIGN_MD_DRIFT`/成品呈现对账等 |
