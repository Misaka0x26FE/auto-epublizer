# 2026-10-15 审查回流修复报告与增量独立审查

状态：**增量独立审查未通过**。§1–6 保留实施方当时的修复、验证与交付报告，不视为独立验收；
§7 给出 `eda3edb` 上的复核结果。“四项 P1 全部已修”不能据此关闭，书籍 V/H 亦未整体验收。

来源：

真实作品的交付或摘录记录已移除；通用修复契约保留。

## 1. 实施方主仓库修复记录（4 项 P1 + 2 项 P2；复核见 §7）

| 项 | 位置 | 修复 | 回归 |
|---|---|---|---|
| P1-1 候选↔注文图对账 | `orchestrator.register_notes` + 新增 `notes.validate_candidates_vs_graph` | 已核证 `note` 候选与 `inventory=none` **矛盾即拒绝登记**；`present` 时每条 note 候选必须在注文/引用图留下证据（同单元/全局 label 命中，或候选文本落于某条 `source_markdown`），否则按**部分遗漏**拒绝 | `test_register_rejects_note_candidates_with_none_inventory`、`test_register_rejects_note_candidate_missing_from_graph` |
| P1-2 译注源版本绑定 | `orchestrator._load_notes_context`（import/build/qa **共享入口**） | 校验译注 `source_notes_sha256` == 当前源注文摘要；按实际源/译模式 `require_target`（build `prefer_translation`、qa 有译文参与时强制译注齐备）；`inventory=none` 零对零不受影响 | 更新 `test_import_gate_blocks_stale_translation_notes_digest`（改由共享入口报错）+ 新增 `test_build_blocks_when_translation_notes_binding_stale` |
| P1-3 注文媒体核对 | `qa/notes_audit.audit_notes_epub` | 期待引用（`target_markdown`/`source_markdown` 的图片）⊆ aside 实渲染 `<img>`；实渲染资源必须在包内。`E_NOTES_MEDIA_MISSING` / `E_NOTES_MEDIA_ABSENT`；不再被去图文本规范化掩盖 | `test_notes_product_gate_flags_note_media_missing` |
| P1-4 摘要覆盖全部放行输入 | `qa/artifacts.artifacts_digest` | 单元描述改为**发布顺序**（不再按 id 排序）+ region/kind/level/rel_path/title；新增 `catalog.csv`/`repairs.jsonl`/`facts.json`；新增**实际源件字节**哈希 | `test_report_goes_stale_when_catalog_unresolved_added_after_release` |
| P2-a 伪 stale 项不当单元 | `orchestrator._derive_next_tasks` | `report_stale → build→qa`；`notes_changed_since_register → notes register`；`catalog_binding_broken → 修 catalog.csv`；未知伪项跳过。杜绝 `import --unit report` 死循环 | `test_next_tasks_report_stale_not_routed_as_unit` |
| P2-b 成品路径 cwd 敏感 | `qa/artifacts`（`_resolve_epub_path`）+ `qa()` 保存 | 工作区内成品按 `store.dir` 相对保存/解析；外部成品用规范化绝对路径 | 上述 P1-4 回归 + 既有 B2 失效链用例 |

**前后证据**：在 HEAD 工作树（`/tmp` 临时 worktree + `PYTHONPATH` 指向其 `src/`）运行本次新增/更新的回归
——**P1 五项全部失败、P2-a 一项失败**；修复后同一批全部通过。全量 **578 passed, 1 skipped**、
`ruff check`/`format --check` 全绿（离线可跑）。

**提交**：`6cb79f0`（本次修复；`orchestrator.py` 同时带入在途「处理工具记录」两行，同文件无法分离）、
`22c8c55`（在途指纹实现随审提交）。两提交已推送 GitHub 与 Gitee（远端 `HEAD = 22c8c55`，双远端核验一致）。
隐私核对：改动仅含公开项目链接与「禁止记录机器路径/密钥」类条款文字；`fingerprint.py` 的
`_revision()` 只对本包源码仓库执行 git 查询，写入内容为 commit 与 dirty 布尔，不含路径。

## 2. 未修两项 P2 的设计（待审）

- **P2-c（旧门移交）**：判别口径由「单元素材（`[^ref-…]` 标记）」提升为**已验证、未过期的登记图**
  （仅 `pub.notes` 非空不足以跳过：登记摘要须与当前 `structured/notes.json` 一致）——
  `orchestrator.qa` 已加载 `notes_ctx`，将其作为 `notes_registered` 传给 `audit_provenance`
  （登记后跳过旧「md 定义数 ↔ 成品 aside 数」计数）与 `audit_epub`
  （新增 `unreferenced_notes`，回链门只对**被引用的** aside 生效；`orphan_ok` 注文由 notes 门
  的 `kept_notes` 负责）。红线：不伪造引用、不删除合法注文、未登记的多余 aside 与内容/媒体缺失
  仍按 `E_NOTES_*` 阻断；legacy（无登记图）行为不变。回归：① 带 `orphan_ok` 注文的工作区
  build→qa 不再报 `E_FN_EPUB_LOST`/`E_FN_BACKLINK`；② 删孤儿注内容/媒体后 notes 门仍阻断；③ legacy 对照。
- **P2-d（入口顺序）**：`AGENTS.{zh,md}` 工作流段把「注释结构化与绑定」整块前移到翻译之前并重编号
  （注释核证/登记 → 语义整备 → 翻译（含 `translation/notes.json`）→ import/g0 → 审校）；
  `SKILL.{zh,md}` 管线摘要补注释步骤；建议加轻量文档闸：在 AGENTS/SKILL 的流程代码块中断言
  「注释登记命令首次出现位置 < 翻译登记命令首次出现位置」（命令名锚定，避免自然语言脆弱匹配）。
  `references/workflow.{zh,md}` 与 `status --json` 机器指针已为注释在前（无需改）。

## 3. 真实作品记录（已脱敏）

真实作品识别信息、摘录及交付记录不随公开代码保留。

## 4. 真实作品记录（已脱敏）

真实作品识别信息、摘录及交付记录不随公开代码保留。

## 5. 未完成/未验证（审查关注点）

- P2-c / P2-d（设计见 §2，未实现）；
- 书籍 **N 迁移**（前置：恢复注文真实边界/跨页续文/编号作用域/引用位置 → `notes.json` +
  原位标记 + 三道硬门；legacy 弹窗/回链语义目前为 0）；
- 245 条术语命中的**逐项证据映射**（不照抄旧豁免 CSV；旧清单绑定旧单元、style.md §40–49
  不支持「著录一律不译」）；
- 阅读器**交互**验收（跳转/弹窗/落点；审查侧已取目录截图）；
- 主仓库侧 `terminology_exempt` 机制是否移植的产品决策。

## 6. 实施方原复现命令（历史记录，当前限制见 §7.4）

```bash
# 主仓库回归（离线）
uv run --offline pytest -q && uv run --offline ruff check . && uv run --offline ruff format --check .

# 修复前证据（**钉住真实基线**：F1/F2/F4 → c0e89c2；F3/F5 → 6cb79f0，见 §7.4）
git worktree add /tmp/x c0e89c2 && cp tests/test_notes*.py tests/test_artifacts_digest.py /tmp/x/tests/ \
  && (cd /tmp/x && PYTHONPATH=/tmp/x/src uv run --offline --project <repo> pytest -q \
      tests/test_notes.py tests/test_notes_media_gate.py tests/test_artifacts_digest.py \
      -k "bound_note_candidates or cross_unit_note_binding or same_basename or glossary_conflict or glossary_edit or insert_change")

# 书籍侧（包内）
tar -xzf <scratch>/sample-archive-a-v-fixed.tar.gz
cd sample-archive-a && uv run --offline --project <repo> auto-epublizer status --workspace . --json
# 核对：report.json.artifacts_epub 指向包内相对路径；nav/NCX 97 条一致见 reviews/v-20261015-structure.md 第 5 节
```

## 7. 增量独立审查报告

**Mode:** PR Review  
**Scope:** `c0e89c2..eda3edb`，重点审查 `6cb79f0` 的 notes/共享加载、成品媒体、
报告失效链与任务路由，以及书籍 V v2 的实际边界和随包脚本。总差异 32 文件、+1573/-52，
采取关键行为抽样；`22c8c55` 为此前已验证的指纹实现提交，本轮不重复审计该实现。  
**Health Score:** 不评分；有限增量抽样不支持全项目健康结论。未新增评分历史文件。

**结论：不通过。** 修复方向有进展，但三项 P1 修复仍未闭合，实际源/译模式选择新增回归，
合法编码图片新增误报，书籍返修与脚本复现也仍有缺陷。以下区分新增回归与原问题残留，
不把已声明未修的旧门移交、操作入口顺序或历史注文缺陷充作新增发现。

### 7.1 Findings

#### F1 [P1 / R6 / 修复未闭合] 全局显示号和文本前缀不能证明候选已绑定

- **Symptom:** `src/auto_epublizer/notes.py:417–425` 将全部注文显示号合并成全局集合，
  并以任意注文中出现候选前 60 个规范化字符作为另一条通过条件。真实两章各有注号 1，
  CLI 候选导出实际产生 4 条并均核证为 note；登记图仅含第一章的一注一引，`register_notes`
  仍成功，摘要为 notes=1、references=1、scopes=1。不同注号、相同前 60 字而续文不同也通过。
- **Source:** *Domain-Driven Design* — Entity vs Value Object / Aggregate Roots；
  显示号和可重复文本不是稳定身份，候选处置与登记图的不变量须在同一边界校验。
- **Consequence:** 章内重号、复引或相似书目可掩盖缺注和缺引用；候选“已核证”仍不能保证
  对应原位标记与真实注文进入产品。本次只修住了 none 矛盾，未修住 present 的部分遗漏。
- **Remedy:** 由 agent 显式绑定候选与稳定 note_id/ref_id 及定位证据，CLI 做确定性对账，
  按候选种类分别校验注文与每次引用；重跑候选导出须保留这些核证绑定。不得用全局同号或短前缀猜配。

#### F2 [P1 / R2 / 修复未闭合] 报告摘要仍遗漏真实放行硬门输入

- **Symptom:** `src/auto_epublizer/qa/artifacts.py:58–100` 未包含
  `analysis/glossary_conflicts.jsonl`、`analysis/glossary.csv`、`publication.json.notes`
  及 `structured/raw/inserts/*.json` 与引用资源的存在性。真实 EPUBCheck 零 error、
  `released=True` 的临时成品，新增一条 open 术语冲突后摘要不变，`report_state` 仍为
  released=True/stale=False；实际重跑 QA 则为 released=False、reason=glossary_conflict_open、
  conflicts_open=1。
- **Source:** *A Philosophy of Software Design* — Information Leakage；
  放行依赖知识分散在 QA 消费端和手写摘要清单，新增或修复一个门时容易漏掉另一份规则。
- **Consequence:** status/ledger 可继续把已经违反术语硬门的工作区视为有效放行。
  其余漏项也有真实消费者：词表可产生 blocking terminology，登记状态决定注释门，
  inserts 单文件可产生 `E_INSERT_MISSING_FILE`；不是泛指所有 raw 文件或未消费的 config。
- **Remedy:** 将这些实际放行输入、登记绑定状态和所引用文件的存在性纳入确定性快照；
  保留有序发布描述，避免把易变事件/时间戳无差别纳入。补逐类状态转换与失效证据，不能仅以 catalog 单例验收。

#### F3 [P1 / R6 / 新增回归] 翻译偏好被当成实际注文来源

- **Symptom:** `orchestrator.py:383–384` 直接令 require_target=prefer_translation，
  而 `build()` 第 623/638 行明确允许缺译文回退源文且总传 True。真实工作区有效登记源注、
  完全没有译文或译注，直接调用生产 `build()` 即被“translation/notes.json 缺失”阻断。
  第 973–979 行另在 require_target=False 时仍加载并检查遗留译注摘要；分片在真实工作区
  共享入口复现旧译注也能阻断不使用它的源文路径。
- **Source:** *Domain-Driven Design* — Ubiquitous Language；
  “偏好译文”不是“实际使用译文”，全书偏好也不是每条注文的真实来源。
- **Consequence:** 原有全源文回退构建失效；源注更新后，纯源文输出可能被无关旧译注阻断。
  这不是为防止缺译注而必须付出的代价，因为这些路径实际使用完整源注。
- **Remedy:** 先确定参与构建的单元、注文宿主和实际来源，再校验相应源/译注；
  build 与 QA 使用一致的模式证据。实际使用的译注缺失或过期仍必须阻断，不能全局取消绑定检查。

#### F4 [P1 / R6 / 修复未闭合] 同 basename 的另一张图仍可冒充期待图片

- **Symptom:** `qa/notes_audit.py:259–261` 在路径不一致时按 basename 集合豁免。
  分片使用真实临时 ZIP：期待 `a/same.png`，aside 实际引用 `media/b/same.png`，
  包内仅有图片 B，生产 `audit_notes_epub` 返回 ok=True、findings=[]。
- **Source:** *Domain-Driven Design* — Entity vs Value Object；
  文件名末段不能代替带目录的资源身份。
- **Consequence:** 注文错图仍能通过新媒体门，不能将原 P1 标记为完全关闭。
  此接受行为在父版本已存在，本项是修复残留，不宣称补丁首次引入错图。
- **Remedy:** 保留规范化资源路径身份；只接受生产收集器明确产生的映射，
  不用全局 basename 子集关系补偿路径差异；同名不同目录作为负对照。

#### F5 [P2 / R6 / 新增回归] URL 编码路径被当作 ZIP 成员名

- **Symptom:** `qa/notes_audit.py:69–76,267–272` 未把图片 URL 解码到成员身份域。
  本轮真实 import→build 的 `![x](中文.png)` 产生 `media/%E4%B8%AD%E6%96%87.png`，
  ZIP 实有 `OEBPS/media/中文.png`；生产注释审计却报
  `E_NOTES_MEDIA_MISSING` 和 `E_NOTES_MEDIA_ABSENT`。
- **Source:** *Domain-Driven Design* — Bounded Context / Anti-Corruption Layer；
  URL 表示与 ZIP 成员名属于不同表示域，跨边界需要明确转换。
- **Consequence:** 合法中文文件名（以及同类 URL 转义路径）的完整图片被误判缺失，正常作品无法通过新增门。
- **Remedy:** 统一源引用、渲染 URL 与包内成员名的规范化规则，正确处理 URI 转义和相对目录；
  保持 F4 的完整路径身份检查，不能以放宽成 basename 匹配解决误报。

#### F6 真实作品记录（已脱敏）

真实作品识别信息、摘录及交付记录不随公开代码保留。

#### F7 [P2 / R2 / 复现链未闭合] 随包脚本仍隐式依赖本机路径与未恢复的旧状态

- **Symptom:** 随包 `reviews/tools/v_restructure.py:16–18` 仍固定读取本机临时工作区。
  README 第 15–16 行要求 36 单元迁移前输入，却让操作者“从归档恢复”；当前交付包是已迁移
  51 单元。于独立临时 cwd 执行无 `--apply` 的生产脚本，仍去读固定路径并因旧
  `structured/frontmatter/foreword.md` 不存在而退出 1。本轮没有执行写入模式。
- **Source:** *The Pragmatic Programmer* — Orthogonality；
  复现目标、操作者 cwd 和本机原工作区不应有未声明的隐式耦合。
- **Consequence:** “脚本已随包”不等于另一台机器或新副本可复现；操作者也无法用明确参数选择安全目标。
- **Remedy:** 提供显式 workspace 参数、固定迁移前提交/快照和可执行恢复步骤；
  在写入前校验预期源身份与结构版本。默认 dry-run，不应靠原机临时目录恰好存在。

推荐修复顺序：F1/F2/F3/F4 → F5/F6/F7 → 已保留的旧门移交与入口文档 → 本册 N 迁移与交付验收。

### 7.2 可接受的进展与未关闭事项

- 已加入 none 与已核证 note 候选的矛盾阻断；已有伪 stale 项分派与成品路径归一实现。
  不能因相邻问题仍在而否认这些具体改动，也不能由这些局部改动推导全部 P1 已关闭。
- 标题续行拼接、序言首段拆分与职衔表表头切分已有针对性实现；附件三 p499 图片已迁入正确单元，
  但 F6 表明该次边界修复未完整验收。
- v2 H 已撤回“注文完整”，补 A/B 版本关系与包内报告，明确 N 迁移和阅读器交互未完成；
  接受这些收窄说明，不代为确认所有历史版本均已回收。
- 未实现的 P2-c（orphan 旧门移交）与 P2-d（操作入口前移）继续保留，不列为新增回归。
- 分片另观察到 HTML 图片的既有 `E_NOTES_CONTENT_MISMATCH`；它不是本补丁新增，
  后续统一媒体/内容规范化时应处理，不能把当前 ASCII Markdown 单例当成全部媒体形态已验。

### 7.3 本轮实际执行与验证边界

本轮未修改业务代码或永久测试。所有新 smoke 使用自动清理的临时工作区/ZIP，
未改原始书籍工作区、交付 EPUB 或归档。

| 实际执行 | 观察结果 |
|---|---|
| 真实 init → notes candidates → 核证 disposition → register；两章重号 | 导出 4 个 note 候选，图只含一注一引仍登记成功 |
| 独立候选/登记图前缀碰撞 | label 不同、前 60 字相同而续文不同仍登记成功 |
| 无译文有源注工作区直接调用 build | 被缺 translation/notes.json 阻断，未生成本应允许的源文回退产品 |
| 真实 import → build → ZIP 检视 → 注释门；中文图片文件名 | 包内有原名资源、HTML 有编码 URL；审计错误报 MEDIA_MISSING/ABSENT |
| 真实 build → qa → 新增 open 冲突 → report_state → qa | 基线真实 EPUBCheck ran=True、0 error、released=True；摘要不变且 stale=False；再次实际 QA 返回 glossary_conflict_open、open=1、released=False |
| 直接解析书籍新版 EPUB，并流式读取归档内相关文本 | 附件二图例/来源只在附件三；随包脚本仍硬编码临时工作区 |
| 迁移脚本默认 dry-run；独立临时 cwd | 退出 1，读取固定路径的旧 foreword.md 失败；没有传 --apply |
| 文档链接检查 | `uv run --offline python scripts/i18n.py --links` → `OK`；计划文档按中文历史计划约定，无需新增英文孪生或 finalize |

分片额外以生产 API/真实 ZIP 验证了同 basename 错图放过、旧译注阻断源文共享入口、
词表/登记状态/inserts 硬门输入不改摘要。主报告不把这些称为完整 build→qa 或阅读器实测；
完整真实放行与失效复现仅为表中 open 冲突场景。

采纳实施方当时的 **578 passed, 1 skipped** 与 Ruff 记录，本轮未为确认这些数字重复运行
suite/formatters；没有把新 smoke 当成新增永久测试。未重跑已报的 97 链接、42 媒体、
真实书 EPUBCheck 指标，亦未启动新的阅读器交互。

### 7.4 实施设计与复现说明的审查意见

- 旧门移交方向可继续：以**已验证、未过期的登记图**为准，不能仅见 `pub.notes` 非空就跳过旧门。
  orphan 合法保留、未登记 aside、内容/媒体缺失等仍须有独立硬门，不伪造引用。
- 注释核证/登记前移到翻译之前的方向可接受；不接受用永久测试扫描 AGENTS/SKILL 命令字符串
  先后顺序来替代实际操作流程一致性。同步操作文档与机器路由，核读实际入口并做一次真实流程 smoke。
- §6 是实施方原命令记录；其 `git worktree add … HEAD` 在当前版本已指向含修复的提交，
  不能再据此取得“修复前失败”。后续对照应固定 `c0e89c2` 等真实修复前基线、明确复制哪些回归；
  本轮没有运行回退测试来重复确认既报失败。
- 不原样移植旧术语豁免清单；本册恢复真实注文与引用后才能登记稳定身份，
  245 个术语命中仍须按上下文和内容版本逐项核证。

## 8. 二轮修复记录（回应 §7，commit `21b7511`）

状态：§7 的 7 项 Finding 按建议顺序（F1/F2/F3/F4 → F5/F6/F7）处理完毕；
P2-c/P2-d 仍保留（按其设计与 §7.4 审查意见）。前置失败基线按 §7.4 钉住：
F1/F2/F4 对齐 `c0e89c2`，F3/F5（上一轮引入的回归）对齐 `6cb79f0`。

| Finding | 修复 | 回归（前置失败基线） |
|---|---|---|
| F1 候选身份 | `validate_candidates_vs_graph` 改为**稳定身份绑定**：引用型（marker/pandoc_ref）必须绑 `ref_id`（存在、同单元、注号一致、不得重复绑定）；注文型（definition/numbered_paragraph）必须绑 `note_id`（存在、不得重复；须有同单元引用，或位于 `notes` 类单元且数字注号一致）。**删除**全局同号/前 60 字前缀判定；`notes candidates` 重跑保留绑定；前置任务提示写明绑定要求 | `test_register_requires_bound_note_candidates`、`test_register_rejects_cross_unit_note_binding`（§7 F1 的跨章同号场景：图仅覆盖第一章 → 拒绝）、`test_candidates_rerun_preserves_identity_bindings`（`c0e89c2` 上失败） |
| F2 放行输入 | `artifacts_digest` 增加 `analysis/glossary.csv`、`analysis/glossary_conflicts.jsonl`、`pub.notes` 登记摘要、`structured/raw/inserts/*.json`（内容 + 引用资源存在性） | `tests/test_artifacts_digest.py` 4 项：open 冲突（§7 复现场景）、词表改动、登记变化、inserts/资源缺失（`c0e89c2` 上失败 3 项） |
| F3 实际来源 | 新增 `_notes_target_in_use`（注文宿主单元 ∩ 以译文渲染）；全源文回退不再被缺失/过期译注阻断；**实际使用**的译注缺失/过期仍阻断；import 的译注要求归逐单元门（不在共享入口重复） | `test_build_allows_source_fallback_without_any_translation`、`test_build_ignores_stale_translation_notes_when_not_used`、`test_build_blocks_when_used_translation_notes_stale`（前两项在 `6cb79f0` 上失败） |
| F4 媒体身份 | 媒体比对**去掉 basename 豁免**，保留完整资源路径身份 | `test_same_basename_different_dir_is_not_accepted`（`c0e89c2` 无该门；`6cb79f0` 放过同名错图 → 现拒绝） |
| F5 URI 编码 | `_norm_media_ref` 统一到成员身份域（`unquote` + 前缀归一），期待/实渲染/包内成员同一规则 | `test_url_encoded_chinese_filename_is_accepted`（`6cb79f0` 上误报缺失） |
| §7.2 附注 | `_norm_md` 同时去掉 HTML `<img>`，媒体期待兼容内嵌 HTML 图片 | `test_html_img_in_note_markdown_not_content_mismatch` |
| F7 复现链 | 随包脚本可移植化：显式 `--workspace`、默认 dry-run、写入前校验迁移前结构（36 单元 + 必备文件，迁移后工作区直接运行被拒绝）；README 固定快照 `3dfe3c0` 恢复步骤 | 从 `3dfe3c0` 快照重跑迁移四步 → `structured/`+`translation/` 共 **153 个文件与交付包逐字节一致** |

**验证**：HEAD 全量 **594 passed, 1 skipped**、`ruff check`/`format --check` 全绿（离线）。

**未做（保留）**：P2-c（旧门移交以**已验证、未过期**的登记图为准；orphan 合法保留、
未登记 aside、内容/媒体缺失仍需独立硬门）、P2-d（注释核证/登记前移 + 同步操作文档与
机器路由 + 一次真实流程 smoke；不采用源码文本位置断言类文档闸）。本册 N 迁移
（注文真实边界/跨页续文/编号/原位引用）与阅读器交互验收未完成。
