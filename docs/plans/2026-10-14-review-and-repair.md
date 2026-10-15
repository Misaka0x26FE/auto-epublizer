# 2026-10-14 全项目审查与修复计划

状态：**实施中（审查回流）**。§7 保留原批次的完成记录；§8 已实现成品软件指纹，
但后续审查仍有 P1/P2 待修项；V/H、阅读器注释实测及真实书回源验收仍阻塞，不宣称全项目整改完成。

线上跟踪：[Issue #41](https://github.com/Misaka0x26FE/auto-epublizer/issues/41)。§7 为前批次记录，§8 为本轮本地审查与新增实现；本轮未修改线上 issue。实施状态、回归证据与历史成品重建分别记录。

## 1. 目标与边界

对当前 auto-epublizer 的三包代码、测试、CLI 与下游操作文档制定风险驱动的审查和修复路线，
并将已交付成品的注释与导航问题纳入整改。本轮只更新计划；不修改业务代码、工作区或 EPUB，
不访问 MinerU、不执行知识库推送。一般审查候选与已观察案例分开记录，不把静态推论写成已确认根因。

方法采用 brooks-lint 的 R1–R6 / T1–T6：职责与认知负担、变更传播、知识重复、偶然复杂度、
依赖方向、领域模型，以及测试意图、脆弱性、重复、mock 滥用、风险覆盖和测试层次。
当前不计算 Health Score；有限勘察不足以支持全项目评分。

硬约束：

- 唯一 LLM 是操作 CLI 的 agent；不得引入模型 SDK、端点或语义自动裁决。
- 保持 `auto_common ← auto_translator ← auto_epublizer` 依赖方向；编排层只装配和路由。
- 保持源文件不可变、源哈希绑定、原子状态提交、可恢复处理、稳定输出顺序和追加式事件账本。
- 修复不得削弱 G0–G5、源保真、术语冲突、媒体/脚注/目录及交付审计门槛。
- 测试离线、确定性，使用临时目录和合成样本；不依赖本机真实书库。
- 不因长文件、长函数、相似代码或测试数量直接判债；不预设重写、引入新服务层或抽象。

## 2. 已观察事实与待验证问题

路径和行号来自本轮读取，仅用于定位；实施时重新定位，不能把历史行号当作稳定 API。

| 已观察证据 | 审查问题（尚未判定为缺陷） | 对应任务 |
|---|---|---|
| `src/auto_common/workspace/store.py:47–55` 使用固定 `.tmp` 后缀与 `os.replace`；`:184–197` 的 publication 写入带状态锁，`:265–266` 的 QA 写入直接调用原子写函数 | 调用链是否充分串行化？异常/中断/竞争写入时能否保全旧状态及可读报告？先核对所有调用方和锁作用域，不能仅据固定临时名判故障 | A |
| `src/auto_epublizer/qa/report.py:83–171` 集中计算 G0、审校计数、溯源条件与 released；同时读取 `coverage` 和 `epub_coverage` | 缺失、过期或矛盾证据是否可能放行？成品覆盖率是否通过溯源 findings 完整进入硬门？不能只看该函数局部就认定漏门 | B |
| `src/auto_epublizer/orchestrator.py:1–5` 声明薄 façade；`:67–162` 包含 OCR/MinerU 路由、源嗅探和结构状态推进 | 哪些是合理装配，哪些领域策略泄漏？是否导致 CLI、build、qa、status 的策略分叉？ | C |
| `tests/test_architecture_boundaries.py:90–97` 的薄编排约束检查若干禁用字符串 | 是否仅约束特定写法而未保护实际职责边界？保留有价值的架构契约，不靠增加禁词假装覆盖 | C、F |
| `tests/test_e2e.py:55–128` 的主路径直接调用 orchestrator，手动设置 reviewed，并故意指定不存在的 epubcheck jar | 实际 CLI 登记 review 的路径及真正放行路径由其他测试覆盖了吗？该 E2E 本身不证明它们已覆盖 | B、F |
| `src/auto_epublizer/cli.py:33–40` 明确保护 JSON 不被 rich 折行；`:43–52` 有单工作区选择逻辑 | 非 TTY、窄终端、错误输入与嵌套/异构工作区下，机器协议和选择行为是否一致？ | E |
| `docs/plans/2026-10-05-remaining-fixes.md:3–19` 记载历史完成状态和 445 passed | 历史成绩不是当前基线；已完成 R0–R4 不直接重新列为未修复问题 | S0 |

未发现根目录 `.brooks-lint.yaml`；本计划采用默认风险范围，不创建项目专用配置。

### 2.1 线上 issue 分诊与归属

分诊时 GitHub 开放 issue 为 #33–#41 共 9 条，开放 PR 为 0；本地 HEAD 与线上 main 均为
`4d76c62bfc960aaaaab0fe70b16a01bc75c29cb9`。已读全部正文和评论，未重跑报告者已经提供的失败，
未关闭 issue。以下是该次盘点的快照，实施时刷新，不把快照当作永久状态。

| Issue | 处置 | 归属与独立关闭条件 |
|---|---|---|
| [#37](https://github.com/Misaka0x26FE/auto-epublizer/issues/37) 注释未语义化却放行 | 首批发布阻断专项，不只补 warning | N/B：已有注释证据却无语义注文、部分遗漏均不得全绿；确认无注的书仍可正常通过 |
| [#34](https://github.com/Misaka0x26FE/auto-epublizer/issues/34) 源侧上标注码漏计 | 与 #37 共用身份/作用域契约，独立验收 | N：受约束源侧识别、引用与定义分开统计、真缺失阻断；不扩大共享正则后声称只影响源侧，不搬注码到句末 |
| [#36](https://github.com/Misaka0x26FE/auto-epublizer/issues/36) BOM／显式术语输入静默失效 | 高优先级，可独立实施 | E：有/无 BOM 一致，显式坏输入在写回前失败，空结果可见；保留明确的 cwd-relative 约定，不做 workspace/cwd 存在性 fallback |
| [#35](https://github.com/Misaka0x26FE/auto-epublizer/issues/35) 历史冲突误报为本次发现 | 与 #36 同批可减少交叉修改，但分别结单 | E：新增、当前 open、历史记录分开；重复导入幂等；resolved 不要求重裁，已有 open 仍提示，不删账本掩盖问题 |
| [#33](https://github.com/Misaka0x26FE/auto-epublizer/issues/33) 台账折行／误扫模板 | 两个子问题分别修复验收 | E：stdout Markdown 不经 Rich 折行；排除可识别的工具模板而保留合法嵌套工作区。当前 `-o` 已直接写文件，文件侧报告需另查输入/入口，不照搬 stdout 归因 |
| [#38](https://github.com/Misaka0x26FE/auto-epublizer/issues/38) 缺版面异常检测 | 接受可定位信号，收窄“统一设 error”提议 | D/B：CJK 空格、疑似断段、裸数字插入先作候选，agent 核证；诗歌、标题、合法空格与统计数字不得因此自动阻断或改写 |
| [#39](https://github.com/Misaka0x26FE/auto-epublizer/issues/39) 短源长度比噪声 | 降噪与分类摘要一起处理 | B/E：非空短源比例保护、长度上下文、三条 G0 调用链一致；保留空译检查与其他硬门，不以单元总比掩盖行级异常 |
| [#40](https://github.com/Misaka0x26FE/auto-epublizer/issues/40) AGPL／署名提案 | 拆分声明规范化、可选 producer/署名、PyPI 产品决策，不阻塞内容修复 | 先纠正条款论证；确认版权主体和许可表达后处理 SPDX，不凭覆盖率认定违法；不加遥测，不把书稿版权自动改为工具许可证 |
| [#41](https://github.com/Misaka0x26FE/auto-epublizer/issues/41) 本计划 | 保留为总跟踪单 | 跟踪各项依赖和独立验收；不能因建立总单就把具体 issue 当重复关闭 |

#40 的许可讨论以 [AGPL 正文](https://www.gnu.org/licenses/agpl-3.0.html)为依据：本地 CLI 的现状
不排除第三方修改为网络服务后的 §13 义务；上游仓库公开不等于第三方已经提供其修改版对应源码；
§5(a) 是修改声明与日期，不是 SPDX 文件覆盖率指标。此为条款核对，不替代法律意见。

### 2.2 真实作品记录（已脱敏）

真实作品识别信息、摘录及交付记录不随公开代码保留。

## 3. 执行顺序与依赖

1. **S0 基线与证据规则**：记录环境、当前变更及现有失败，保全已交付版本。
2. **N 注释结构化与绑定 + V 导航恢复**：首批整改，先定来源/身份契约，再落地构建与独立硬门；
   #37/#34 分别验收。A 若发现确定的数据损坏风险，同样立即处理。
3. **A 状态安全 + B 发布完整性**：覆盖新产物登记、失效、恢复和拒绝放行；E 中 #36/#35/#33
   可独立推进，不因小修先完成就宣称注释问题已解决。
4. **D 输入链路 + E 其余用户协议**：处理 #38/#39 等信号与降噪；#40 单列提案，不阻塞内容整改。
5. **C 架构与可维护性**：在正确性契约固定后作最小重构；**F 测试质量贯穿各项**。

N 的来源盘点/边界确认与 V 的章/节结构确认共用一套作用域，必须协同定稿，不能各造章节表。
N 的阶段顺序为：解析保全候选 → 结构整备/作用域确认 → 注释结构化登记 → 正文与译注翻译
→ 审校 → 全书级构建 → 独立注释图/目录树对账 → 阅读器验收。
回源发现结构变化时先修 V 再更新 N 的绑定，禁止沿用过期映射。
修复由一个集成负责人安排，避免同时编辑 `orchestrator.py`、`cli.py` 和共用模型；
C 依赖 A/B/N/V 的契约确认，F 的回归随各修复同步建立。

### S0：建立可复核基线

- 读取现有工作树差异，识别用户在途改动；不覆盖、不清理、不重置。
- 记录 Python/uv、项目依赖和 doctor 的可用能力；不启用网络探测，不要求提供 key。
- 运行一次基线：`uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`。
  已由用户提供的当前失败直接记录，不重跑只为确认。
- 将测试按单元/集成/真实 CLI/外部工具分层，标记 skip 原因，不把文件数等同于覆盖率。
- 对照最新代码、现有计划和工作状态；不将历史计划中的未完成标签直接当成新缺陷。
- 交付：基线命令/退出码、已有失败、能力缺口、受保护契约及待审模块清单，回写本计划。

### N：新增“注释结构化与绑定”阶段（首批，发布阻断专项）

本节为**拟实施契约**，当前不存在这些 JSON 产物、前置登记命令和新硬门，不能按已实现能力执行。
不是增加“智能数字正则”：agent 负责语义核证，CLI 只做提取、登记、搬运、渲染和确定性校验。

#### N1. 解析先保全，翻译前完成核证

- PDF/OCR 解析先保留页底/边注候选、阅读顺序与原始证据，禁止在候选盘点前当页脚噪声删除。
- 源 EPUB/HTML 已有显式引用关系时优先保留；明确的语法/链接可确定性提取。普通数字、
  Unicode 上标、跨页碎片及编号错位只产候选，由 agent 回看源件判断。
- 该阶段位于原始解析后、正式翻译前，与结构整备衔接；核证真实正文/注文边界、跨页续文、
  注号作用域和每次引用，不给每个提取段落重新编号。
- 注释盘点必须区分 `unverified`、`present`、`none`；`none` 是经核证的无注结论，不是检测数为零。
  已确认有注的书不能以未识别为由走无注路径，模糊候选必须有明确处置。

#### N2. 权威 JSON 与身份契约

沿用源/译目录职责，不在多个文件复制绑定关系：

- `structured/notes.json`：完整源注文、源引用与定位证据，是注释语义来源权威。
- `translation/notes.json`：以相同 `note_id` 保存完整译注；不复制源引用关系或源位置。
- 正文 Markdown 仅保留引用标记，不同时保留一份被摘出的完整注文；源件与 raw 永远保留。
  历史集中注文的迁移需按已确认的去向清单处理，不能直接删除整个 back-notes 单元。

| 对象 | 必需信息与含义 |
|---|---|
| 文件头 | `schema_version`、`source_sha256`、绑定的结构版本/摘要、盘点结论及核证证据 |
| `notes[]` | 稳定 `note_id`、`scope_id`、原显示号 `source_label`、来源注释类型、完整 `source_markdown`、`source_locations`、核证结论/未决原因 |
| `references[]` | 每次出现独立的 `ref_id`、指向 `note_id`、正文源锚点、原注码文本、前后文和核证证据 |
| 译注 | 源 JSON 版本/摘要、`note_id`、完整 `target_markdown`；目标内容和源绑定分别登记 |

定位必须保存**两种位置**：注文自己的原始位置，以及正文注码附着的位置。PDF 页码使用明确的
物理页序，印刷页码另存；bbox/页文本范围只在真实可得时填写，不伪造精度。EPUB/HTML 使用源文件
href、原锚点及文本块证据。跨页注文用范围列表，不能只记一个页码。

稳定文本块锚点与原文片段/上下文用于复核；若使用字符偏移，必须注明相对哪个冻结文本及
Unicode 码点计数约定。偏移、行号、单元 index、align `seq` 都不能单独当持久身份。
现有 `SourceSegment.anchor/meta` 可作为接入位置，但须核对其实际持久化链路，不假设已全程保留。

`note_id`/`ref_id` 与显示号分离；作用域取经来源确认的章/节，不由 `chNN-*` 文件名猜测。
一条注文允许多次引用；各章同号合法。完整 Markdown 保留多段、列表、强调、书目、图片和公式，
媒体仍使用现有资源机制；不得为适配当前单段渲染器而压平或截断。

#### N3. 原位标记、CLI 登记与翻译流转

- 摘出完整注文时在正文**原引用位置**保留稳定标记；拟复用 `[^ref-000123]` 文法，
  由源 JSON 记录 `ref_id → note_id`，标记中不编码可见序号。生成器禁止碰撞或在重跑时无故换 ID。
- agent 翻译时保留同一 `ref_id`，置于译文对应语义位置；源偏移只负责回溯，
  **禁止按源文字数偏移向译文插注，也不强制搬到句末**。
- 正文 Markdown 与 align 中的引用身份必须一致；译注本身也参加术语检查、内容完整性与
  G1–G3 审校，不能只审核正文或只确认译注文件存在。
- 拟增加前置 CLI 入口 `auto-epublizer notes register`，校验源 JSON、正文标记、作用域、
  去向与证据后，经 RunStore 原子登记；正式命令、帮助和错误契约随实现一起落地。
  `import` 扩展为同时校验/登记译注与正文，源注释不等待翻译产物才能登记。
- 纯转换/源文构建使用已登记的源注文，不要求不存在的译注；译文构建要求相应译注齐全。
  双语输出需明确源/译引用的独立锚点与关联，不得继续以跳过注释呈现对账代表已验证。
- `publication.json` 仅由 CLI 保存登记摘要和处理状态；agent 可写语义产物，不得手改官方状态。
  `status --json` / `next_tasks` 增加前置注释任务，盘点或必要绑定未完成时不能跳到翻译/交付。
- 旧 `[^label]`/定义式输入通过显式整备登记转换到唯一新模型；构建不维护另一套隐式旧模式、
  不猜测双轨优先级。转换真实边界不明时停止并保留证据。
- G0 fidelity/coverage 要对正文和移出的源注释联合对账，识别有据的注释分离，
  不能仅把含注单元从源保真检查中豁免，也不能把合法搬运报为漏译。
- 模型/登记复用 `auto_common` 的工作区机制；解析与构建/审计归 `auto_epublizer` 领域模块，
  对齐/G0 归 `auto_translator`。不新增并行包层或让 CLI/编排层承载语义配对逻辑。

#### N4. 全书级构建与原位回填

- 先收集并验证全书定义和引用，再逐文件渲染；不能在每个单元独立创建注释真相。
- 正文标记输出标准 `epub:type="noteref"` 链接，注文输出匹配其类型的标准语义节点，
  使用有效的 `role`、跨文件 href/fragment 与回链；每次引用的 HTML id 独立唯一。
- 注文可保留在集中注释文件中，不必把全文塞进正文段落。一注多引共享正确注文，
  但保留每次引用的定位及返回路径；显示编号按已确认作用域确定性生成，而非每 XHTML 重置。
- 注文按现有 Markdown 能力渲染完整块内容；不直接透传不受控 HTML，不用 CSS/JavaScript
  仿弹窗冒充语义结构。构建不得静默丢弃未配对引用、未归属残片或已确认但未引用的注文。
- 标准语义不等于每个阅读器都弹窗；支持者须实测弹窗，不支持者保留可读注释区和往返跳转。

#### N5. 独立硬门、失效与恢复

- **分离登记门**：移出范围均有去向，无吞字/重复；每条真实注文边界和引用关系有依据。
  候选允许在核证过程中未决，但开始正式翻译所需的绑定必须完成；未决不能默认接受。
- **翻译导入门**：引用身份/出现次数与目标标记守恒，所需译注完整，源 JSON 版本绑定有效，
  无未知 `ref_id`/`note_id`；空译、术语和其他结构硬门仍生效。
- **成品门**：独立解析最终 XML，对照已登记 JSON 检查每个引用的目标、目标语义、注文内容、
  唯一 ID、跨文件 fragment 与回链。不得由同一个渲染函数重建期望，再自证一致。
- 无注书经盘点为 `none` 时零对零合法；有注而零语义节点、部分语义化/部分普通段落、
  缺定义、错目标、错内容、孤立引用、未决真实注文都必须定位并阻断交付。
  原书确有未引用注文时须保留并明确核证其归属/处置，不能为满足计数而删除或强造引用。
- 源哈希、结构、正文绑定、源 JSON 或译注变更后，使受影响的登记/审校/build/report 失效，
  由 CLI 派生重做任务。重切/并单元必须显式重绑定或重新核证，不静默按数字/附近位置匹配。
- 登记失败保留上次有效状态，不能先移除正文再留下半份 JSON；重复执行身份稳定、结果幂等。
  将此提交边界、产物摘要与中断恢复纳入 A，不新增独立状态数据库。

#### N6. 必须覆盖的回归与关闭标准

离线合成样本覆盖：同文件/跨文件、章节重号、小节拆文件但原作用域不变、一注多引、多段和
跨页注文、带媒体/公式、源侧上标/裸数字候选、统计数字负对照、真无注、有注零语义节点、
部分遗漏、等量错配/重复抵消、重复 ID/坏回链、正文或 JSON 变更后旧报告失效、重跑/故障恢复。
丢一个引用又重复另一个不能靠总数相等过门；模糊数字不因恰好在注号范围内就被自动确认为注码。

关闭 #34 必须证明源侧关键形态及负对照、引用缺失检查和所有调用点接线；关闭 #37 必须证明
未语义化/部分遗漏不再全绿、已确认映射回到正确正文位置且注文内容正确。两者不是重复 issue。
工具阶段以合成样本建立失败前/通过后证据；真实书稿另作私有验收，不成为离线测试前置条件。

### V：目录导航与结构恢复（与 N 共用章/节作用域）

- 回源确认前置页角色、导论真正起点、六章/各节及结语附录边界；修复 structured、译文、
  align 与单元清单，不仅改 nav 显示标题。版式目录页与机器导航分别定位、分别验收。
- 以来源确认的节点身份、父节点、顺序、译名及 `file#id` 建立独立期望树；nav 与 NCX
  既须相互一致，又须符合该树，不能仅比较深度序列或标题是否出现。
- 明确单元入口“拥有”的标题，避免首标题再成为同义子节点；保留真实第一节和内部标题，
  不全局按同名去重，不一律删首 H2，不从文件名自动猜章，不以 `nav_depth=1` 掩盖错误。
- 纠正输入的标题语义和层级；章节点可指向现有第一节文件中的正确章锚点，
  不为目录凑层级而新建空 spine 文件。封面/献词/前言等角色按源证据确认。
- 验收：导论与六章同级，各节归正确章；“目录”跳到正确内容，入口/自有首标题不重复；
  nav/NCX 的父子、标签、目标、顺序符合独立映射，合理深度投影不丢必要章入口；
  正文、媒体、注释绑定与合法锚点没有因修目录丢失。
- 现有重建流程可能删除 raw、重写单元和重置状态；不得直接用于历史书原地抢修。
  必须先保全原工作区，在副本中明确旧新 unit/rel_path/align/注释锚点映射后重建。

### H：历史成品回收、重建与分发同步

- 按用户报告将所有既有成品列为待复验，不以本案例替代逐本验收；不删除旧版、
  不手改 publication/released 标志，也不把旧 `released=ok` 当新阶段通过。
- 逐本记录 EPUB 哈希、原工作区/源身份、注释盘点与映射状态、期望目录树、重建版本、
  QA 和阅读器验收、各分发副本同步状态。优先注释密集、OCR 和结构重切过的书。
- 找回原源件/raw、结构化文本、译文、align 和登记/审校记录；对本案例先确认真注文边界，
  再修编号作用域和引用关系。禁止将 2074 个带号段落自动当成 2074 条注文。
- 在保全的工作副本中完成 V/N → 登记 → 必要重译/审校 → build → qa → 独立交付审计；
  不直接编辑已交付 ZIP，不只修未来构建而留下旧成品继续分发。
- 支持弹窗的目标阅读器实点首/中/尾及高风险引用，覆盖跨文件、章重号、一注多引、长注文，
  核对弹出内容和返回位置；目录实点章、节、前置页和附录。
- 完整验收后同步本地 output/备份/仓库/云盘等分发副本并做字节核对；旧版保留可追溯记录。
  找不到原工作区或映射证据的书明确列阻塞项，不宣称修复、不从 EPUB 数字顺序猜配。

### A：状态、恢复与跨文件一致性（最高审查优先级）

入口：`src/auto_common/workspace/`、`src/auto_epublizer/structure/`、
`src/auto_epublizer/orchestrator.py`；关联 `tests/test_workspace.py`、
`tests/test_import.py`、`tests/test_restructure.py`、`tests/test_preprocess.py`。

审查：

- init 是否最后提交成功标记；解析中断/强制重建后能否安全恢复，而非跳过残缺产物。
- 源哈希变更、同名单元内容变更、重分拆合并后，状态和产物是否仍然绑定。
- `import --reviewed/--force` 的失败回退、已完成单元跳过和重复登记是否符合契约。
- 读取—修改—写入锁覆盖、导出快照与产物一致性；JSON、CSV、SQLite、事件的实际提交边界。
- 故障注入验证写入前失败、替换失败、进程中断及受支持并发入口；不凭猜测新增重试机制。

修复规则：只在复现后调整事务边界、锁归属或失效规则；尽量复用 RunStore，不另造状态真相。
验收：临时工作区复现失败前/修复后行为；失败后旧状态可读、无错误完成态；重复运行产物和
业务计数不被错误累加；源文件和用户原件字节不变。

### B：G0–G5 与成品对账（最高审查优先级）

入口：`src/auto_translator/review/`、`src/auto_epublizer/qa/`、
`src/auto_epublizer/build/`、编排层的 import/build/qa；关联 `tests/test_review.py`、
`tests/test_provenance.py`、`tests/test_qa.py`、`tests/test_build.py`、`tests/test_e2e.py`。

审查：

- 从源单元 → structured → align/译文 → EPUB spine/media/nav → report 追踪完整证据链。
- 逐项检查术语、marker、脚注、标题、表格、fidelity、未裁决冲突、catalog 未决项、
  审校未修问题、epubcheck 未执行/失败、溯源和成品覆盖率的放行条件。
- 区分 advisory 与 blocking；检查 `released`、`passed`、原因字段的语义和优先级。
- 修改译文/align/审校产物后，旧 build/report/review 是否仍会被误当成当前证据。
- 检查语义审校是否真的由 agent 负责；代码不能用启发式伪造 G1–G3 通过。

修复规则：先建立契约真值表，对每个证实的漏门从拥有该不变量的层修复；不以清空告警、
默认放行或更改阈值掩盖缺失证据。
验收：每个硬门至少有一个独立破坏场景，拒绝放行且定位正确；干净合成工作区能够通过真实
CLI 完成 build/qa。epubcheck 可用时实跑，无工具时明确记录未验证，不能宣称 released 成功。
另对产物 ZIP 做独立核对，不能只断言报告自身声称通过。

### D：输入解析、保真与可信边界（高审查优先级）

入口：`src/auto_epublizer/ingest/`、`preprocess/`、`structure/`；关联
`tests/test_ingest.py`、`tests/test_epub_reader.py`、`tests/test_mineru.py`、
`tests/test_reading_order.py`、`tests/test_links.py`、`tests/test_toc_mapping.py`、
`tests/test_repair.py` 及 tables/formula/inserts/rtl 测试。

审查：

- 合成 EPUB/HTML/PDF 的阅读顺序、标题级别、脚注链接、媒体、表格/公式和 RTL 是否守恒。
- 文件中声明的路径、ZIP 成员、媒体引用、符号链接是否可能越出工作区；不要预先宣称有漏洞。
- 外部转换命令的参数、退出码和输出完整性；MinerU 下载/解包和失败结果是否进入正式状态。
- 缺工具、坏文件、扫描件路由失败是否给出明确错误；不静默产出空章节或假成功。
- 页边界证据与语义修复职责分离，启发式不得自动替 agent 做内容判决。

修复规则：以最小坏文件证明风险，从输入边界修复；不全局禁用合法复杂输入作为捷径。
验收：离线合成样本覆盖问题边界与相邻合法案例；写入限定在沙箱，原始输入不变；对结构、
正文顺序和引用目标做语义断言。真实书稿仅在独立沙箱用于补充抽检，不成为测试前置条件。

### E：CLI、术语库与下游操作契约（中高审查优先级）

入口：`src/auto_epublizer/cli.py`、`knowledge.py`、`workroot.py`、
`src/auto_translator/glossary/`、`src/auto_common/config.py`；关联
`tests/test_cli.py`、`tests/test_status_all.py`、`tests/test_status_next_tasks.py`、
`tests/test_knowledge_store.py`、`tests/test_glossary.py`、`tests/test_config.py`。

审查：

- 实际子进程调用的退出码、中文可预期错误、stdout JSON 与 stderr 进度分离。
- `status --json` 的 next_tasks 是否对应真实缺失产物；嵌套和异构工作区不误选、不污染。
- 配置覆盖顺序、敏感环境变量不落盘；知识库语言对和冲突裁决规则一致。
- 知识库合并失败/git 提交失败时的可恢复性，公开库不得夹带书稿正文或密钥。
- 代码、帮助文字、skills 路由和任务卡对命令/状态的描述是否一致。

修复规则：维护已发布机器协议；若契约确需改动，统一迁移全部调用方和文档，不留双轨别名。
验收：在临时 HOME、临时知识库和本地 git 仓库运行；不触碰真实统一库、不网络 push；长中文
标题和窄终端下 JSON 可解析；所有失败场景有正确退出码且无非预期 traceback。

### C：架构与技术债（在正确性契约固定后）

入口：三包 import 图、CLI/编排/领域边界及跨模块重复的状态/路径/QA 策略。

审查：

- 实际依赖图与固定方向是否一致，是否存在反向引用、环或隐藏的动态依赖。
- 编排层承担的决策是否造成同一规则多处维护；长文件仅作为入口线索，不自动拆分。
- R1–R6 每个候选都追踪一个具体变更影响路径，区分稳定 DTO、合理 composition root 和真债。
- 查看共享策略的调用方与测试，再决定内聚迁移位置；有 LSP 时先查询 references。

修复规则：先写不变量/消费者行为证明，再作小步移动；复用现有领域模块，删除被替代路径；
不为每个函数新建 Service/Protocol，不以降低行数作为完成标准。
验收：架构契约保持；实际 CLI 和产物行为不变；同一业务规则的拥有者清晰；调用方全部迁移。

### F：测试质量与风险覆盖（贯穿全程）

- 优先检查 N/V/A/B/D 的绑定身份、状态转换、失败恢复、拒绝放行和内容守恒，再检查 T1–T6。
- 核实主 E2E 之外是否覆盖真实 CLI 的 review 登记与工具执行；不凭一份文件判全库缺覆盖。
- 删除只固定措辞/源码片段/实现细节的无效测试，保留真正架构约束与用户协议测试；不重钉
  偶然行为。mock 仅隔离外部边界，核心业务与文件产物必须真实执行。
- 新永久测试只保护可见缺陷、边界、不变量、状态转换或错误；不新增空壳和转发接线测试。
- 每个确认缺陷先加最小失败回归，再修复并确认通过；纯重构优先复用已有行为测试。

验收：测试独立、离线、确定性且全套可运行；关键回归能够证明修复前失败/修复后通过；
skip 与外部工具缺口单独列出，不用总通过数掩盖。

## 4. 缺陷分级与实施单元

只有取得证据后才登记正式 finding，每条采用：

- **Symptom**：文件/符号/行号、输入与实际行为；注明已复现或仅静态证据。
- **Source**：确实匹配的书籍原则，例如 Clean Architecture 的 Dependency Rule、
  The Pragmatic Programmer 的 DRY、xUnit Test Patterns 的 Erratic Test；不堆砌书名。
- **Consequence**：受影响的用户路径、数据和传播范围，说明触发前提。
- **Remedy**：最小修复、受影响调用方、回归场景、运行证据和文档同步项。

| 级别 | 判据 | 处理 |
|---|---|---|
| P0 | 可复现的数据损坏、工作区外写入、错误发布或敏感数据外泄 | 中断低优先事项，先修复并验证故障路径 |
| P1 | 导入/恢复错误、内容丢失、状态/产物漂移、机器协议破坏 | 按消费者影响与传播范围排序修复 |
| P2 | 有具体传播证据的职责泄漏、重复知识、测试脆弱性 | 在对应正确性回归保护下最小重构 |
| 不立项 | 纯风格偏好、阈值告警、无法说明影响的抽象建议 | 不为凑健康评分改代码 |

每个修复批次只处理一个不变量或紧密关联的根因。记录受影响文件、回归、CLI smoke 和剩余风险；
失败则停留在该批次修正，不压制异常或缩小验收条件。代码修改不涉及真实书稿状态回滚；需要
数据迁移或破坏性操作时另行明确其范围和授权。

## 5. 验证与文档交付

### 实施阶段的验证顺序

1. 取得当前问题的最小复现；建立失败回归。
2. 修改后运行对应测试和**真实 CLI/产物 smoke**。在临时工作区执行 preprocess、agent
   核证/写入源注释 JSON 与原位标记、拟新增的 `notes register`、正文与译注翻译/align、
   import、g0、build、qa、status，并独立解析 EPUB 引用图/目录树及拒绝放行原因。
   源文转换路径另外验收；review 和注释状态通过 CLI 合同推进，不手工编辑 publication.json。
3. 每批结束统一运行受影响测试、`uv run ruff check .`、`uv run ruff format --check .`；
   集成结束运行一次 `uv run pytest -q` 和文档检查，不在编辑过程中反复跑全套。
4. 工具依赖不足时完成所有可离线部分，明确具体未验证项，不把工具缺失当成功。

### 文档同步矩阵

- 新阶段/命令/工作区/QC 行为落地时：同步 `AGENTS.{md,zh.md}` 的工作流、目录、登记入口与
  不变量，`skills/auto-epublizer/SKILL.{md,zh.md}` 路由及
  `references/workflow`、`preprocessing`、`structure`、`repair`、`translation`、`analysis`、
  `review`、`qa`、`delivery`、`build`、`invariants` 的受影响中英章节；同步 manifest 和相关任务卡。
  仅计划更新时不改这些操作文档，不把待实现接口提前写成可用命令。
- 发布/模板约束有变：同步 `docs/quality-control`、`postprocessing-spec`、`epub-template-spec`
  中实际涉及的章节；仅修改确实受影响的文档，不无差别重写。
- 中文权威文档与英文派生同步后执行 `python3 scripts/i18n.py --finalize <英文文件>`，
  再运行 `python3 scripts/i18n.py --check` 和 `python3 scripts/i18n.py --links`。
- 本计划和计划索引按现有 `docs/plans/` 约定仅中文，不创建英文孪生。
- 复用经验仅在实际修复并验证后沉淀 `skills/auto-epublizer/lessons/`。

### 完成标准

所有确认的 P0/P1 已修复并具备前后证据；每个 P2 有修复结果或明确保留理由；无静默缩小的待办。
N 的新阶段、JSON/原位绑定、译注审校、全书构建和独立硬门必须端到端可执行；V 有独立来源树；
H 逐本记录重建/阅读器验收/副本同步，缺源证据的具体书保留阻塞，不以工具测试通过代替修复完成。
本案例在材料齐备后必须实测注释内容、弹窗/往返及目录真实落点；源码或截图结构推断不算阅读器实测。
工具能力下的回归、CLI、成品和文档验证均有真实记录；外部路径未验证项明确列出。
计划状态仅在实施完成后改为已完成并附实际提交号，本轮不提交代码。

## 6. 本轮计划交付记录

- 已读取：项目契约、包/测试布局、pyproject、计划索引与最近完成计划，以及状态存储、
  编排、放行汇总、CLI、输入分发、知识库与架构/E2E 测试的相关片段。
- 本轮无业务代码改动；无当前测试通过数、漏洞确认或健康评分结论。
- `python3 scripts/i18n.py --check`：`OK`；`python3 scripts/i18n.py --links`：`OK`。
- 本机 `python` 命令不存在，初次调用退出 127；改用 `python3` 完成检查。
- 此次补充：线上 issue 逐项处置、典型成品只读证据、新增注释结构化与绑定阶段 N1–N6、
  导航恢复 V、历史成品处置 H，以及相应实施顺序、模式差异、回归与文档义务。
  所有新增命令/JSON/硬门仍属规划，未修改业务代码、原始工作区或成品。
- 本次文档验证：i18n `--check` / `--links` 均为 `OK`；
  `uv run --offline pytest -q tests/test_i18n.py` 为 **13 passed**；
  `uv run --offline ruff check .` 通过，`ruff format --check .` 报 **277 files already formatted**。
  未执行新注释/导航功能测试或阅读器验收，这些功能尚未实现。

## 7. 实施记录（2026-10-15 起）

### S0 基线（已完成测量）

- 环境：Python 3.12.3、uv 0.11.32；HEAD `4d76c62`（与线上 main 一致）。
- 在途改动（保全，未覆盖）：`docs/plans/README.md`（M）、本计划文件（未跟踪）。
- 基线命令与退出码（实施前）：
  - `uv run --offline pytest -q` → **458 passed**（0 failed）；
  - `uv run --offline ruff check .` → `All checks passed!`；
  - `uv run --offline ruff format --check .` → `277 files already formatted`。
- 能力缺口（`auto-epublizer doctor`，未启用网络探测）：
  - 缺失：`tesseract`、`ocrmypdf`、`rapidocr`（扫描 PDF 离线 OCR 不可用）、`mineru`（无 API key）；
  - 可用：`pandoc`、`pdftotext`、`pymupdf`、`lxml`、`epubcheck`（`~/.cache/epubcheck.jar`）；
  - `multimodal` / `search` 由 agent 自报，CLI 无法探测。
- 测试分层（`tests/` 现 42 个文件 / 460 个 test 函数；分层按主依赖而非文件数）：
  - 单元（纯领域逻辑）：`test_glossary`、`test_review*`、`test_analysis`、`test_config`、`test_architecture_boundaries`、`test_signals`、`test_taskcards`、`test_work_root`、`test_install_skills` 等；
  - 集成（多模块 + 真实文件产物）：`test_workspace`、`test_import`、`test_build`、`test_qa`、`test_provenance`、`test_structure`、`test_restructure`、`test_preprocess`、`test_catalog`、`test_repair`、`test_ingest` 等；
  - 真实 CLI：`test_cli`、`test_status_all`、`test_status_next_tasks`、`test_e2e`；
  - 外部工具门控：`test_epub_reader`（pandoc `skipif`）、`test_knowledge_store`（git `skipif`）、epubcheck 走 jar；
  - 当前无 skip（pandoc / git 可用）；工具缺口不影响离线测试，但扫描 PDF 路径无离线 OCR 备选。
- 已有失败：无。受保护契约与待审模块清单沿用 §2 表格（入口文件与行号已重新核对存在）。
- 结论：基线可复核；实施从 E 组独立小修开始，逐批建立失败前/修复后证据。

### 批次 E-1（#36 / #35 / #33，代码已完成并具前后证据）

- #36：`load_glossary_csv` / `read_conflicts_jsonl` / `load_legacy_category_csv` 改 `utf-8-sig`；
  `import --terms` 路径不存在时在写回前抛 `OrchestrationError`（报解析后路径，保持 cwd 相对约定，
  不做工作区回退）；术语计数（`proposed`/`skipped`）进入结果与 CLI 汇总，0 条时可见警告。
- #35：`write_conflicts_jsonl` 按 `(source, existing_target, proposed_target)` 去重并只返回**本次新增**；
  `import` 分开返回 `conflicts_new` 与 `conflicts_open`（后者为账本内 `status=open` 总数）；
  CLI 消息区分「本次新增」与「待裁决（含历史 open）」，`resolved` 不再要求重裁，重复导入幂等。
- #33：`ledger` stdout 改走 `_emit_plain`（`soft_wrap=True`，与 `--json` 同口径），markdown 表格
  一条记录一行；`status_all` 增加 `_is_tool_tree` 过滤（`pyproject.toml` + `src/auto_epublizer`），
  跳过工作根内的 CLI 仓库副本（其 `template/publication.json`），保留合法嵌套工作区与 base 自身为
  仓库时的原行为（不过度过滤）。
- 回归证据（新增 6 项，先证失败后修复）：
  - 回退 `src/` 后运行新回归 → **6 failed**（BOM 整表丢光、缺失 terms 静默、冲突新增误报、
    工具树被扫、ledger 折行等原状全部复现）；
  - 恢复修复后 `/tmp` 受影响文件 → **55 passed**；全套 → **466 passed**（458 + 8）。
- 仍需：受影响 ruff（下一批统一跑）、文档同步（work-root 推荐命令与 references 说明在 E 组批量收尾时处理）。

### 批次 B-1（#39 / #34 / #38，已完成并具前后证据）

- **#39 长度比短源保护**（`auto_translator/review/g0.py`、`orchestrator.py`、`config.py`）：
  - `g0_unit_flags` 新增 `min_src_chars`（默认 20，配置项 `qc.length_ratio.min_src_chars`）：
    源文去空白不足该长度不做比值判定；**译文为空**（不看源长）与长源行比值越界不受影响；
    告警 data 带 `src_len`/`tgt_len`/`ratio` 上下文。
  - 三条调用链（import / g0 / qa）统一经 `orchestrator._g0_thresholds` 取同一阈值——
    修复前 import 与 g0_check 硬编码默认值，自定义 `too_short` 只在 qa 链生效。
  - 回归：回退 `src/` 后新增 6 项全失败 → 修复后 6 项全过；`tests/test_config.py` 默认值断言同步。
- **#34 注码识别与缺失核证**（`g0.py`；**关键实测**：只读抽检 `sample-archive-b`，33 单元）：
  - 计数式放宽**不可用于硬门**：旧口径 src=696/tgt=691（余量 −5，4 单元触发，修复前既有行为）；
    两侧同一判据 + 上标式 → src=979/tgt=1842（余量 +863：译文形态更多，真丢失被掩盖）；
    只放宽源侧或不含全角形态 → src=979/tgt=846（余量 −133：误报成片）。
  - 落地：`count_footnote_refs` **保持句末式口径不变**（硬门零行为变化）；新增
    `footnote_numbers(text)`（句末式 ∪ 上标式 ∪ 括号式 `〔N〕`；小数/千分位/缩写点/量词/
    前导零排除）与 **advisory** `footnote_suspect`——单元级**集合差集**（源侧有而译文侧没有
    的注号 + 行级样本 seq），供 agent 逐条核证。
  - 真实书差集信号量小可核：ch06 缺 10；ch07 缺 167/168/169/170/204/226；ch10 缺 54；
    ch13 缺 45（共 9 个注号待核证）。计数窗口径与修复前逐单元一致（无新增误报）。
  - 「真缺失阻断」归 **N 阶段身份契约**（`ref_id` 守恒）；本项在 N 落地前以 advisory + 行级
    样本交付，不声称已完成阻断。引用与定义分开统计：新增 `count_footnote_defs`，
    `footnote` 告警 data 带 `*_refs`/`*_defs`/`*_marks` 分解。
  - 回归：回退 `src/` 后 6 项全失败 → 修复后 `tests/test_review.py` 43 passed。
  - 缺口：`sample-document-g` 工作区本机不存在（仅有 3 个旧项目），
    该书真实书稿私有验收未做，已在 §7 记录为待办。
- **#38 版面型候选**（`auto_epublizer/qa/audit.py`）：新增 `_layout_candidates`（W 级、
  每文档每类至多一条、不改写、不阻断）：`W_CJK_SPACED`（同段落 ≥2 处汉字间空格）、
  `W_PARA_UNCLOSED`（≥20 字段落末字为汉字或悬挂的逗号/顿号/分号）、
  `W_NOTE_IN_PHRASE`（汉字-空格-数字-空格-汉字且数字后非量词，带片段）。
  负对照：`他共获得 3 枚奖章，另有 12 名同事参加仪式。` 三类均不报、`result.ok` 不变。
  回归：回退 `src/` 后正例 failed → 修复后 2 passed。
- 全量：**481 passed**（B-1 前 466；+15），`ruff check` / `ruff format --check` 全绿。

### 批次 N（注释结构化与绑定，issue #37/#34；端到端已落地）

本批把计划 §N1–N6 的**拟实施契约**落为可执行能力（新增 2 个领域模块、1 个子命令组、
3 道门与全链路测试），并记录残余未验证项。

- **N2 身份契约**：`structured/notes.json`（源注文/引用/双位置证据/核证结论，权威）+
  `translation/notes.json`（同 `note_id` 的完整译注，绑定源注文 sha256）+
  正文原位标记 `[^ref-000123]`（标记即 ref_id，不编码显示号）+
  `publication.json.notes`（CLI 写的登记摘要，agent 不手改）。领域模块
  `src/auto_epublizer/notes.py`；成品独立门 `src/auto_epublizer/qa/notes_audit.py`。
- **N1 候选盘点**：`auto-epublizer notes candidates` → `preprocessing/note_candidates.jsonl`
  （marker/pandoc_ref/definition/numbered_paragraph 四类；身份为内容哈希、不含行号，重跑
  保留已有处置）；复核确认清洗层不含「删注文候选」逻辑（structure/links 只做链接/锚点归一）。
- **N3 登记与检索**：`notes register`（分离登记门：schema/源哈希绑定/身份唯一/作用域/
  双位置证据/unresolved 未决阻断/正文标记 ↔ 引用双向对账/候选处置完整性）；
  `import` 扩展（翻译导入门：译文标记守恒 + 译注齐全 + 摘要绑定，缺失即阻断该单元）；
  `status --json` 增加 `notes` 段与 `notes_verify`/`notes_register` 前置任务
  （只在书内确有注文候选时出现，无注书不增步骤）。
- **N4 全书级构建**：`_note_plan`（作用域显示号、宿主=spine 序首个引用单元、一注多引回链、
  未引用注文按 `orphan_ok` 保留渲染）+ `build/html.py`（标准 noteref / `aside epub:type=footnote`
  /跨文件 href/完整块级 Markdown/注文媒体收集）；发现未登记标记或未进成品的引用即报错
  （**不静默丢弃**）。
- **N5 三道独立硬门 + 失效**：登记门/导入门/成品门（成品门**独立解析最终 XHTML**，不与渲染
  函数共享期望）；放行条件新增 `notes_ok`，拒绝原因 `released_reason=notes_open`；源注文/
  译注变更后 `E_NOTES_STALE` 在 import/build/qa 明确阻断；旧 `[^label]:` 对照在有原位标记的
  文档上让位于成品门（消除重复口径），`E_FN_BACKLINK` 升级为支持跨文件回链解析。
- **验证**：
  - 单元/集成：`tests/test_notes.py` **28 项**（候选处置保留、登记门各阻断项、导入门、
    构建渲染、跨文件+一注多引+章内重号、多段注文、带媒体注文、部分遗漏、等量错配、
    坏回链/孤儿锚点、none 零对零、失效链、报告放行条件）；
  - 真实 CLI smoke（`<scratch>/notes-smoke`）：init → notes candidates → agent 核证写
    notes.json/标记 → notes register → 译文/align/译注 → import（0 告警）→ g0（0 告警）→
    build → qa（**released: True / ok**）→ status --json；独立解析成品引用图：
    3 个 noteref 锚点全部指向真实 aside、一注多引回链完整、跨文件 href 正确；
  - 拒绝放行实测：篡改成品去掉语义节点 → `released: False（notes_open）` +
    `E_NOTES_ANCHOR_MISSING` 定位 `ref-000001`；
  - 全量 **509 passed**；`ruff check` / `ruff format --check` 全绿。
- **文档同步**：新增 `skills/auto-epublizer/references/notes.{zh,md}`；`SKILL.{zh,md}` 路由表、
  `manifest.json`、`references/workflow.{zh,md}` 命令总览、`AGENTS.{zh,md}`（标准流程 5.7、
  目录契约、QC 流程 5b + 放行条件）同步；i18n `--check`/`--links` 为 OK（孪生对 60→61）。
- **残余未验证项**：V/H（典型成品缺源工作区/raw 证据，见 §6）与阅读器实测（弹窗/往返需真机）
  不在本批；#34 的 auschwitz 真实书私有验收仍待办；`structured/raw/media` 内注文媒体的
  「源件抽取」环节由既有 ingest 负责，本批只验证了收集与渲染链路。

### 批次 A（状态、恢复与跨文件一致性）

**审查（先复现、后修复；未复现的候选不立项）**：

- `atomic_write_json` 原用**固定** `<target>.tmp`：并发写同一目标时两个写入者共享临时文件——
  写者 B 以 `"w"` 截断 A 正持有的临时文件；A 继续写后再 `os.replace`，会因临时文件已被 B
  移走而抛 `FileNotFoundError`，或把 B 的半成品 replace 成正式文件（目标被就地交错写）。
  已用确定性线程交错复现（`tests/test_state_safety.py`）。
- 写到一半失败会**残留**半成品临时文件（旧值安全，但垃圾留在工作区）。
- 写入后未 `fsync`：断电/崩溃后新值可能仍在页缓存，「旧或新二选一」无法保证。
- `save_qa`（`report.json`）不在任何锁内，属上述竞态面之一；唯一临时名落地后为安全 last-wins。
- `RunStore.run_lock` 定义但**无调用方**：文档承诺的「同一工作区一次只跑一条长流程命令」是
  用户约定而非强制。state/event 级写均有锁且写入原子；未复现长流程并发导致的数据损坏，
  按计划「只在复现后调整事务边界」保留现状，记为 **P2（保留理由）**：引入 run_lock 会改变
  CLI 阻塞行为并存在同进程二次 flock 死锁风险，收益未经证实。

**修复（根因级单点）**：`atomic_write_json` 改唯一临时名
（`.<name>.<pid>.<随机>.tmp`）+ 失败/中断清理自己的临时文件 + `fsync` 后再 `os.replace`；
并发语义明确为 last-wins，任何时刻读到的目标都是完整的旧值或新值。

**验证（前后证据）**：

- 回退 `src/auto_common/workspace/store.py` 单文件：并发用例失败（共享临时文件 →
  `FileNotFoundError`/交错）、失败清理用例失败（残留 `state.json.tmp`）→ 修复后 2 passed。
- 新增 `tests/test_state_safety.py` **7 项**：① 写到一半失败保旧值且不留临时文件；
  ② 并发写不共享临时文件（确定性交错）；③ init 在提交 publication.json 前中断 → 无半成功
  状态、重跑 init 成功；④ 结构未写完（publication 有、units 空）→ `rebuild` 恢复且状态重置
  `split`；⑤ 全链路（init→preprocess→import→build→qa）源文件与 `source/` 副本字节不变；
  ⑥ preprocess/import/qa 重跑不累加（单元/词数/G0/句数一致）；⑦ 同名不同内容被
  `ensure_source_identity` 拒绝。
- `import --reviewed/--force` 的跳过/回退语义由既有 `tests/test_import.py` 覆盖（幂等、
  reviewed/built 跳过、force 失败回退 aligned）。
- 全量 **516 passed**、`ruff check` / `ruff format --check` 全绿。

### 批次 B2（发布完整性：真值表 / 失效链 / 破坏场景）

**真值表**落在 `tests/test_release_truth_table.py` 文件头（条件 → 拥有层 → 级别 → 用例），
共 15 项；既有 `test_qa`/`test_notes` 覆盖术语/结构/冲突/catalog/审校/epubcheck/溯源/注释门。

**发现与修复（先复现后修）**：

1. **forward fidelity 级别分叉**：文档写明「前向缺块=advisory」，但 `qa/report.py` 按
   check 名把所有 `fidelity` 计入 `g0_structure_open` —— 同一告警在 import 是 advisory、
   在放行时是硬门。修复：`G0Flag` 增加 `blocking` 字段（默认 True）；fidelity 前向、
   长度比、注码差集显式 `False`；两条 G0 链序列化该字段；`report.py` 只计 blocking；
   import 阻断与 CLI 红/黄渲染统一读该字段（不再靠消息文本/检查名猜级别）。
2. **空/缺失对照表的已登记单元在 qa 被跳过**（`if not rows: continue`）：把 align 清空后
   qa 仍 `released=True`。修复：对「有译文文件或状态进入译文族」的单元，即使 rows 为空
   也跑 `check_alignment`（产出 `align`「对照表为空」，硬门，定位到单元）；源文回退/
   convert 工作区不要求（避免把「无译文」误判成缺失）。另把 `align` 纳入放行硬门集合。
3. **旧报告被当当前证据**：`report.json` 无产物指纹——改译文/align/审校后
   `status`/`ledger` 仍显示 released。修复：新增 `qa/artifacts.py`（`artifacts_digest`：
   源哈希 + 各单元 structured/translation/align + 注释文件 + 最新审校 result + 成品字节；
   `report_state`）；`qa` 写入 `artifacts_digest`/`artifacts_epub`；`status` 增加 `report`
   段与 stale 项；`status_all` 增 `report_stale`，过期即把进度降为 `built_not_released`。

**破坏场景（拒绝放行 + 定位）**：forward advisory vs reverse hard、align 清空、
catalog 未决、审校未修（g2>g3）、epubcheck 未运行、术语/结构（test_qa）、注释门
（test_notes）、篡改 nav（`audit_failed` + `E_NAV_HREF`）、删 spine 文档
（`audit_failed` + `E_MANIFEST_HREF`/`E_NAV_HREF`/`E_NCX_HREF`/`E_LANDMARKS_HREF`）。

**成品 ZIP 独立核对**：干净工作区经真实 CLI `import→build→qa` 放行后，直接解析 ZIP 验证
mimetype 首位未压缩、container/opf/nav 存在、spine 文档在、单 h1、nav 为 toc——不以
report 声称代替产物检查。

**验证**：全量 **531 passed**（516→531）、`ruff` 全绿；`invariants.{zh,md}`/`qa.{zh,md}`
放行条件表与报告时效说明同步；i18n `--check`/`--links` OK。

### 批次 D（输入解析、保真与可信边界）

**先证后修（两条，均由最小坏文件/最小合成样本固定）**：

1. **P0 越界读取（媒体引用缺包含性校验）**：`build/__init__.py::collect_media._resolve`
   用 ``media_root / cand`` 词法拼接后直接 ``read_bytes()``——``../../…`` 链（或指向工作区
   外的符号链接）可读取工作区之外乃至 ``/etc/*`` 的文件，并把 ``media/../../…`` 作为成员名
   写进成品（越界读 → 成品外泄 + 非法成员名）。实测：读到 ``/etc/hostname`` 内容并产出
   ``media/../../../../../../../../etc/hostname``；端到端成品里出现
   ``OEBPS/media/../../../../../outside-secret.txt``。
   修复：候选 ``resolve()``（含符号链接）后必须 ``is_relative_to(media_root)``，越界一律记入
   ``dropped``（→ ``media_dropped`` 事件 + provenance ``E_MEDIA_EPUB_LOST`` 阻断放行）；
   相邻合法用例（嵌套子目录、``raw/media`` 前缀去重、basename 兜底）保持不变。
   同口径加固 ``qa/provenance._audit_inserts``：``source.file`` 越界计缺失、不去 stat 工作区外。
   证据：回退 ``build/__init__.py`` + ``qa/provenance.py`` → 3 项失败（含上述成品成员名）
   → 修复后 6 passed。

2. **EPUB 源媒体引用未相对化（内容丢失 + 机器路径入产物）**：``read_epub`` 直接
   ``run_pandoc(...)``，漏了 ``read_pandoc`` 里的 ``normalize_media_refs`` 一步——pandoc 的
   **绝对**媒体路径原样进入 ``structured/``（机器路径进 git 追踪产物），且构建时
   ``media_root/tmp/…`` 命中不到、basename 兜底也命中不到嵌套子目录 → 插图丢失。
   修复：``read_epub`` 同样 ``normalize_media_refs(run_pandoc(...), media_dir)``。
   证据：合成 EPUB（嵌套 ``img/pic.png`` + 脚注 + h1/h2）修复前 structured 含绝对路径、成品
   缺图；修复后引用为 ``raw/media/img/pic.png``、成品含 ``OEBPS/media/img/pic.png`` 与脚注内容。

**守恒断言（合成样本，离线）**：新增 ``tests/test_ingest_boundary.py`` 8 项：EPUB 源标题层级/
脚注/嵌套媒体守恒（pandoc 用例带 ``skipif`` 门控）；越界引用四形态（相对 ``..``、绝对路径、
符号链接、合法嵌套对照）；成品不含 ``..`` 成员名；inserts 越界；坏 zip 与缺 pandoc 的明确
错误（不静默空章节/假成功）。既有 ``test_reading_order``/``test_tables``/``test_formula``/
``test_rtl``/``test_links`` 覆盖其余守恒维度。

**验证**：全量 **539 passed**（531→539）、``ruff`` 全绿。**工具缺口（未验证项）**：本机无
tesseract/ocrmypdf/rapidocr，扫描 PDF 的离线 OCR 路由仅以合成样本/伪后端覆盖
（``test_fake_ocr_backend``），真实扫描件的 OCR 质量未验；MinerU 走既有 mock 测试
（``test_mineru``），未访问真实 API。

### 批次 E2（#40 许可与署名 + CLI 契约）

**#40 处理结果**（按「不加遥测、不改书稿版权」边界实施）：

1. **§5.1 版权/SPDX 声明**（原 2/62 → 现 **65/65**）：`src/` 下全部 ``.py`` 带
   ``SPDX-License-Identifier: AGPL-3.0-only`` + ``Copyright (C) 2026 Misaka0x26FE``；
   ``pyproject.toml`` 的 ``license`` 改为 SPDX 表达式 ``AGPL-3.0-only``；离线打包实测
   wheel METADATA 为 ``License-Expression: AGPL-3.0-only`` + ``License-File: LICENSE``
   （PEP 639）；回归 ``tests/test_licensing.py`` 逐文件核对（含版权行）防回退。
2. **§5.2 来源可识别（不追踪）**：``PublicationMeta.producer``（init 写入
   ``auto-epublizer@<version>``）+ ``run_initialized`` 事件同一字段 + ``build`` 日志固定带
   工具/许可证/源码地址；旧工作区（无该字段）照常解析（空串）。
   **未做（明确保留）**：程序内不加遥测/心跳/部署识别（issue §3 结论）；成品内 about 页
   仍未接线（``output.about_page`` 仍是保留项，配置文档已注明）——issue 允许「about 页或
   build 日志」二选一，本批取 build 日志 + 工作区指纹路径。
3. **条款论证**：issue §2 的「纯本地 CLI，AGPL §13 不触发（无服务端交互）」保留为设计
   前提；本批不新增任何出网行为（``doctor --ping``/MinerU/知识库 push 仍由用户显式触发）。

**e-contract（CLI 契约）**：修复 ``IngestError`` 由 ``RuntimeError`` 改为 ``ValueError``
（与 ``InitError``/``SourceIdentityError`` 同口径）——此前 ``init <不支持的格式>`` 因 CLI
只捕获 ``ValueError`` 而冒未捕获异常；现统一为中文提示 + 非零退出码（回归含「无 traceback」
断言）。新增 ``tests/test_cli_contract.py`` 3 项：``next_tasks.done_when.cmd`` 必为已注册
命令（含「notes register」组合形态；跨 4 个工作区状态）、可预期错误退出码与中文提示、长标题
下 ``status --json`` 可解析且 ``notes``/``report`` 段齐备。

**验证**：全量 **547 passed**（539→547）、``ruff`` 全绿；离线 ``uv build`` 成功（wheel+sdist）；
README/AGENTS/development-plan/pdf-parsing 中英同步（i18n ``--check``/``--links`` OK）。

### 批次 C（架构与技术债：最小重构）

**实际 import 图核对（AST，含函数内延迟导入）**：

- 跨包方向：``auto_epublizer → auto_common``（9 文件）、``auto_epublizer → auto_translator``
  （5 文件）；无反向导入（``auto_common`` 不依赖另两包；``auto_translator`` 仅用 stdlib 与自身）。
- 动态导入：全库仅 ``importlib.util.find_spec`` 能力探测；无 ``__import__``/动态模块加载。
- **发现（债）**：``review/fidelity.py``（模块级 ``from .g0 import G0Flag``）与
  ``review/g0.py``（函数内延迟 ``from .fidelity import fidelity_flags``）构成**双向依赖**
  （非导入期环，但共享模型放错层）。修复：``G0Flag`` 迁入 ``review/models.py``（文档化的模型
  家），``g0`` 保留重导出；双向依赖消除。修复后全库**模块级导入图 0 环**（AST 检测）。

**编排层决策泄漏清单**（``orchestrator.py``；B 组后 2088 行 → C 组后 1966 行）：

| 位置/内容 | 决定 |
|---|---|
| ``_ocr_backend_if_needed`` 内联 ``find_spec`` 能力探测 | **移出**：新增 ``ingest/ocr.py::rapidocr_available()``（与 doctor 同口径），编排层只读结果 |
| ``_source_language`` 内联判定规则（en 无拉丁 → und） | **移出**：新增 ``analysis/detect.py::detect_source_language()``；编排层只做采样/截断 |
| ``read_repairs``/``read_catalog``（catalog/repairs 契约校验约 130 行） | **移出**：新模块 ``preprocess/artifacts.py``（预处理层拥有自己的产物契约）+ ``ArtifactContractError(ValueError)``；``orch.read_*`` 经导入保持可用 |
| ``_mineru_client_if_preferred``（ingest 后端路由） | 保留：路由是编排职责（config+环境变量+嗅探的组合选择） |
| ``_note_plan``/``_render_and_pack``（跨单元注释/渲染装配） | 保留：跨单元装配 + 调用渲染，属 facade 职责（N 阶段测试覆盖） |
| ``_norm_title``/``_title_match``/``_toc_missing_from_facts``（facts TOC × 单元标题） | 保留：跨产物一致性检查；``subheading_anchors`` 在 build，移出需跨层依赖或新模块，且无重复实现 |
| ``render_ledger``（跨书台账渲染 27 行） | 保留：纯格式化，cli 直接调用，无重复 |
| ``_derive_next_tasks``/``_task``/``_notes_next_task``（状态协议） | 保留：状态组装/协议职责，有专测覆盖 |

**验收（c-verify）**：新增架构回归（模块级导入无环；orchestrator 无 ``find_spec``/``importlib``；
preprocess 拥有产物契约读取且错误按 ``ValueError`` 口径）+ 单元（``detect_source_language``
策略、``rapidocr_available`` 探测）；全量 **551 passed**（547→551）、ruff 全绿；真实 CLI smoke：
坏 catalog → ``qa`` exit 1 + 「质检失败：catalog.csv 第 2 行：kind 非法（badkind）」+ 无
traceback（与迁移前同文案）；``orch.read_catalog is preprocess.artifacts.read_catalog``；
``docs/semantic-repair`` 中英同步（i18n OK）。

### 批次 F（测试质量与风险覆盖）

**f-regressions（每个修复批次的失败回归 + 前后证据）**：

| 批次 | 回归（用例） | 修复前证据 |
|---|---|---|
| E-1（#33/#35/#36） | BOM 容忍 / `--terms` 缺失写回前失败 / 空结果可见 / 冲突新增与待裁决分离 / 工具树跳过 / ledger 单行 | 回退 `src/` → 6 failed |
| B-1（#39/#34/#38） | 长度比短源保护与阈值覆盖 / 注码上标形态与负对照 / 差集 advisory / 布局候选正例与合法负对照 | 回退 `src/` → 6 failed |
| N（#37/#34） | `tests/test_notes.py` 28 项（登记门/导入门/成品门/失效链/跨文件/一注多引/部分遗漏/等量错配/多段/媒体） | 篡改成品 → `notes_open` 精准定位（smoke） |
| A（状态安全） | `tests/test_state_safety.py` 7 项（失败保旧值/并发不共享 tmp/中断恢复/源字节不变/幂等计数/身份拒绝） | 回退 `store.py` → 2 failed |
| B2（放行真值表） | `tests/test_release_truth_table.py` 15 项（含 6 个独立破坏场景与 ZIP 独立核对） | 三处缺陷先复现（forward advisory 误升硬门/空对照表跳过/无指纹当当前证据） |
| D（输入边界） | `tests/test_ingest_boundary.py` 8 项（越界四形态/符号链接/守恒/坏文件与缺工具） | 回退两文件 → 3 failed（含成品出现 `OEBPS/media/../../…`） |
| E2（#40/契约） | `tests/test_licensing.py` 5 项 + `tests/test_cli_contract.py` 3 项 | init 不支持格式冒 traceback（修复前） |
| C（架构） | 架构 2 项 + 扩展 1 项；单元 2 项 | 行为保持：551 passed + 真实 CLI 同文案 smoke |

**f-audit（mock 面与真实覆盖核实）**：

- mock/monkeypatch 共 60 处 / 8 文件，逐文件核对**全部**用于外部边界或故障注入
  （epubcheck jar、MinerU HTTP、calibre/kindle、git、pandoc 可用性、原子写故障注入、体积
  阈值注入），无用 mock 替代内部业务逻辑；`match=` 断言 11 处均为契约消息（错误分类/行号/
  API key 提示），非纯措辞测试——**未删除任何用例**（无「只固定措辞/实现细节」的无效测试）。
- 「真实 CLI review 登记」：原仅领域层覆盖（`test_import::test_import_reviewed_marks_aligned_units`）；
  新增 `tests/test_external_tools.py::test_real_cli_import_reviewed_registers_reviewed_state`
  走真实 CLI（`import` → `import --reviewed` → `status --json`），并把文档化的「两步登记」
  契约固定进断言（防静默改变语义）。
- 「工具执行覆盖」：原 `run_epubcheck` 仅有「缺 jar」路径与 stub（密闭策略）；新增
  `test_real_epubcheck_executes_and_clean_product_releases`（java + jar 可用时**真实执行**，
  断言 `ran=True`、零 error、`released=True(ok)`；不可用则 skip 并给出原因）。本机真实执行通过。

**f-report（skip 与外部工具缺口，单独列出）**：

- 条件 skip（工具存在即运行）：pandoc 门控 3 项（`test_epub_reader` 2 + `test_ingest_boundary` 1）、
  epubcheck 门控 1 项（`test_external_tools`）。
- 本机缺口：tesseract / ocrmypdf / rapidocr-onnxruntime 未安装，MinerU 无 key —— 扫描 PDF 的
  离线 OCR 只经 `FakeOcrBackend` 覆盖（`pdf.ocr` 路由有用例），**真实扫描件的 OCR 质量未验证**；
  MinerU 仅 mock 覆盖、未访问真实 API（`doctor --ping` 未启用网络探测）。
- 全量用例离线可跑（`uv run --offline pytest`）；F 组新增 2 项后全量 **553 passed**（551→553）。

### 批次 docs（文档同步与计划回写）

- **AGENTS.**{zh,md} 架构边界新增三条契约：共享模型归 `models` 且**模块级导入图无环**（C 组）；
  预处理产物 schema 契约归 `preprocess/`（`catalog.csv`/`repairs.jsonl`）；
  可预期输入错误须为 `ValueError` 子类、CLI 统一中文提示 + 非零退出码（E2 口径）。
- **references/build.**{zh,md} 补两条：媒体引用边界（D 组包含性校验 + `media_dropped` +
  `E_MEDIA_EPUB_LOST`）与构建日志署名（#40，不出网）。
- **任务卡补 N 阶段缺口**：新增 `references/taskcards/notes.{zh,md}`（`notes_verify`/
  `notes_register` 现场 → 动作 → 完成判据 → 失败处置），索引补行；`tests/test_taskcards.py`
  的 drift guard（`KINDS`/`_CARDS`）扩展覆盖两个注释 kind——此前新 kind 未被该 guard 覆盖。
- **放行条件文档补齐**：`docs/quality-control` 与 `docs/postprocessing-spec` §5 的放行条件
  列表补 `catalog_unresolved_open == 0`、**有注书成品注门**（`notes_open`）与越界媒体引用
  的拒绝读取说明（对齐 `qa/report.py`/`qa/notes_audit.py` 实际行为）。
- 其余 references 与 docs 已在对应批次同步：`ingest`（D）、`invariants`/`qa`（B2/N）、
  `notes`/`review`（N）、`semantic-repair`（C）；README/AGENTS/development-plan/pdf-parsing（E2 许可）。
- **新增 lessons 两篇（中英）**：`2026-10-15-media-ref-containment`、
  `2026-10-15-epub-source-media-normalization`（附索引与「来源与去向」更新）。
- i18n：受影响英文文件 `--finalize` 后 `--check` / `--links` 均 OK。

### 完成状态与提交清单（2026-10-15）

基线 `4d76c62` 之后共 12 个提交（**已推送** GitHub `Misaka0x26FE/auto-epublizer` 与 Gitee 镜像，`4d76c62..badf4f5`）：

| 批次 | 提交 | 内容 |
|---|---|---|
| 计划 | `98eac6e` | 新增本计划（含 S0/E-1/B-1 实施记录） |
| E-1 + B-1 | `e6396c1` | #33/#35/#36 + #39/#34/#38（退出码/术语/ledger/长度/注码/版面候选） |
| — | `386ebf6` | 示例配置补 `min_src_chars` 短源保护项 |
| N | `1ac3233` | 注释结构化与绑定：notes.json 权威 + 原位标记 + 三道独立硬门 + 全书构建 |
| A | `e8b58b0` | 原子写唯一临时名 + fsync + 失败清理（并发/失败/恢复 7 项回归） |
| B2 | `a4a14d9` | 放行真值表（15 项）+ `blocking` 级别统一 + 报告指纹失效链 |
| D | `421cf46` | P0 媒体越界读修复 + EPUB 源媒体引用归一化 |
| E2 | `131993c` | #40 全源码 SPDX/来源标识 + CLI 契约（`IngestError` 口径） |
| C | `6867d50` | 架构最小重构：导入图 0 环 + 4 处归位（模型/探测/策略/契约） |
| F | `2140ba7` | 真实 epubcheck 执行 + 真实 CLI review 登记覆盖 + 回归映射与工具缺口报告 |
| docs | `2bbb64b` | 文档矩阵同步（AGENTS/build/taskcards/放行条件）+ lessons 两篇 + 计划回写「已完成」 |
| — | `badf4f5` | 提交清单补 docs 提交（计数修正） |

**最终验证**：`uv run --offline pytest -q` = **553 passed**；`ruff check` / `ruff format --check`
全绿；`python3 scripts/i18n.py --check` / `--links` = OK；离线 `uv build` 成功且 wheel
METADATA 为 `License-Expression: AGPL-3.0-only`（Metadata 2.5）。

### 保留阻塞项（缺外部材料，未完成部分）

- **V（导航与结构恢复）**：需回源确认前置页角色/导论起点/章节目录边界并建立**独立期望树**；
  本机无目标书的源工作区与 raw 证据 → 保留阻塞，**不得从 EPUB 数字顺序猜配**。
- **H（历史成品回收）**：典型成品 `sample-archive-a` 的源工作区/构建版本未定位
  → 逐本记录（EPUB 哈希/源身份/注释盘点/期望树/重建版本/QA/阅读器验收/副本同步）无法执行；
  按要求不删除旧版、不手改 released、不直接编辑已交付 ZIP。
- **阅读器实测**（弹窗、往返、目录真实落点）：需真机阅读器环境；源码或截图结构推断不算实测。
- **#34 真实书私有验收**（`sample-document-g`）：本机无该工作区。
- **扫描件 OCR 质量**：无 tesseract/ocrmypdf/rapidocr/MinerU key（详见 F 报告），仅伪后端覆盖。

## 8. 后续审查与成品软件指纹增补

状态：**指纹增补已实现并验证；审查发现待修**。审查基线为 `4d76c62..c0e89c2`，
覆盖关键正确性路径而非 129 个文件逐行全审；仅 SPDX 变动不算行为变化。前批次的
553 passed 不作为本次审查结论，以下既有缺陷本轮只复现与报告，未擅自修复或结单。

本次用户新增要求：EPUB 内包含项目名、项目地址、实际构建版本，以及实际使用的其他开源工具。
实施边界：

- OPF 元数据、内容 XHTML 的机器可读注释、版权页的独立制作声明使用同一份指纹。
  无版权页时生成独立制作信息页，作为非线性 spine 文档并提供地标入口；不伪造原书版权页。
- 不修改原书作者/译者/出版社和 `dc:rights`，软件许可证不自动扩张到书稿。
- 构建身份取当前执行代码版本；源码检出时另记 revision/dirty，不复用 init 时的旧 producer。
- 处理工具在实际成功的 ingest 路径记录名称、版本、项目 URL 与许可，随工作区持久化；
  未调用的 OCR/转换器不列入。服务与开源软件区分，版本不明明确记未知，旧工作区明确未记录，
  不根据当前安装列表倒推历史工具。默认制作声明不依赖网络，不含主机路径、密钥或唯一追踪 ID。
- 保持输入/工具快照不变时构建确定性；源/译/双语共用构建内核。QA 仅认可有效的工具指纹注释，
  其他残留注释仍报错；生成制作页不能被误报成丢失/未知书稿单元，其他未知文档照常阻断。
- 补消费行为/边界回归，运行受影响测试、Ruff、i18n，使用真实 CLI 合成 EPUB 与 EPUBCheck 验证；
  核对版权声明保留、元数据/注释一致、工具历史冻结、无多余工具与字节确定性。

### 8.1 审查回流（未修复）

| 级别 | 位置 | 已观察行为／影响 | 最小处置方向 | 状态 |
|---|---|---|---|---|
| P1 | `orchestrator.py:1038–1040` | 合成源文导出的 2 个候选均判为 note，仍可登记 inventory=none，构建零语义注文且注释门 ok | 已核证候选必须与 note/ref 图对账，拒绝 note 候选与 none 矛盾及 present 的部分遗漏 | **已修**（`6cb79f0`）：`validate_candidates_vs_graph` + register 接线；回归 2 项（HEAD 上失败） |
| P1 | `orchestrator.py:964–967` | 修改源注文并重新登记后，译注 source_notes_sha256 不符仍可 build，成品注释门也 ok | 共享加载/构建/审计入口验证译注源版本绑定，并按实际源/译模式检查需要的译注 | **已修**（`6cb79f0`）：共享加载入口校验译注绑定 + 按模式 `require_target`；回归 2 项 |
| P1 | `qa/notes_audit.py:48–56` | 注文图片不存在时 collect_media 删除引用，仅记 drop 事件，注释文本对账仍 ok | 单独核对注文媒体期待和实际 aside/包内资源，不能由去图片的文本规范化掩盖缺失 | **已修**（`6cb79f0`）：注文媒体单独核对（期待引用 ⊆ aside 实渲染 + 包内资源）；回归 1 项 |
| P1 | `qa/artifacts.py:35–57` | 已放行后新增 catalog unresolved，status 报告不 stale、台账仍 released；重跑 QA 才变为 catalog_open | 摘要覆盖所有放行输入及有序 publication 发布描述、实际源身份，不能排序抹去单元顺序 | **已修**（`6cb79f0`）：发布顺序单元描述 + catalog/repairs/facts + 实际源件字节；回归 1 项 |
| P2 | `orchestrator.py:1691–1700` | 旧报告过期被路由为 import --unit report，执行后同一任务持续返回 | 按 stale 类型分派 build/qa，不把 report 当真实单元 | **已修**（`6cb79f0`）：伪 stale 项按类型分派（report→build→qa 等）；回归 1 项 |
| P2 | `qa/artifacts.py:92–93` / `orchestrator.py:1538` | QA 保存相对 EPUB 路径，切换 cwd 后未变的产物被误判 stale | 工作区内路径相对 store.dir 保存/解析，外部产物用规范化绝对路径 | **已修**（`6cb79f0`）：工作区内成品相对 `store.dir` 保存/解析 |
| P2 | `qa/provenance.py:425–430` / `qa/audit.py` | 已登记 orphan_ok 无引用注文通过新注释门，却被旧门报 E_FN_EPUB_LOST / E_FN_BACKLINK | 根据已登记图移交旧计数/回链门，不通过伪造引用或删除合法注文解决 | **未修**：设计见 `2026-10-15-review-backflow.md` §2（按书级登记状态移交旧计数/回链门，不伪造引用） |
| P2 | `AGENTS.zh.md:89–110` 及英文对应流程 | 标准流程先翻译/import，再到 5.7 注释登记，与前置绑定要求相反；workflow reference/机器指针则已前置 | 把中英文入口的核证/登记步骤移到翻译前，统一入口契约 | **未修**：设计见 `2026-10-15-review-backflow.md` §2（注释核证/登记前移至翻译前 + 文档闸） |

前 7 项均以临时合成工作区运行观察；报告/cwd 两项使用真实 EPUBCheck 的已放行产物，
没有伪造检查器成功。最后一项为文档直接核对。脚本/书稿样本未加入永久仓库；
这组结论不证明历史真实书已修好，也不承诺现有测试覆盖上述未修缺口。

### 8.2 指纹实现与本次验证

- 新增 `auto_epublizer/fingerprint.py`：项目 URL/软件许可、当前构建版本、源码 revision/dirty、
  Python/Pydantic 运行时、冻结的实际处理工具；可见页、OPF aep:build 和 XHTML 注释共用数据。
- ingest 各实际路径记录工具快照并通过 RunStore 保存；RapidOCR 只有真实处理页面才列入，
  MinerU API 是版本/许可未知的服务，不倒推其内部实现。旧工作区 processing_tools=null 明示未知。
- 已有版权页保留原文并追加独立软件声明；无版权页生成不覆盖同名书稿的非线性制作页，
  从 copyright-page 地标访问。有效结构指纹注释被窄豁免，普通/坏 JSON 注释仍报 E_RESIDUE；
  只有 OPF 与页内标识、指纹一致的制作页被识别为软件附页，其他未知文档仍阻断。
- 新增消费行为测试 `tests/test_fingerprint.py` 与 `tests/test_processing_tools.py`：
  当前构建/初始版本区分、源版权保留、JSON/XML 特殊字符、旧历史未知、工具冻结、
  实际解析路径/失败保留、生成页同名冲突、辅助页篡改、残留门及重复构建字节一致。
- **本次全套**：`uv run --offline pytest -q` → **572 passed, 1 skipped**；
  `ruff check .` 通过，`ruff format --check .` → **299 files already formatted**；
  i18n `--check` / `--links` 均 OK（5 对中英文文档已 finalize）。
- **真实 CLI smoke**：源文 convert、译文 build、双语 build 均实际执行 EPUBCheck，
  **零 error 且 released=true**；译文/双语保留 `dc:rights=© Original rights owner`。
  实际 HTML→EPUB 记录 Pandoc **3.1.3**；纯 Markdown 不虚列额外外部解析工具。
- **可见面**：从真实合成 EPUB 提取制作 XHTML/CSS，在 Chromium 实际渲染并查看，
  确认项目链接、版本、源码 revision/modified 状态、软件许可边界和运行时工具可见。
  这不是 EPUB 阅读器弹窗验收，不能据此消除 §7 的注释/目录真机阻塞。
- 临时 EPUB、复现工作区、预览服务与浏览器页均已清理。未修改用户历史成品、未提交/推送代码，
  未同步/关闭线上 issue；后续先修上述 P1 漏门，再安排真实书 V/H 回收。


