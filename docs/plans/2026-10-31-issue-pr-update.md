# Issue / PR 修复更新计划（2026-10-31）

状态：已完成（本仓代码/回归/文档范围）；S/C/P/Q/E/D 全部任务见 §7–§9，实书剩余项保留为 unknown。提交 `86c7f3c`、`c60c2e5`、`0a44632` 已推送 GitHub/Gitee；未改变远端 issue/PR 状态。

## 1. 基线与证据范围

- 仓库：<https://github.com/Misaka0x26FE/auto-epublizer>。
- 本地 HEAD 与查询时远端 main 均为 `bb419a7ce80ffc9ea828c868a6ad09f8d5bfdf43`。
- GitHub：21 个 open issue、0 个 open PR；全部 PR 列表共 18 项。读取开放 issue 正文及返回的评论，并核对近期关闭议题、历史 PR 和 CI。
- 最新 CI：`40997139621`，2026-10-30，success；此结果属于远端提交，不涵盖本地在途封面变更。
- 本地已有封面相关源码、测试、双语文档及计划索引修改，另有未跟踪文件。保留现状；本计划仅新增本文及索引条目。
- 定向基线：`uv run --offline pytest -q tests/test_restructure.py tests/test_review_ledger.py tests/test_pdfexport.py tests/test_artifacts_digest.py` → **54 passed，21.41s**。
- 实际执行 `build/qa/ledger --help`：三个命令均没有 `--json`。本轮未跑全套测试、未重排现场书稿，未验证 issue 中的实际书籍统计。
- 本计划沿用仓库 `docs/plans/` 约定，任务清单集中于本文；不另建 tasks/，不以新计划替换尚未完结的历史实书验收。

### 已核实的关键代码证据

| 问题 | 当前证据 | 判断 |
|---|---|---|
| #77 正文改后仍 built | `orchestrator.py:1796–1805` 仅比较路径、标题、层级、类型、区域、nav | 存在明确实现缺口；须补行为回归 |
| #80 status 错误协议 | `cli.py:178–181` 直接调用 status，无可预期错误捕获 | 错误出口缺口明确 |
| #79 清点类型 | `preprocess/artifacts.py:186–209` 枚举无 image/blank；相对证据错误见 153–155 行 | 契约扩展和提示改进 |
| #78 自引用 | `review/ledger.py:290–314` 已有缺父与 DFS 成环检查；`qa/report.py` 已有 inconsistent 字段 | 不能按“完全没有检测”重做；先复现字段丢失路径 |
| #75 封面 | `pdfexport.py:265–267` 跳过全部非线性 spine；366 行仍按文件名认封面 | 身份与选页需一起修 |
| #74 图版 / #81 缩放 | `pdfexport.py:81–115` 无普通图版高度预算，表格仅字号与 padding | 具备触发条件，实际分页须 Chromium 验证 |
| #76 元数据 | Package 仅 title/author；render 仅保留这两项 | 缺口明确 |
| #73/#82 目录页码 | render 只排一次，attach_outline 后写书签，未回填实体目录 | 缺口明确 |
| PDF 摘要口径 | `pdfexport.py:21–22`、`qa/artifacts.py:118` 起的摘要输入 | PDF 不因放进 output 就进入 EPUB QA 摘要；#64/#71/#82/#83 的旧经验不能照搬 |
| #83 书目相同 | `read_style_exemptions()` 已支持有体例依据的逐正则豁免 | 优先验证现有入口，不自动豁免所有外文书目 |

## 2. 全量议题与 PR 处置矩阵

以下编号均指本仓库；链接格式为 `https://github.com/Misaka0x26FE/auto-epublizer/issues/<编号>`。

| Issue | 优先级 / 任务 | 处理与关闭条件 |
|---|---|---|
| #77 | P1 / S1–S2 | 内容摘要、历史工作区迁移、漂移诊断和重新登记全链验证 |
| #80 | P1 / C1 | status/qa/ledger 等可预期错误均可解析、非零退出 |
| #78 | P1 / C2 | 自引用/缺父/环的错误到 report 和 CLI 全链可定位；如原报告不再复现，提供版本化证据 |
| #79 | P2 / C3 | kind/status 正交契约、空白证据、相对路径提示与文档 |
| #73 | P1 / P4–P5 | 实体目录页码与最终 PDF 落点一致 |
| #74 | P1 / P2 | 图版绘制不跨页重复，图注与图片保全 |
| #75 | P1 / P1 | 权威封面身份纳入 PDF，非线性附件不被全部纳入 |
| #76 | P2 / P6 | OPF 出版/日期/权利字段有明确 PDF 映射及读回证据 |
| #81 | P1 / P3–P5、S2、C4 | 四项分别验收：缩放、目录、import skip、JSON；不可只修 PDF 就整体关闭 |
| #82 | P1 / P4–P5、D1 | 接受绝对页序标准；匹配和失败策略经验证后固化 |
| #83 | P1/P2 / P3–P5、Q1–Q2、D1 | P1–P8 逐项标注修复/已有能力/文档纠正，非整单一键关闭 |
| #72 | P2 / E1–E5 | 九项提案拆分跟踪，先补证据与事务，再做输出偏好和工作根治理 |
| #71 | P2 / D1 | 经验更新：尺寸/字号/封面身份可保留，摘要次序错误须纠正 |
| #69 | P2 / E1、D2 | 18 项逐条映射已合入 PR70/既有门禁/待核证，真实书质量独立记账 |
| #64 | P2 / E1、D2、C4 | #60–#63/#65 已关闭，不重复实现；保留源注/OCR/索引证据及术语态提示 |
| #58 | P1 / E1、D2 | 多栏、源 TOC、跨页注尾全范围证据；实书回源另验 |
| #57 | P1 / E2、D2 | 复用现有 quality_evidence/safe_repair，补多权威层边界；不宣称机器完成语义审校 |
| #34 | P1 / E1、D2 | 源侧上标/OCR 候选与负对照，稳定 ref_id 守恒；不扩大正则冒充语义识别 |
| #37 | P1 / D2 | 已有 notes 注册/独立成品门需逐场景验收；有注零语义/部分遗漏持续阻断；历史书独立跟踪 |
| #40 | P3 / D2 | SPDX/指纹现已存在，核对剩余文档与发布提案；不新增遥测；PyPI 为独立决策 |
| #41 | 跟踪汇总 / D2 | 回写本计划与已完成代码证据，继续保留历史书缺源/未验项 |

### PR 核对

- **MERGED**：#1、#2、#7、#9、#42、#44、#45、#59、#70。作为既有实现和经验来源，不重复合并；#70 是经验文档，不代表 #69 的 18 项全部修完。
- **CLOSED、未标 merged**：#11、#15、#17、#27、#51、#52、#66、#67。按当前代码和历史集成计划核实是否被替代吸收，不能仅凭 CLOSED 判定未实现。#66/#67 对应功能已在 main，当前主要修后续边界。
- #82/#83 称有 `fix/pdf-toc-absolute-pages` PR：本次全部 PR 中未找到；`git ls-remote origin refs/heads/fix/pdf-toc-absolute-pages` 也无结果。实施前重新查询；拿到真实 PR/提交后先审 diff、测试与基线，不据文字承诺判为已交付。
- #50 已关闭但当前 build/qa/ledger 缺 JSON，列为**关闭状态与当前能力不一致**；实施阶段补证据评论或重新开启，不在本轮改远端。

## 3. 顺序、依赖与集成约束

推荐：**S1 → S2 → C1/C2 → P1 → P2/P3 → P4 → P5 → C3/C4/P6/Q1/Q2 → E → D**。

- 先修状态可信度与诊断，再修 PDF 页数相关问题；封面、图版、宽表修好后才冻结目录分页测试。
- C1 的错误协议先确定，C4 的 JSON 扩展复用它；不让各命令各造一套错误格式。
- PDF 任务共享 `pdfexport.py`，顺序集成；CLI 任务共享 `cli.py`，由同一集成序列处理。
- 封面在途工作按 `2026-10-31-generated-cover.md` 继续；本计划 PDF 只消费其登记/OPF 产物，不再实现第二个封面生成器。
- 每个任务先补失败回归，再做最小修改；测试用合成源件与临时工作区，不依赖现场私有书籍。
- 单项通常 2–5 个实现/测试文件，双语文档另作同步提交单元；超过范围即拆分，不顺手做架构大迁移。

## 4. 可执行任务清单

### S：状态与重新登记（首批）

- [x] **S1 内容身份与历史迁移（M）**
  - 在结构初始化/登记的共同边界记录源单元摘要；restructure 比较已持久化摘要与当前字节，不比较“已经被改过的两个当前文件”。
  - 旧工作区缺摘要标为 unknown，要求显式重登记/核验，不把新字节当历史基线悄悄认可。确定历史缓存有旧摘要时可验证复用。
  - 验收：同字段改正文回退 split；未变重跑保留状态；新/删/移单元行为正确；源注绑定、review/report 失效一致，失败不留下半份状态。
  - 文件：`orchestrator.py`、`auto_common/workspace/` 中摘要拥有者、`structure/` 登记入口、`tests/test_restructure.py`；具体存放模型由实现前调用链核对决定。
  - 验证：restructure/workspace/notes 受影响测试，真实 CLI 合成“built→改源→restructure→import→build→qa/status”链。
- [x] **S2 import 跳过可解释与漂移显式化（M，依赖 S1）**
  - 分开 `missing_rel_path`、`already_reviewed`、`already_built`、`content_changed`，输出具体单元及下一动作，新增结构化详情时保留旧消费者兼容。
  - 未变的批量重跑仍幂等；内容变化不以“失败=0”伪装已经重校验。明确 `--force` 是重验已写入的 md/align，不负责把私有 `.work` 文件组装成译稿。
  - 验收：未变 skip、变更后诊断、force 成功、force 失败回退均有真实 CLI 回归；status 给出对应 next_tasks。
  - 文件：`orchestrator.py`、`cli.py`、import/status 测试；文档 translation/workflow。

### C：错误诊断与机器协议

- [x] **C1 结构化可预期错误（M）**
  - `ArtifactContractError` 带稳定 code/artifact/line/field 信息；保留中文消息，不通过解析中文文本提取机器字段。
  - status 单本/多本及相关入口统一 JSON 错误出口，stdout 单一 JSON、进度走 stderr、退出非零；多本中坏工作区逐项可见，不悄悄过滤。
  - 验收：非法 catalog、repairs、结构路径、缺工作区、窄终端分别可解析且无 traceback；正常 JSON 结构保持兼容。
  - 文件：`preprocess/artifacts.py`、CLI 错误出口、`tests/test_cli.py`、status_all 相关测试；验证真实子进程。
- [x] **C2 审校血缘诊断贯通（M）**
  - 先构造 #78 完整 v2 自引用记录，经 ledger→report→qa→status 定位字段损失；已有 DFS 保留，增加明确自引用定位而非另写一套图算法。
  - 验收：自引用、两节点环、缺父、重复 id、输入摘要过期均阻断且带 review_id/path/原因；合法链通过。`import --reviewed` 的登记含义与 QA 全局验收分别说明。
  - 文件：`review/ledger.py`、`qa/report.py`、实际丢字段调用点、`tests/test_review_ledger.py`；验证真实 report 与 CLI，而非仅单测 ledger。
- [x] **C3 catalog 与证据路径契约（S/M，依赖 C1）**
  - 推荐增加 `kind=blank`；图像沿用 figure 并明确包含地图/整页图，可兼容 image 输入规范化为 figure。status 保持处置语义，不把 blank 同时当状态。
  - 空白页须有原页核证理由，OCR 空字符串不是“已核证空白”；included/excluded/absent/unresolved 的约束逐格列明。
  - 路径错误给工作区相对示例，保持越界和 symlink 限制。
  - 验收：旧 CSV 仍可读；blank 待核证仍阻断；坏值给合法集合；错前缀/缺文件/越界明确区分。
  - 文件：`preprocess/artifacts.py`、repair 测试、structure/preprocessing 中英指南。
- [x] **C4 JSON 覆盖与术语状态提示（拆为 C4a/C4b，各 M；依赖 C1/S2）**
  - C4a：build/qa/ledger 增 JSON，qa 字段与 report 对齐；明确命令运行失败与质量未放行的退出码契约，避免不经说明改变旧脚本行为。
  - C4b：import/g0 增 JSON；import 输出 imported/revalidated/pending/skipped/failed 及 reason，术语 seed/candidate/conflict/confirmed 统计来源明确。
  - 验收：成功、质量阻断、输入错误均可机器解析；文本默认保持；不再出现“文档要求 JSON，命令不支持”。
  - 文件：`cli.py`、各命令现有结果序列化、CLI/import 测试；运行各命令子进程 smoke。

### P：印刷 PDF（核心交付批次）

- [x] **P1 封面身份与页序（M）**
  - 按 OPF cover-image、landmarks/封面内容文档关系判身份，不采用 href 含 cover 的快捷补丁。明确只有图片登记、SVG 包装、非线性封面、封面重复引用的优先级。
  - 验收：确认封面只出现一次且在首页；普通非线性制作页/附件不误当封面；无封面首正文页仍按实际页序编号。
  - 文件：`pdfexport.py`、`tests/test_pdfexport.py`；与在途 cover 测试联验。检查实际绘图而非只查 spine。
- [x] **P2 图版和图注分页（M，依赖 P1）**
  - 高度从开本、边距、图注所需空间计算，不写死 A5 的 160mm；区分超长图注可续页和图片重复绘制。
  - 验收：A5/16k、竖图/横图、长图注/无图注、同图合法重复引用均正确；不裁切、不漏图注。
  - 文件：`pdfexport.py`、PDF 合成 fixture/测试；以 `get_image_info()`、绘制 bbox、页面渲染核对，不能仅数资源 xref（资源被共享不等于实际绘制）。
- [x] **P3 宽表与实际字号诊断（M；CSS 修复和诊断可拆两步）**
  - 约束表格宽度、单元格换行与长 token；不默认按列数任意缩表，保留可读性。对残余溢出给页码/对象定位。
  - 正文/注文分组统计字符加权字号分布；仅全书众数也会受注释占比影响，样本不足输出 unknown。新增 strict 的阈值、误差容限和退出语义写入契约。
  - 验收：13 列宽表不使整书 10.5pt 缩至约 8.6pt；大量纯注页不误报；纯图片页不编造字号；实测尺寸与目标相符。
  - 文件：`pdfexport.py`、PDF 测试、CLI 参数接线；真实 Chromium + PyMuPDF 验证。
- [x] **P4 实体目录映射（M，依赖 P1–P3）**
  - 分清机器 nav、源版式目录、索引；以完整 href#fragment 身份映射最终位置，为片段锚点建立可定位标记，不靠整页标题子串。
  - 支持段落、跨段题名、列表两类现场结构；先利用显式链接，再经无歧义标题/顺序校验。条目数相等本身不构成正确匹配证据。
  - 对 #82“保留旧页码”和 #73/#81“留空”的冲突作明确选择：拟默认显示未定位占位并给 finding，strict 阻断；若保留原版数字须明确标注原版页码，不能当作 PDF 页码发布。
  - 验收：短标题“序”、同名章节、重排 nav、相同数量错序、子节、跨目录路径均不误配；索引原版数字保持并披露口径。
  - 文件：PDF 目录映射领域模块（必要时从 `pdfexport.py` 内聚拆出）、PDF 测试；不改源 EPUB 和译文。
- [x] **P5 多遍排版收敛和原子交付（M，依赖 P4）**
  - 初排定位→回填→复排→重算；最多三次渲染（初排加两次修正），按目录映射摘要判断收敛，循环/未收敛记异常，strict 不交付新件。
  - 页码、页脚、书签统一取最终 PDF 的绝对页序。当前 render 在后处理前已替换目标文件，需把书签、元数据、诊断全部放到暂存件内完成后再原子替换。
  - 验收：页码位数改变引起目录换页仍正确；超时/后处理失败/不收敛保留旧 PDF 字节；标记清理不破坏图片和正文。
  - 文件：`pdfexport.py`、PDF 测试；故障注入 + 真实两遍分页验证。
- [x] **P6 出版元数据与派生件清单（M）**
  - OPF publisher/date/rights 原样保留到明确的 XMP 字段；标准 Info 的 title/author/subject/keywords 映射文档化，不把完整权利声明截断后冒称已保全，不把出版日期误作生成时间。
  - JSON 回传实写字段、源 EPUB hash、参数及 PDF hash；保持 PDF 不进入 EPUB QA 摘要，由交付 MANIFEST/审计绑定派生件。
  - 验收：Unicode、空字段、长 rights、多个作者及译者角色读回正确；改 PDF 字节不改变 EPUB report_state，但派生清单对账失败。
  - 文件：`pdfexport.py`、PDF/artifacts_digest 测试；build/delivery 指南同步。

### Q：成品诊断与体例

- [x] **Q1 标点候选与标题定位（拆为两个 S）**
  - `.。` 在正文、译注、书目、索引全范围报候选，附 unit/seq/note_id/上下文；不在 build 静默替换，保留代码、引文等负对照。
  - E_HEADING_SKIP 附 XHTML 文件、标题、锚点及可得行号；源码行号无映射时不捏造。给“核实层级后提升/补标题”的建议，不自动改稿。
  - 文件：`qa/audit.py`、quality_evidence 对应候选层、现有测试；验证成品侧和源定位。
- [x] **Q2 书目原文保留（S）**
  - 先复现 #83 P6 并验证既有 style_exemptions；补按块体例证据的示例。若小节定位不足，再复用结构化 token 的块身份扩展。
  - 验收：有凭据书目保留为 language_exempt advisory；同章复制正文仍阻断；空译文不豁免；体例变更使旧报告失效。
  - 文件：体例读取/G0 实际缺口、language/import 测试、translation/review 指南。

#### Q1/Q2 实施证据

- Q1：`audit_epub` 新增 `W_PUNCT_MIXED`，扫描最外层可见块（`p`/`li`/`dd`/`td`/`th`/`figcaption`），覆盖正文、注文（最近 `aside id`）、书目与索引；`pre`/`code`/`blockquote` 整段排除。`data` 带 `document/unit/seq/seq_end/note_id/block/match/context/seq_basis/advice`；seq 只在真实 `translation/align` 译文行覆盖段落时给出，缺失明确 unknown。QA 成员上下文现携带 align 行；build 不自动替换。
- Q1：`E_HEADING_SKIP` 现给出 XHTML 文件、标题文本、`id` 锚点、XHTML 行号（`line_scope=xhtml`）与建议；没有源行映射时不写 `source_line`。回归覆盖锚点/行号和候选的正文/注文命中、代码/引文负对照；`tests/test_qa.py` **35 passed**。
- Q2：复核既有 `style_exemptions.csv` + `language_exempt` 路径，无需新增宽松门。回归证明同一单元内书目块保留为 advisory（带 seq/reason），同章复制正文仍 blocking；空译文始终 blocking，不被体例正则豁免；体例/CSV 改动使摘要过期由既有测试覆盖。中英文 translation 指南补充按块示例。`tests/test_t12_gates.py` 定向 **4 passed**；QA/i18n 联合 **66 passed**。
- Q1/Q2 已同步 qa/translation 中英文文档并 finalize；未提交、未改远端。

### E：#72 与源证据后续（不塞入 PDF 热修）

- [x] **E1 注释全量证据清单（M；裁剪渲染再拆 M）**：以每条注册 note 的 source_locations 为全集，输出 note_id/page/bbox/证据状态；坏 OCR 只影响排序，不缩小范围。按 note_id 按需裁剪，保留多页续注；缺坐标明确 unknown。复用现有 source evidence 与 OCR 证据，不新增 LLM 调用。验证 20 注、拆散缩写、跨页尾部、多栏、无 bbox，证据生成不自动改审校通过状态。落点 `source_evidence`/notes 领域、CLI evidence、相关测试。关联 #34/#58/#64/#69/#72.1。
- [x] **E2 多层修复事务（先契约 M，再接线 M）**：审查 `safe_repair._allowed/_prepare/_validate_overlay`，区分权威层和派生 chunk；显式登记支持的 notes/chunk 适配器，不开放任意路径写。验证 dry-run 零写入、顺序 old→new、全量预检、摘要和证据绑定、中断回滚、重复应用可解释。落点 `safe_repair.py`、`tests/test_safe_repair.py` 及适配器，关联 #57/#72.2。
- [x] **E3 逐处术语例外（M + 接线 M）**：unit/seq/note_id、出现序号、文本摘要和证据共同定位；改稿后例外失效。先做命中/已豁免计数与全部调用方接线，再另定禁止译法/固定复合词 schema。测试同单元只有一处豁免、相同词其他位置仍报、notes 覆盖与摘要失效。关联 #72.3。
- [x] **E4 页码策略/源实印疑误（各 M）**：toc/index 声明 original/product/none，重复目录只报候选；复用 repairs 和 align 的 corr 先评估是否已可表达实印疑误，确需独立产物时才增 schema。验收源原件不变、保留与更正可区分、证据缺失不自动豁免。关联 #72.4/#72.9。
- [x] **E5 偏好与工作根治理（四个独立 S/M）**：制作信息详略仍保留权利声明；镜像索引诊断不改锁文件；成熟工作根 scaffold 增 dry-run/逐项预览并维持旧调用兼容；忽略清单须含理由且非声明缺失仍失败。每项独立 fixture/测试和决策，不把 #72 整单关闭。关联 #72.5–8。

#### E1–E5 实施证据

- E1：`evidence source` 新增 `note_evidence`，以注册 `structured/notes.json` 的每条 `source_locations` 为全集，逐位置输出 page/bbox/candidate_id/unit/line/status/raw_matches；缺坐标 `unknown`、无命中 `unmatched`、仅页 `page_only`，跨页续注保留全部位置并稳定排序。`--note-id` 可裁剪但返回总数与 `missing_note_ids`；证据读取前后 notes/publication 字节不变。20 注夹具（含缺 bbox、跨页、坏 OCR）通过。
- E2：`safe_repair` 引入显式 `RepairAdapter` 权威层登记（structured/translation md、align、source/translation notes.json）；`structured/raw/`、`preprocessing/` 等派生层明确拒绝。notes 适配器只允许完整注文文本变化，身份/位置/引用/顶层绑定守恒；同一文件多项替换按计划顺序链式预检，源注文改动与译注 `source_notes_sha256` 必须同事务对齐。回归覆盖 dry-run 零写入、派生拒绝、身份/位置拒绝、顺序替换、摘要绑定与重复应用。
- E3：`terminology_exemptions.csv` 扩展可选 `seq,note_id,occurrence,text_sha256,evidence`；定位行必须同时给摘要与证据，legacy 行仍按单元整词。G0 用真实 align 行与 `note_id` 匹配，按源/目标出现次数计算剩余缺失；单处豁免不掩盖同词其他位置，改稿后摘要不符报 `terminology_exempt_stale` 且术语门重新阻断。QA 增加 `g0_terminology_exempt/stale` 计数，import 三处调用统一走 rows。
- E4：新增 `preprocessing/page_numbers.csv`（`unit,policy,reason,evidence`；policy=original/product/none），`product` 无映射证据直接拒绝；`evidence page-numbers` 只读输出策略、页码候选、重复目录候选与源文件摘要，未声明不冒充 original，源件不变。源实印疑误继续用 align `corr:`/repairs 表达，未新增重复 schema。
- E5：制作信息新增 `detail=brief`，保留非空权利声明与软件许可声明，仅省略工具/修订明细；work-root 增 `--dry-run` 逐项预览且不创建目标；`check_tracked.py` 的允许文件改为 `pattern|理由`，旧 `--allow` 纯模式兼容，未声明忽略仍失败，并验证运行不改 `.git/index`、不产生 `index.lock`。
- 受影响定向：E1 **14 passed**、E2 **22 passed**、E3 glossary/related **143 passed**、E4 **4 passed**、E5 **31 passed**；随后并入全量。

### D：对账、文档与历史验收

- [x] **D1 同步操作契约**：按实际改动同步 `AGENTS.{md,zh.md}`、SKILL 路由/manifest、build/qa/delivery/structure/review/translation/workflow/quality-evidence 及任务卡。PDF 不进 EPUB 摘要、目录绝对页码、索引保留原页码、生成封面优先级均写清。经验放 lessons，不复制过时现场断言。
- [x] **D2 逐 issue 结案账本**：#34/#37/#40/#41/#57/#58/#64/#69 的既有实现、当前回归、剩余实书核证分列；先校验旧计划中的“已完成”，不把所有开放项重做。真实书缺源、未读图、未测阅读器逐项保留，不用 54 项测试通过代替。
- [x] **D3 发布收尾**：每个完成任务登记测试/CLI/产物证据和实际提交号；未来获准推送后再核 CI 并回写 issue。此次仅计划，不发布或关闭远端议题。

## 5. 检查点与统一验收

1. **状态检查点（S/C）**：内容变更可见，失败状态可恢复，机器输出稳定；每个已报问题有失败前/修复后证据。
2. **PDF 检查点（P）**：至少两种开本，封面、图版、宽表、长注、目录、索引合成书实排；独立读取最终 PDF 校验尺寸/字体/绘图/目录落点/XMP，人工看封面、正文、表格、图注、目录页。
3. **协议检查点（E）**：权威层修改有事务，候选与语义裁定明确分离，所有摘要失效和重复运行路径均验证。
4. **集成检查点**：受影响测试后执行 `uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run python scripts/i18n.py --check`、`--links`、`git diff --check`。中文修改须实际翻译英文后 finalize，不仅改戳。
5. 外部工具环境须真实执行 Chromium/PyMuPDF、pandoc、Java/EPUBCheck 相关验收；缺工具记录具体未验证项，普通单测通过不替代真实排版。

## 6. 风险与尚待确认项

| 风险 | 处理 |
|---|---|
| 旧工作区没有“修改前摘要” | 显式 unknown/迁移，不伪造旧基线、不自动认可当前完成态 |
| 目录格式多样且无可靠链接 | 身份优先、歧义可见；禁止仅按同数量顺序配对 |
| 字号众数被脚注占比带偏 | 分正文/注释类别，样本不足输出 unknown |
| PDF 变更与封面在途改动冲突 | 复用登记契约，分文件/提交单元集成，保留原改动 |
| 旧关闭议题仍缺功能 | 用当前 CLI 与回归证据重开/补充，不依据状态标签推断 |
| 外部“已修 PR”尚未出现 | 实施前复查 PR URL/提交；没有证据前按待实现安排 |
| 开放汇总 issue 含多项和实书人工任务 | 子项验收矩阵分别关闭，工具完成不掩盖实书未完 |

预估实施批次（非承诺工期）：状态/协议 2–3 批，PDF 3–4 批，诊断/文档 1–2 批，E 系列按独立小提案再排。首个可交付里程碑为 S1/S2/C1/C2；第二个为 P1–P5 的实排验证；其后再扩展长期能力。

## 7. 实施证据（持续更新）

### S1/S2：内容摘要与导入漂移

- 初次新增两个 restructure 回归在原实现 **2 failed**：同结构字段正文变化和旧 built 缺摘要均未回退。修复后初始化登记 `structured_sha256`；restructure 按正文摘要与结构字段共同比较，旧无摘要保守回退并建立新基线。
- 新增两个 import 回归在原实现 **2 failed**：改译稿仍 skipped 成功，且缺少 skip 详情。成功导入现登记三层 `import_digests`，完成态内容漂移返回 `E_STATE_DRIFT` 并让 CLI 非零退出；未变保留幂等，缺旧摘要明确 unknown。
- `status` 增 `content_state/content_digests`；next_tasks 对源改动路由 restructure，对译文改动路由 import --force；保留旧 skipped id 列表并新增 skipped_details。
- 已同步 structure/translation 的中英文说明并 finalize；CLI 明示 force 只重验 md/align，不组装用户自建中间文件。
- 最新定向：`uv run --offline pytest -q tests/test_import.py tests/test_restructure.py tests/test_status_next_tasks.py tests/test_workspace.py tests/test_cli.py tests/test_i18n.py tests/test_architecture_boundaries.py` → **96 passed，50.13s**。包含 CLI 漂移非零退出、force 失败回退、两类 next_tasks 和架构约束。
- `ruff check .`、i18n `--check`、`git diff --check` 通过；`ruff format --check .` → **364 files already formatted**。
- 当前未提交；全套验证和其余 C/P/Q/E/D 任务继续，不将首批完成等同全目标完成。

### 全量检查点与 C1–C4 实施进展

- S 批次全套：`uv run --offline pytest -q` → **1049 passed，3 skipped，271.61s**。跳过项仍需集成验收时单独核对；结果包含原有封面在途代码，不替代其独立验收。
- C1 新增 4 项契约/缺工作区回归先 **4 failed**；status/ledger 现统一错误 JSON 和非零退出，catalog/repairs 校验点提供稳定 artifact/line/field，非中文消息反解析。多本总览保留坏工作区；损坏 publication 曾被静默过滤，新增回归先失败后修复为错误行。
- C4 新增管线 JSON 回归先 **5 failed**；build/qa/ledger/import/g0 现支持 --json，并统一输入错误出口。保持 qa/g0 原有“命令运行成功”退出语义，放行必须看 released/flags。术语落盘状态计数回归先失败，现从 analysis/glossary.csv 读回并明确 status_source。
- C2 完整自引用 qa CLI 合成回归证实：当前主线已有非空 review_inconsistent，现场“空数组”未在该样本复现；新增具体 finding 的断言先失败。现自引用/缺父/父次序/环/重复 id 有结构化代码、review_id、parent 与路径，并贯通 report/status/文本 qa；不把旧 DFS 重写成第二套规则。
- C3 图像/blank 及 evidence symlink 回归先 **2 failed**。现 image 规范化为 figure，blank 独立 kind 且须定位与核证理由，未决仍未决；evidence 相对路径示例明确并阻断 symlink 越界。
- 两轮定向分别 **75 passed**（review_ledger/import/CLI/status_all，82.30s）、**39 passed**（catalog/repair/status_next_tasks/status_all，59.63s）；其后新增损坏 publication 防漏场景，综合回归仍在运行，未提前标记 C 阶段完成。
- 真实子进程 smoke（`/tmp/opencode` 合成工作区、COLUMNS=20）：status/status --all/ledger 输出均可 JSON 解析，E_ARTIFACT_CONTRACT 行号 2、非零退出、stderr 无 traceback。
- 已实际同步 workflow/structure/review/SKILL 中英内容并 finalize。当前未提交，待综合回归确认后转 PDF 批次。

### C 阶段综合确认

初次综合命令受 120s 超时中断，未计为成功；改为 600s 后完成 **160 passed，145.02s**。ruff check/format（364 文件）、i18n --check/--links、git diff --check 均通过。C1–C4 已完成；没有变更远端 issue/PR。

### P1/P2：封面身份、路径与图版分页

- 三个身份回归先 **3 failed**：非线性封面丢失、discoveries.xhtml 普通章节因含 cover 而正文消失、只有封面图时少一页。现按 cover 地标/语义和登记图的精确资源身份确定，唯一封面前置；SVG 保留，非线性软件附件不混入。图像-only 登记形成虚拟印刷封面区段。
- 渲染回归又证实：100vh/嵌套封面让图像跨入后续章节；无封面时第一页也漏页脚号。改用毫米版面、条件首页边距与页码，封面留 0.5mm Chromium 取整余量；实际图片 bbox 不越纸边。
- 定位标记清理重叠图片的回归在 **重新加载 PyMuPDF 页面后**失败（旧 Page.get_image_info 有缓存，不能用旧页面对象自证）。现清理只移文字，不改底图像素/矢量图形。
- 路径回归覆盖百分号编码、带 # 文件名、容器 rootfile 越界及嵌套 OPF 的合法 ../兄弟资源。前两类缺陷先失败；现在以明确 archive_root 保持完整包内身份，URL 只解码一次并重编码，不用拒掉合法兄弟目录作捷径。
- 图版首轮 **5 failed**，804×1293 图确实被绘制两次。高度按开本/边距/图注计算，标题紧邻大图另留标题空间。覆盖 A5/16k、竖/横图、单次/多次合法引用、无图注、超长图注续页；实际绘制次数逐项对账，180 句图注在排除页脚后完整保留。

### P3：宽表、源绑定字号与严格检查

- 13 列表格回归先失败，实际正文 **7.0pt 而非 10.5pt**；strict 入口回归也先失败。现表格限制版心宽、单元格可换行、表内 p 继承表字号，不按列数静默缩字。
- 新增 `pdfdiagnostics.py`：由源 body/notes 段落前缀绑定实际 PDF span，按命中字数统计分组字号众数；同形歧义/不足/未匹配为 unknown，不拿全书中位数或全书众数猜正文。纸张、文字和栅格绘制 bbox 独立实测；避免 get_text dict 复制全部图片二进制。
- 已有合成对照证明注文占多数时正文 10.5pt 不误报、正文缩为 8.6pt 能识别；纯图、歧义文字不伪造实测。字号偏差 >5%、纸张偏差 >1pt、版心越界 >2pt 出 error；strict 在替换目标前检查，故障保留旧产品。输出含统计口径与具体 finding，不宣称替代图文语义/字形人工验收。
- 真实 Chromium → PDF → PyMuPDF → PNG 预览已查看：`/tmp/opencode/aep-pdf-checkpoint-knep1aby/`。A5 封面完整，13 列表格换行不丢列；正文请求/实测均 **10.5pt**，命中 98 字符，overflow=0；strict 通过。
- 最新综合：PDF/PDF diagnostics/cover/i18n/架构 **82 passed，133.85s**；ruff check、format（366 文件）、i18n --check/--links、git diff --check 全部通过。已同步 build/SKILL 中英说明。P4/P5/P6 与 Q/E/D 继续，尚未完整交付全目标。

### P4：目录绑定与多遍接线

- 新增 `pdftoc.py` 和 10 项纯回归：跨段标题、尾部章号保留、列表/作者强调、罗马页码、同名显式链接、同条数错序、缺目标/歧义、索引排除、转义文字、URL 身份。模块原缺失导致首次收集失败；后续转义与无原页码的缺目标回归先 **2 failed**，修复后通过。
- 匹配只用显式完整 href#fragment 或无歧义完整标签，不按相等条数或标题子串猜。分段标题 `Chapter 2` 的尾数字实证说明它可能是标题的一部分，故匹配成功前保留全部源文。
- 默认未定位条目保留源数字并在成品该条后明确 `[原版页码，未定位]`，同时返回 error；这落实了计划中“若保留原版数字必须明确标注”的约束，比对不明尾数字直接替换更能保全标题。strict 接入后将阻断此类未决项。
- PDF 包内路径/fragment 归一复用同一实现；literal # 文件名、Unicode/百分号与 fragment 分离，修正书签路径身份。当前联合 **61 passed，70.02s**（pdftoc/pdfexport/pdfdiagnostics/架构），ruff check 和 diff check 通过。
- 真实根因回归 `test_print_toc_and_bookmarks_use_final_fragment_pages_not_title_echoes` 在接线前 **2 failed**：目录仍为 999、书签用区段起始页。现在锚点注入到真实 `id` 之后，目录重写与书签都读最终渲染的绝对页；`document.get_toc()` 与目录文字逐条对账；源 EPUB 字节未改。
- 未定位/重号锚点明确 `E_PDF_ANCHOR_MISSING`/`E_PDF_ANCHOR_AMBIGUOUS`/`E_PDF_ANCHOR_UNLOCATED`；strict 目录未定位回归会保留旧 PDF。索引文档不会被当作目录（仅优先 `toc` 语义或完整目录标题）。
- P4 已完成并接入物理目录；证据见 §7。

### P5：多遍收敛、绝对页序与原子交付

- `render` 改为最多三遍：初排 → 回填 → 复排；按最终 PDF 页映射比较收敛，循环或第三遍仍变化报 `E_PDF_TOC_UNSTABLE`，旧 PDF 不变。回归用漂移页映射验证恰好三遍且字节保留。
- 页码、页脚、书签、元数据、诊断全部在暂存 `final.pdf` 完成后才同目录 `os.replace`；后处理故障注入回归确认旧产品字节不变。
- 定位标记改为按 EPUB 内容哈希派生唯一前缀（并对源文本碰撞追加 `X`），清理只按本次显式标记集合 redaction。`test_marker_like_source_text_survives_positioning_and_cleanup` 先失败（源文字 `AEPMARK0001` 被误擦），修复后正文/锚点字面量都保留。
- P5 已完成；真实两遍分页证据见 §7 的 Chromium 测试。

### P6：出版元数据与派生件清单

- OPF `publisher/date/rights/language/subject/description/identifier` 进入 XMP，作者与译者分列；Info 的 title/author/subject/keywords 映射明确，`CreationDate` 用生成时间而非出版日期。回归覆盖 Unicode、双作者、译者、长 rights 不截断、空字段不补造。
- 每次成功渲染写 `<pdf>.manifest.json`，含源 EPUB/PDF sha256、字节数、页数、参数、Info/XMP 读回、目录/诊断摘要；`pdf --json` 返回同份 `artifact`。`pdf-verify` 重算哈希，PDF 改动/清单损坏/源件缺失非零退出。
- 回归验证 PDF 改动使清单对账失败，而 `artifacts_digest` 在渲染 PDF/清单前后不变；PDF 仍不进 EPUB QA 摘要。
- P6 已完成；build 中英文指南已同步并 finalize。

## 8. D2 逐 issue 结案账本（只记录，不关闭远端）

| Issue | 既有实现 / 本轮落地 | 当前回归证据 | 剩余实书核证 |
|---|---|---|---|
| #34 源注/OCR 候选与注码守恒 | 守恒门、源注候选、逐处例外与 `note_evidence` 定位 | `test_notes.py`、`test_source_evidence.py`；候选不对应语义 | 真实扫描书的上标/OCR 误读仍需逐页核证 |
| #37 注释登记与成品门 | notes candidates/register/status、产品注文门、跨页位置保留 | `test_notes.py`、`test_notes_media_gate.py`；E1 20 注夹具 | 有注真书的零语义/部分遗漏仍需独立验收 |
| #40 来源可识别与许可 | SPDX/构建指纹/无遥测、`aep:` 元数据、派生 PDF 元数据 | `test_fingerprint.py`、`test_production_metadata.py` | PyPI 发布是独立决策，未做 |
| #41 跟踪汇总 | 本计划与历史计划对账，不重做已关闭项 | 计划表与提交号 | 仍需在获准推送后回写远端 |
| #57 审计假绿与安全修复 | quality_evidence 只读边界；safe_repair 权威/派生适配器、整组预检与回滚 | `test_quality_evidence.py`、`test_safe_repair.py`（22 passed） | 人工语义/音译正确性不由程序背书 |
| #58 多栏/源 TOC/跨页注尾 | `evidence source/partition/breaks/page-numbers` 保留栏、块、跨页与 TOC 候选 | `test_source_evidence.py`、`test_page_numbers.py` | 实书多栏与跨页注尾仍需回源逐项核证 |
| #64 源注/OCR/索引证据 | 源证据、注文清单、页码策略、术语命中/豁免计数 | 上述定向测试 + QA 计数 | 历史书缺源/未读图项继续保留 |
| #69 18 项映射 | 既有门禁/证据已覆盖的保持，不重复实现 | 分项回归与计划证据 | 真实书质量独立记账，不用测试数冒充 |

- 本表是**结案账本**，不改变任何远端 issue/PR 状态；未获用户另行授权前不推送、不评论、不关闭。
- “已完成”只指本仓代码/回归/文档范围；真实书缺源、未读图、未实测阅读器等仍按 unknown 保留。

## 9. D3 发布收尾记录

- 全量：`uv run --offline pytest -q` → **1134 passed, 3 skipped, 574.35s**（含真实 Chromium/PyMuPDF PDF、epubcheck 边界与所有新增回归）。
- 风格：`ruff check .` 通过；`ruff format --check .` → **372 files already formatted**；`i18n --check` / `--links` 通过；`git diff --check` 通过。
- 真实工具：Chromium headless 生成的 A5 PDF 已用 PyMuPDF 读回目录/书签/Info/XMP/图片 bbox，并查看 PNG 预览；`pdf-verify` 对篡改 PDF 返回非零；工作根 `check_tracked` 在真实 Git 仓库上验证不改 index、不产生锁文件。
- 运行环境：Python 3.13（uv 项目虚拟环境）、Chromium、PyMuPDF、Java/EPUBCheck 按本机可用性执行；未安装的外部阅读器仍记未实测。
- 剩余实书项：扫描书 OCR 语义、真实多栏/跨页注尾、历史工作区缺源、阅读器兼容性仍按 plan §8 的 unknown 保留，不用机械测试替代。
- 提交：`86c7f3c`（S/C/P1–P3 与首批文档）、`c60c2e5`（P4–P6/Q/E 与 D 收尾）；工作树无未提交代码，远端 issue/PR 未变更。
