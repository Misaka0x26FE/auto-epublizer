# Analysis（分层理解 + 术语播种）

`analyze` 命令产出 agent 对全书的理解，作为翻译与审校的上下文输入。

**LLM 可选**：有 API Key 时 `analyze` 生成 overview/global/units/keypoints 并播种术语；
**无 Key 时自动确定性降级**——仅做语言/体裁启发式检测（回填 `publication.json`）+ 写
`style.md`，其余理解产物走 agent 预处理路径：`preprocess` 产 facts 后由 agent 撰写
`preprocessing/{plan,global,units,terms,risks,report}`（见 `references/preprocessing.md`）。
translate/review 的上下文读取优先级：`analysis/` → `preprocessing/`。

## 产出（`analysis/`）

```text
analysis/
├── overview.md            # 全书内容概要（翻译时注入为「全书概览」）
├── global.md              # 全局理解：主题/人称/语气/跨章依赖/高风险处
├── units/<id>.md          # 每单元理解：梗概/登场人物/术语注意
├── keypoints.md           # 重点内容：难点段落/复杂排版/多语片段
├── style.md               # 文体档案（genre + 术语白名单 + 翻译指引 + 语言指引）
├── glossary.csv           # 术语表（权威，人类/agent 可读）
├── characters.csv         # 人物表（小说）
└── glossary_conflicts.jsonl   # 术语冲突外置（待裁决）
```

## 语言与体裁检测

`analyze` 会检测并回填 `publication.json` 的 `meta.language` 与 `meta.genre`：

- 源语言：按脚本启发式（拉丁→en、汉字→zh、假名→ja、谚文→ko、西里尔→ru…）。
- 体裁：按内容启发式（参考文献/脚注/引用密集 → academic；短标题块 → newspaper；默认 novel）。

## 术语播种（三态）

`glossary.csv` 列序：`source,target,type,aliases,gender,reading,status,note`。

- `analyze` 从原文提取人名/地名/组织/术语，种入 `status=seed`（不覆盖既有译法）。
- `references/user/` 导入的参考材料也可种入。
- 三态：`seed → candidate → conflict → confirmed`；同 source 异 target 外置到
  `glossary_conflicts.jsonl` 待裁决。

## 术语类别

`person`（人物）/ `place`（地名）/ `org`（组织）/ `term`（术语）/ `event`（事件）/
`period`（历史时期）/ `work`（作品）/ `fixed_expr`（固定表达）。小说还含 `appellation`（称谓）/
`honorific`（敬称）/ `speech`（口癖），这些 **source-only** 类型只按完整原文精确匹配。

## 注意事项

- `analysis/` 是智能产物，可重跑覆盖；改术语/理解后须覆盖受影响单元重跑 translate/review。
- 网络检索写 `references/web/` 是后续扩展点，当前 `analyze` 未做网络检索。
