# 2026-10-04 三项待办梳理与实施思路（导航层级 / skills 化 / 工作原子化）

状态：规划中（2026-10-04 已完成可行性审查：代码逐条核实，行号断言全部准确；
S-A 风险点已论证解除；S-B 两处语义已澄清；依赖关系已修正。见各节「审查核实」）

## 背景

用户于 2026-10-04 复盘时提出三项待办，要求**落成文档并保留在仓库中**（含具体内容 +
修改思路），避免再次依赖会话记忆。本文件是这三项的**唯一权威梳理**，逐项给出：来源、
真实状态（含已完成/未完成的判定）、修改思路、验收与依赖关系。

> **本文件不改动任何代码**。它是立项前的现状核对与思路存档；真正动手时按
> `docs/plans/README.md` 的约定另立 `YYYY-MM-DD-<主题>.md` 实施计划。

---

## 总览：三项的性质与依赖

| # | 待办 | 载体 | 真实状态 | 影响面 |
|---|---|---|---|---|
| 1 | 成品 EPUB 导航层级过扁平 | GitHub Issue **#16**（open） | **部分完成**（nav-depth 计划已建能力，#16 剩余 2 个缺口） | **成品交付质量**（读者实际阅读体验） |
| 2 | 项目 skills 化（标准 skill 包） | 仅在 `2026-09-30-workflow-microtasks.md` 末节被提及 | **未立项**（无独立计划、无代码） | 文档/包装 |
| 3 | 工作原子化（弱模型可执行） | `docs/plans/2026-09-30-workflow-microtasks.md`（S1–S5） | **规划中**，S1–S5 均未实施（代码零命中） | 流程使能 |

**依赖关系（审查修正：仅一条硬依赖，其余是价值排序）**：

```
#16 导航扁平     原子化 S1 ──硬依赖──→ skills 化
（独立可开工）    （独立可开工）        （素材前置，最后做）
```

- **唯一的硬依赖**：skills 化 ← 原子化 S1（`status --json` 的 `next_tasks` 机器指针
  与任务卡是 skills 化的**前置素材**，`2026-09-30-workflow-microtasks.md` 末节已明确）；
- **#16 与原子化 S1 技术上相互独立**（前者是 build/qa/orchestrator 的导航链路，后者是
  status 派生逻辑，代码路径零交集）——排序 `#16 → S1` 只是**价值优先级**（#16 是三项中
  唯一影响一本书实际交付质量的一项，先做），不是阻塞关系。若用户拍板先做 S1 也不依赖
  #16 的任何产物；
- 因此推荐顺序 #16 → 原子化 S1 → skills 化（价值排序），其中前两者可并行或换序。

---

## 待办 1：成品 EPUB 导航层级过扁平（Issue #16）

> **目标（用户 2026-10-04 明确）**：导航**立体化**——成品 EPUB 的目录应与正常出版物
> 一样有**多个层级**（如「章→年→条」），而非扁平单层。立体化的本体 = structured/
> 里有层级标题（h2/h3）+ build 渲染嵌套 nav/NCX（后者 6b3acb7 已实现）；S-A 修声明
> 失真、S-B 修告警误报，均为配套而非本体。

### 1.1 来源与现象

- **来源**：现场报告 #10（波斯语/RTL 编年史）遗留告警 `W_TOC_MISSING`，2026-09-29 单独立项。
- **真实案例**：`Misaka0x272F/matla-al-sadayn-1` —— 267 页、**232 条源 PDF 书签**的编年史。
  成品导航**完全扁平**：`nav.xhtml` 仅 16 个并列 `<li>`、`toc.ncx` 16 个一级 `navPoint`；
  正文实际有 138 个单元内标题（h2×45 + h3×93）**全部不在导航里**；
  `content.opf` 却声明 `nav-depth=3`（**声明 3、实际 1** 失真）；`qa` 仅 warning
  `W_TOC_MISSING`（227 条源书签未映射），不阻断。读者失去「章→年→条」两级书内导航。

### 1.2 已完成的部分（`2026-09-29-nav-depth.md`，提交 6b3acb7）

该计划把「标题进导航」所需的**链路能力**基本建好了，S1–S4 均已实施：

- **S1** g0 标题守恒（`review/g0.py` 新增 `heading` 计数，进 `g0_structure_open` 硬门）；
- **S2** 锚点级 nav（`build/html.py` 自动 id、`subheading_anchors()`、`nav/NCX` 渲染
  `file.xhtml#anchor`、`dtb:depth` 取含锚点的实际最大深度）；
- **S3** qa 目录对账扩展到锚点级（`nav_depth_sequence()`，build 与 qa 共用防漂移）；
- **S4** ingest 层级保真（`pdf_reader._apply_sub_toc` 处理 level≥2 书签三策略、
  `rebuild._render_markdown` 按 `heading_level` 写标题）。

### 1.3 #16 仍未闭合的两个缺口（已逐条核实代码）

| #16 建议 | 状态 | 核实结论（文件:行） |
|---|---|---|
| 1. 单元内标题进 TOC | ✅ 已由 nav-depth 计划覆盖 | `build/__init__.py:359` nav 经 `nav_toc_entries` + `_toc_tree` 渲染锚点条目 |
| 2. `nav-depth` meta 如实声明 | ✅ **已完成（2026-10-05）** | 见 §1.4 S-A：`nav-depth` 改为写**实际深度** A（与 `dtb:depth` 同源），另加 `nav-projection` 保留投影上限 K 给 qa。**实施修正**：不能只把 `nav-depth` 改成 A——qa 用该 meta 重建期望集，扁平/错误构建声明 A=1 会自证「期望扁平」而漏报 `E_TOC_FLAT`（由 `test_provenance_anchor_toc_flat_detection` 暴露），故须新增 `nav-projection` 分离两种语义 |
| 3. 源书签映射（可选增强） | ❌ **完全未做** | 全库 `grep` 无「书签→标题锚点」映射逻辑；`orchestrator.py:999` 的 `W_TOC_MISSING` 仍只做「facts 源 TOC vs 单元标题」文本对账，无法反映真实覆盖缺口 |
| 4. 配置面 | ✅ 够用 | `config.output.nav_depth` 默认 3，无需新增开关 |

**结论（审查后更精确的根因链）**：#16 报的那本书之所以仍扁平，是**两层问题叠加**：

1. **读者可见的扁平**：该书 `structured/` 是旧代码产物（无 h2/h3 标题段，单元全
   `level=1`），S4 的 `_apply_sub_toc` 需要**重跑 `preprocess`** 才会把 level≥2 书签落成
   标题段；此后 S2 锚点链路会自动让 nav 嵌套（能力已在）。
2. **告警不反映真实缺口**：即使重跑后导航修好，`_toc_missing_from_facts`
   （orchestrator.py:687-710）仍只对账**单元级标题**（`e.get("title")`），不看
   `anchors`——已进导航的子标题书签仍会全部计入 `W_TOC_MISSING`（误报），
   这才是 S-B 要修的「映射未建」。

### 1.4 修改思路（建议按 S1/S2 拆两个小步）

**S-A `nav-depth` meta 如实声明（✅ 2026-10-05 已完成）**

> **实施记录**：`_render_nav` 写两个 meta——`nav-depth` = 实际深度 A（`max(nav_depth_sequence(entries), default=1)`，与 NCX `dtb:depth` 同一表达式）、`nav-projection` = 投影上限 K；qa 的 `_nav_declared_depth` 读 `nav-projection`（旧产物回退 `nav-depth`）。回归：`test_build.py::test_nav_depth_meta_equals_ncx_dtb_depth` +
> `test_provenance.py::test_provenance_anchor_toc_flat_detection`（守住 E_TOC_FLAT 不漏报）。
> **修正了本文档原审查结论**：原文断言「用 A 重建期望集与 K 恒等」只在**良构构建**下成立；错误/扁平构建下源在 (A,K] 有节点，用 A 会漏报，故必须分离 `nav-projection`。



- `build/__init__.py:_render_nav` 的 `<meta name="nav-depth">` 改为写入**渲染后实际最大
  深度**（复用已存在的 `nav_depth_sequence(nav_toc_entries(...))` 或 NCX 已用的同一
  计算路径），与 `dtb:depth` 同源，消除「声明 vs 实际」失真。
- ~~注意：qa 侧对账需确认……这是本步唯一技术风险点，需读 qa 侧对账代码确认。~~
  **审查核实（2026-10-04，风险解除）**：qa 侧（`qa/provenance.py:471-490`）把该 meta
  读出后仅作**投影上限**使用——`effective_depth = declared_depth if ... else nav_depth`
  （:474），再 `nav_toc_entries(spine_entries, effective_depth)`（:484）重建期望集，得到
  `nav_exempt`（:486-490）与 `toc_depths_expected`（:491）。设 build 投影参数为 K、渲染后
  实际最大深度为 A，则 A ≤ K 恒成立，且渲染树中不存在深度 > A 的节点（A 即最大值）；
  因此用 A 作上限重建期望集与用 K 重建**恒等**（深度区间 (A, K] 内无节点可剔除）。
  → 把 meta 从 K 改为 A 对 `E_TOC_COVERAGE`/`nav_exempt`/`E_TOC_FLAT`/`W_TOC_DEPTH`
  **全部无行为影响**（对良构构建），meta 只变得对外部工具/读者 truthful。
- 实现要求（防漂移）：`_render_nav` **不得新写第二份深度计算**——直接复用
  `_render_ncx` 已有的 `max(nav_depth_sequence(entries), default=1)`（`build/__init__.py:417`）
  同一表达式，nav 与 NCX 两侧同源；空目录时与 NCX 一致取 `default=1`（qa 的
  `_nav_declared_depth` 校验 1–6，天然通过）。
- 回归：单元链全 level=1 且无锚点 → meta 写 1；含 h2/h3 → 写实际深度；`--nav-depth`
  投影截断时 meta 与实际一致；**新增一条断言**：任意工作区 build 后
  `_nav_declared_depth(epub) == NCX 的 dtb:depth`。

**S-B 源书签映射（工作量主要在这步）**

- 在 `orchestrator.py` 现有 `W_TOC_MISSING` 对账处（facts 源 TOC vs 单元/锚点）升级为
  **锚点级映射**：按标题文本（优先全等/规范化后等）→ 就近页码兜底，把 facts 里的源书签
  映射到具体 `unit#anchor`；映射不上的才计入 `W_TOC_MISSING`，使该告警反映**真实覆盖
  缺口**而非「书签数 vs 导航数」的量差。
- **设计约束（审查补充，两条）**：
  1. **对账必须在源文语言空间完成**：`structure_entries` 的锚点标签是 structured/
     源文标题，facts 源 TOC 也是源语言——二者可匹配；成品 nav 里的锚点标签是**译文**，
     不可作为对账对象（翻译改写标题文本，但 g0 heading 守恒保证结构不变）。已核实
     `structure_entries` 条目携带 `anchors` 字段（`qa/provenance.py:482` 有消费），数据可得。
  2. **「就近页码兜底」的准确语义**：锚点本身**无页码**（structured 标题段不带可对账的
     页码元数据），页码只能用于**定位候选单元**——书签页 → 落在该页码范围（或最近
     source_page）的单元 → 单元内做标题匹配。实施时需先确认单元级页码范围的可得性
     （publication.json unit meta / structured 段的 source_page 聚合）；若无，兜底退化为
     「全局标题唯一匹配，多个同名才算 missing」。另注意：**EPUB 源的 facts TOC 无页码**
     （`preprocess/sniff.py:107-143` 只解析出 title+href），页码兜底仅 PDF 路径适用，
     EPUB 源只走标题匹配。
- **告警数据结构升级**：`toc_missing` 从裸标题列表升级为结构化映射结果（每条：
  书签 title / page / 匹配到的 `unit#anchor` 或未匹配原因），`generate_report` 的消费方
  同步；`report.json` 字段语义变化需保持向后可读或注明版本。
- 纯函数、零 token（符合单 LLM 原则），可离线单测。
- 回归：`#16` 场景复现——「单元全 level=1 + 单元内多级标题 + facts 源书签」断言
  `W_TOC_MISSING` 只剩真正无法映射者；`E_TOC_FLAT` 语义（`qa/provenance.py:493-499`：
  期望深度 >1 而 nav 实际单层 → 报 error）保持不变且能检出该场景。
- **文档同步义务（AGENTS.md 契约，审查补充）**：改 QC 行为必须同步——
  `skills/auto-epublizer/references/qa.md`（+zh）的 `W_TOC_MISSING` 解读、
  `references/review.md`（+zh）相关段落、`docs/postprocessing-spec.md` §2.3
  （W_TOC_MISSING 线索的定义），走 `i18n.py --finalize`。

**边界与不变量**

- 不改 `nav_depth` 投影语义（1–6，超深不进目录、保留 spine 与锚点）；
- 不改单元状态机；不改 `publication.json` 契约；
- 既有工作区需重跑 `preprocess` 才完全受益（facts 刷新幂等；但是否连带重建
  structured/ 及其对已有 translation 的影响**待核实**，见 1.5 清单第 2 项）；
- 验收：nav/NCX 按 `nav_depth` 真实嵌套；`nav-depth` meta == `dtb:depth` == 实际深度；
  `W_TOC_MISSING` 只剩真缺口；epubcheck 0 error；回归覆盖「全 level=1 + 多级子标题」。

### 1.5 前置依赖（开工前需用户确认；审查已具体化为核实清单）

#16 的真实案例工作区在**另一仓库** `Misaka0x272F/matla-al-sadayn-1`。开工前需访问该
工作区（或请用户提供路径 / `publication.json` 现状），逐项核实：

- [ ] **该书是 convert-only 还是翻译流程**：决定立体化的数据侧路径——
  convert-only → 直接重新 `convert`（S4 书签落段 + 嵌套 nav 一步到位）；已翻译 →
  见下一条；
- [ ] **structured/ 重建入口与 translation 影响**：`preprocess` 只刷新 facts
  （orchestrator.py:350-367），**不重建 structured/**——重建要走重新 `init`/ingest。
  若单元边界不变（只是章内新增标题段、单元 id 与 rel_path 不变），用 `restructure`
  登记后状态保留（unchanged ids keep state 契约）；已翻译单元需 agent 把新增标题段
  补进译文（g0 heading 守恒会拦出不一致）；
- [ ] **单元级页码范围可得性**（S-B 页码兜底的前提）：publication.json unit meta /
  structured 段的 source_page 聚合是否可用（见 1.4 S-B 设计约束 2）；
- [ ] **publication.json units 的 level 现状**（是否全 level=1）。

---

## 待办 2：项目 skills 化（标准 skill 包）

### 2.1 来源与真实状态

- **来源**：`2026-09-30-workflow-microtasks.md` 末节「与『标准化 skill 改造』待办的关系」——
  该计划产物（原子任务卡、机器指针、一屏契约）是改造为**标准 skill 包**的素材与前置，
  「标准化改造立项时直接复用，避免二次返工」。
- **真实状态**：**未立项**。全库无 `references/taskcards/` 目录、无 skills 化独立计划；
  现有 `skills/auto-epublizer/`（`SKILL.md` + 15 篇 references + 10 篇 lessons）已是可用
  skill 形态（可 `scripts/install-skills.sh --target opencode` 安装），但**不是「标准
  skill 包」**（渐进式披露 / 任务卡粒度 / 机器可判完成判据等标准 skill 特征尚未落地）。

### 2.2 修改思路

- 立项时以**原子化 S1–S5 的产物为素材**（顺序：#16 → 原子化 S1 → skills 化），不重复造。
- 关键改造点（源自标准 skill 实践 + 本仓库约束）：
  - `SKILL.md` 保持**入口精简**（渐进式披露），把阶段细节下沉到 `references/`；
  - 弱模型主路径 = `SKILL.md` → `status --json.next_tasks` → 对应**原子任务卡**（原子化 S2）；
  - 每张卡「一屏以内、自包含」，完成判据是**跑一条命令/查一个文件**级（原子化 S1 的
    `done_when`）；
  - `manifest.json` references 清单与实际目录严格一致。
- 边界：`skills/` 是纯文档（无业务逻辑）；强模型路径（阶段级 references）**无损保留**，
  skills 化是增量而非替换；文档 i18n（中英双语 + `i18n.py --finalize`）契约照旧。

### 2.3 验收

- **端到端**：可被下游 agent 仅凭 `AGENTS.md` + `skills/` + `docs/` 完成一本书
  （审查注：现有 skills 形态已应基本满足此条，作为 skills 化的**增量**验收太弱，
  应以弱模型专项为准）；
- **弱模型专项（主验收）**：一个偏弱 agent 能沿
  `SKILL.md → status --json.next_tasks → 任务卡` 路径完成至少一个完整阶段（如
  逐单元翻译循环 `translate-unit → import-unit → fix-g0-unit`）而不跳步、不重做、
  不依赖会话记忆——这是「标准化 skill」区别于现有文档形态的核心特征；
- 任务卡索引与 `manifest.json` 一致；`--links` / `--check` 全绿。

---

## 待办 3：工作原子化（弱模型可执行）

### 3.1 来源与真实状态

- **来源**：`docs/plans/2026-09-30-workflow-microtasks.md`（状态：规划中）。核心目的（用户
  原话）：让**比较弱的模型**也能按**较小的多次任务**完成全部翻译/转换工作。
- **真实状态**：S1–S5 **均未实施**——`next_tasks` / `taskcards` / `done_when` 在代码与
  skills 中**零命中**（仅出现在计划文档文本里）。该计划的自诊断痛点：①单阶段产出过重；
  ②「下一步做什么」靠模型推断；③任务完成判据无机器校验；④上下文自包含性缺失。

### 3.2 修改思路（建议先只做 S1，单独成一次提交）

计划本身设计扎实（边界与不变量：单一状态源、零 token 可测、强模型路径无损），**不反对
其设计**；但建议**先只实施 S1**，理由：

1. **成本分布极不均衡**：S1/S3/S4 是代码，S2/S5 是文档；S2 要新建
   `references/taskcards/` 首批 ~12 张卡 × 中英双语 ≈ 24 个新文件，还要把 15 篇阶段级
   references 降级重写，每篇都要走 `i18n.py --finalize`。真正让弱模型能动的使能项是 S1，
   其余是包装。
2. **计划出发点尚未验证**：「让弱模型能完成全流程」是真实目标，但 4 条痛点是**推断出的
   假设**，没有实测支撑。S1 的 `next_tasks` 对任何模型都有独立价值（把状态→行动的映射
   从散文变机器可读），先做风险为零；S2 那 24 个文件是押注在「弱模型确实需要任务卡」这个
   假设上的。

**S1（`status --json` 增加 `next_tasks` 机器指针）要点**：

- 在 `orchestrator.status` 现有状态机/对账逻辑上**派生**（不新增第二份状态源），输出
  `next_tasks: [{kind, unit?, hint, done_when}]`，按执行顺序排列，弱模型只取首条执行，
  完成后重跑 `status --json` 刷新；
  （审查核实：派生基础已确认存在——`orchestrator.py:1067` 的 status 已含产物-状态
  对账与 stale 检测 :1070-1136，S1 是在其上叠加输出，无新状态源，可行。）
- 派生规则（与 workflow 路由伪代码一一对应，注释互引）：无 `publication.json` →
  `preprocess`；facts 有而理解产物缺 → 逐文件「写 preprocessing/<file>」；repair 信号触发
  → 语义整备；有 structured 无 analysis → 逐单元「分析 chXX」（每批 ≤5 防贪多）；translation
  在而状态 stale → 「import --unit chXX」；状态 ≤analyzed → 「翻译 chXX」（一次只给一个
  单元 id）；aligned 未 reviewed → 「审校 chXX」；全部 reviewed → `build`→`qa`→`delivery`；
- `done_when` 是判据的机器表述（如 `{"cmd":"import","unit":"ch03"}` /
  `{"file":"preprocessing/global.md"}`），可跑/可查级。

**后续（S3→S2→S4→S5）**：S3 todo.md 骨架契约化（`preprocess` 生成固定 checkbox 骨架，
`status` 对账虚报/漏勾）→ S2 任务卡 → S4 review 产物 per-unit 批化（`units/<id>.json`，
`result.json` 的 g1/g2/g3 计数改为派生）→ S5 自包含纪律写入任务卡与 SKILL.md。
**建议在 S1 落地后，拿一本真书 + 一个偏弱 agent 实测**，用真实「卡在哪」决定 S2–S5 范围，
而非照推测一次性铺 24 个文件。

### 3.3 边界与不变量（沿用计划）

- 单一状态源不变：`next_tasks` 从现有状态机派生，不新增状态文件、不改 `publication.json`
  契约；`done_when` 全部可用现有 CLI 判定；
- 离线确定性：`next_tasks` 派生与 todo 骨架生成都是零 token 纯函数（可测）；
- 单元状态机 `pending→…→built` 不变，本计划只细化**任务粒度**。

### 3.4 验收

- `test_status_next_tasks`：构造各阶段工作区（facts-only / 缺不同理解产物 / stale /
  半 translated / 全 reviewed / built）断言 `next_tasks` 序列与 `done_when`；
- todo 骨架生成 + 对账（漏勾/虚报告警）回归；review `units/*.json` 派生汇总 + qa 兼容
  （`result.json` 旧格式仍可读）；
- 全量 `uv run pytest -q` + ruff。

---

## 与其他在办事项的关系

- 本文件与仓库现有计划**并存**：本文件是「三项待办的总梳理」，具体实施仍按
  `docs/plans/README.md` 约定另立当主题计划；#16 已存在于 GitHub Issues，计划文档
  完成后应回写 #16 状态并关闭 issue。
- **待办 2「skills 化」已另立实施计划**：[2026-10-05-skills-standardization.md](2026-10-05-skills-standardization.md)
  （skills.sh / Agent Skills 合规 + 发布 + 渐进式披露 + 多 skill 拆分 + 跨文档总表）；
  其中 P0 合规已完成（`SKILL.md` frontmatter 置顶）。待办 2 的「修改思路/验收」以其为准，
  本文件不再展开。
- 统一术语库/知识库已于 2026-10-04 转为公共仓库（`auto-epublizer-knowledge`，内容
  CC BY-SA 4.0，地址已固化 `DEFAULT_KNOWLEDGE_REMOTE`）——与本三项独立，不在此展开。

## 实施顺序建议

> 审查修正：#16 与原子化 S1 **技术独立**（代码路径零交集），顺序是价值排序而非阻塞
> 关系；两者可并行或换序。唯一硬约束：skills 化最后做（素材前置）。

1. **#16 导航扁平**（唯一影响成品质量；拆 S-A / S-B 两小步——S-A 风险已解除可立即
   动手，S-B 开工前完成 1.5 核实清单，需确认案例工作区可访问）；
2. **原子化 S1**（使能项，独立可交付，单独提交；随后拿真书 + 偏弱 agent 实测，
   用真实「卡在哪」决定 S2–S5 范围）；
3. **skills 化**（复用前两者产物，最后包装；以 2.3 弱模型专项为主验收）。
