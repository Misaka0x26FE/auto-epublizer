# Analysis（分层理解——agent 任务）

**唯一 LLM 原则**：理解是 agent 任务。CLI 只提供确定性助手（语言/体裁启发式检测、
`render_style_md` 文体档案渲染）；`analysis/*.md` 与术语表由你用自身能力撰写。

`analysis/` 是翻译与审校的上下文输入；读取优先级 `analysis/` → `preprocessing/`。

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

## 撰写要点

1. 先读 `preprocessing/facts.md` 与 `preprocessing/` 的理解产物（plan/global/units/terms）；
2. 写 overview/global/units/keypoints（概述、全局、每单元、重点）；
3. 语言与体裁：`publication.json` 的 `meta.language`/`meta.genre` 由 convert 路径用
   确定性启发式回填（拉丁→en、汉字→zh、假名→ja、谚文→ko、西里尔→ru…；体裁按
   参考文献/脚注/引用密集→academic、短标题块→newspaper、默认 novel）；如启发式不准，
   直接用自身判断修正；
4. `style.md`：可用 `render_style_md`（CLI 确定性助手）生成初稿再按书调整，或直接参照
   `references/style.md` 写。

## 术语三态（agent 播种）

`glossary.csv` 列序：`source,target,type,aliases,gender,reading,status,note`。

- 从原文提取人名/地名/组织/术语，种入 `status=seed`（不覆盖既有译法）；
  `preprocessing/terms.csv` 预提取后经 `import --terms` 导入亦可。
- `references/user/` 导入的参考材料也可种入。
- 三态：`seed → candidate → conflict → confirmed`；同 source 异 target 外置到
  `glossary_conflicts.jsonl`（import 自动完成）待你终局裁决写回。

## 术语类别

`person`（人物）/ `place`（地名）/ `org`（组织）/ `term`（术语）/ `event`（事件）/
`period`（历史时期）/ `work`（作品）/ `fixed_expr`（固定表达）。小说还含 `appellation`（称谓）/
`honorific`（敬称）/ `speech`（口癖），这些 **source-only** 类型只按完整原文精确匹配。

## 注意事项

- `analysis/` 是智能产物，可重跑覆盖；改术语/理解后须覆盖受影响单元的后续阶段。
- 需要背景知识时按「背景知识补齐」路由：有搜索工具查证写 `references/web/`，
  无则问用户放 `references/user/`。
