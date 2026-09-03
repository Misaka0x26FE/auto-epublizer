# Translation（切片翻译 + 句对齐 + 术语闭环）

翻译有两条等价路径，产物同构（`translation/` 镜像 structured 树 + `align/` 句级对照表），
汇入同一套 G0 校验、状态机与构建：

- **路径 A（CLI 内部 LLM）**：`translate` 命令，读 `analysis/` 自动翻译。
- **路径 B（agent 手写，无 LLM Key 环境）**：agent 读 `structured/<rel_path>.md`，
  用自身能力逐段翻译，写 `translation/<rel_path>.md`（镜像结构）+
  `translation/align/<unit-id>.jsonl`（`{seq, src, tgt, note}`），然后**必须**跑
  `auto-epublizer import` 登记——G0 结构校验（seq 断号/空译文阻断）+ 状态推进
  （translated→aligned）+ 术语冲突外置。未 import 前单元状态停在 `analyzed`，
  `status --json` 会报 stale。

## 产出

```text
translation/
├── body/ch01.md ...      # 译文（镜像 structured 相对路径）
└── align/ch01.jsonl      # 句级对照表
```

## 切片机制

| 参数 | 默认 | 说明 |
|---|---|---|
| `max_chars_per_segment` | 1200 | 单段超过则按句末标点再拆，续段标 `cont` 回并 |
| `max_chars_per_batch` | 1800 | 一个批次（句群）目标大小 |
| `rolling_context_segments` | 6 | 注入前文译文尾段数 |

- 段落 = Segment（最小可对齐单元）；批次 = 若干段落，一次 LLM 调用，**必须返回等长句对 JSON**。
- 超长段拆成多段，续段 `cont=True` 回并到上一段，不另起段落。

## 分层上下文注入（静态 → 动态）

`system` 放文体指引 + 语言指引 + 标点规则；`user` 按"风格/概览 → 章梗概 → 重点 → 术语子集 →
前文译文 → 待译正文"排列，越靠前越稳定。

| 层次 | 来源（`analysis/` 缺失时回退 `preprocessing/`） |
|---|---|
| 全书概览 | `analysis/overview.md` 或 `preprocessing/global.md` |
| 风格/全局 | `analysis/global.md` 或 `preprocessing/global.md` |
| 章梗概 | `analysis/units/<id>.md` 或 `preprocessing/units/<id>.md` |
| 重点 | `analysis/keypoints.md` |
| 术语子集 | `glossary.csv` 中本批正文实际出现的（`terms_in_text` 过滤） |
| 前文译文 | 上一批 `align/` 的 `tgt` |

两者共存时 `analysis/` 优先（LLM 路径产物）；纯 agent 预处理路径用 `preprocessing/`。

## 句级对齐

`translation/align/<id>.jsonl` 每行一句：

```jsonl
{"seq": 1, "src": "原句", "tgt": "译句", "note": null}
```

- `seq` 是双语排版、QA 定位、断点续跑的锚点。
- 段级等长：输入 N 段，输出 N 项；数量不符重试（`align_retry_limit`），再逐段兜底。
- 拆句/并句在 `note` 声明；`note` 记录拆/并句/漏译/存疑。

## 术语三态闭环

```text
种子(seed) ── analyze 播种（LLM）/ agent 撰写 glossary.csv + references/user 导入
    │
注入(inject) ── 每批按 terms_in_text 过滤注入（确认态译法必须遵守）
    │
登记(import/translate) ── 术语冲突检测，同 source 异 target 记冲突
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

单元：`split → analyzed → translated → aligned → reviewed → built`。路径 A 的 `translate` 与
路径 B 的 `import` 都把完成单元置为 `aligned`；已完成单元可安全跳过（translate）/重复 import 无害。

## 双语

`--bilingual` 产出双语对照：`build --bilingual` 时按 `align/` 对照表渲染源/译交错排版，
输出 `<slug>-bi.epub`。
