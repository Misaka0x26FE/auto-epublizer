# Repair（语义整备：解析缺陷 / OCR 修正 / 结构重切）

> **定位**：凡「靠语言理解才能判对」的源文本问题，都是你的活，不是脚本的活。
> 信号由 `facts.md`「可疑信号」给出（`references/preprocessing.md` §2.0b）；本手册
> 给「读什么证据 → 怎么修 → 怎么留痕 → 怎么自查」。
> **规范**：`docs/semantic-repair.md`（场景全清单与反模式）。

## 何时做

- **信号触发**：facts.md 有「可疑信号」表 → 逐单元核对修复；
- **OCR / 扫描件路径**：无论有无信号都做一遍（传统 OCR 的换行/误识是必然项）；
- **MinerU 层级乱**：标题层级混乱、单元边界需要重切（走 restructure）；
- **翻译/审校回流**：翻译中发现缺句/重复/语义不通，定位回源（窗口 F）。

## 证据在哪（先看证据再动手）

| 证据 | 位置 | 用途 |
|---|---|---|
| 逐页文本块（含 bbox/OCR 标记） | `structured/raw/page-NNN.json` | 页边界、换行、OCR 原文 |
| 扫描页渲染图 | `structured/raw/pages/pNNN.png` | 看图判定版面/插图/页眉脚 |
| MinerU 原始产物 | `structured/raw/mineru/`（content_list.json + full.md） | 层级错乱时的 ground truth |
| 源文件 | `source/`（只读） | 终审依据 |
| 当前结构化文本 | `structured/<unit>.md` | 被修复对象 |

## 逐类操作（摘要；完整清单一览 `docs/semantic-repair.md` §2）

**A. 文本流**：硬换行按语义重断段落；跨页续段合并；页眉/页脚/页码按页图判定
（工具只兜 50% 频率法）；脚注/边注分离并建立注码↔注文对应；多栏/异形版面按阅读
顺序重排；重复文本层去重。

**B. OCR 噪声**：字符混淆（`l/1/I`、`己/已/巳`…）按语言与上下文校正；西文粘连
（`delos`→`de los`）恢复词边界；标点套用出版规范；mojibake 按语言还原；版面噪声
对照页图剔除；**每行成段必须按语义重断（禁止写阈值合并脚本）**。

**C. 结构**：标题判定（字号/代码/图注误判）、层级推导、单元边界重切/合并
（走 restructure）、四层归类纠正、垃圾页剔除（去向记 `catalog.csv`）。

**D. 媒体**：封面多候选择一；插图归属（整页图版/内嵌/装饰/扫描背景）；图注与图序；
表格结构恢复（无框线/合并单元格/跨页/表头）；公式 LaTeX（`inserts` 语义层）。

**E/F. 元数据与源缺陷回流**：`meta` 核对；翻译期单点源错走 `corr:`；影响段落/结构
的源缺陷回写 structured 并重译该单元。

## 留痕：`preprocessing/repairs.jsonl`（操作级，每行一个修复动作）

```json
{"unit": "ch03", "kind": "line_join", "pages": [12, 13], "count": 18,
 "summary": "OCR 每行成段，按语义重断合并", "method": "逐页看图 + 手动重排",
 "evidence": "structured/raw/pages/p012.png", "status": "done"}
```

- `unit`：必填，必须是 `publication.json` 中的单元；
- `kind`：`line_join|hyphen|ocr_char|mojibake|punct|header_footer|footnote|order|
  heading|boundary|classification|garbage|media|metadata|other`；
- `pages` / `count`：可选（源页号 / 影响处数）；
- `summary`：必填（做了什么）；`method`：可选（怎么做）；
- `evidence`：可选，工作区相对路径且**必须存在**（页图/页 JSON/MinerU 产物）；
- `status`：`done`（已修）或 `unresolved`（无法确定，勿硬修；qa 会提示）。

## 结构重建：`preprocessing/structure.csv` + `restructure`

只按前 S 级切单元、更深标题留单元内，或干脆手动重切/合并：

```csv
id,region,kind,title,level,rel_path
ch01,body,chapter,第一章 缘起,1,body/ch01.md
ch02,body,chapter,第二章 入城,1,body/ch02.md
```

```bash
auto-epublizer restructure      # 校验 + 更新 publication.units（同 id 未变保留状态）
```

- `rel_path` 必须在 `structured/` 内、文件必须存在；每个 md 首行 `# 标题` 与
  `title` 一致；`structured/`（除 raw/）不得有未登记的孤儿 md；
- 单元内容有变 → 状态回退 `split`（需重译重 import）；消失单元提示孤儿产物。

## 自查三件事（批量修复后必做）

1. **守恒**：grep 标记（`{fig:NNN}`）/脚注（`[^label]`）/图片引用数量与修复前一致
   （丢失会被 G0/交付审计阻断）；
2. **抽样**：首/中/尾各抽若干页，与 `raw/` 页证据对照，确认没有静默吞内容；
3. **无法确定**：写 `status: unresolved` 并说明，不要「猜着修」。

## 反模式（再强调）

- 不要写「智能合并/拆分/清洗脚本」——阈值永远差一点（真实教训反复翻车）；
- 脚本只做确定性检索/统计/搬运；语义判断（哪是标题/哪里断段/哪个字错）由你自己读；
- 修复后必须重走 `import`（md↔align 不一致会阻断）与全量验证。
