> **中文** | [English](translation.md)

# Translation（切片翻译 + 句对齐 + 术语闭环）

翻译是 **agent 任务**（唯一 LLM 原则）：agent 读 `structured/<rel_path>.md`，用自身能力
逐段翻译，写 `translation/<rel_path>.md`（镜像结构）+ `translation/align/<unit-id>.jsonl`
（`{seq, src, tgt, note}`），然后**必须**跑 `auto-epublizer import` 登记——G0 结构校验
（seq 断号/空译文阻断）+ 状态推进（translated→aligned）+ 术语冲突外置。
未 import 前单元状态停在 `analyzed`，`status --json` 会报 stale。

## 产出

```text
translation/
├── body/ch01.md ...      # 译文（镜像 structured 相对路径）
└── align/ch01.jsonl      # 句级对照表
```

## 翻译时参考上下文（读取优先级）

翻译前先读理解层产物，保证前后一致：

| 层次 | 来源（`analysis/` 缺失时回退 `preprocessing/`） |
|---|---|
| 全书概览 | `analysis/overview.md` 或 `preprocessing/global.md` |
| 风格/全局 | `analysis/global.md` 或 `preprocessing/global.md` |
| 章梗概 | `analysis/units/<id>.md` 或 `preprocessing/units/<id>.md` |
| 重点 | `analysis/keypoints.md` |
| 术语子集 | `glossary.csv` 中本批正文实际出现的（`terms_in_text` 过滤） |
| 前文译文 | 已完成的 `align/` 的 `tgt`（保持术语/风格连续性） |

两者共存时 `analysis/` 优先；纯 agent 预处理路径用 `preprocessing/`。

## 句级对齐

`translation/align/<id>.jsonl` 每行一句：

```jsonl
{"seq": 1, "src": "原句", "tgt": "译句", "note": null}
```

- `seq` 是翻译验证、保真审校、QA 定位及断点续跑的锚点，从 1 起连续。
- 段级等长：一个源段通常对应一句（或多句）；拆句/并句在 `note` 声明；
  `note` 记录拆/并句/漏译/存疑（前缀 `corr:wrong→right` 记源文勘误先例）。

空 align 仅在现有、非空的 `structured/` 与 `translation/` 文档**双方都只有规范 ATX 标题行和空行**时允许；缺失/空源文、标题后无空行紧接正文或译文多出正文均不适用。import 与 G0/QA 共用此判定，`heading` 逐层守恒仍须通过。

### 块身份（段落 ↔ 连续句区间）

段落身份**不写进 align 列**：每行仍是句。块由 `content_blocks` 定义（跳过标题/纯注释，
围栏代码独立成块，块号从 1 起，与逐段覆盖率、源保真用同一切块）。一个块对应 align 的
一段**连续** `seq`；多句同块是常态，拆句/并句只改句数，不改块身份。

- 合法：一段多句；一句拆成多行（`note=split`）；重复句按顺序各占各行；只改换行/缩进。
- 结构变化：块合并/拆分、块增删、乱序、把一句分到两个块——须由 import 重新登记基线。
- 推导失败（缺句、顺序不符）输出 issue，不猜边界；历史工作区没有基线时状态为 unknown。
- 基线是块号/类型/seq 区间/块文本摘要的哈希（`review/blocks.py:structure_digest`），
  import 成功时写入 `publication.json` 单元的 `meta.align_structure`；只改块内换行不会使基线失效。
  `qa`/交付审计重新推导并比对：有基线不一致报块边界缺陷（`E_ALIGN_MD_DRIFT`），无基线或
  映射歧义报 `align_structure_unknown`，不阻断历史书迁移。`import --force` 会重新登记。
- **源块与译块各自编号，不要求数量相等**：源块身份用于源保真/覆盖率，译块身份用于
  md↔align 漂移；二者只通过 align 的 `src` 句建立对应。不能用「行数=段数」或
  「全文归一化相等」代替边界核对。

### 只读重建提案

`auto-epublizer align-propose --workspace <dir> [--unit ch01]` 输出 JSON 且不写任何正式文件：
`mappings[]` 给出 `status`（`exact` / `merge` / `split` / `propose` / `unmatched`）、
`source_blocks`、`seq_range`、复用的已核验 `rows`、`uncovered` 源块和 `issues`。

- 对应关系由块与 seq 区间重叠建立，不做跨语言字面相似判断；重复句、OCR 缺行、大幅改写
  不会被自动认可。
- `propose` 表示该译文块没有 align 行覆盖：只列候选，不出行；拆句源归属由 agent 核证后
  再写 align。
- 提案不是应用结果；写入必须走 B4 的显式事务（`repair apply --apply` 同族入口）。

### 显式应用与恢复

```bash
auto-epublizer align-apply plan.json --workspace <dir>          # 默认只读预检
auto-epublizer align-apply plan.json --workspace <dir> --apply  # 明确写入
```

计划绑定源件、`translation/`、`align/` 的 SHA-256；预检不通过或预检后文件变化即拒绝。
写入前先落含旧字节的事务日志，任一失败整组恢复旧件；成功后重新登记
`meta.align_structure` 与导入摘要，并把 `reviewed`/`built` 回退到 `aligned`——
旧审校与成品结论随摘要失效，须重走 `import`/审校/构建。`already_applied` 只在
对照表字节与新基线都一致时返回，不重放已变化的文件。

### 只读卫生扫描

`auto-epublizer hygiene --workspace <dir> [--unit ch01]` 输出 JSON（`writes: false`），
逐条给出 `unit`、`block`、`seq_range`、`context` 和候选类型：残留原语词、引号/括号失衡、
相邻重复词、半句边界、超长段、疑似丢尾。译注 `translation/notes.json` 一并扫描（带
`note_id`）。

- 全部为 **advisory**：只定位候选，不判断词义、不改文本、不替代 agent 审校。
- 负对照：围栏/行内代码不参与；书目/索引/术语表单元跳过；缩写点不报半句；
  冒号引导句的下一块存在时不报丢尾；引号在整单元范围配对，允许跨段引文。
- 候选要人工核证；确属缺陷走 `repair apply`/重建流程，不能按扫描器输出批量改写。

## 特殊段处理（PDF 内容提取产物）

PDF ingest 会产出三类非纯文本段（来源见 `references/ingest.md`；描述文件在
`structured/raw/inserts/`）。翻译时按类型处理：

| 段形态 | 处理 |
|---|---|
| 图片引用段：`![p012-img01](raw/media/…)` | **原样保留**，不翻译 alt（alt 是 inserts id，非内容）；译文段与源段一致即可通过 G0 |
| 公式段：`$$原始抽取文本$$` | 保留 `$$…$$` 包裹；内部公式文本**不做翻译**（多为符号乱串，译文保持原样；真实 LaTeX 进 inserts 的 `latex`，见下节） |
| markdown 表格段：`\| a \| b \|…` | 翻译**单元格文字**，保留管道符/分隔行/对齐结构；表格两端不要加空行合并 |

## inserts 补全（agent 任务：语义字段）

`raw/inserts/<id>.json` 的确定性字段（id/type/source/file）由 CLI 生成；
**语义字段由你补全**——时机：该单元翻译完成后、跑 `qa` 之前。provenance 审计以
`<id>.json` 单文件为权威（`index.jsonl` 只是快照，可不改）：

1. **必做·所有记录**：按 `source.page` 回源页（PDF 查看器翻到该页）核对内容，
   写 `content_desc`——这个插图/表格/公式**讲什么、为什么出现在此处**（一两句即可）；
2. **formula 记录**：手写 `latex`（依据 `source.bbox` 定位页内公式；`$$…$$` 里的
   原始抽取文本仅供参考，以图为准）；
3. 可选：确认文件在盘（`source.file` 对应 `structured/raw/<file>`）——缺失会报
   `E_INSERT_MISSING_FILE`，见 `references/qa.md`。

不补全不阻断构建（W 级 warning），但 `content_desc` 会进 EPUB 的图片 alt/说明位，
空描述直接影响成品质量——**视为必做**。

## 术语三态闭环

```text
种子(seed) ── agent 撰写 glossary.csv + references/user 导入（preprocessing/terms.csv 预提取）
    │
注入(inject) ── 按 terms_in_text 过滤注入（确认态译法必须遵守）
    │
登记(import) ── 术语冲突检测，同 source 异 target 记冲突
    │
外置(record) ── 冲突追加到 analysis/glossary_conflicts.jsonl（import 自动完成）
    │
裁决(resolve) ── agent 读冲突文件终局裁决，写回 glossary.csv（权威）
    │
回写统一库 ── knowledge import：工作区已确认术语合并进统一库（跨书复用 + 自动 git 提交）
```

**裁决写回 glossary.csv 后，对全部已译单元重跑 `g0`**——旧译法违例（terminology）
当场清零，不要只查新译单元；未决冲突未写回前 `qa` 不放行（`glossary_conflict_open`）。

保留原文书名/引文等确有证据的例外，可写可选的
`preprocessing/terminology_exemptions.csv`，必需列为 `unit,source,reason`：
按单元与术语表 canonical source 精确匹配，`reason` 写回源核证理由；不得批量豁免真实误译。
完全空行跳过，部分空行或空白理由会报错；文件缺失表示无豁免。
命中输出为 `terminology_exempt`（`blocking=false`、`data.reason`），在 import 告警、
独立 `g0` 与 QA 的 `g0_flags` 三处可见；其他术语违例仍阻断。报告失效规则见 `qa.md`。

- **跨书复用**：开工先用 `knowledge export` 从统一库播种 `preprocessing/terms.csv`；
  本工作区术语定稿后用 `knowledge import` 回写统一库（默认 `~/Documents/auto-epublizer/`，
  私有 git 仓库，可 `knowledge push` 跨设备同步）；跨书同键异译外置到统一库
  `conflicts.jsonl` 待你裁决。

- 冲突不自动覆盖已确认译法，保留候选待裁决（对应"译名统一 + 约定俗成"）。
- `import --terms <csv>` 可批量导入 agent 提取的新术语提案（三态自动判定：新 source→seed，
  与 confirmed 异译→conflict）。
- 称谓/敬称/口癖/固定表达（source-only 类型）是文体档案的分类标注；
  术语命中检查对所有类型统一按字面/词边界匹配。
- **语言一致性门**：`src` 与 `tgt` 归一化后**逐字相同**是须核证的复制信号，不是语义证明；判**硬门待办**
  （`language`，import 阻断）。只对**正文行**成立：标题行、图片/链接行、注码定位行、
  属性锚点行等页面家具按体例保留原文，不在本门内。
  文献著录体例（书名/刊名/出版社/档号/索引条目/ISBN 等按体例保留原文）需要豁免时，
  写可选的 `preprocessing/style_exemptions.csv`，必需列为 `unit,pattern,style_ref,reason`：
  `pattern` 是正则（空 = 整单元），`style_ref` 指向该书 `analysis/style.md` 的体例条目，
  `reason` 写回核证理由。命中输出为 `language_exempt`（`blocking=false`），
  在 import 告警、独立 `g0` 与 QA 的 `g0_flags` 三处可见；未豁免的同类行仍阻断。
  示例（只豁免著录块，不豁免同章复制正文）：

  ```csv
  unit,pattern,style_ref,reason
  ch07,^Müller, Hans\.,§5,§5 文献著录体例：按体例保留德文书目
  ```

  同一单元里 `This copied body sentence…` 仍报 blocking `language`；空译文始终阻断，
  不会被体例正则豁免。`language_exempt` 的 `data` 带命中 `seq` 与源句 `head` 作为
  块级证据，改稿或改体例后报告摘要失效。
  `style_ref` 必须非空，且能定位现存 `analysis/style.md` 的条目（例如 `§5` 对应 `## 5.`）；
  依据和 CSV 改动均使报告过期。不得以整单元豁免覆盖用户明确要求中文化的索引。
  内嵌脚注标记不豁免正文；非 ASCII 字母同样检查；代码字面量不作为待译正文，
  已明确同源/目标语的转换不要求翻译。
  判据只看剔除标题/家具及代码后的正文：中文标题不能掩盖复制的外语正文；中文目标中
  汉字占正文全部字母/汉字不足一半时，少量夹杂汉字不豁免复制信号。此为待核证启发式，
  不证明实际语言或误译；代码字面量不计入严重短译的源/目标字数。
- **严重短译待核证门**：独立于原有 0.30 比值 advisory；剔除独立家具/代码后源正文
  至少 80 个字母/汉字、非空译文仅余至多 4 个字母/汉字时，输出 blocking `length_review`。
  须回源补译或用体例表的**非空、针对该源句的正则**及成文依据核证，命中输出
  `length_review_exempt`。空译文始终阻断，不能被豁免。这不覆盖所有语义漏译。
- **src 原样摘抄**：align 每行 `src` 必须原样取自 `structured/`（含标题行也可作
  src）——import 做源保真校验，被改写/截断/杜撰的 src 会阻断登记（源文勘误只改
  `tgt` 并用 note `corr:` 留痕，不要顺手改 src）。
- **表格形状必须与源一致**：md 管道表格的表数与每个表的行列数在译文中须与
  `structured/` 相同（单元格内容正常翻译，结构不动）——import 硬校验，
  违例阻断登记（`table`）。
- **标记一个都不能丢**：`{fig:NNN}` 插入标记与脚注标记（`[^label]`/句末数字）在
  译文中必须与源文总量一致（拆句/并句可挪位，不可丢）——G0 单元级守恒校验，
  丢失即硬缺陷（`marker`/`footnote`），阻断 G5 放行。

## 状态机与续跑

单元：`split → analyzed → translated → aligned → reviewed → built`。`import` 把完成单元
置为 `aligned`；重复 import 无害（幂等）。审校通过后 `import --reviewed` 可在同次调用中把新验证通过的单元推进为
`reviewed`（幂等）；`reviewed`/`built` 单元通常跳过重导；强制重验失败不得再提升为 reviewed。

成功导入后 CLI 登记 structured/translation/align 的字节摘要。已完成单元若字节变化，普通 import 报 `E_STATE_DRIFT`，而非静默跳过；`status --json` 的单元 `content_state` 为 `current/changed/unknown`，并给出当前 `content_digests`。源正文变化先核证并 `restructure`；仅译文/align 修订用 `import --unit ID --force` 重校验。旧工作区无导入摘要时标为 unknown，跳过详情提示显式重验；未变单元仍幂等跳过。`--force` 只校验已写入的 translation/align，不负责从 `.work` 等自建中间文件组装译稿。
