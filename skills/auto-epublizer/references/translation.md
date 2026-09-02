# Translation（切片翻译 + 句对齐 + 术语闭环）

`translate` 命令读 `analysis/`，把 `structured/` 的每个单元切片翻译，写 `translation/`（镜像
structured 树）+ `align/` 句级对照表。

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

| 层次 | 来源 |
|---|---|
| 全书概览 | `analysis/overview.md` |
| 风格/全局 | `analysis/global.md` |
| 章梗概 | `analysis/units/<id>.md` |
| 重点 | `analysis/keypoints.md` |
| 术语子集 | `glossary.csv` 中本批正文实际出现的（`terms_in_text` 过滤） |
| 前文译文 | 上一批 `align/` 的 `tgt` |

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
种子(seed) ── analyze 播种 + references/user 导入
    │
注入(inject) ── 每批按 terms_in_text 过滤注入（确认态译法必须遵守）
    │
提案(propose) ── 翻译后抽取新术语/称呼变体，追加到 glossary_conflicts.jsonl
    │
裁决(resolve) ── 单线程合并：同 source 异 target 记冲突，裁决后写回 glossary.csv
```

- 冲突不自动覆盖已确认译法，保留候选待裁决（对应"译名统一 + 约定俗成"）。
- 称谓/敬称/口癖/固定表达（source-only 类型）只按完整 source 精确匹配。

## 状态机与续跑

单元：`split → analyzed → translated → aligned → reviewed → built`。`translate` 把已翻译单元置为
`aligned`；已完成单元可安全跳过。

## 双语

`--bilingual` 产出双语对照：`build --bilingual` 时按 `align/` 对照表渲染源/译交错排版，
输出 `<slug>-bi.epub`。
