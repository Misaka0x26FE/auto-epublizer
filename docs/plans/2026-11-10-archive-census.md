# 归档普查口径（A1，2026-11-10）

状态：**只统计，不含语义结论**｜脚本：`scripts/archive_census.py`

## 输入与可复现命令

```bash
sha256sum ~/Downloads/translate.tar.gz
# c22235b46b2f72cf1ef921ff323da4882442be2aaee7fc3798361fad9bc59a08

python3 scripts/archive_census.py <解包后的 translate 根目录> \
  --source-sha256 c22235b46b2f72cf1ef921ff323da4882442be2aaee7fc3798361fad9bc59a08 \
  -o /tmp/archive-census.json
```

脚本只读 `workspaces/*/report.json`、`translation/align/*.jsonl`、
`structured/notes.json`、`translation/notes.json`；输出只含 slug、计数、状态与相对路径。
缺文件/坏 JSON 记 `errors`，不静默跳过。

## 实测结果（52 个工作区）

| 指标 | 值 |
|---|---|
| 有 `report.json` 的工作区 | 52 |
| `report.json` 的 `total_sentences` 合计 | **154,239** |
| `translation/align/*.jsonl` 实际非空行合计 | **153,458** |
| 差额 | **781**（原因未查明；两种口径**不得混用**分母） |
| 源注文登记总数 | **16,199** |
| 空 `note_id` / 重复 `note_id` | 0 / 0 |
| 源有、目标无的 `note_id` | 0 |
| 目标有、源无的 `note_id` | 0 |
| 有源注文但缺 `translation/notes.json` | **0**（`inventory=none` 的书不计） |

> 注文 ID 契约干净，不代表内容已译：ID 齐全只说明登记关系完整；语言是否为目标语
> 由 `note-review` 候选与逐条处置判断（C2/C3）。

## 七本高风险书的候选分层（只按注文类型与表面特征）

| 工作区 | 总注 | 零汉字候选 | 其中说明性散文候选 | 注文类型 |
|---|---:|---:|---:|---|
| pod-znakiem-krola-daniela | 2,215 | 2,024 | 1,693 | footnote |
| unlikely-allies | 1,292 | 1,221 | 599 | endnote |
| stalins-commandos | 1,036 | 888 | 188 | endnote |
| cambridge-history-south-africa-2 | 740 | 723 | 487 | footnote |
| vanguard-of-the-imam | 946 | 545 | 188 | endnote |
| prague-spring-and-its-aftermath | 840 | 411 | 187 | footnote |
| sorel-presentation-textes-choisis | 235 | 235 | 121 | footnote |

「说明性散文候选」= 目标文本 ≥10 词且 ≥2 个句末标点；只是**分层线索**，仍可能包含
合法外文引文。**本轮未做逐条语义核验**，因此：

- 不宣称「未译数量」；
- 不据此判定任何一本书的译文质量；
- 复核时应按 `note_id` 抽样回原页，确认「纯著录 / 外文引文 / 应译未译」。

## 已知限制

- `report.json` 由各书历史版本生成，`total_sentences` 与 align 行数并非同一时刻快照；
  781 的差额可能来自空行/跳过单元/历史重跑，未查清前不解释为漏译。
- `inventory=none` 的书没有译注文件是合法的，不计 error；只有
  `inventory=present` 且有注文却缺译注文件才写入 `errors`。本次普查 `errors=0`。
