# Review（六道关 QC 操作指引）

六道关按成本分层：先零 token，再 cheap 档，再 strong 档，按需升级。`review` 命令跑 G1–G3 收敛循环，
`qa` 命令跑 G4，G5 是交付前的终局汇总。

## 关卡总览

| 关卡 | 做什么 | 成本 | 产出 |
|---|---|---|---|
| G0 | 零 token 静态校验（对照表完整性/句数一致/长度比/术语命中/标点/残留） | 0 | 静态告警列表 |
| G1 | 逐批双语审校（cheap 档 Reviewer） | cheap | `issues` 候选 |
| G2 | 证据取证复核（strong 档 Agent Loop） | strong | `issues` 确认/驳回 |
| G3 | 冲突仲裁 + 影子修订 + 盲复审收敛 | strong | `patches` + 收敛判定 |
| G4 | EPUB 结构 QA（epubcheck + 解包审计） | 0（本地） | 结构审计报告 |
| G5 | 交付验收（汇总 + 放行清单） | 0 | `report.json` |

## 运行与产物

```bash
auto-epublizer review [--workspace <dir>]
```

产出 `reviews/review-<ts>/`：

```text
reviews/review-<ts>/
├── metadata.json         # 内容摘要 + 审校配置指纹
├── rounds/<n>/{issues,patches,summary}.json   # 每轮问题/补丁/小结
├── shadow_overlay.json   # 影子译文覆盖（不改正式 translation/）
└── result.json           # 终局：issue_count / termination / rounds
```

## 审校结果判读

```bash
auto-epublizer review ...   # 输出：issue=N 收敛=<termination> 轮次=<rounds>
```

`termination`（收敛终态）含义：

| 值 | 含义 | 下一步 |
|---|---|---|
| `clean_confirmed` | 连续 N 轮无 issue | 可进入 build |
| `max_rounds` | 达轮数上限仍未收敛 | 人工检查 `rounds/` 遗留 issue |
| `no_progress` | 影子译文摘要出现 A↔B 循环 | 振荡，人工介入裁决 |
| `unresolved_fixes` | Fixer 失败积压且复审不再报 | 人工处理无法修订的句子 |

## G1 问题类型（宁缺毋滥）

`missing`（漏译）/ `added`（增译）/ `mistranslation`（误译）/ `terminology`（术语违例）/
`pronoun`（人称/性别错误）。合理语序调整、自然意译、风格润色**不算问题**，拿不准不报。

## 影子修订与盲复审

- G3 只在 `shadow_overlay.json` 上生成"最小修改的完整单句替换"，正式 `translation/`、
  `glossary.csv`、`publication.json` 全程只读。
- 下一轮审校不传旧问题说明，只读修订后的影子译文（盲审），防止"按说明书打勾"。

## 术语冲突仲裁

跨块对同一术语/人称/固定表达给出矛盾译法时，应外置到 `analysis/glossary_conflicts.jsonl`
并终局裁决；同一词多种译法并存（如赤区/苏区）是"最隐蔽的质量问题"，裁决后写回
`analysis/glossary.csv`（权威）。

## G4 / G5（见 qa.md 与 build.md）

- G4：`auto-epublizer qa` 跑 epubcheck（零 error）+ 解包逐项审计（mimetype 首位未压缩、
  container 指向 OPF、manifest/spine 可解析、nav 链接可解析、URL 安全、lang 正确、每章一个 h1）。
- G5 放行条件：`g2_confirmed == 0` 或全部已修订；`g4_epubcheck_errors == 0`；`g4_audit == "pass"`。

## 验收阈值（默认）

| 指标 | 阈值 |
|---|---|
| 长度比 | `0.30 ≤ len(tgt)/len(src) ≤ 3.0` |
| 空译文 | 禁止（直接退回） |
| 句数一致 | 严格相等（含 `note` 声明例外） |
| 差错率 | `confirmed_issues / 总句数 ≤ 1e-4` |
| epubcheck | 0 error |

> 当前实现说明：G0 在 `qa` 命令中对全部已对齐单元自动执行（告警进 `report.json.g0_flags`，
> 作为 G1 线索的 advisory，**不阻断放行**——英→中长度比天然偏低会大量误报）；G1–G3 由
> `review` 命令驱动；G4 由 `qa` 命令驱动；G5 由 `qa` 聚合 G0–G4 写 `report.json`（含
> `error_rate`/`released` 放行判定）。协议违例（G1 缺 `complete:true`、翻译句对数量不符）
> 会整批重试 2 次后报错。
