# Review（六道关 QC 操作指引）

> 排障与放行判读速查（错误码全集/条件全集）见 `references/invariants.md`。

六道关按成本分层：G0/G4/G5 是 CLI 确定性校验（零 token）；G1–G3 的**语义审校是 agent
任务**（唯一 LLM 原则）——你用自身能力读双语对照找问题、裁决、修订，并把产物按契约写进
`reviews/review-<ts>/`，`qa` 从 `result.json` 读 g1/g2/g3 计数与收敛状态。

## 关卡总览

| 关卡 | 做什么 | 谁做 | 产出 |
|---|---|---|---|
| G0 | 零 token 静态校验（对照表完整性/长度比/术语命中/标记守恒/脚注守恒/源保真） | CLI（`g0`/`import`） | 静态告警列表 |
| G1 | 逐段双语审校（漏译/增译/误译/术语/人称） | agent | `issues` 候选 |
| G2 | 证据取证复核（回源文/上下文确认） | agent | `issues` 确认/驳回 |
| G3 | 仲裁 + 修订 + 收敛判定 | agent | `patches` + `termination` |
| G4 | EPUB 结构 QA（epubcheck + 解包审计） | CLI（`qa`） | 结构审计报告 |
| G5 | 交付验收（汇总 + 放行清单） | CLI（`qa`） | `report.json` |

## 审校产物契约（agent 手写）

产出 `reviews/review-<ts>/`：

```text
reviews/review-<ts>/
├── metadata.json         # 内容摘要 + 审校配置指纹
├── issues.json           # 本轮发现的问题（G1–G2 确认后）
├── patches.json          # 修订建议（G3）
├── summary.md            # 审校小结
└── result.json           # 终局：issue_count / termination / rounds（qa 读取）
```

`result.json` 键（qa 契约；缺省按 0，`issue_count` 是 `g2_confirmed` 的旧回退键）：

```json
{
  "g1_candidates": 0,
  "g2_confirmed": 0,
  "g3_patched": 0,
  "termination": "clean_confirmed",
  "rounds": 2
}
```

审校通过（`termination == "clean_confirmed"`）后，用 `auto-epublizer import --reviewed`
把处于 `aligned` 的单元推进 `reviewed`（幂等；已 reviewed/built 的单元跳过重导）。
若你的修订改动了 `translation/`+`align/`，先重新 `import`（回到 aligned）再
`import --reviewed`。

## termination（收敛终态）

| 值 | 含义 | 下一步 |
|---|---|---|
| `clean_confirmed` | 连续 N 轮无 issue | 可进入 build |
| `max_rounds` | 达轮数上限仍未收敛 | 人工检查遗留 issue |
| `no_progress` | 修订摘要出现 A↔B 循环 | 振荡，人工介入裁决 |
| `unresolved_fixes` | 无法修订的句子积压 | 人工处理 |

## G1 抽样策略

小书（≤10 单元）全审。大部头按**章节类型 × 高风险特征**分层抽样，高风险必审：
论证密集/表格、脚注、引文密集/多语材料/OCR 存疑段（对齐 `risks.md` 与
`preprocessing/units/<id>.md` 的风险标注）/复杂版式/**每章首尾单元**；其余随机抽查。

## G1 问题类型（宁缺毋滥）

`missing`（漏译）/ `added`（增译）/ `mistranslation`（误译）/ `terminology`（术语违例）/
`pronoun`（人称/性别错误）。合理语序调整、自然意译、风格润色**不算问题**，拿不准不报。

## 修订与盲复审

- 修订先出 `patches.json`（"最小修改的完整单句替换"），确认后再改 `translation/`+
  `align/`（改后重新 `import`）；正式 `translation/`、`glossary.csv`、`publication.json`
  不要绕过 import 直接手改。
- 下一轮审校不传旧问题说明，只读修订后的译文（盲审），防止"按说明书打勾"。

## 术语冲突仲裁

跨段对同一术语/人称/固定表达给出矛盾译法时，应外置到 `analysis/glossary_conflicts.jsonl`
并终局裁决；同一词多种译法并存（如赤区/苏区）是"最隐蔽的质量问题"，裁决后写回
`analysis/glossary.csv`（权威）。

## G4 / G5（见 qa.md 与 build.md）

- G4：`auto-epublizer qa` 跑 epubcheck（零 error）+ 解包逐项审计（mimetype 首位未压缩、
  container 指向 OPF、manifest/spine 可解析、nav 链接可解析、URL 安全、lang 正确、每章一个 h1）。
- G5 放行条件：`g2_confirmed == 0` 或全部已修订；`g0_terminology_open == 0`（术语命中清零）；
  `g4_epubcheck_errors == 0`（且 epubcheck 实际运行）；`g4_audit == "pass"`；
  溯源完整（`provenance_coverage ≈ 1.0`、三边对账/媒体溯源零缺失、目录层级不扁平、
  溯源 findings 无 error 级）。

## 验收阈值（默认）

| 指标 | 阈值 |
|---|---|
| 长度比 | `0.30 ≤ len(tgt)/len(src) ≤ 3.0`（G0 告警，advisory） |
| **插入标记守恒** | **`{fig:NNN}` 等标记 src/tgt 单元级总量一致（硬缺陷；未清零 G5 报 `structure_open`）** |
| **脚注守恒** | **pandoc `[^label]` 与句末数字注码总量一致（硬缺陷，同上）** |
| **术语冲突** | **`glossary_conflicts_open == 0`（裁决写回 glossary.csv 前 qa 不放行，`glossary_conflict_open`）** |
| **术语命中** | **0（G0 `terminology` 是真实缺陷，不是 advisory——译文缺了术语表源词；必须逐条核验清零，否则 G5 不放行，`released_reason=terminology_open`）** |
| 空译文 | 禁止（`import` 阻断该单元） |
| 差错率 | `confirmed_issues / 总句数 ≤ 1e-4`（agent 自查参考，非 CLI 硬门） |
| epubcheck | 0 error（且须实际运行；jar 缺失 → `epubcheck_not_run`） |

> 说明：G0 可独立运行——`auto-epublizer g0` 在翻译/导入后立即校验。
> **G0 告警分两类，处理方式不同**：
> - `terminology`（术语命中）：**真实缺陷**，CLI 以红色 `✗` 标出，`import` 也会单独
>   计数提示；必须逐条核对译文/术语表后清零（补译 / 修术语表 / 声明例外）才能放行。
>   豆包实测教训：曾把术语未命中与长度误报混为一谈全当噪声，漏掉真问题。
> - `length`（长度比过低/过高）：advisory，英→中长度比天然偏低会大量误报，不作为
>   放行硬条件；但**抽样核对**是否真漏译（尤其超长句被省略号收尾的段落）。
>
> G1–G3 由你审校后写 `result.json`；全局理解上下文在 `analysis/` 缺失时回退
> `preprocessing/global.md`。G4 由 `qa` 命令驱动；G5 由 `qa` 聚合 G0–G4 写
> `report.json`（含 `error_rate`/`released`/`released_reason`）。

## 翻译期间的过程校验（QC 落实，豆包实测教训）

- **每译 3–5 个单元 build 一次**：格式契约问题当轮暴露（图片段缺 `<img>` 行、
  空行破坏、转义残留），避免一次污染多个单元到最后集中返工。
- 每个单元写完即 `import --unit <id>` 登记 + `g0 --unit <id>` 校验，术语告警当场处理。
- 标题在开工前一次性定稿进 `preprocessing/plan.md`，不在翻译中途改。
