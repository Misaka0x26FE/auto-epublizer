# 翻译流程设计

在传统"切片翻译"（`split/` → 分批译）基础上，加入**章节目录结构划分**与
**全本 → 章节 → 重点内容的分层理解 + 术语表辅助**，作为质量控制的输入。
范围沿用：只负责交付质量，不做价值观判断；翻译引擎为 OpenAI 兼容 API。

## 1. 总体流程

```text
source ──ingest──▶ structured/（章节目录结构划分，四层结构）
                       │
                       ▼
                   analyze/（分层理解：overview 全本 + global 全局 + units 章节 + keypoints 重点
                       │      + glossary 术语表 + characters 人物表）
                       ▼
                   translate（切片翻译：章节 → 段落 → 批次 → 句对）
                       │
                       ▼
                   translation/ + align/（句级对照表）
                       │
                       ▼
                   review（QC G0–G3）→ build → qa（G4–G5）
```

## 2. 章节目录结构划分（切片的基础单元）

`structured/` 按出版物四层结构拆成**单元（unit）**，每个单元一个文件、一个稳定 ID：

```text
structured/
├── frontmatter/{titlepage,copyright,dedication,foreword,preface,toc}.md
├── body/ch01.md            # 正文单元（翻译主战场）
├── backmatter/{afterword,appendix,notes,bibliography,index}.md
└── media/…
```

- **单元 = 翻译的最小可管理单位**，状态机：`pending → split → analyzed → translated → aligned → reviewed → built`。
- 每个源文单元对应一个译文单元（`translation/<镜像路径>/<id>.md`）+ 一个句级对照表（`translation/align/<id>.jsonl`）。
- 切片的"片"是**批次（batch）**，不是章节；章节是调度与状态管理的边界，批次是发给模型的边界。

## 3. 切片机制（chunking）

在单元内部，把段落（Segment）按字符预算打包成批次：

| 参数 | 默认 | 说明 |
|---|---|---|
| `max_chars_per_segment` | 1200 | 单段超过则按句末标点再拆，续段标 `cont` 回并 |
| `max_chars_per_batch` | 1800 | 一个批次（句群）目标大小，按字符估算 token |
| `rolling_context_segments` | 6 | 注入前文译文尾段数 |
| `align_retry_limit` | 2 | 句对数量不符时的重试次数 |

- 段落 = Segment（最小可对齐单元），一段对应源/译文各一个；
- 批次 = 若干段落，一次发给模型，模型**必须返回等长句对 JSON**；
- 超长段拆成多段，续段 `cont=True`、无独立 anchor，回填时并回原段；
- 批次边界 = 断点续跑检查点（`.progress.json` 记录每章译到第几批）。

## 4. 分层理解注入（全本 → 章节 → 重点）

翻译每个批次前，按"静态 → 动态"顺序组装上下文（前缀缓存友好，沿用 wenyi 经验）：

| 层次 | 来源文件 | 内容 | 稳定性 |
|---|---|---|---|
| 全书概览 | `analysis/overview.md` | 主线、人物弧光、伏笔、结局 | 书级静态 |
| 风格指南/全局 | `analysis/global.md` | 叙事人称、语气、语域、对话风格、跨章依赖 | 书级静态 |
| 本章梗概 | `analysis/units/<id>.md` | 本章情节/论证推进、登场人物、术语注意 | 章级静态 |
| 重点内容 | `analysis/keypoints.md` | 高风险段落、复杂排版、多语片段提醒 | 书级静态（命中注入） |
| 术语子集 | `glossary.db` / `glossary.csv` | 本批正文**实际出现**的术语（`terms_in_text`） | 批级动态 |
| 前文译文 | 上一批 `align/` 的 `tgt` | 最近 N 段，保持代词/称谓/语气衔接 | 批级动态 |
| 待译正文 | 本批 `src` 段落（带编号） | 翻译对象 | 批级动态 |

> prompt 结构（对应 wenyi 缓存约定）：system 全静态；user 按"风格/概览 → 章梗概 →
> 重点 → 术语表 → 前文译文 → 待译正文"排列，越靠前越稳定，命中越多前缀缓存。

## 5. 翻译批次数据流（切片 → 句对）

```
段落数组 [p0, p1, …] + 分层上下文 + 术语子集
        │  （一次 LLM 调用，json_mode）
        ▼
{"translations": [ [句, 句, …], [句, …], … ]}   ← 每个段落返回一句或数句
        │  （校验：段数一致，否则 align_retry_limit 次重试，再逐段兜底）
        ▼
align/<id>.jsonl  ← {seq, src, tgt, note}
```

关键保证：

1. **段级等长**：输入 N 段，输出必须 N 项（每项是该段的译文句数组），数量不符重试、逐段兜底——从结构上杜绝整段漏译。
2. **句级对齐**：每段译文按句拆开，与原句一一对应，写入 `align/<id>.jsonl` 的 `{seq, src, tgt, note}`；拆句/并句在 `note` 声明。这是 QC G0（对照表完整性）与双语排版的唯一来源。
3. **续段回并**：`cont=True` 的续段译文回并到上一段，不另起段落。

## 6. 术语表辅助（三态闭环）

```text
种子(seed) ── analyze 播种 + references/user 导入
    │
    ▼
注入(inject) ── 每批按 terms_in_text 过滤后注入 prompt（确认态译法必须遵守）
    │
    ▼
提案(propose) ── 翻译后抽取新术语/称呼变体，追加到 glossary_conflicts.jsonl
    │
    ▼
裁决(resolve) ── 单线程合并：同 source 异 target 记冲突，人工/agent 确认后写回 glossary.csv
```

- 称谓/敬称/口癖/固定表达只按完整 source 精确匹配，避免裸名 alias 误注入；
- 冲突不自动覆盖已确认译法，保留候选待裁决（对应传统"译名统一 + 约定俗成"）。

## 7. 状态机与续跑

- 单元：`pending → split → analyzed → translated → aligned → reviewed → built`。
- `.progress.json` 记录每单元译到第几批、每句对齐状态；中断后同命令续跑，已完成批次安全跳过。
- 改术语表/理解/解析缓存时，须覆盖受影响单元的中断后续跑（与 RunStore 不变量一致）。

## 8. 与质量控制的衔接

| 翻译环节 | 对应的 QC 关卡 |
|---|---|
| 句级对齐产出 `align/` | G0 对照表完整性、句数一致、长度比、空译文 |
| 术语注入 → 译文术语 | G0 术语命中（确定性）+ G1 术语违例 + G2 裁决 |
| 分层理解注入 | 翻译一致性（代词/称谓/语气），G1 审校的上下文依据 |
| 切片批次 | 断点续跑粒度 + G1 逐批审校粒度 |

## 9. 与传统切片翻译的差异

| 传统切片 | 本项目 |
|---|---|
| `split/NNNN.md` 纯文本切片 | `structured/` 章节目录结构 + 稳定单元 ID |
| `_analysis.md` / `_understanding.md` 单文件 | `analysis/` 分层：overview/global/units/keypoints |
| `GLOSSARY.csv` 人工维护 | glossary 三态 + 冲突外置 + 注入过滤 |
| 译后无句级对齐 | `align/<id>.jsonl` 句级对照表（QC 与双语的锚点） |
| 无 QC 闭环 | 翻译 → G0–G3 审校闭环 |
