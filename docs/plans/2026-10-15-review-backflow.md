# 2026-10-15 审查回流修复报告与增量独立审查

状态：**当前代码、操作契约与架构图已提交 `1db8752`（§10）；整体书籍交付仍未验收**。
§1–9 保留既有实施与独立审查记录；源件内容核证不由测试替代，GUI 兼容抽查不作为通用阻塞。

来源：

- 审查输入：`Downloads/temp.txt`（2026-10-15 处置结论）与计划 `2026-10-14-review-and-repair.md` §8.1 表；
- 主仓库基线：本报告提交前的 `22c8c55`；书籍工作区基线：交付版 `0d978b4f…`（可逐字节重建）。

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

## 2. 旧门与入口设计（现已实施，当前验证见 §10）

- **P2-c（旧门移交）**：`orchestrator.qa` 先校验已登记源图的摘要并执行独立产品注释门，
  再向 `audit_provenance` / `audit_epub` 传 `notes_registered`。仅移交旧定义计数及必须有回链判据；
  现有锚点与已给回链的目标解析仍保留。`orphan_ok` 不伪造引用，未登记的多余 aside、
  注文/媒体缺失与 none 非零仍由 `E_NOTES_*` 阻断。无登记或过期上下文不移交。
- **P2-d（入口顺序）**：必要语义整备 → 源注核证/抽离/登记 → 翻译（含译注）→ import/g0 → 审校。
  AGENTS 中英文、SKILL 和实际路由同步；以真实流程核证，不使用源码命令字符串位置断言。

## 3. 书籍侧 V 返修（`forced-labour-and-extermination`）

四处（均复核到源件，源 = 47 条书签 + 页码）：

1. 印刷目录尾块混杂的**序言首段**按起句拆开，首段移回序言单元（目录页不再含该段）；
2. 附件二/三边界：**p499 图 + 图例 + WVHA 组织内容归附件三**（附件三自 p499 起；附件二仅 p494–497）；
3. 职衔表**表头与首条军衔**在混合块内切开，归 `back-dienstgrade`（附件三尾不再含 `Vergleichbarer`）；
4. 专论**德文标题补齐续行**（原截断于 `FüHRERKORPS DER`），并把**标题文字纳入守恒核对**
   （新增：全部文本守恒断言，逐项列明 5 处块内拆分、部分标题转换、Exkurs 合并、陈旧注组移除、人名补全）。

补充交付物：**「源节点 → 单元／锚点」对应表**（51 单元全覆盖，含无书签节点）；成品核对
nav == NCX **97/97**、href **97/97** 可解析、顶层 27、媒体与 `<img>` **42/42** 与交付版一致、
epubcheck 0 error、`provenance_coverage/epub_coverage = 1.0`、`align_md_drift = 0`。
修复版：`output/forced-labour-and-extermination-v-20261015.epub`
（sha256 `40e2f07c…b32a`）；报告在**包内位置经 CLI 重新生成**（`report.json.artifacts_epub`
为工作区相对路径，未手改放行字段）。

## 4. 书籍侧 H（版本回收与初步盘点）

- **撤回**上一版「注释内容完整」声明：2074 条 align 条目 ↔ 成品段落一一对应只证明
  **抽取块守恒**；两处确证注文缺陷（已在自有副本复核到源件）：① 导论注 7 跨页续文丢失
  （译注与 align 均止于断词处，源 PDF p17 有完整续文）；② 职衔表来源说明被拆成
  `ch06-385/386/387` 三条注文（译文出现孤立片段；源 PDF p501 为一条连续无编号说明）。
- **版本关系**：最初案例（`38b92118…`）与工作区交付版（`0d978b4f…`）成员集相同（85），
  **11 个 XHTML 内容不同**（每文件 1–4 个规范化字符，无图/段增删），对应工作区后续修复提交；
  旧版未删除；`0d978b4f…` 可由工作区逐字节重建（本轮实测）。
- 复现材料随包：`reviews/tools/{v_restructure.py,v_structure_csv.py,README.md}`；
  工作区记录：`reviews/v-20261015-structure.md`、`reviews/h-20261015-recovery.md`；
  包：`/tmp/opencode/forced-labour-and-extermination-v-fixed.tar.gz`。
- 不推送、不放行（工作区远端凭据查询 404，私有性待确认）；旧成品与原始归档未改动。

## 5. 未完成/未验证（审查关注点）

- 旧门与入口两项当前已实施，验证见 §10；
- 书籍 **N 迁移**（前置：恢复注文真实边界/跨页续文/编号作用域/引用位置 → `notes.json` +
  原位标记 + 三道硬门；legacy 弹窗/回链语义目前为 0）；
- 245 条术语命中的**逐项证据映射**（不照抄旧豁免 CSV；旧清单绑定旧单元、style.md §40–49
  不支持「著录一律不译」）；
- 可选阅读器兼容抽查尚未执行完整往返；此项不构成通用交付阻塞；
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
tar -xzf /tmp/opencode/forced-labour-and-extermination-v-fixed.tar.gz
cd forced-labour-and-extermination && uv run --offline --project <repo> auto-epublizer status --workspace . --json
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

#### F6 [P2 / R6 / V 返修残留] 附件二图例和来源随 p499 图片一起被移到附件三

- **Symptom:** 书籍 `reviews/tools/v_restructure.py:277–280` 将 c217b 及后续整段交给附件三。
  源 PDF p498（提取行 13856–13866）明确属于附件二，含 Legende、DESt/DAW 说明及 Quellen；
  p499 才开始 ANLAGE 3。新版 `structured/backmatter/back-anlage2.md` 仅有四张图，
  `back-anlage3.md:4–16` 却含上述图例与来源。已直接解析新版 EPUB：图例与该来源只在
  `OEBPS/back-anlage3.xhtml`；交付归档同样保留这个错误。
- **Source:** *Domain-Driven Design* — Ubiquitous Language / Bounded Context；
  资源块边界不能代替源书章节及图例的语义归属。
- **Consequence:** 附件三首页图已归位，但附件二失去自己的解释与来源，
  附件三得到不属于自己的说明；第 3 节“全部四处返修完成”的结论仍不能接受。
- **Remedy:** 将 p498 图例、说明、来源留在附件二；只把 p499 图片和真正的附件三内容迁入附件三，
  同步源/译 Markdown、align、对应表与成品落点。链接/媒体总量守恒不能替代这一核对。

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
- 当时未实现的旧门与入口两项不列为新增回归；当前实现与验证见 §10。
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

## 8. 二轮修复记录（回应 §7，commit `60b3553`）

状态：§7 的 7 项 Finding 按建议顺序（F1/F2/F3/F4 → F5/F6/F7）处理完毕；
当时旧门/入口仍保留，当前实现与验证见 §10。前置失败基线按 §7.4 钉住：
F1/F2/F4 对齐 `c0e89c2`，F3/F5（上一轮引入的回归）对齐 `6cb79f0`。

| Finding | 修复 | 回归（前置失败基线） |
|---|---|---|
| F1 候选身份 | `validate_candidates_vs_graph` 改为**稳定身份绑定**：引用型（marker/pandoc_ref）必须绑 `ref_id`（存在、同单元、注号一致、不得重复绑定）；注文型（definition/numbered_paragraph）必须绑 `note_id`（存在、不得重复；须有同单元引用，或位于 `notes` 类单元且数字注号一致）。**删除**全局同号/前 60 字前缀判定；`notes candidates` 重跑保留绑定；前置任务提示写明绑定要求 | `test_register_requires_bound_note_candidates`、`test_register_rejects_cross_unit_note_binding`（§7 F1 的跨章同号场景：图仅覆盖第一章 → 拒绝）、`test_candidates_rerun_preserves_identity_bindings`（`c0e89c2` 上失败） |
| F2 放行输入 | `artifacts_digest` 增加 `analysis/glossary.csv`、`analysis/glossary_conflicts.jsonl`、`pub.notes` 登记摘要、`structured/raw/inserts/*.json`（内容 + 引用资源存在性） | `tests/test_artifacts_digest.py` 4 项：open 冲突（§7 复现场景）、词表改动、登记变化、inserts/资源缺失（`c0e89c2` 上失败 3 项） |
| F3 实际来源 | 新增 `_notes_target_in_use`（注文宿主单元 ∩ 以译文渲染）；全源文回退不再被缺失/过期译注阻断；**实际使用**的译注缺失/过期仍阻断；import 的译注要求归逐单元门（不在共享入口重复） | `test_build_allows_source_fallback_without_any_translation`、`test_build_ignores_stale_translation_notes_when_not_used`、`test_build_blocks_when_used_translation_notes_stale`（前两项在 `6cb79f0` 上失败） |
| F4 媒体身份 | 媒体比对**去掉 basename 豁免**，保留完整资源路径身份 | `test_same_basename_different_dir_is_not_accepted`（`c0e89c2` 无该门；`6cb79f0` 放过同名错图 → 现拒绝） |
| F5 URI 编码 | `_norm_media_ref` 统一到成员身份域（`unquote` + 前缀归一），期待/实渲染/包内成员同一规则 | `test_url_encoded_chinese_filename_is_accepted`（`6cb79f0` 上误报缺失） |
| §7.2 附注 | `_norm_md` 同时去掉 HTML `<img>`，媒体期待兼容内嵌 HTML 图片 | `test_html_img_in_note_markdown_not_content_mismatch` |
| F6 附件二归属 | 书籍侧按源页证据重新划界：p498 的图例/DESt-DAW 说明/`Quellen` 留在**附件二**，p499 起才是附件三（块内拆三段） | 成品核对：附件二含图例与 `Quellen: BA, NS 3/32…`、不含 p499 图；附件三含 p499 图、不含 p498 图例项；nav==NCX 97/97 |
| F7 复现链 | 随包脚本可移植化：显式 `--workspace`、默认 dry-run、写入前校验迁移前结构（36 单元 + 必备文件，迁移后工作区直接运行被拒绝）；README 固定快照 `3dfe3c0` 恢复步骤 | 从 `3dfe3c0` 快照重跑迁移四步 → `structured/`+`translation/` 共 **153 个文件与交付包逐字节一致** |

**验证**：HEAD 全量 **594 passed, 1 skipped**、`ruff check`/`format --check` 全绿（离线）。

**当时未做**：旧门移交和操作入口前移；当前实现见 §10。本册 N 迁移
（注文真实边界/跨页续文/编号/原位引用）未完成；阅读器兼容抽查属于可选记录，不作为通用阻塞。

## 9. 本轮七项边界修复（`80b0694` 后，未提交）

本节对应用户最近一次审查后的修复授权；七项按新的边界问题分组，不覆盖或重编号 §7 的历史 F1–F7。
起点主仓库工作树干净，基线 `80b0694`。本轮修改源码、消费者回归与实际操作文档；
未提交/推送，不修改线上 issue，不改原始书籍正文、权威状态或交付 EPUB。

### 9.1 修复与契约

| 项 | 修复 | 保留的阻断 |
|---|---|---|
| 1. P1 资源有效性失效链 | `ingest.inserts.insert_file_exists` 先解析并确认 raw 包含性，再判断真实文件；`artifacts_digest` 与 provenance 共用。摘要读取生产 inserts schema，坏 JSON 不再造成 status 属性异常；冲突回归只改单个冲突账本 | 越界文件不作存在性探测；缺失/越界仍报 `E_INSERT_MISSING_FILE`，不伪造可用资源 |
| 2. P1 逐注文实际来源 | `_render_inputs` 一次选择实际源/译 Markdown；首个 spine 引用或孤儿规则确定宿主，同一计划用于目标摘要绑定、文本渲染与 QA。只校验/传递实际译注子集；完全未用到的坏 JSON 不读，混合成品未用空译注不阻断。OPF 写 `aep:render-mode`，QA 从成品读模式 | 实际译注缺失、过期、内容不完整仍拒绝；已登记注释但模式缺失/非法/歧义时要求重建，不猜配 |
| 3. P2 候选多位置 | 取消注文 note_id 在候选间唯一及物理位置必须有同单元引用/notes 类的限制；每个注文候选在所绑 note 的 `source_locations` 中须有 candidate_id，附带 unit/line 时逐项核对。删除已无意义的 `unit_kinds` 参数并迁移调用 | 图内 note/ref 稳定身份唯一；引用候选仍核对同单元、注号及独立引用，缺/错位置证据拒绝；不靠同号/文本前缀猜配 |
| 4. P2 媒体根与裸路径 | `media_paths.resolve_media_path` 共用现有源文件安全解析，期待侧由真实源文件得出包内身份。`audit_notes_epub` 必需 `media_root`，调用全部迁移；不从审计调用渲染器重建期望 | 源资源缺失、越界、错目录及成品漏资源仍阻断，不恢复 basename 集合豁免 |
| 5. P2 URI/字面身份 | Markdown/pandoc 路径百分号保持字面语义；HTML URL 解码一次，ZIP 名不解码。收集器单次改写避免把新 URL 再当源路径读取；注文门与通用 G4 共用 `epub_member_path` | `%41.png` 与 `A.png` 不能互冒，URL 编码外观的 ZIP 错名不能代替一次解码后的成员；外链/包外成员不能充当本地资源 |
| 6. P2 操作规范 | 同步 `SKILL`、notes reference、notes taskcard、build reference 和 EPUB template spec 五对中英文件；给出完整 note/ref 映射、candidate_id 位置证据、多位置/孤儿与构建模式规则 | 不让 agent 只写 disposition 后误入登记；不把新规则仅留在 Python 错误消息里 |
| 7. P2 脚本写入契约 | 恢复的 `v_structure_csv.py` 默认输出预览，无文件写入；只有显式 `--apply` 写 CSV。README 明确每一步预览/写入及输入快照边界，另交付脚本修订包 | 不重跑原书迁移、不覆盖 EPUB/归档、不声称脚本修订等于整书复现 |

### 9.2 实际验证

> **验收更正（当前 §10）**：本节此前把旧包装器的 `ran=true / errors=0` 当成真实 EPUBCheck 通过，结论撤销。后续实测发现默认单 JAR 缺相邻依赖，Java 非零退出仍可被旧包装器误记零错误。保留 CLI/子门/字节等观察和测试统计；本节旧报数不再作为外部校验成功证据。当前完整检查器与新判定后的真实重验见 §10。其他批次的历史记录不据此凭空判定通过或失败。

- 最终完整回归：`uv run --offline pytest -q` → **637 passed, 1 skipped**。
- 主仓库 `ruff check .` → `All checks passed!`，`ruff format --check .` → **304 files already formatted**；
  随包 CSV 修订脚本单独 check/format-check 亦通过。
- 集成期间修正了附录 fixture 对生成单元 ID 的错误假设，并删除固定错误文案断言；
  未通过重钉文案或降低产品门槛来取得绿色结果。
- 五对中英操作/模板文档已同步并 finalize；收尾 `i18n.py --check` / `--links` 均 **OK**，
  历史计划按约定保持中文。

以下保留当时 CLI/公开入口及旧报告的观察；其外部通过结论已撤销：

| 场景 | 当时调用/旧报告观察（不作为外部通过证据） |
|---|---|
| init → 候选核证/位置绑定 → notes register → import --reviewed → build → qa，完整译文 | EPUBCheck `ran=true`、0 error/0 warning，G4 pass、notes_findings 空、released=true |
| 第一注源文宿主、第二注译文宿主，target JSON 同时含第一注未用译文 | 源注/实际译注各归正确宿主；同上零错误并 released=true，不误比第一注的未用译文 |
| 上一混合产品只把第一条未用译注清为空占位，再 build → qa | 成品逐字节不变，notes_findings 空；旧报告声称 released=true |
| 无任何译文 Markdown，存在损坏但未用到的 target JSON | 源文回退构建和 QA 调用完成；旧报告声称 released=true |
| 工作区已有译文 Markdown，但通过公开 convert 入口构建源文 | QA 按 OPF source 模式核对源注，不误读坏译注；旧报告声称 released=true |
| 旧报告声称放行后，仅将 inserts 的 symlink 从 raw 内改指向存在的 raw 外文件 | 摘要变化、report_state.stale=true；status --all 为 built_not_released；重跑 QA 后 released=false、provenance_incomplete、E_INSERT_MISSING_FILE；旧 checker 零错误报数不作外部证据 |
| 合法孤儿译注宿主先渲染新鲜译注，再改过期摘要 | 过期后 build 拒绝且原成品字节不变，QA 注释门报 E_NOTES_STALE；负场景禁用外部检查器，只验证版本绑定 |
| CSV 脚本在无关 cwd 指向合成 51 文件工作区，原 CSV 为哨兵 | 默认调用保持所有文件和哨兵不变；--apply 仅改变目标 CSV，51 行顺序正确；归档中两文件与修订文件逐字节核对 |

真实 smoke 曾暴露通用 G4 仍按编码 href 直接查 ZIP 的误报（中文和字面百分号）；
已修复并增加合法链路与编码外观错成员的正/负回归，再完成上表整条 build→qa，不只报告子门通过。
`report_state.released` 保留**旧报告声明**，过期时可仍为 true；真正有效性须同时看 stale。
本轮验证了聚合 progress 退回与重跑 QA 拒绝，未擅自改写历史 report 的 released 字段。

### 9.3 脚本交付与未关闭事项

本轮在 `read` 和实际 `stat` 均无法取得原 `/tmp/opencode/` V 工作区/完整修订归档；
Downloads 原始书籍目录和归档仍在。仅从会话原文恢复 CSV 脚本与说明并修订，
不拿原始 36 单元归档冒充新 51 单元 V 交付。

- 修订包：`/home/misaka0x26fe/Downloads/forced-labour-and-extermination-script-fix.tar.gz`；
  仅含 `reviews/tools/v_structure_csv.py` 和 `reviews/tools/README.md`，不含书稿/EPUB/迁移前快照或 v_restructure.py。
- SHA-256：`ce6bb6c56168e598246adcbc4ef5db42d4ba04add266266bc6509c4bcdd6c9f9`。
- 恢复的原 CSV 脚本与会话原文 snapshot `1B3B` 一致后再修订；不声称完成原完整归档的替换或 153 文件复现。
- 剩余真实书工作：N 迁移、续文/编号/原位绑定和 245 个术语命中逐项核证；
  阅读器兼容抽查为可选，未实测不阻塞标准交付。代码与入口收尾见 §10。
- 临时 smoke 工作区自动清理。源文/译文回退合成场景的成功不代表历史真实书已放行或完成交付审计。


## 10. 单一输出与标准注释收尾（代码与架构已提交 `1db8752`）

用户明确只保留源文转换和译文优先构建，相关额外模式的实现、参数、配置、后缀、
审计旁路、测试与旧说明均删除，不保留别名或兼容开关。句级 align 继续服务源译核对、
保真、修订定位和恢复，不承担成品排版。

官方 QA 先得到有效登记上下文并执行独立成品注释门，再移交旧数量与必须有回链判据；
合法无引用注文不再被旧门误拦，未登记/过期及缺内容、缺媒体、额外 aside 仍阻断。
AGENTS 语义整备和注释核证/登记步骤已前移，保持 CLI 机器指针一致。

交付基线不要求桌面：agent 核证内容与来源，CLI 校验标准 noteref/footnote、引用/回链、
资源、目录图和 EPUBCheck。弹窗呈现由阅读器决定；可选 GUI 抽查有则记录环境与观察，
无桌面记未实测，不因此阻塞，也不声称任意阅读器兼容。

### 10.1 实测发现并修复的额外硬缺陷

- **校验器 fail-open**：非零退出（包括缺依赖的 `NoClassDefFoundError`）和 FATAL 不能按零错误放行；固定英文诊断，保留退出码及错误输出。`EpubcheckResult` 必需声明实际 `returncode`，无执行为 null；报告只有 `ran=true && returncode=0 && errors=0` 才可通过。
- **旧放行证据失效**：已有摘要但缺退出证据的旧 released 报告在 `report_state` 标为 `epubcheck_unverified`，聚合进度退回 `built_not_released`；保留原 released 声明，不手改历史。原 `digest_missing` 优先级保留。
- **媒体 manifest ID**：路径替换生成 ID 会令字面 `%` 非法，并令 `a/b.png` 与 `a_b.png` 碰撞。改为稳定顺序分配合法唯一 ID，封面仍引用实际项；不把 ID 格式当公共文件名约定。
- **普通正文媒体身份**：真实产品已通过 EPUBCheck，却因 provenance 把 Markdown `%41` 误解成 `A` 而阻断。现与既有源文件解析和 URL→ZIP 规则一致，按完整路径及数量核对，不以 basename 放过错目录图片。HTML 图片不作正文标签字面探针，但邻接文字仍必须保全。

环境修复不需要再装 Java：用户已安装 JRE 21。缓存中完整 5.2.1 发行包与默认 JAR 的 SHA-256 一致，仅恢复默认 JAR 相邻 `lib` 的链接，未替换 JAR、未下载、未 sudo。实际 `--version` 为 EPUBCheck 5.2.1。

### 10.2 当前真实无桌面验证

所有 smoke 使用临时合成工作区并移除 DISPLAY/WAYLAND/会话总线环境，不调用 LLM 或网络，不用外部检查器替身。

| 场景 | 实测 |
|---|---|
| 真实 CLI 源文转换 → QA | released=true，保存 checker returncode=0、0 error/0 warning |
| 仅删除报告 checker.returncode，其余产物保持原样 | 原 released=true 保留，stale=true、epubcheck_unverified，status_all 进度 built_not_released |
| 临时复制同一 JAR 但不带 lib，实际 CLI QA | JVM NoClassDefFoundError，returncode=1、errors≥1，released=false、epubcheck_errors；诊断保留 |
| `%41`、嵌套目录与路径替换碰撞名共存 | 真正 checker returncode=0、0 error/0 warning，完整 QA released=true；重复构建逐字节相同 |
| 当前标准 noteref 与合法无引用注文分别完整构建 → CLI QA | 均 released=true、checker returncode=0、notes_findings 空；引用数分别为 1 和 0，无伪造引用 |
| 分别删除上述两个成品的注文内容 | 均 released=false、notes_open、E_NOTES_CONTENT_MISMATCH |
| 合法产品的 left/same.png 被换成已有 right/same.png | 真正 checker 仍 returncode=0，provenance 精确查出 1 个缺失身份并拒绝放行 |
| HTML 图片周围正文被删 | 真正 checker 仍 returncode=0，E_EPUB_PARA_LOST、覆盖率下降且拒绝放行；未用删除整个图片段落来掩盖误报 |

恢复完整检查器并修复退出判定后，还实际重跑完整译文、逐注源/译宿主混合、清空未用译注、源文回退、显式源文转换，以及合法无引用注文；正例均 0 error/0 warning 并放行。独立删除注内容/aside/媒体、添加额外 aside、登记过期、未登记和 inventory=none 残注均保持阻断。具体旧报数的撤销见 §9.2，不把这些合成样例称为原书完成验收。

真实阅读器兼容未实测，按用户边界为可选。原书 N 迁移、245 条术语核证和缺失 V 工作区前置条件不变；未覆盖原书。当前主仓库提交与架构补充见 §10.4。

### 10.3 单一输出阶段回归与文档同步（提交前补充见 §10.4）

- `uv run --offline pytest -q`：**643 passed, 1 skipped**。
- `uv run --offline ruff check .`：**All checks passed!**；`ruff format --check .`：**305 files already formatted**。
- `i18n.py --check` / `--links`：均 **OK**；当前补充的 8 对检查器/媒体契约文档已同步并 finalize，之前的单一输出与无桌面文档同步保留。
- 初次完整回归发现 4 个测试检查器替身未显式迁移退出值，以及旧封面测试锁定路径派生 ID；已迁移替身、删除无意义 ID 文案/格式断言，不重钉新格式。新的合法唯一 ID / 封面绑定测试检查真实 OPF 关系。
- 新增过程失败/FATAL、旧报告缺退出证据、特殊媒体 ID、字面百分号/单次 URL 解码、错目录同名图及 HTML 图片邻接正文缺失的行为回归；百分号误拦和错图漏检均观察到修复前失败。

### 10.4 架构整理与提交收口

- **实现提交**：`1db8752a6b7593f478c1ed24b14b66068575e886`，`fix(epub)!: enforce single-output builds and verified release gates`；包含 91 个本轮源码、测试、模板、操作指南和架构文档，不含书籍工作区、归档或成品。
- **当前架构**：[中文权威](../architecture.zh.md) / [英文孪生](../architecture.md)，README 已加入口。组件依赖和 agent/CLI 数据流各一图，中英文共 4 图经 Mermaid 11.12.0 在真实 headless Chromium 解析、渲染与目视检查；无横向溢出。按现状标明无 SQLite 术语后端、无独立 services 包、不存在内部自动翻译或 G1–G3 执行器，不将模型保留状态和纯函数误画成在用服务。
- **聚合器判据去重**：架构核对发现 `passed` 检查 returncode、`released` 却另写条件。现直接复用 passed，错误计数为零但退出未知/非零也拒绝；两个消费者用例观察到修复前失败，修复后相关 52 项回归通过。再跑真实 CLI：完整检查器 returncode=0 放行；缺 lib 的同一 JAR returncode=1、epubcheck_errors 阻断。
- **删除数量快照测试**：新增架构文档触发“固定 64 对文档”断言；删除该偶然实现断言，不改钉新数量。翻译哈希、语言横幅及链接契约检查保留并通过。
- **最新完整回归**：`uv run --offline pytest -q` → **644 passed, 1 skipped**；Ruff check 通过、format-check **307 files already formatted**；`i18n.py --check` / `--links` 均 **OK**。§10.3 的 643 条记录保留为前一阶段实测，不冒充当前统计。

