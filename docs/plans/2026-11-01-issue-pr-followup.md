# Issue / PR 增量更新与修复计划（2026-11-01）

状态：**已完成主体（提交 `5aee910`、`db20a42`）**；H2 三书实书复验仍 blocked（材料缺失）。
A–G 的实现、回归与中英文档均已落地；H1 旧议题证据矩阵、H3 全量集成检查、审查修复与复审 5 项
缺口均已回填并提交推送。后续增量任务见
[11-03 修复交接方案](2026-11-03-issue-pr-repair-handoff.md)；真实 outbox 迁移与远端议题处置
仍未获授权。

## 1. 查询基线

- 仓库：<https://github.com/Misaka0x26FE/auto-epublizer>。
- 本地 HEAD 与查询时 GitHub main 相同：`0d023c78ad3fc8f9c5b89d50b51061e841b13832`；开始时工作树干净。
- 当前开放 issue **38** 项；开放 PR **0** 项；`gh pr list --state all --limit 100` 返回历史 PR **17** 项。
  上轮计划记载的“18 项”与当前列表不符，本轮采用实际返回列表，不推测差额原因。
- 最新 CI `41285238977` 在该 HEAD 上 success；这是远端 CI 证据，不等于本轮运行全套测试。
- 已读取开放 issue 列表/正文，重点逐项读取 #84–100 正文与评论、其余开放项的评论及上轮实现账本。
- 本轮定向验证：`uv run --offline pytest -q tests/test_pdftoc.py tests/test_cover_hanze.py`
  → **30 passed，31.62s**。覆盖目录匹配和汉译封面；未重新执行完整 PDF 实排与全套回归。
- 本计划接续 [10-31 更新计划](2026-10-31-issue-pr-update.md)，不重置其完成项，亦不覆盖
  [10-14 审查计划](2026-10-14-review-and-repair.md) 的历史实书待验收事项。
- 任务清单集中在本文，沿用仓库 `docs/plans/` 规范；本轮不修改 GitHub issue/PR 状态。

## 2. 当前代码改变了哪些处置结论

| 议题 | 当前源码/验证证据 | 处理结论 |
|---|---|---|
| #90 缺段定位 | `qa/provenance.py` 有 `coverage_missing`，`qa/report.py:QaResult` 未导出该字段 | 明确诊断缺口，优先补端到端字段传递 |
| #87 段边界漂移 | `review/g0.py:410–411` 在去空白全文相同时立即返回 | 存在结构可见性缺口；但 align 是逐句契约，不能直接要求行数等于段数 |
| #99 排版收敛 | `pdfexport.py:1150–1180` 比较最终目标页映射，最多三遍；不稳定抛 `E_PDF_TOC_UNSTABLE` | 已有实现，先扩展现场形态回归，不另造两遍排版器 |
| #92 节页码 | `pdfexport.py` 收集实际 anchor_pages；已有 `test_unlocated_fragment_is_not_guessed_from_section_start` | 有锚点路径已有保障；重点查无锚点目录条目及现场版本 |
| #98 西文字形 | `pdfexport.py:105` 默认 CJK 族优先；EPUB 主题用 generic family，QA 限制具体族名 | PDF 修字体回落顺序；EPUB 另按规范评估，不能直接复制 PDF CSS |
| #95 按书样式 | `build/__init__.py` 固定三个主题 | 新功能，须维护既有主题约束与摘要失效 |
| #100 封面模板 | `cover_hanze.py`、CLI template alias、生成/嵌入测试；当前 HEAD 即模板提交 | 核心功能已实现，做需求差异验收而非重做 |
| #97 书名页误删 | issue 给出了 raw→structured 差异，但本轮未定位当前代码的具体删除函数 | 先追踪清洗链及 agent 操作记录，再判断代码、skill 或现场脚本责任 |

重要约束：issue 是问题证据，不是必须原样采用的设计。#87 的“全文相等就跳过块检查”仍会漏掉
其报告的故障；#88 的相似度 0.97 也不是源译对应正确的证明；#92 的 ±1 页不适合作为最终验收。

## 3. 全量 issue 处置矩阵

所有编号链接格式：`https://github.com/Misaka0x26FE/auto-epublizer/issues/<编号>`。

| Issue | 归属/优先级 | 本轮后续处置与关闭条件 |
|---|---|---|
| #90 | A1 / P1 | report、JSON、文本一致定位缺段，正负回归后回写 |
| #89 | A2 / P1 | 点引导线负对照与真实引用正对照；保留源摘抄，不整类豁免 toc/index |
| #97 | A3 / P1 | 找到真实删除责任点；书名页/半书名页/封面保全，正文页眉仍正确处置 |
| #87 | B1–B2 / P1 | 逐句到段落的有序映射及历史基线契约；合法多句同段不误报 |
| #88 | B3–B4 / P1 | 先只读重对齐提案，再显式事务应用；模糊映射留人工核证 |
| #85 | C1 / P2 | 页界与半句断段候选，可定位 advisory，不自动合并 |
| #86 | C2 / P2 | bbox/栏内缩进证据与段落候选，保全字符和源位置 |
| #93 | C1 / P2 | 只读卫生扫描与负对照；词义和词性错误交 agent 审校 |
| #84 | D1–D2 / P1 | 可读目录视图、来源绑定、内部目标和独立对账 |
| #92 | D3 / P1 | 复验当前锚点路径，补无锚点/同名/缺目标诊断；最终页码精确一致 |
| #99 | D3 / P1 | 验证已有收敛机制在目录换行/提示行/页数变化下仍有效 |
| #98 | E1 / P2 | PDF 拉丁/CJK 字体回落实测；EPUB 保持独立规范 |
| #95 | E2 / P2 | 受约束按书样式，QA 同规则、摘要纳入、越界资源检查 |
| #96 | E3–E5 / P2 | 书版目录/图版/部分页/页眉页脚/索引等拆批实现 |
| #91 | F1–F2 / P2 | 有身份依据的归档预览、事务、忽略规则、链接及重跑保护 |
| #100 | G1 / 验收 | 对照已实现模板，列出外部意象/参数/署名检查等未覆盖项后分别定案 |
| #94 | 汇总 / H | 用 A–F 的子项证据逐项更新，真实三书交付独立核验 |
| #77 | H / 既有实现 | 上轮内容摘要与 import 漂移已落地，复核当前回归后提供证据 |
| #80 | H / 既有实现 | 上轮结构化错误出口已落地，复验非法 catalog/repairs 的 JSON |
| #79 | H / 既有实现 | image→figure、blank 及相对证据提示已落地，核对文档后回写 |
| #78 | H / 既有实现 | 已有 review_findings，复验完整 QA 自引用路径 |
| #73、#82 | D3/H | 绝对页序标准已落地；与 #92/#99 一起验目录精确落点 |
| #74、#75 | E3/H | 已有图版高度预算/封面身份修复；新增书版能力不回退这些保障 |
| #76 | H / 既有实现 | 出版/日期/rights 的 XMP 与派生清单已有实现，复验读回 |
| #81 | H | 缩放、目录、import skip、JSON 四项分别验，不只验 PDF |
| #83 | D3/E1/H | 八项现场反馈对照上轮 P/Q 账本；评论补丁是旧基线参考，不直接应用 |
| #72 | H | 九项提案对照上轮 E1–E5，区分已实现、替代方案和人工待验 |
| #71 | G1/H | 默认版式及封面身份已有实现；自动回退策略保持独立决策 |
| #69、#64 | H | 18 类/扫描书汇总逐子项对账，PR70 文档不等于实书验收 |
| #58 | C2/H | 栏内顺序、索引孤页、跨页注尾仍需源图；沿用现有 source evidence |
| #57 | B4/H | 复用 safe_repair 与质量证据契约，外部脚本问题另列 |
| #34、#37 | A2/H | 稳定 ref_id/notes 门已有实现，保留 OCR 候选和旧书注释重建验收 |
| #40 | H / P3 | SPDX/来源指纹已有实现；PyPI 决策与许可证表述另列，不加部署追踪 |
| #41 | H / 汇总 | 衔接旧总计划，不用新工具通过数替代历史书恢复 |

### PR 处理

- 已合并 9 项：#1、#2、#7、#9、#42、#44、#45、#59、#70。
- 已关闭未标 merged 8 项：#11、#15、#17、#27、#51、#52、#66、#67。
  依据现有实现和历史集成记录核查吸收情况，不重开重复功能 PR。
- #83 评论含提交 `22a64a6` 的补丁，但没有对应开放 PR。其“数量相等按顺序配对”和
  “未找到片段退到章首”与当前更强契约冲突；仅抽取测试场景，不移植这些退化路径。
- 实施开始前刷新 PR/HEAD/CI；若出现新 PR，先对照任务矩阵审查差异，再决定集成顺序。

## 4. 依赖与可执行任务

推荐顺序：**A → B → C → D → E → F → H**；G 可作为早期验收独立完成。
D1 的目录来源身份须先于 D2，D2/D3 完成后再实现 E 的分页外观；E 修改分页后重新验证 D3。
所有命令/schema 名称以下均为拟定，最终接口随实现审查确定。
每项实现与测试通常 2–5 文件，双语文档另批同步；超出即再拆分。

### A：先修可定位性与保真（3 个独立批次）

- [x] **A1 导出缺段诊断（M，无前置）**。文件：`qa/provenance.py`、`qa/report.py`、CLI 及 provenance/CLI 测试。
  增 `coverage_missing` 与含 unit/block/preview 的详情，文本显示前 5 项，JSON 保全清单。
  验收：缺一段可直接定位，正常书为空列表，零翻译路径口径正确，阈值/放行规则不变。
  验证：合成缺段→真实 qa JSON/文本输出，检查序列化全链。
- [x] **A2 目录页码与注码分离（M，无前置）**。文件：`review/g0.py`、共享注码识别函数及 review 测试。
  排查 count/编号差集/全部调用方，连续引导点、OCR 混合点、三位页码作为负例；真实句末注码、
  标准 `[^ref-*]` 和目录内合法注释作为正例。验收：相同源字节通过误报场景，真丢注仍阻断。
  验证：review/import/g0 定向回归，不修改 align src 迎合正则。
- [x] **A3 标题保全责任追踪与修复（M，无前置）**。先追 `ingest/`→`structure/`→agent 清理规范。
  用合成书名页（大标题/副题/编者）和正文重复页眉复现；若当前代码没有删除，交付明确的
  skill/外部脚本修正而非虚构代码根因。验收：各标题字节保全、清理决定带来源位置与理由。
  验证：ingest/preprocess/structure 相关回归；定位后再冻结具体修改文件。

**检查点 A**：缺段可读、真注守恒、书名页保全；每个确认缺陷先失败回归后最小修复。

### B：段落与逐句对齐契约（顺序执行）

- [x] **B1 明确身份契约（S）**。文件：translation/align 模型及相关规范。
  保持 `seq/src/tgt/note` 的逐句语义；定义一个 Markdown 块对应连续多句、标题/代码/表格独立类型、
  跨块行如何显式表达。明确源块与译块身份、注册时结构摘要及旧工作区 unknown/迁移口径。
  验收：合法多句同段、拆合句、重复文本、只改换行与真实改段均有真值表。
- [x] **B2 结构漂移检测（M，依赖 B1）**。文件：`review/g0.py`、共享 Markdown 块解析、import 绑定及测试。
  全文相等仍检查有依据的块边界；历史无边界基线时输出候选/unknown，而非猜测曾经有几段。
  验收：可定位 md 块与 seq 范围，合法多句同段不过度阻断，增删/重复/乱序继续检出。
  验证：review/import/provenance 定向测试及历史工作区兼容 fixture。
- [x] **B3 只读 align 重建提案（M，依赖 B1）**。文件：`translation/align.py` 或内聚新模块、CLI、对应测试。
  默认 dry-run，输出一对多/多对一映射、未覆盖块、歧义及差异；src 只取已验证来源。
  相似度仅排序参考，重复句/OCR 缺行/大幅改写不得自动认可；拆句源归属留给 agent。
  验收：不写正式文件，每块去向可解释，低置信映射明确待核证；合并后文本守恒。
- [x] **B4 显式应用与恢复（M，依赖 B2/B3）**。复用 `safe_repair.py`、RunStore、import 及相关测试。
  提案绑定输入摘要，全量预检后同步 md/align，故障回滚；状态由 CLI 登记并失效旧审校/成品。
  验收：dry-run 零写入、输入变化阻断、重复执行可解释、写盘故障保全旧件。


### B1/B2：块身份与结构漂移

- 新增 `review/blocks.py`：`block_spans` 用 `content_blocks` 的同一套块定义，把每个正文块
  映射到 align 的**连续 seq 区间**；`structure_digest` 哈希块号/类型/seq 区间/块文本摘要。
  无法精确还原时报 issue，不猜边界。
- 真值表 `tests/test_align_blocks.py` **10 passed**：多句同段、拆句、重复文本、只改换行/
  缩进不改变基线；合并、拆分、乱序、缺句、多余句改变基线或报 issue；围栏代码独立成块。
- 契约文档写入 `references/translation`（中英）：源块与译块独立编号、不要求数量相等，
  「行数=段数」「全文归一化相等」都不替代边界核对。
- B2 接线：`import` 成功登记 `meta.align_structure`（映射有歧义则不登记并给 advisory）；
  `qa`/`quality_evidence` 重新推导，有基线不一致进 `E_ALIGN_MD_DRIFT`，无基线记
  `align_structure_unknown`（迁移可见性，不阻断）。CLI 文本与 `report.json` 均可见。
- 端到端回归：import 后把两段合并（归一化全文仍相等），build + qa 报块边界缺陷且不放行；
  真实 CLI 用例 **1 passed（57.94s）**。import/provenance/quality_evidence 定向联验通过。

### B3：只读重建提案

- 新增 `translation/align_proposal.py`：先用 `block_spans` 分别把译文块映射到 align `tgt`
  区间、把源文块映射到 `src` 区间，再按区间重叠判定 `exact`/`merge`/`split`；
  `propose` 只列候选、不出行，`uncovered` 报告源文剩余块，`writes: false` 恒为只读。
- 对应关系不依赖跨语言字面相似；重复句/OCR 缺行/大幅改写不会被自动认可，拆句源归属留给 agent。
- 新增 `align-propose` CLI（`--workspace`、`--unit`，JSON 输出）与只读回归：提案前后工作区
  文件 mtime 全等。提案真值表 **5 passed**，CLI 只读用例 **1 passed**。
- 中英 translation 指南已写入口径与「提案≠应用，写入走 B4 事务」。

### B4：显式应用与恢复

- 新增 `align_rebuild.py` 与 `align-apply` CLI：默认 dry-run；`--apply` 前先做全量预检
  （源件/译文/对照表摘要、seq 连续、md↔align 一致、源保真反向），预检后文件变化拒绝覆盖。
- 事务先持久化旧字节日志再替换；写盘故障整组恢复旧件。成功后重新登记
  `meta.align_structure` 与导入摘要，`reviewed`/`built` 回退 `aligned`，旧报告随摘要失效。
- 回归 **6 passed**：只读零写入、应用后基线与行落盘、输入变化阻断、行与 md 不一致阻断、
  reviewed 失效、第二单元写盘失败时两组均恢复原字节；CLI dry-run **1 passed**。
- 中英 translation 指南补充应用/恢复入口与 `already_applied` 语义。

**检查点 B**：以逐句契约验证结构修复，不能用“行数=段数”或“全文相似”代替对应关系。

### C：候选扫描与源版面证据

- [x] **C1 只读卫生扫描（M；CLI 接线可另分 S）**。依赖 B1 的块类型；复用 `quality_evidence`/`evidence breaks`。
  报原语词、引号不平衡、重复词、半句边界、超长段、疑似丢尾，带 unit/seq/块/上下文。
  覆盖正文与译注；代码、书目、诗行、缩写、正常跨段引文和冒号引导句作为负对照。
  全部语义候选为 advisory；词义选错不宣称正则可判。验收：只读、稳定 JSON、正负例齐备。
- [x] **C2 bbox 段落候选（M；解析持久化与证据输出分两步）**。文件：`ingest/pdf_reader.py`、版面/reading_order、preprocess 及测试。
  沿用已有坐标，按栏和版式估计缩进，保留字号、行距、源页与字符范围；不用全页统一 8pt 阈值。
  无坐标明确 unknown。验收：双栏、引文、悬挂缩进、列表、RTL、跨页均保全阅读顺序与字符，
  可疑边界由 agent 核证；不按 300/420 字硬切原文。用合成 PDF 验证。

### C1：只读卫生扫描

- 新增 `hygiene.py` 与 `hygiene` CLI：正文与 `translation/notes.json` 只读扫描，输出
  `unit`/`block`/`seq_range`/`context` 与候选类型，`writes: false`。
- 候选：残留原语词、引号/括号失衡、相邻重复词、半句、超长段、疑似丢尾，全部 advisory。
- 负对照落地：围栏/行内代码跳过；书目/索引/术语表单元跳过；括号内原词不报；
  冒号引导句不报丢尾；引号按整单元配对。
- 真值表 **9 passed**；CLI 只读回归 **1 passed**；中英 translation 指南已加入口径。
- 未把词义/词性错误纳入正则判定（不是本扫描能证明的范围）。

### C2：bbox 段落候选

- 解析持久化：`pdf_reader._page_blocks` 在文字层块上增加逐行 `lines:[{text,bbox}]`（无坐标的行
  不写），既有 `bbox/font_size` 不变，raw 页 JSON 仍可重建。
- 证据输出：`preprocess/layout.py` + `evidence layout --json` 输出每页栏号、块序、字符范围、
  字号、估算行高、缩进/悬挂缩进/列表/引文分类、块内新段候选、跨页续接候选；无 bbox 明确
  `unknown`，不重排双栏/RTL，也不按字符数切原文。
- 真值表 **8 passed**：双栏/字符范围、unknown、缩进与列表、块内合并候选、悬挂缩进、跨页续接、
  RTL 栏号、合成双栏 PDF 顺序与字符守恒；ingest/OCR/source_evidence **52 passed** 回归。
- 中英 ingest 指南已加入 `evidence layout` 口径；现场双栏/OCR 书仍待真实源件验收，不冒充完成。

### D：目录视图与精确页码

- [x] **D1 目录来源模型（M）**。文件：结构/nav 领域及契约测试。
  用经来源确认的节点/父节点/顺序/标签/完整 href#fragment；区分原版目录文本与生成结构视图，
  保留作者、副题、原版页码及源摘录去向，定义 page_numbers 策略消费位置。
  验收：来源条目均有去向，缺锚点列未决，不从 `§` 字样自动判定标题。
- [x] **D2 目录生成与独立检查（M，依赖 D1/B）**。文件：build 目录模块、QA 及测试。
  生成可点击层级目录；与独立期望树核父子、目标、顺序、标签，不让生成器自证正确。
  原目录重排经来源映射说明，不靠清空 align 或降低覆盖率阈值通过。
  验收：跨行题名、多作者、同名节、缺页码、压在 `<br/>` 中的目录都有明确结果。
- [x] **D3 PDF 现有能力验收与剩余修复（M，依赖 D1/D2；现有回归可先跑）**。
  文件：`pdftoc.py`、`pdfexport.py`、对应测试。复跑 fragment/unstable/atomic 场景；新增长题名、
  目录提示行、页码位数变动和跨多页 § 条目。无锚点优先请求结构补证，歧义不猜首页或首次全文命中。
  验收：最终实体目录、书签、实际锚点的绝对页序逐项完全一致；不收敛/缺目标不伪装成功，旧件保全。
  验证：真实 Chromium + PyMuPDF 及独立最终 PDF 读取，不接受 ±1 页作为通过条件。

### D1：目录来源模型

- 新增 `toc_model.py` 与 `evidence toc`：`nodes` 给结构视图（unit/parent/order/level/label/
  href，单元内子标题锚点带 `file.xhtml#fragment`）；`original` 保留目录单元逐行文本、行号、
  页码候选与匹配状态。
- 目标绑定只认完全同名（unit_exact/anchor_exact）；重复记 ambiguous、找不到记 unresolved，
  `§` 无正文锚点记 section_anchor_absent，不从 `§` 字样造标题；`page_display` 仅在
  `page_numbers.csv` 声明 original 时给出。
- 真值表 **7 passed**（父节点/顺序/完整 href、子标题锚点、精确匹配、§、策略消费、只读）与
  CLI 只读 **1 passed**；中英 build 指南已写入口径。
- 三书原目录重建仍需 D2 生成与独立对账，不能以模型输出代替成品验收。

### D2：目录页生成与独立对账

- `build --toc-page` / `output.toc_page`：toc 单元按单元树 + 子标题锚点渲染分级可点击
  `<nav data-aep="generated-toc">`；页码只读显式 `preprocessing/toc_pages.csv`，缺省留空。
- 独立对账：`qa/toc_page.py` 从 publication 单元与 md 锚点重算期望树，解析成品实际
  `<ol>/<a>` 逐条核对顺序/层级/标签/href；provenance 识别生成标记后跳过 md 段落探针，
  结果写入 `report.json.toc_page_findings`（advisory），不拿生成器自身产物自证。
- lint：`toc_compressed`（`<p>` 内 ≥2 `<br/>`）、`toc_no_links`、`toc_count`、
  `toc_entry_*`、`toc_missing_pages`。
- 回归 **6 passed**（可点击嵌套目录、独立对账与探针跳过、错目标、压缩/缺页码、页码映射、
  非法映射拒绝）；build/provenance/CLI **124 passed（273.27s）**；中英 build 与配置文档同步。
- 三书成品目录仍待真实工作区验收（H2），不以合成夹具代替。

### D3：PDF 片段/收敛验收与补充场景

- 现有实现复核：fragment 身份、三遍收敛、`E_PDF_TOC_UNSTABLE`、旧 PDF 保全、未定位/重号锚点
  不猜位置均已有测试；未重写两遍排版器。
- 新增现场形态回归：页码 1→2 位整体替换、`Contents`/`§` 无页码提示行不参与配对、
  跨三块长题名合并匹配、两个 `§` 条目按标签而非位置对应；真实 Chromium+PyMuPDF 用例
  **1 passed（14.66s）**：长题名+提示行的最终页码与书签逐项一致且 `converged=true`。
- 既有 PDF 定向：`test_pdftoc` **16 passed**，fragment/unstable/strict/旧件保全 **5 passed（44.50s）**。
- 三书实体目录仍须真实工作区与最终 PDF 逐项核验（H2）；本轮不以单元测试替代。

### E：受约束样式与书版 PDF

- [x] **E1 混合文字字体（S）**。文件：`pdfexport.py`、PDF 测试。
  PDF 拉丁字体优先、CJK 回落，明确缺字体诊断；用 l’État/Marx’s/中文标点读回、bbox 和渲染检查。
  EPUB 保留 generic font 默认；若拟引入功能性字体规则，先修规范及 QA，另批实施。
- [x] **E2 按书样式（M）**。文件：配置模型、build 样式加载、QA 与测试。
  复用同一受限 CSS 检查，限制工作区资源路径/外链，样式及引用资源纳入 build/report 摘要。
  验收：合法缩进/间距可覆盖，禁用属性与越界不通过，修改样式使旧报告 stale。
- [x] **E3 图版/部分页/目录行（M，依赖 D3）**。文件：PDF 样式/HTML 构建及测试。
  根据明确单元角色呈现，长标题点线/右对齐、整页图、部分页；不凭“单图”删除标题正文。
  验收：两种开本无标题孤页、无图重复/裁切、长目录无错页。
- [x] **E4 页眉页脚（M，依赖 E3）**。明确封面、部分页、章节首页和正文页规则，页脚隐藏不改变绝对页序。
  验收：真实页角色与章名对应、长名截断可读，目录页码仍精确；独立 PDF 检查。
- [x] **E5 索引/CIP/混合强调（M，依赖 E3）**。按已确认角色提供索引分栏、版权块不缩进、CJK 强调。
  验收：索引栏序/页码不串位，中文避免假斜体且拉丁语义强调保留。复排后重跑 D3。

### E1：混合文字字体

- PDF 正文族改为拉丁优先（Nimbus Roman → Liberation Serif → DejaVu Serif），再回落
  Noto Serif CJK SC / Songti；EPUB 主题仍保持 generic family，不改 EPUB 字体规范。
- 诊断从 FontDescriptor 的 FontName 取真实族名（Type3 也能读出），统计 latin/cjk 用字：
  拉丁字落 CJK 族记 `W_PDF_FONT_LATIN_USES_CJK`，CJK 字落拉丁族记
  `W_PDF_FONT_CJK_USES_LATIN`；`--json` 增加 `script_fonts`。
- 真实 Chromium 回归：`l’État`/`Marx’s`/中文标点读回、latin 全为 NimbusRoman、
  cjk 全为 NotoSerifCJK、无字体错配告警；PDF 全套 **51 passed（194.87s）**。
- 中英 build 指南已写入回退顺序与诊断码；实书字形视觉验收仍待 H2 的真实源件。

### E2：受约束按书样式

- 新增 `build/bookcss.py` 与 `output.css` / `build --css`：工作区内相对 CSS 追加在主题层后；
  只允许缩进/段距/行距/对齐/字重等排版属性，字体名/字号/颜色/背景/`@` 规则/`url()` 一律拒绝。
- 路径限制：拒绝绝对路径、`..`、符号链接越界；UTF-8、≤64 KiB；非法样式在写盘前抛中文错误。
- 审计独立兜底：`style.css` 含 `@import`/`url()` 记 `E_THEME_EXTERNAL`，不依赖构建期校验。
- 摘要：构建事件记 `book_css_used`（path/sha256）；样式随 EPUB 字节进入 `artifacts_digest`，
  重建后旧报告自然过期。
- 回归 **13 passed**（合法追加/摘要、七类禁用属性、越界路径、超限、写前拒绝）、审计 **2 passed**；
  中英 build 与配置文档已同步。实书按书版式视觉验收仍待 H2。

### E3：目录行、图版与书版页面

- 目录行：生成页采用「题名 + 点线 + 右对齐页码」；长题名换行后页码仍贴右并落在末行。
- 发现并修复真实缺陷：`pdftoc.rewrite_toc` 原用 XML 序列化，`<span class="toc-dots"/>`
  在 HTML 解析中吞掉后续节点，导致点线/页码布局失效；改为 `method="html"`。
- 回归：真实 Chromium 下目录行题名/页码同基线、页码贴右（A5 宽 0.7 以上），长题名同样成立；
  A5/32 开图版只绘一次、不越纸面、图注与后文完整。
- 定向 **3 passed（25.08s）**，`test_pdftoc` **16 passed**；中英 build 指南补充目录行/图版规则。
- 三书实体书版视觉验收仍待 H2；不以合成 PDF 替代。

### E4：页眉页脚角色

- 明确角色：封面无页眉页脚；区段首页不重复页眉；后续正文页页眉为区段章名
  （按版心宽度截断并加 `...`）；页脚始终为 PDF 绝对页序，隐藏封面页码不重编号。
- `PrintEvidence.section_titles` 记录区段标题，`stamp_folios` 按 `section_pages` 起始页判断角色；
  页眉放在上边距内，不参与正文越界诊断，也不改变分页/书签/目录页码。
- 真实 Chromium 回归：封面无页眉页脚；首章首页无页眉、页脚为绝对页码；次页页眉截断可读；
  次章首页不重复页眉、次页页眉与章名一致。中英 build 指南已写入规则。
- 三书实体页眉视觉验收仍待 H2；不以合成 PDF 替代。

### E5：索引、CIP 与混合强调

- 区段标题为 `Index`/`索引`（含人名/地名/主题索引）时排两栏、`h1` 跨栏；`Copyright`/`CIP`/
  `版权` 区段取消首行缩进；`<em>`/`<i>` 含汉字时改为 `span.cjk-em`（正体加粗），
  拉丁语义强调保留斜体，代码/预格式块不参与改写。
- 回归：真实 Chromium 下索引条目分布左右两栏、CIP 首行不缩进而正文仍缩进、中文强调结构
  改写且拉丁 `<em>` 保留；E3 后的目录/书签页码用例复跑通过（索引文本换行按归一化断言）。
- PDF 全套 **56 passed（192.20s）**；中英 build 指南已补充规则。
- 三书索引栏序/页码与视觉验收仍待 H2，不以合成 PDF 替代。

### F：旧产物归档

- [x] **F1 归档身份与预览（M）**。先核对本仓 `workroot/workpack` 能力，现场 `docs/pack_outbox.py`
  不是当然的本仓入口。以 manifest 的书身份/版本归组；缺版本或同版不同字节留歧义，不猜“终版”。
  验收：dry-run 给保留/待移动/冲突清单且零写入；已归档批次被 pack 识别。
- [x] **F2 归档事务（M，依赖 F1）**。规划移动、链接改写及忽略规则，先预检再显式应用，失败可回滚。
  验收：跟踪/忽略/混合文件均可处理，无覆盖，symlink 越界受控，重跑幂等；每个产物 hash 不变，
  `git check-ignore` 和 Markdown 链接检查通过。测试仅临时工作根，不自动 git add/commit。

### F1：归档身份与只读预览

- 本仓无 `pack`/`pack_outbox.py` 入口；新增 `archive.py` 与 `archive <outbox>` CLI，先做只读预览。
- 身份/版本只读 `MANIFEST.md` 显式字段；缺失、不可解析或「终版」列未决；同版不同清单记冲突，
  不按目录名或字数猜最新；`.archive/` 已有同版批次识别为 `already_archived`。
- 回归 **7 passed**：最高版保留、缺版本未决、同版冲突、已归档识别、symlink 不扫描、预览零写入、
  CLI 只读 JSON。中英 workflow 指南已写入边界。
- 实际移动/链接/忽略规则留给 F2 事务；测试只用临时工作根，不做 git 操作。

### F2：归档事务、链接与忽略规则

- `archive --apply`：移动待归档批次、改写 `docs/**/*.md` 的 `outbox/<批次>/` 链接、补齐
  `.archive/*/epub|pdf` 忽略规则；目标已存在不覆盖，重跑 `up_to_date`。
- 事务日志 `.archive/.transactions/<id>.json` 先落盘；失败回滚移动/链接/忽略规则，
  `--recover` 恢复中断现场。移动使用文件系统操作（测试不执行 git add/commit），
  文件字节哈希保持不变。
- 回归 **15 passed**：预览零写入、应用/幂等、已存在目标跳过、故障整组回滚、pending 恢复、
  `git check-ignore` 覆盖归档二进制、CLI apply 幂等。
- 补缺陷（H1 复核时发现）：不存在的 `outbox` 原先返回空计划并退出 0，`--apply` 还会为不存在的
  路径创建 `.gitignore` 规则；显式 `--docs` 指向不存在目录时静默跳过链接改写。现均改为中文
  `ValueError` + 非零退出，另有正例确认「同级默认 `docs` 缺失」不报错。先写失败回归再修。
  中英 workflow 指南同步该边界。
- 真实 outbox 的 884 MB 迁移仍须用户授权后执行；本轮不以临时夹具代替。

### G1：#100 需求差异与验收

| 需求 | 现状 | 决定 |
|---|---|---|
| 1600×2400 JPEG q92、纸纹/晕影/双线框/四角金线 | 已实现，版式测试覆盖 | 通过 |
| 四段式文字（丛书/主副题/原题/编者/署名/书系/出版/免责） | 已实现，元数据与 CLI 覆盖优先 | 通过 |
| 主色 `--accent`/palette、丛书行、出版行、免责行、署名后缀 | 已实现 | 通过 |
| 主书名按宽度二分自适应 | `fit_title` + 长题名回归 | 通过 |
| 意象区 globe/arch | 已实现且互异、在预留带内 | 通过 |
| 外部 PNG 意象 | 未实现 | 不纳入本轮；`--motif` 只接受内置图案，避免未登记资源进入封面 |
| 自动写 cover 单元 md/align | 未实现 | 不采用：生成封面走 `cover-generated.json` 登记与 build 接线，伪造 align 行会违反逐句契约 |
| QA 检查封面/制作页含译者 | 制作页已有译者字段；封面位图不可 OCR | 以封面 PDF 文本层回归核验书名/译者/出版行，位图视觉仍由 H2 实书验收 |
| 三书实际观感 | 本轮无源工作区 | 留 H2，不以合成封面替代 |

- 新增 PDF 文本层回归：书名、译者「马加丹汉化组 译」、出版行可见（compatibility ideograph 经 NFKC 归一）。
- 封面模板全套 **19 passed**；中英文档无需新增命令说明（既有 build/cover 指南已覆盖）。

### G/H：已有实现验收与收尾

- [x] **G1 #100 需求差异清单（S/M）**。复用当前模板；核对 metadata/覆盖参数/源封面优先/长题名/署名、
  外部意象、输出路径等每项。生成封面走既有登记机制，不为模仿建议而重写三份 manuscript。
  1600×2400 是 2:3，不等于 A5 的 148:210；说明实际裁切/留白契约。
  验收：封面和制作页署名可追溯，视觉抽检完成；未支持能力明确单列。
- [x] **H1 旧议题证据复核（按模块分 S/M）**。按 §3 分组重跑相关现有回归，对上轮完成项只补真正缺口。
  输出 issue→当前提交→测试/产物→剩余实书事项；经确认后再更新远端，不批量机械关单。
- [ ] **H2 三书及历史实书复验（逐本独立）——指定三书缺失，blocked；已用本机真实工作区完成部分复验（见下）**。取得用户指定工作区/源件后在保全副本中执行登记、build、
  qa、pdf 和交付审计；逐条目录/高风险段/注释核源及阅读器核验，各分发副本做字节对账。
  材料缺失明确 blocked；本轮未读取或修改现场书稿，issue 数字不冒充本机复现值。
- [x] **H3 文档与集成**。行为变更同步 AGENTS/SKILL 路由、manifest、对应 references 的中英双版本；
  经验经实际验证后入 lessons。新命令确认前不写成已发布操作步骤。

## 5. 实施验证与完成标准

1. 每个确认缺陷：最小失败回归→修复→受影响测试→真实 CLI/产物检查；纯验收项先复用现有测试。
2. A/B/C/D/E/F 各检查点保留退出码、输入摘要、测试与产物证据。候选扫描不自动签署语义审校。
3. 集成执行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、
   `uv run python scripts/i18n.py --check`、`--links`、`git diff --check`。
4. PDF 真实排版、EPUBCheck 和阅读器视觉验收分别记录；skip/unknown 不算成功。
5. 工具修复、文档更新、远端议题处置、历史书重建四种完成状态分开记录。
6. 本轮交付仅为计划；实施后逐项回填证据及实际提交号。全套绿色 CI 不代替新增场景和实书验收。

## 6. 实施记录

### A1 首批：缺段诊断

- 新增/加强正常、缺段、真实 CLI→落盘 report 的回归，原实现 **3 failed / 2 passed**，
  均因公开报告缺少 `coverage_missing`。
- 源审计在原覆盖率计算处同步记录 unit/block/path/preview，report 原样贯通；CLI 展示前五项，
  JSON 保留全量。段号明确为源正文块序，不冒充源码行号或 align seq。
- 修复后同一定向 **5 passed / 59 deselected（65.89s）**；未调整覆盖率阈值或放行规则。
- QA 中英文指南已更新；综合 provenance/CLI/i18n **76 passed（245.33s）**，A1 已验收。

### A2：引导点页码

- 五项回归先 **5 failed**，覆盖长 ASCII 引导点、混合点字形、方括号页码和同文真实引用。
- 共享行尾长引导点判据接入普通计数与两类数字/括号差集；保留 `...1` 省略号注码、
  标准显式引用和同文的真实引用，未按 toc/index 整单元豁免。
- review 与 PR42 契约回归 **62 passed（2.90s）**；中英 review 指南已明确判据边界。
- import/notes 消费者联验 **148 passed（22.40s）**；A2 已验收。

### A3：书名页标题保全

- 追踪结论：当前 CLI 没有任何代码把「与单元 title 同文」的块当页眉删除。
  `rebuild.py:_render_markdown` 只在 heading 段与将要写入的 `# title` 同文时省略该段，文本仍以 h1
  出现；`rebuild_structure` 虽计算 `clean_unit`，但 `write_structured` 仍按原始段渲染；现场书名页
  丢失来自 agent 按工作区清理规则手工删除，不能归因于确定性拆分。该结论写入经验条目，不虚构代码根因。
- 仍确认两处同类代码风险并先写失败回归：`clean_header_footer` 原实现按文本全局删除，
  连页中正文和 heading 段一起删；`clean_unit` 对书名页套用页码剔除会删掉「2024」「5」这类内容行。
- 修复：只删除页首/页末**那一次**出现且保留 heading 段；`clean_unit` 对 `cover`/`titlepage`
  原样返回。直接调用 `strip_page_numbers` 的证据显示原逻辑会丢弃出版年，修复后书名页三行全保留。
- 定向回归 **18 passed（3.99s）**；新增合成书名页经 `rebuild_structure`→`write_structured`
  逐字保留书名/副题/编者/出版地。
- 中英文档：新增 `lessons/2026-11-01-titlepage-echo-deletion`（判据、处置、代码边界、现场核验），
  并在 `quality-evidence` 结构章节写入「书名页/半书名页/封面不得按页眉删除、删除须带源页块与理由」。
- 现场三书仍未提供源件/工作区，A3 的实书恢复验收与 H2 一并列为阻塞；不以合成夹具代替。

### H1：旧议题证据复核矩阵

复核口径：HEAD 仍为 `0d023c78ad3fc8f9c5b89d50b51061e841b13832`，下列实现与回归均在本机工作树
（未提交）上实跑；「证据」列给出代码入口与直接断言该行为的测试，不把 issue 标题或上轮记录当证据。
两批定向执行：批一 `test_import/quality_evidence/provenance/build/ingest/qa/notes/safe_repair/
fingerprint/preprocess/cover/layout/source_evidence` → **324 passed（97.40s）**；
批二 `test_review_ledger/collected_notes_advisory/field_quality_followup/notes_media_gate/
notes_render_modes` → **119 passed（31.45s）**。

| Issue | 当前实现证据 | 回归/产物证据 | 剩余实书事项 |
|---|---|---|---|
| #77 | `import` 以 `source_sha256`+产物摘要登记；`status.stale` 报 `content_changed_since_import` | `test_import.py::test_import_completed_changed_products_are_not_silent_success`（`E_STATE_DRIFT` + CLI 文本） | 真实工作区改稿后的重登记仍属 H2 |
| #80 | `ArtifactContractError` 结构化出口，catalog/repairs 逐行定位 | `test_cli.py::test_status_json_contract_error_is_structured`（两参数化）、`test_pipeline_json_missing_workspace_is_structured` | 无 |
| #79 | image→figure、blank 段与相对证据提示 | `test_build.py::test_cover_image_and_linear_no`、`test_ingest_code_preservation.py` 全套；ingest/build 指南已写边界 | 三书插图实际落位（H2） |
| #78 | `qa/report.py` 汇总 `review_findings`，与 ledger 同源 | `test_review_ledger.py` 全套（含 `E_REVIEW_PARENT_SELF` 贯通到 `status.review.findings`） | 无 |
| #73、#82 | 绝对页序与 PDF 派生清单 | `test_pdfexport.py`、`test_pdftoc.py`、`test_pdfdiagnostics.py` → **78 passed（328.24s）**；`pdf-verify` 对账入口 | 最终 PDF 页码与清单逐页核验（H2） |
| #74、#75 | 图版高度预算、封面身份优先 | `test_pdfexport.py` 图版预算组；`test_cover.py` 19 passed（含源封面优先） | 三书图版观感（H2） |
| #76 | XMP/派生清单出版、日期、rights 读回 | `test_fingerprint.py`（`rights` 非空仍输出、`brief` 保留声明） | 无 |
| #81 | 缩放/目录/import skip/JSON 分别有断言 | `test_pdfexport.py` 全套 + `test_import.py::test_import_completed_unchanged_reports_specific_skip` + `test_cli.py` JSON 契约组 | 现场缩放参数复验（H2） |
| #83 | 八项现场反馈已由 A–E 覆盖；评论补丁的两条退化路径不移植 | 见 A–G 各节；`test_pdftoc.py`/`test_toc_page.py` 覆盖目录落点与独立对账 | 现场版本目录复验（H2） |
| #72 | 九项提案对照 E1–E5 | `test_book_css.py`、`test_pdfexport.py` 字体/页眉/索引组 | 三书版式视觉（H2） |
| #71 | 默认版式与封面身份已有实现 | `test_cover.py`、`test_cover_hanze.py` 19 passed | 自动回退策略仍为独立决策，未实现 |
| #69、#64 | 18 类/扫描书逐子项仅到文档与规则层 | `test_source_evidence.py`、`test_layout.py` 通过；`lessons/` 记录判据 | 扫描书实书重构（H2），PR70 文档不等于验收 |
| #58 | 栏内顺序、索引孤页、跨页注尾判据在 `evidence layout` | `test_layout.py`（栏/缩进/块内分段/跨页候选 + bbox 持久化） | 仍需源图抽样（H2） |
| #57 | `safe_repair.py` 同组预检、回滚、幂等、恢复 | `test_safe_repair.py` 全套（含 I/O 失败回滚、中断后拒绝其他工作） | 外部脚本侧问题另列，不在本仓修复 |
| #34、#37 | `notes register` 分离登记门 + in-place `[^ref-*]` + 译文 notes 校验 | `test_notes.py` 全套（未绑定/未登记/未处置候选均阻断）、`test_notes_media_gate.py`、`test_collected_notes_advisory.py` | OCR 候选与旧书注释重建（H2） |
| #40 | SPDX 头、`producer`/指纹、离线不联网 | `test_fingerprint.py`（`producer` 与版本不推断） | PyPI 发布与许可证表述另列；不加部署追踪 |
| #41 | 衔接 10-14 旧总计划 | 本文件 §6 与 H2 阻塞项 | 历史书恢复验收（H2） |
| #84–#100 | A–G 各节实现与回归 | 见上；PDF 78、封面 19、归档 13、A–G 定向批次 | 三书成品验收统一归 H2 |

结论：H1 范围内没有发现需要新开修复的缺口——上轮已落地项在 HEAD+工作树上均有直接断言；
剩余未知全部是「需要真实工作区/源件」的实书事项，不用工具测试替代。

### H2：实书复验阻塞（当前）

- 计划要求的三本书 `global-marx-history-and-critique`、`marxism-and-medieval-studies`、
  `tamozhennaya-politika-rossii` 在本机 `find` 无工作区、无 `outbox`、无源件；
  用户亦未指定替代工作区路径。因此 H2 的登记/build/qa/pdf/交付审计全部无法执行。
- 阻塞判定依据是「材料不存在」，不是「测试未通过」；A3 的书名页恢复、D2 的目录观感、
  E 的版式视觉、G1 的封面观感都因此保持未验收状态，不写成已通过。
- 解除条件：用户给出三书工作区或源件路径（或明确以其他实书替代），随后在保全副本中逐本执行
  `import`→`build`→`qa`→`pdf`→`pdf-verify`→交付审计，并逐条核源。

### H3：文档与集成（已完成）

**全量回归**：`uv run --offline pytest -q` → **1268 passed, 3 skipped（830.35s / 13:50）**，
在最终代码树上执行（含 archive 守卫、封面地标、标点悬挂三项修复；此前 1265 passed 为中间树，已被本次取代）。三项 skip 逐条说明，不当成功计：

| skip | 原因 | 处置 |
|---|---|---|
| `test_external_tools_required.py` ×2 | 本地未设 `AUTO_EPUBLIZER_REQUIRE_EXTERNAL` | 已单独以 `=1` 执行 → **2 passed**（pandoc/java/epubcheck 真实存在） |
| `test_processing_tools.py::...RapidOCR` | 本机未装 `rapidocr`（`doctor` 同样报 false） | 扫描书 OCR 路径本机未验证，记为 unknown，不加装依赖、不写成功 |

**静态与文档门**：`ruff check .`、`ruff format --check .`（400 files）、`git diff --check`、
`scripts/i18n.py --check`、`--links` 全绿；`test_i18n.py` **12 passed**（文档改动后复跑）。

**真实 CLI/产物**（临时工作区，非实书）：
- `convert book.md` → EPUB 6451 B；`java -jar epubcheck.jar` → `0 fatals / 0 errors / 0 warnings`。
- `init` → `build`（3 单元缺译文按源文打包，未推进 built）→ `pdf`：3 页/3 节/3 书签、A5、
  `toc.converged=true rounds=1`、CJK 实际字体 `NotoSerifCJKsc-Regular 30 + Bold 9`；唯一告警
  `W_PDF_FONT_SAMPLE_UNKNOWN`（字号采样未知，advisory，不作成功）。
- `pdf-verify` → `ok: true`（schema/pdf_sha256/pdf_bytes/pdf_pages/epub_bytes 全通过）。
- `qa` → `G4 pass、epubcheck errors 0、G5 放行：是`；G0 告警 0、G1/G2 0、硬门全 0。
- `evidence toc`（`writes:false` + 节点/来源摘要）、`evidence layout`（Markdown 源空集正例）、
  `hygiene`（无译文单元 `units:[]`，`writes:false`）均按文档契约返回。

**行为/文档同步**：`AGENTS.zh.md`/`AGENTS.md` 工作流补 `align-propose`、`align-apply`、
`hygiene`、`archive`；`SKILL.zh.md`/`SKILL.md` 路由补归档、`build --toc-page`/`output.css`、
`evidence layout/toc`、重对齐与卫生扫描；`manifest.json` 补 `quality-evidence`；
`references/workflow.{zh.,}md` 同步归档守卫；`docs/configuration.zh.md` 删除与英文版矛盾的
“只有一套版式”陈旧段落（中文为权威源，英文已一致）。

**本轮新发现并修复的缺陷**（均为先失败回归）：
1. `archive` 对不存在的 outbox 返回空计划并退出 0，`--apply` 还会为不存在路径写 `.gitignore`；
   显式 `--docs` 缺失时静默跳过链接改写 → 现为中文 `ValueError` + 非零退出；`tests/test_archive.py`
   **15 passed**。
2. `docs/configuration.zh.md` 封面段落的“只有一套版式”与同文件/英文版冲突 → 删除陈旧段；
   i18n 全绿。
3. 真实书 EPUBCheck `OPF-096`：非线性封面文档无任何链接可达 → landmarks 增加
   `epub:type="cover"`；`test_build.py` **55 passed**。
4. 真实书 11 页 `E_PDF_OVERFLOW` 实为 CJK 收标点悬挂 → 新增 advisory
   `W_PDF_PUNCT_HANG`（≤0.62em）并保留更大悬出的 error；PDF 两套 **64 passed**。
   两项详见「H2（部分执行）」；指定三书仍缺，故 H2 未勾选。

**明确未完成/未验证**（不写成通过）：H2 三书实书验收（材料缺失）、真实 outbox 迁移（待授权）、
远端 issue/PR 状态更新（待授权）、阅读器视觉抽检（无桌面/阅读器记录）、扫描书 OCR 路径
（本机缺 RapidOCR）。

### H2（部分执行）：可用的真实工作区复验（指定三书仍缺）

指定三书（`global-marx-history-and-critique`、`marxism-and-medieval-studies`、
`tamozhennaya-politika-rossii`）仍不存在；但本机有**当前 schema**的真实工作区，故在
`/tmp/opencode/realbooks/` 的**保全副本**中执行只读/可重建验收，原件未改动：

| 工作区 | 规模 | 用途 |
|---|---|---|
| `~/work/translate/slave-labor-nazi-camps/book` | 33 单元、9.1 MB、已译已对齐 | 全文 QA/构建/PDF/证据/对齐提案 |
| `~/Downloads/forced-labour-and-extermination` | 36 单元、135 MB | 同上（未在本轮执行，留后续） |
| `~/Documents/机械制图国标/解析工作区/*` | 20 单元、转换路径 | 无译文路径（未在本轮执行） |

**真实书结果（nazi-slave-labor 副本）**：

1. **旧成品 vs 当前代码重建**：旧 EPUB `qa` → `toc_flat=true`、`epub_coverage=0.9986`、
   4 处 `E_EPUB_PARA_LOST`、EPUBCheck `OPF-096`；用当前代码 `build` 后 →
   `toc_flat=false`、`epub_coverage=1.0`、段落缺失消失、`provenance_coverage=1.0`。
   说明 D1（目录层级）与段落保真诊断在真实书上生效。
2. **确认缺陷 1：非线性封面不可达**。`cover.xhtml` 在 spine 为 `linear="no"`，landmarks 无
   `cover` 项 → EPUBCheck `OPF-096`（error）。修复：生成式/源封面单元在 landmarks 增加
   `epub:type="cover"` 条目（不污染正文、不改阅读顺序）；真实书重建后 `epubcheck errors=0`。
   回归：`tests/test_build.py::test_cover_landmark_makes_non_linear_cover_reachable`，
   `test_build.py` **55 passed**。
3. **确认缺陷 2：CJK 收标点悬挂被误判越界**。真实书 434 页 PDF 命中 11 处
   `E_PDF_OVERFLOW`，全部是单个 `）`/`〕` 悬出右边距 5–7 pt；诊断 `status=fail`。
   修复：仅当整段为收标点且悬出 ≤0.62em 时记 advisory `W_PDF_PUNCT_HANG`，其余（含正文
   文字或更大悬出）仍记 `E_PDF_OVERFLOW`。真实书重排后 `diagnostics.status=pass`、
   `overflow_count=0`、`W_PDF_PUNCT_HANG=11`。回归：
   `test_pdfdiagnostics.py::test_hanging_closing_punctuation_is_advisory_not_overflow`、
   `::test_punctuation_overflow_beyond_one_em_is_still_an_error`；PDF 两套测试 **64 passed**。
   中英 `build` 指南补充该码与阈值。
4. **PDF 与产物**：434 页 / 33 区段 / 164 书签，目录 `converged=true rounds=2`，A5；
   `pdf-verify` → `ok: true`（schema/hash/bytes/pages/epub_bytes 全过）。
5. **证据与提案（只读）**：`evidence layout` 98 页、15 个跨页候选、`body 609/quote 194/
   heading 43/indent 96/list 8`；`align-propose --unit ch07` 源 444 块 vs 译 440 块、
   逐块 proposal、`writes:false`；`hygiene` 全书只读、按单元计 findings、无改写。

**转换路径真实书（gbt-4458-1-2002 副本）**：`build`→`qa` → `released=true ok`、
epubcheck 0、`toc_flat=false`、`epub_coverage=1.0`；`pdf` → 35 页 / 20 区段 / 目录收敛 2 轮、
0 越界。**未解决**：PDF 正文实测 8.24 pt（请求 10.5，`E_PDF_FONT_SCALE`，`diagnostics.status=fail`）。
定位到「删除全部 `<img>` 后字号恢复 10.5」，说明与整页扫描图相关；`max-width`/`width`
多种 CSS 变体（`100%`、`116mm`、`section` 定宽）均未改变字号，根因尚未定位。
本轮不把该现象写成已修复，也不以 CSS 试错改动冒充修复（试改已回退）；留作独立议题。

**未完成（不冒充通过）**：该书 `qa` 仍 `released=false, reason=structure_open`——232 条
blocking 中 195 条为 `back-bibliography` 的 `language`（文献著录逐字保留）与 21 条附录、
7 条索引、1 条版权页同类命中，需按体例写 `preprocessing/style_exemptions.csv`（该书缺此文件）；
另有 5 条 `length_review` 与 2 条 `footnote` 需逐条核源人工裁决。这些是内容级审校，
不属于本轮代码修复，也不以工具跑绿代替。

## 7. 审查报告修复（2026-11-02）

审查复现的 4 项 P1、4 项 P2 逐项处理；每项先写失败回归再修。

| 项 | 缺陷 | 修复 | 回归证据 |
|---|---|---|---|
| P1 | 对齐事务报“已回滚”，但 publication 状态/摘要未恢复 | 事务日志记录每单元 `status_before`/`meta_before`；新增 `RunStore.restore_unit_registration`，失败时按快照原样恢复（含 `import_digests` 与 `align_structure` 的“原本不存在”） | `test_failure_during_registration_restores_state_and_digests`；`test_align_rebuild.py` **8 passed** |
| P1 | structured 源文缺失时重对齐仍登记成功 | `_unit_plan` 要求 structured 文件存在，缺失直接报“缺少结构化源文” | `test_missing_structured_source_blocks_registration` |
| P1 | 生成目录丢失原目录独有条目；明确错链仍 `released=true` | 生成侧把未被结构树覆盖的原目录条目保留为无链接 `toc-plain`；QA 期望树同步；provenance 新增 `E_TOC_SOURCE_LOST`、`E_TOC_BROKEN_LINK`（目标文档与 fragment 均校验），error 级阻断放行 | `test_source_only_toc_lines_are_preserved`、`test_broken_generated_toc_link_blocks_release`；`test_toc_page.py` **9 passed** |
| P1 | `.archive` 为符号链接时归档把批次移出 outbox | `plan_archive` 拒绝符号链接归档目录 | `test_symlinked_archive_dir_is_rejected`；`test_archive.py` **17 passed** |
| P2 | 多级子标题目录被压平 | `build_toc_tree` 用深度栈嵌套子标题 | `test_multi_level_subheadings_stay_nested` |
| P2 | 中文页眉实际输出圆点 | 页眉按文字选字体（CJK 用内置 `china-s`），测量与绘制同字体 | `test_cjk_running_head_is_not_dots`（修复前实际文本为 `··· ····`） |
| P2 | 改按书 CSS 后旧报告摘要不变 | `ConfigSnapshot.css` 记录最近构建的样式路径；`build` 登记；`artifacts_digest` 纳入路径与当前字节 | `test_book_css_change_invalidates_report` |
| P2 | 同版本同清单但产物字节不同未判冲突 | `Batch.artifacts_sha256`（除 MANIFEST 外全部文件）+ `same_version_different_artifacts` 冲突，整组不改 | `test_same_version_same_manifest_but_different_artifacts_conflicts` |

定向回归：provenance/qa/artifacts_digest/book_css/align_rebuild/archive/build/pdfdiagnostics
**195 passed（113.77s）**；toc_page **9 passed**；archive **17 passed**；align_rebuild **8 passed**。

全量回归：`uv run --offline pytest -q` → **1277 passed, 3 skipped（946.47s / 15:46）**；
skip 口径与 H3 相同（2 项 CI 外部工具门、1 项 RapidOCR 缺装），不重复计为通过。
文档：`skills/auto-epublizer/references/build.{zh.md,md}` 补充目录保留与两个阻断码；
i18n `--check`/`--links`、`ruff check`、`ruff format --check`（400 files）、`git diff --check` 全绿。

## 8. 复审 5 项缺口修复（2026-11-02 晚）

复审以 `5aee910` 为基线逐项复现，5 项均先写失败回归再修。

| 项 | 缺口 | 修复 | 回归证据 |
|---|---|---|---|
| R1 | 目录条目指向另一**真实章节**（链接存在）仍 `released=true` | provenance 把结构对账（`toc_entry_*`、`toc_count`、`toc_generated_missing`、`toc_no_links`）转为 error `E_TOC_MISMATCH`；压缩/缺页码仍 advisory | `test_wrong_but_existing_toc_target_blocks_release`（`released=false` + code） |
| R1 | 中断的 align 事务无恢复入口，`repair recover` 返回 `no_pending` | 新增 `_open_journals` / `assert_no_pending_align` / `recover_align_rebuild`；`repair recover` 聚合两类事务，新增 `align-apply --recover`；pending 时普通命令（含 `status`）停止 | `test_interrupted_transaction_is_recovered_from_journal`、`test_pending_transaction_blocks_new_apply`；CLI 实测：恢复后字节与 `reviewed` 状态回归、`status` 恢复 0 |
| R1 | 状态恢复失败仍写 `rolled_back` 并称“已回滚” | 统一 `_restore_journal`；任一步失败记 `rollback_incomplete` 并抛“回滚未完成”，恢复入口可重试 | `test_failed_state_restore_is_not_reported_as_rolled_back`（注入 record/restore 双故障 → incomplete；修复后 recover → rolled_back） |
| R1 | 同一计划成功后重试因旧 align 摘要退出 | 先算计划结果，再判 `already_applied`（对照表字节与基线均等于结果），之后才校验旧基线 | `test_retry_after_success_is_idempotent` |
| R2 | 保留条目直接输出归一化文本，`Edited by John Smith 2024` 空格与年份被吃掉 | 显示 `label` 与匹配 `key` 分离：只剥「连续引导点 + 页码」，词间空格/年份原样保留；QA 独立实现同样分离 | `test_preserved_toc_line_keeps_original_spacing_and_year` |

CLI 恢复语义：`align-apply --recover` 与 `repair recover` 在 `incomplete` 时以非零退出，
日志保持未决；重复恢复安全。中英 `translation` 指南已补充中断/恢复与幂等说明。

验证：定向 `test_align_rebuild/test_toc_page/test_provenance/test_qa/test_cli`
**129 passed（342.41s）**；全量 `uv run --offline pytest -q` → **1283 passed, 3 skipped
（948.16s / 15:48）**（skip 口径同前：2 项 CI 外部工具门 + 1 项 RapidOCR 缺装）；
`ruff check`、`ruff format --check`（400 files）、i18n `--check`/`--links`、
`git diff --check` 全绿。
