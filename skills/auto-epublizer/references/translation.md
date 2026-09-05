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

- `seq` 是双语排版、QA 定位、断点续跑的锚点，从 1 起连续。
- 段级等长：一个源段通常对应一句（或多句）；拆句/并句在 `note` 声明；
  `note` 记录拆/并句/漏译/存疑（前缀 `corr:wrong→right` 记源文勘误先例）。

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
```

- 冲突不自动覆盖已确认译法，保留候选待裁决（对应"译名统一 + 约定俗成"）。
- `import --terms <csv>` 可批量导入 agent 提取的新术语提案（三态自动判定：新 source→seed，
  与 confirmed 异译→conflict）。
- 称谓/敬称/口癖/固定表达（source-only 类型）只按完整 source 精确匹配。

## 状态机与续跑

单元：`split → analyzed → translated → aligned → reviewed → built`。`import` 把完成单元
置为 `aligned`；重复 import 无害（幂等）。已完成单元可安全跳过。

## 双语

`--bilingual` 产出双语对照：`build --bilingual` 时按 `align/` 对照表渲染源/译交错排版，
输出 `<slug>-bi.epub`。
