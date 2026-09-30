# 2026-09-30 工作阶段细分：原子任务卡 + 机器可判的下一任务指针

状态：规划中

## 背景与目标

**核心目的（用户）**：让**比较弱的模型**也能按照**较小的多次任务**完成全部翻译/转换工作。

现状把流程分成了 11 个阶段（SKILL.md 路由 → references/*.md），但阶段内部的工作量对弱模型
仍然过大，具体痛点：

1. **单阶段产出过重**：preprocessing 一次要写 7 份语义文件（todo/capabilities/plan/
   global/units/terms/risks/report）、analysis 一次写 overview/global/units/keypoints、
   review 一次写 issues/patches/summary/result.json——弱模型单会话上下文有限，写到一半
   丢失前文，产出半途而废或漏项。
2. **「下一步做什么」靠模型推断**：`status --json` 给出状态与 stale 对账，但把
   状态→行动的映射留给模型（workflow.zh.md 的路由伪代码是给人读的散文）。弱模型推断
   不可靠，容易跳步、重做或卡死。
3. **任务完成判据无机器校验**：写了 global.md 但没人检查「写全了没有」；todo.md 是
   agent 自由撰写的 markdown，格式不统一，无法对账。
4. **上下文自包含性缺失**：弱模型跨会话续跑时依赖对话记忆——上一会话的决定（术语
   取舍、路线选择）没有强制落盘到任务现场，续跑即失忆。

**设计原则**（由「弱模型」约束推出，全程不放松）：

- **磁盘即进度**：任何任务做完，进度必须 100% 落在工作区文件 + publication.json 里，
  新会话零记忆可续跑；
- **每任务一个 CLI 可判的完成判据**：判据必须是「跑一条命令 / 查一个文件」级别的
  确定性检查，不依赖模型自评；
- **下一任务由 CLI 给出**：弱模型不读路由表做决策，只问工作区「现在该干什么」；
- **任务卡自包含**：每张卡开头重述现场（书名/语对/当前单元/判据），不引用会话历史。

## 技术设计

### S1 `status --json` 增加 `next_tasks` 机器指针（核心使能）

- 在 `orchestrator.status` 现有状态机/对账逻辑上**派生**（不新增第二份状态源）：
  输出 `next_tasks: [{kind, unit?, hint, done_when}]`，按执行顺序排列，弱模型只取
  首条执行，完成后重跑 `status --json` 刷新。
- 派生规则（与现有路由伪代码一一对应，写入注释互引）：
  - 无 publication.json → `preprocess`；
  - facts 有而理解产物缺 → 逐文件给「写 preprocessing/<file>」任务（缺哪份给哪份，
    顺序按 todo 依赖：capabilities → global → units → terms → risks → report → todo 收尾）；
  - repair 信号触发 → 「语义整备」任务；
  - 有 structured 无 analysis → 逐单元「分析 chXX」任务（限每批 ≤5 个，防弱模型贪多）；
  - translation 在而状态 stale → 「import --unit chXX」；状态 ≤analyzed → 「翻译 chXX」
    （一次只给**一个**单元 id——弱模型的原子粒度）；
  - aligned 未 reviewed → 「审校 chXX」；全部 reviewed → 「build」→「qa」→「delivery」。
- `done_when` 字段是判据的机器表述（如 `{"cmd": "import", "unit": "ch03"}` /
  `{"file": "preprocessing/global.md"}`），既给人读，也为将来任务循环脚本留接口。

### S2 任务卡（task cards）：skills 新增 `references/taskcards/`

- 每张卡 = 一个原子任务，四段式，**一屏以内**：
  `上下文重述（从工作区读哪些文件）→ 动作（做什么、写到哪）→ 完成判据（跑哪条命令）
  → 失败处置（告警怎么看、找哪篇 lesson）`。
- 覆盖弱模型会独立面对的最小任务集（首批 ~12 张）：
  `write-capabilities / write-global / write-unit-analysis / write-terms / write-risks /
  write-report / repair-unit / translate-unit / import-unit / fix-g0-unit /
  review-unit / build-qa-delivery`。
- 阶段级 references（preprocessing/analysis/review…）**降级为编排说明**（给强模型与
  人类维护者），弱模型主路径 = SKILL.md → `status --json.next_tasks` → 对应任务卡。
- SKILL.md 路由表加「弱模型执行模式」一行，manifest.json references 清单同步。

### S3 todo.md 契约化

- `preprocess` 生成**固定骨架**（checkbox 列表，机器可解析：每行
  `- [ ] <task-id> <说明>`），agent 只在骨架上填内容、勾选——不再自由撰写。
- `status` 对账 todo.md：骨架项未勾且对应判据已满足 → 提示补勾；勾了但判据不满足 →
  提示虚报。弱模型只负责「按卡执行 + 如实勾选」。

### S4 review 产物最小批化

- G1–G3 语义审校改为 per-unit 小批次：每单元写
  `reviews/review-<ts>/units/<id>.json`（小、独立、可断点）；
- 汇总 `result.json` 的 g1/g2/g3 计数改为**从 units/*.json 派生**（CLI 提供合并校验，
  或 agent 按卡汇总——契约写进 review.md）。qa 读 result.json 的现有接口不变。

### S5 自包含性纪律（写入任务卡与 SKILL.md）

- 每张卡第一步强制「重述现场」：从磁盘读书名/语对/单元数/术语要点（术语从
  analysis/glossary.csv 读），不依赖记忆；
- 单会话最小循环固化为卡间衔接：`translate-unit → import-unit → fix-g0-unit → 下一个`
  （现有 QC 纪律的卡化，见 AGENTS.md「In-process validation」）。

## 边界与不变量

- **单一状态源不变**：next_tasks 从现有状态机派生，不新增状态文件、不改
  publication.json 契约；`done_when` 全部可用现有 CLI 判定。
- **强模型路径无损**：阶段级 references 保留，强模型可继续按阶段自由编排；
  弱模型路径是增量选项，不是替换。
- **离线确定性**：next_tasks 派生与 todo 骨架生成都是零 token 纯函数（可测）。
- 单元级状态机（pending→…→built）不变；本计划只细化**任务粒度**，不动状态语义。

## 测试设计

- `test_status_next_tasks`：构造各阶段工作区（facts-only / 缺不同理解产物 /
  stale / 半 translated / 全 reviewed / built）断言 next_tasks 序列与 done_when。
- todo 骨架生成 + 对账：缺漏勾/虚报勾的告警回归。
- review units/*.json 派生汇总：合并正确性 + qa 兼容（result.json 旧格式仍可读）。
- 全量 `uv run pytest -q` + ruff。

## 文档同步

- `skills/auto-epublizer/SKILL.md`（+zh）：弱模型执行模式路由行；
- `references/workflow.md`（+zh）：next_tasks 用法 + 任务卡索引；
- `references/preprocessing.md`（+zh）：todo.md 骨架契约；
- `references/review.md`（+zh）：per-unit 审校批与派生汇总；
- 新增 `references/taskcards/`（首批 12 卡，中英双语）+ manifest.json 清单；
- `AGENTS.md`（+zh）：skills 目录结构段更新。

## 与「标准化 skill 改造」待办的关系

本计划的产物（原子任务卡、机器指针、一屏契约）正是把仓库改造为**标准 skill 包**的
素材与前置——任务卡即 skill 的最小指令单元，next_tasks 即 skill 的无状态续跑接口。
标准化改造立项时直接复用，避免二次返工。

## 实施顺序

S1（CLI 指针，核心）→ S3（todo 骨架）→ S2（任务卡）→ S4（review 批化）→ S5（纪律
写入）→ 文档收尾。S1/S3/S4 是代码，S2/S5 是文档为主；每步独立可交付。
