# Issue / PR 完整修复与验收交接方案（2026-11-03）

状态：**实施完成（2026-11-03）**。T0–T7、T9、T10 已落地并实跑验收；T6a 按需裁图延期（见 §8）；
T8 三书实书验收**材料缺失 blocked**；本轮改动未提交、未推送，未修改任何远端 issue/PR。

撰写时仅查询 GitHub、阅读源码/测试/历史记录并编写方案；实施阶段（2026-11-03）已按 §8 逐项
落地并实跑验收（全量 1300 passed / 1 skipped）。本文件是后续 agent 的增量执行入口，接续而不覆盖
[11-01 计划](2026-11-01-issue-pr-followup.md)、
[10-31 计划](2026-10-31-issue-pr-update.md)及
[10-14 总审查](2026-10-14-review-and-repair.md)的未决实书事项。
任务集中于本文，遵循本仓 `docs/plans/` 约定，不另建重复任务清单。

## 1. 基线、证据和结论

- 仓库：<https://github.com/Misaka0x26FE/auto-epublizer>。
- 本地 HEAD / GitHub main：`db20a42cbebf3f0481fa510b4c7883c1775b7253`。
- 已读取全状态 issue/PR 清单、开放 issue 正文及评论、历史集成记录和相关源码/测试。
- 当前开放 issue **38**，开放 PR **0**，历史 PR **17**（9 merged、8 closed 未标 merged）。
- 当前 HEAD 的远端 CI 为 success：<https://github.com/Misaka0x26FE/auto-epublizer/actions/runs/41412133657>。
- 旧计划记载当前提交全套 **1283 passed / 3 skipped**；这是历史验证记录，**不是本轮实跑结果**。
- 开始时工作树仅有未跟踪 `book/`。本轮未读取书稿，也不将该目录当作可覆盖的测试夹具。
- 本文源码行号对应上述 HEAD；实施前刷新 HEAD、issue/PR、工作树及适用目录规范。

**主要判断：开放状态不等于功能尚未实现。** `5aee910` 已落地大部分 11-01 任务，
`db20a42` 又修复目录错链放行、对齐事务恢复与幂等等问题。下一轮重点是剩余接口断点、
具体漏检边界、书版需求差异和实书闭环；不重新开发整套 notes、PDF、目录、align 或 archive。

证据级别：**源码确认**表示从当前控制流可直接定位；**待复现**表示有合理触发条件，须先建立
失败样本；**历史实测**引用旧记录，须在目标版本复验；**材料待补**不等于代码失败。

## 2. 当前实现的增量差异

| 编号 | 关联 | 当前证据与差异 | 执行处置 |
|---|---|---|---|
| F1 | #91/#57 | `template/work-root/docs/pack_outbox.py:74–81` 仅查顶层 batch；101–109 的清单只列文件/工作区/hash。`archive.py:101–117` 需要显式书身份/版本，且打包入口支持多书一批 | 源码确认协议未闭环；T1a 定义多书批次身份，T1b 接通模板与归档器 |
| F2 | #91 | `archive.py:159–181` 只校验最高版本 `same_top` 冲突；187–199 用 `(book,version)` 字典认已归档，未比较归档侧字节且同键可覆盖 | 待复现旧版本冲突和跨顶层/归档冲突；T1c 全版本、全位置核对 |
| F3 | #93/#85 | `hygiene.py:119–123` 扫所有拉丁词，未限制中文语境、未读术语缩写/强调节点；`_is_code` 只认反引号；`_TERMINAL` 无英文句点 | 源码确认负对照不足；T2a 按结构和语种限定检查 |
| F4 | #93/#57 | `hygiene.py:192–195` 吞掉 notes JSON 解析错误并当空对象；`--unit` 时完全跳过译注；引号统计仍包含行内代码 | 源码确认范围/错误可见性缺口；T2b 输出 coverage 与结构化错误，不以零 findings 表示全扫通过 |
| F5 | #86/#58 | `preprocess/layout.py:122–127` 要求大行距、句末标点、缩进同时成立；#86 报告的是常规行距下的段首缩进。57–79 过滤无 bbox 块后重新编号，字符范围只基于过滤后文本 | 待复现等行距缩进；明确 raw block 身份和 offset 基准，T3a/T3b |
| F6 | #96 | `pdfexport.py:_section_kind` 仅 index/cip；`stamp_folios:904–912` 对封面之外每页盖页码；没有部分页/图版角色参数 | 源码确认需求未全覆盖；T4a/T4b 做显式角色，不按单图猜用途 |
| F7 | #81/#74 | 11-01 计划 §H2 记录扫描图导致正文 10.5→8.24pt，去掉 img 才恢复；宽表分支已修但此分支未定位 | 历史实测未解决；T5 单独最小化和修复，不调低字号门 |
| F8 | #96/#98 | `_mark_cjk_emphasis:83–95` 把含任一汉字的整个 em/i 改成正体；当前测试只分开测中文 em 与拉丁 em | 待复现混合节点、已有 class 的结构问题；T4c 保留混合文字强调语义 |
| F9 | #72.1 | `preprocess/source_evidence.py:_registered_note_evidence` 已逐注输出位置、状态、hash；未输出裁剪图 | 定位能力已具备；T6a 明确按需渲染为独立补齐项，不重做 note 清单 |
| F10 | #72.2/#88 | `align_rebuild.py:_unit_plan` 接受当前 md 摘要并仅准备 align 路径；它不是同时编辑 md 的语义修复器。safe_repair 有显式权威层适配器，派生 chunk 不在其中 | T6b 写清 repair 与 align-apply 的分工、派生 chunk 失效/重建，禁止宣传任意四层同步已完成 |
| F11 | #81.4/#50 | 工作根模板 `AGENTS.md` 第5条仍说 build/qa/ledger/g0/import 不可盲加 JSON；当前 CLI 已有 JSON | 源码/文档确认过时；T0 同步模板、示例和版本化说明 |
| F12 | #72/#100/#40 | 禁止译法/固定复合词新 schema、外部 PNG 意象、源/生成封面自动回退、PyPI 发布仍无完整交付证据 | T9 给明确决策；不把未采用方案藏在“全部完成”中 |

上述是本轮计划的增量发现，不宣称已完成运行时复现。旧计划“H1 无新缺口”的结论仅适用于当时
覆盖的检查；本表给出了重新检查相关范围的具体依据。

## 3. 38 个开放 issue 全覆盖矩阵

编号指 `https://github.com/Misaka0x26FE/auto-epublizer/issues/<编号>`。
“已有”仅指代码能力，不自动等于现场书已修；T7 是当前版本再验收，T8 是独立实书任务。

| Issue | 当前处置 | 任务 / 关闭条件 |
|---|---|---|
| #34 | 已有稳定 ref_id、源注候选与成品门；OCR 上标证据仍需核源 | T6a/T7c/T8；上标/裸数字/误读候选及数学数字负例、丢引用真失败 |
| #37 | 已有 notes 登记和成品语义检查 | T7c/T8；有注零语义、部分遗漏、等量错配均挡住；历史书正确弹注/往返 |
| #40 | 已有 SPDX、producer、离线指纹 | T9/T10；核对许可证说明、来源不等于签名，PyPI 明确另议 |
| #41 | 总跟踪单 | T10；逐子项继承旧计划，不用新测试总数关闭历史书整改 |
| #57 | 已有 quality_evidence、safe_repair；外部自写脚本另有责任边界 | T1/T2b/T6b/T8；缺证 unknown、事务/副本对账及语义审校分别验收 |
| #58 | 已有 source/partition/breaks/layout 候选 | T3/T6a/T8；双栏姓名页码、跨页注尾和源 TOC 逐项有去向 |
| #64 | #60–63/#65 已解决；源注/OCR/索引待核 | T7c/T8/T10；8子项及两条口径逐项回写 |
| #69 | PR70 为经验，18项不等于全部代码修复 | T2/T3/T6/T8/T10；按 §4 的18项账本结案 |
| #71 | PDF 基准/封面身份已有；旧摘要次序说法过时 | T0/T7b/T9；明确 PDF 独立 manifest、回退策略不自动猜 |
| #72 | 部分提案已有，部分采用替代接口 | T6/T9/T10；九项分别决定，见 §4 |
| #73 | 已有目录绝对页序及锚点定位 | T7b/T8；最终 PDF 目录、书签、锚点页逐条精确相同 |
| #74 | 已有高度预算/单次绘图 | T4b/T5/T7b；两开本、长图注、合法重复引用及扫描图分支 |
| #75 | 已有非线性封面身份纳入 | T7b；确认封面仅一次、非封面附件不混入 |
| #76 | 已有完整 XMP 和派生清单 | T7b；直接读回 publisher/date/rights/译者，长字段不截断 |
| #77 | 已有内容摘要、状态回退、E_STATE_DRIFT | T7a；改源/改译/旧无摘要分别有真实 CLI 结果 |
| #78 | 已有 review_findings | T7a；自引用/缺父/环贯通 QA/report/status |
| #79 | 已有 image→figure、blank 和相对路径提示 | T7a/T0；kind×status 及缺证空白页负例，旧文件兼容 |
| #80 | 已有结构化可预期错误 | T7a；坏 catalog/repairs/工作区，stdout 单 JSON、非零退出 |
| #81 | 四项不得合并成“PDF 已修” | T5/T7a/T7b/T0；扫描图缩放、目录、import 跳过、JSON 分别验 |
| #82 | 绝对页序标准采用；顺序猜配建议不采用 | T7b/T0；未定位显式诊断，索引原页码单独披露 |
| #83 | 八项已有多项修复，评论旧补丁不直接移植 | T7a/T7b/T8；见 §4 分项对账 |
| #84 | 已有生成目录及 E_TOC_MISMATCH 等硬门 | T7d/T8；源独有行保全、错而存在目标阻断、实书目录可读 |
| #85 | 已有 hygiene/breaks；负对照与定位仍需补齐 | T2/T3/T8；半句候选可追源、合法诗/表/引文不乱报 |
| #86 | 已有行 bbox 与 layout；等行距缩进需补测 | T3/T8；只供候选，分段由 agent 核源，不按字数硬切 |
| #87 | 已有块身份基线与结构漂移门 | T7d；合法多句同段通过，无字变并段检出，旧无基线 unknown |
| #88 | 已有 align-propose/apply/recover | T6b/T7d；提案→审批→应用→恢复闭环，区分编辑 md 与重登记 |
| #89 | 已有引导点排除 | T7a；连续点页码负例、真注正例，保留源字节 |
| #90 | 已导出 coverage_missing/details | T7a；真实 QA JSON/文本能定位块及预览 |
| #91 | 归档事务已有；与模板打包缺闭环 | T1a–c/T8；同名已归档、混合批次、字节冲突、ignore/链接均验 |
| #92 | 已有 fragment→实际页，不猜章首页 | T7b/T8；无锚点待补结构证据，不接受 ±1 页 |
| #93 | hygiene 已有，但范围与负对照不完整 | T2a/b/T8；不以正则判断词义，覆盖正文和译注 |
| #94 | 三书综合报告 | T8/T10；十项工具+三书内容分别记录，不以 released 自证可读性 |
| #95 | 已有受限 output.css 且摘要绑定 | T7d；CSS 改后 stale，禁用规则/外部资源仍拦截 |
| #96 | 目录行/图版/CIP/索引/页眉已有；部分页等未齐 | T4a–c/T7b/T8；八项版式需求逐项实排 |
| #97 | 已有 titlepage/cover 保护与经验约束 | T7a/T8；书名副题保全，半书名页也核证，不把手工删除归咎 ingest |
| #98 | PDF 已拉丁优先；EPUB 按独立规范处理 | T4c/T7b/T9；撇号字形视觉与字体证据，EPUB 不私加具体字体 |
| #99 | 已有三遍收敛与旧件保全 | T7b；位数/目录换行改变分页，最终精确一致，未收敛不交付新件 |
| #100 | hanze-academic 已有 | T7e/T8/T9；长题名/署名/优先级实测，PNG 意象等未支持项明列 |

## 4. 汇总 issue 的子项账本

### #72 九项

1. 注释清单：保留已有全集定位；T6a 补按需图像及覆盖状态，OCR 命中仅排序。
2. 多层事务：保留 safe_repair；T6b 明确权威/派生层，chunk 重建和冲突检测另列。
3. 逐处术语例外：已有 seq/note_id/occurrence/hash；T7c 验同词其他位置仍报。
   “禁止译法+允许复合词”尚待 T9 决策，不以例外 CSV 冒充同等能力。
4. 页码策略：已有 original/product/none；T7d 验生成消费，T8 人工核表头与原版页码。
5. 制作信息：已有 brief，保留 rights；T7e 验重建不复活旧详表。
   “仅权利字段”是另一个提案，T9 明确是否采用。
6. 镜像索引：T0/T7a 核 doctor 和操作文档，不因环境索引改写 uv.lock。
7. 成熟工作根：现有 dry-run 与“默认不补顶层文件”非同一语义；T9 定默认策略，T0 写清。
8. 声明式忽略：已有 pattern|理由；T1/T7a 验非声明忽略失败、index 不变。
9. 实印疑误：继续用 corr:/repairs 记录；T7c/T8 验原件保全、源疑误与译误分列。

### #69 十八项

| 子项 | 归属与处置 |
|---|---|
| 1 完成态 import | T7a 验已有 force/漂移；不重做入口 |
| 2 失败=0但有术语硬缺陷 | T7a 保存版本/真实命令；现版复现才修，未复现保留证据不足 |
| 3 混入原语 | T2a + T8 语义复核 |
| 4 length 噪声 | T2b 复用结构化 flags 做按单元/check 聚合和排序，原阈值保留 |
| 5 OCR/断段/缺文 | T3 + T8 源图/邻页核证 |
| 6 双栏人物表 | T3b + T8，逐条姓名/职务/任期绑定 |
| 7 zip 凑 align | T6b + T7d，用显式映射，不补空行凑数 |
| 8 注释源全集 | T6a + T7c + T8，注册数不冒充源总数 |
| 9 比例分配尾注/通用补句 | T8 撤销错误生成策略并逐注重建，属书稿修复 |
| 10 注码上下文 | T7c，稳定 ref_id 与数学数字负例 |
| 11 公式/插图笼统说明 | T8 逐 bbox 看图裁定，未看保持 unresolved |
| 12 局部审校覆盖旧问题 | #68 已关闭；T7a 验 ledger 血缘，继承未结项 |
| 13 JPX 媒体 | T7e 先验证规范化/诊断实际能力，支持解码时真实转码并留身份，缺解码明确报错 |
| 14 标题回声删除 | T7a + T8，家具与书名页分开 |
| 15 CJK 空格/游离引号 | T2 + T8，逐处判定，不全局补标点 |
| 16 打包依赖/批次重复 | T1 + T0，当前模板不凭旧现场假定依赖 zhconv |
| 17 版本/tag/push | T10，只有获准发布后核远端；本轮不发布 |
| 18 审计假绿 | T8/T10，实际执行范围与 pass/fail/unknown/manual 对应 |

#64 的1–4项分别对应已关闭 #60–63；5对应 #46、6对应 #34/#37、7对应 #58、8对应 #65。
只做已有能力验收及历史书重建；两条附带口径分别由 T0（PDF 摘要）和 T7a（落盘术语态）处理。

#83 P1/P2/P3 → T7b 的目录结构、短标题、锚点；P4 → T5/T7b 的分正文/注文采样；
P5 → T2/T8 的 `.。` 全范围候选；P6 → T7a 的有据书目豁免；P7 → T7a 的标题跳级定位；
P8 → T0 的 PDF 独立清单。评论中的 `22a64a6` 仅提供场景，不移植数量相等顺配和章首回退。

## 5. PR 处置与防回归

PR 链接格式为 `https://github.com/Misaka0x26FE/auto-epublizer/pull/<编号>`。

| PR | 远端状态 / 吸收证据 | 后续动作 |
|---|---|---|
| #1 | MERGED，EPUB spine/表格 | T7 保留非线性资源、层级和表格回归 |
| #2 | MERGED，锚点/跨单元链接 | T7d 保留完整资源身份、fragment 与同名文件负例 |
| #7 | MERGED，Unicode 术语边界 | T7c，俄文短词不匹配长词内部 |
| #9 | MERGED，#8 现场集 | T7a 保留 build 源回退、import pending、媒体归一化 |
| #11 | CLOSED，评论确认 cherry-pick `bbef5a4/a6013f3/1ccf1bc` | RTL/词数/编号已吸收，不重开 |
| #15 | CLOSED，评论确认 `221edfc` 历史吸收 | 当前改用 `tests/test_synthetic_cases.py` 的合成波斯语回归；不恢复旧真实语料 fixture |
| #17 | CLOSED，评论确认 `e01a4d0…decf758` | 锚点/NCX/归类及额外加固均保留 |
| #27 | CLOSED，评论确认 `70165a5/c8e3a47/eaebb2c` | 还覆盖正文未列的 #28/#29；以当前 JSON/notes 契约验 |
| #42 | MERGED，历史加固见10-17计划 | 不恢复“Unicode 上标可抵销显式 ref 缺失”的旧建议 |
| #44 | MERGED，相对工作区摘要 | T7a 绝对/相对路径及实际 EPUB 字节绑定 |
| #45 | MERGED，注释分段 lesson | T6/T8 复用判据，不把经验文档当已完成书稿修复 |
| #51 | CLOSED；本地历史有 `eae80c0/406de54`，当前 production_toc_entry 存在 | T7e 核制作页目录与完整包身份；评论为空不推断未实现 |
| #52 | CLOSED；历史 `6a65147/f6ed57f`，当前 generation_tools 与 publication 渲染存在 | T7e 核未知/明确未使用及元数据；不重复合入旧分支 |
| #59 | MERGED，语言/图注/注释/证据契约 | T7a/c 保留坏样本端到端门；#57/#58 实书事项独立 |
| #66 | CLOSED，评论确认 `1f0c87f` 替代 | 单条编号段落与真正列表的双向回归 |
| #67 | CLOSED，评论确认 `1f0c87f` 重写吸收D1–D3 | T4/T5/T7b 修增量边界，保留安全解包/原子产物 |
| #70 | MERGED，18项经验文档 | 按 §4 分项验，不以 merged 关闭 #69 |

已关闭 issue 用作回归基线：#3–6、#8/#10/#12–14/#16、#18–26/#28–33、#35–36、
#38–39、#43/#46–50/#53–56/#60–63/#65/#68。若当前版本确有复现，单列新证据，
再由维护者决定补充原单或重开；状态标签本身不是通过证据。

## 6. 可交接任务卡

所有任务先读相应目录契约与匹配 skill；实现限确定性计算，语义裁定由 agent 完成。
每张卡通常2–5个实现/测试文件；超出时按契约/实现/接线/文档再分 PR。
下面命令供**实施 agent**运行；本轮不执行这些修复或验证任务。

### T0 — 基线与操作文档校正（P1，S/M，无前置）

- 范围：工作根 `AGENTS.md`、`references/work-root/workflow`、旧计划头部状态与索引。
- 动作：用当前 `--help` 核 JSON；区分 qa/g0 退出0与质量放行；PDF 只绑定自身 manifest；
  明确模板按当前版本适用，更新成熟工作根时先 diff 不覆盖本地规则。
- 验收：JSON 示例对当前 CLI 成功/失败均可解析；未执行项不勾选；历史计划头“未提交”与
  已存在 `5aee910/db20a42` 的关系有后续注记，H2 未决保留。
- 验证：`uv run pytest -q tests/test_cli.py tests/test_work_root.py tests/test_i18n.py`。

### T1 — 打包与归档闭环（P1，三张 M 卡；a→b→c）

- **T1a 契约**：统一可版本化的批次清单，记录 batch_id、逐书 source identity、version、
  artifact path/hash、report/PDF manifest 绑定；人读 Markdown 从同份数据导出。
  多书批次是整体搬运单元：仅当每本书在顶层都有经核验的更新交付时才可归档；混合新旧批次
  留待决，不拆目录或按某一本书最高版推断整批过时。旧 Markdown 可精确解析才迁移，否则 unresolved。
- **T1b 接线**：`archive.py`、模板 `pack_outbox.py` 与 `tests/test_archive.py/test_work_root_tools.py`。
  打包前检查顶层及 `.archive/<batch>`；已归档同名不新建；先全批核当前 report 和字节再复制。
  PDF 如纳入批次必须校验 `pdf-verify`，不从文件名猜已通过。
- **T1c 冲突**：按所有版本而非 same_top 比较，同版多位置多清单/字节冲突均列出；不字典覆盖。
  已存在目标即使不同目录名也要身份核验。应用前重验计划基线，保留现有恢复/ignore/链接事务。
- 验收：模板真实打包结果能被 archive 识别；多书混合批次不误归档；旧版本双副本冲突可见；
  顶层/归档同版异字节阻断；dry-run 零写入，故障整组恢复，重复应用幂等，产物 hash 恒定。
- 验证：`uv run pytest -q tests/test_archive.py tests/test_work_root_tools.py`；临时 Git 工作根
  补“打包→归档→同名再打包”真实子进程链，并检查链接及 `git check-ignore`。

### T2 — 卫生扫描范围与可信度（P2，a/b各 M，可与T1并行）

- **T2a** 范围 `hygiene.py`、共享 Markdown 解析、`test_hygiene.py`。复用 token 分类，支持两种
  围栏/行内代码；拉丁残词限定目标中文正文语境，括注/书名强调/有据术语缩写按检查类型处理。
  引号配对剔除代码；英文句点、列表、诗行、合法续引文有负例；半句候选记录下一块与可得页界证据。
- **T2b** 范围扫描器、CLI 结果与测试。坏 notes JSON/schema 显式报错；缺文件、跳过单元、
  未选译注和无 findings 分开；`--unit` 的译注范围经 source reference 确定，或显式说明未扫。
  统计 coverage/scope 与 findings，聚合大量 advisory 但保留完整详情；不改变原 length 硬软门。
- 验收：正常英文、代码、书目保留词不淹没候选；真正中文残词/重复/丢尾仍报；坏译注不是“0问题”；
  全程只读。词义、词性错误留人工，阈值800/1200等差异明示，不为追赶 issue 数字改阈值。
- 验证：`uv run pytest -q tests/test_hygiene.py tests/test_cli.py`；保存扫描前后文件摘要/mtime。

### T3 — 行版面证据与稳定定位（P1/P2，a→b，各 M）

- **T3a** `preprocess/layout.py`、`ingest/pdf_reader.py`、`tests/test_layout.py`：常规行距但段首
  x0 明显变化也给候选，保留 indent/gap/句末等独立证据，不强制三者同时成立。RTL 用阅读方向
  的对应边，列表/引文/悬挂缩进给反例；不自动重排正文。
- **T3b** 同模块及 `source_evidence`：保留原始 raw block index，缺 bbox 也有独立记录；
  `chars` 标明相对哪个冻结文本、是否含换行，并绑定 raw hash。只对实际相邻页出跨页候选，
  不从页1与页3拼续文；多栏最后/首块身份有明确证据，歧义为 unknown。
- 验收：#86 等行距夹具能定位候选；混有无坐标块不重编号冒充 raw；文本和顺序原样保全。
- 验证：`uv run pytest -q tests/test_layout.py tests/test_source_evidence.py tests/test_reading_order.py`；
  用合成多栏 PDF 读回 page/bbox/行序，实书正确分段留 T8。

### T4 — 书版 PDF 剩余需求（P2，a→b→c，每张 M）

- **T4a 角色契约**：从经确认的单元角色向 EPUB/PDF 传递 part/titlepage/plate/index/cip 等信息。
  旧无角色输入按普通章节保守处理；单图或标题关键词只可作候选。确定兼容字段后再接线，
  不先在多个层新增不同“角色真相”。范围：现有结构/meta、build、PDF Package，契约测试。
- **T4b 呈现**：`pdfexport.py` 和 PDF 测试；部分页居中/分隔，确认图版标题及图注同行策略，
  按角色抑制页眉/页脚；页码隐藏不改变绝对页序。长图注可续页且不重复绘图；现有正文页眉保留。
- **T4c 混合强调**：用 XML/token 节点处理而非重复 class 属性的字符串替换；
  `<em class="x">中文 Latin</em>` 中 CJK 正体强调、拉丁斜体保留，链接/嵌套/code 原结构守恒。
- 验收：#96 八项各有实排或明确取舍；至少 A5/32k，封面/部分页/图版/正文脚号符合角色；
  最终目录、书签、实际页序精确对账。
- 验证：`uv run pytest -q tests/test_pdfexport.py tests/test_pdftoc.py tests/test_pdfdiagnostics.py`；
  真实 Chromium + PyMuPDF 读回及页面图像检查，不能仅匹配 CSS 字符串。

### T5 — 扫描图触发整书缩放（P1，M，先于T4b集成）

- 范围 `pdfexport.py/pdfdiagnostics.py` 及对应测试；以旧计划8.24pt现象为线索，不预判 CSS 根因。
- 动作：合成同尺寸扫描图+正文；分别去图、去宽高/内联样式、替换包装/SVG，记录 print DOM
  实际宽度与 PDF span；二分到最小触发对象，再在资源/容器宽度拥有层最小修复。
- 验收：相同输入正文实测10.5pt在现行容差内，图/图注完整；纯图正文采样 unknown；
  宽表旧回归不退化；strict 失败保全旧PDF。未复现则交付最小化记录和材料缺口，不猜修。
- 验证：`uv run pytest -q tests/test_pdfexport.py tests/test_pdfdiagnostics.py`；记录浏览器版本、
  开本、CSS、字体、图像尺寸与输出hash。现场国标书需材料后在副本验证。

### T6 — 注释证据与修复职责（P1/P2，a/b独立，各 M）

- **T6a** 基于现有 `note_evidence` 按 note_id/源hash/page/bbox 按需渲染；先盘点已有页面渲染器，
  复用而不造第二套。定位查询维持只读，图像生成用显式选项/输出目录并报告写入，缓存绑定源hash、
  几何和渲染参数。没有 bbox 提供 page_only，缺源 unknown；每个多页 location 都有记录。
  范围 source_evidence/现有PDF渲染模块/CLI及测试，超过5文件先拆契约与接线。
- **T6b** 修复流程：语义改文由 approved repair 事务处理 md/align/notes；段边界重建由
  align-propose→agent批准 rows→align-apply；publication 由CLI登记。派生 chunk 显式失效后重建，
  不直接开放任意 preprocessing 路径写权限。补端到端示例、失败恢复和 pending 守卫矩阵。
- 验收：20注含坏OCR/跨页/缺坐标，清单不漏注且裁图不自动签审；事务支持重复恢复、
  rollback_incomplete 不伪报成功，派生重组不复活旧文，旧审校/report 正确失效。
- 验证：`uv run pytest -q tests/test_source_evidence.py tests/test_safe_repair.py tests/test_align_rebuild.py tests/test_align_proposal.py`。

### T7 — 已有实现再验收（P1，五个独立验收包，先复用现有测试）

仅在失败/确有遗漏时加最小回归和修复；不复制实现、不把历史测试数当当前执行结果。

| 包 | 用例重点 | 验证命令（`uv run pytest -q` 后接） |
|---|---|---|
| T7a 状态/CLI | source摘要回退、force、纯标题/源回退、review血缘、catalog错误、缺段定位、标题保护、引导点真注、术语状态 | `tests/test_import.py tests/test_restructure.py tests/test_cli.py tests/test_review_ledger.py tests/test_review.py tests/test_preprocess.py` |
| T7b PDF | fragment/同名/长目录/收敛/旧件保全、图版、封面、XMP、字号分组、PDF manifest与EPUB摘要隔离 | `tests/test_pdfexport.py tests/test_pdftoc.py tests/test_pdfdiagnostics.py` |
| T7c 注释/术语 | 零语义/部分遗漏/等量错配、跨文件回链、数学上标负例、逐处例外失效、未知源全集 | `tests/test_notes.py tests/test_notes_media_gate.py tests/test_glossary.py tests/test_source_evidence.py tests/test_synthetic_cases.py` |
| T7d 结构/目录 | 同文改段、合法多句同块、旧无基线；源目录独有行；真实但错误目标；CSS字节变stale | `tests/test_align_blocks.py tests/test_align_rebuild.py tests/test_toc_page.py tests/test_toc_model.py tests/test_book_css.py tests/test_artifacts_digest.py` |
| T7e 制作/媒体 | brief权利、null/[]模型、制作页目录、hanze封面/源封面优先、JPX真实编码与MIME | `tests/test_fingerprint.py tests/test_production_metadata.py tests/test_cover.py tests/test_cover_hanze.py tests/test_build.py` |

各包输出 issue→断言→当前提交→运行日志→未验证事项。#76 必须用 PDF XMP 读回测试，
不能用 fingerprint 的 rights 测试代替；#79 必须测 catalog 契约，不能用封面图片测试代替。
JPX 若仍未支持，先区分“明确错误提示”与“承诺自动转码”，由单独小任务完成所选接口。

### T8 — 三书与历史成品重建（P1，逐书独立；材料前置）

- 三书：`global-marx-history-and-critique`、`marxism-and-medieval-studies`、
  `tamozhennaya-politika-rossii`。实施阶段只在已知工作根/`Documents` 常用目录查过同名工作区，
  均不存在（未做全盘个人目录扫描）；结论为**材料缺失 blocked**，需用户提供工作区或源件。
- 历史注密集书/扫描书清单继承旧计划；同名/近名书需 source hash 核实，不替换验收对象。
- 输入：source/raw、publication、structured、translation/align/notes、reviews、旧成品及
  分发清单；缺哪件写哪件，只有 EPUB 不足以证明源注/翻译语义正确。
- 工作流：保全副本→全源分区/注释/结构盘点→agent逐处裁定→事务修复→必要 retranslation/
  review→CLI登记→build/qa→pdf --strict/pdf-verify→独立交付审计→获准后同步副本。
- 验收：目录全条目父子/目标/页序对账；每条注内容与来源去向全量核对；阅读器首中尾与
  高风险引用实点；正文首中尾/改动处/长段/跨页/公式图表重点读图。完整性全量、语义抽检
  的分母和样本范围分别记录，不以抽检宣称全书逐字审校。
- 每书交付 `reviews/delivery-<ts>.md`，含source/output hash、操作版本、旧新映射、
  pass/fail/unknown/manual、未决条目、阅读器结果、各副本一致性。材料不足保持 blocked。
- T1真实 outbox 迁移单列，执行前确认目标清单；本轮不迁移884MB历史产物。

### T9 — 未采用/待定提案的明确决定（P3，S；不阻塞无关修复）

推荐默认：逐处术语例外沿用现有机制，禁止译法/固定复合词先定义匹配语义和兼容迁移再另开任务；
封面 PNG 意象保留为显式本地资源扩展提案（源hash/尺寸/路径/署名均登记），不暗中下载素材；
不自动写伪造 align 封面行；源/生成封面回退维持显式确认；EPUB字体继续当前规范；
brief保留权利；成熟工作根默认行为如需改变须兼容迁移；PyPI单独批准后才做发布配置。
每项写“采用/替代/延期+理由+验收”，未获决定记 pending，不用整单关闭消失需求。

### T10 — 集成与结案交接（P1，M，依赖所有适用任务）

- 更新受影响中英 references、SKILL路由/manifest、AGENTS与模板；真实翻译后再 finalize。
- 全量一次：`uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、
  `uv run python scripts/i18n.py --check`、`uv run python scripts/i18n.py --links`、`git diff --check`。
- 外部工具严格组：`AUTO_EPUBLIZER_REQUIRE_EXTERNAL=1 uv run pytest -q tests/test_external_tools_required.py`。
  Chromium、EPUBCheck、OCR路径各有实际记录；skip不计通过，环境缺口不靠改阈值隐藏。
- 更新本计划任务状态和提交号，保留未决实书/决策；获准后才提交/推送/评论/关闭远端。
- 结案正文逐项含：原症状、采用/替代方案、实现提交、前后回归、实书结果或阻塞。
  汇总单只有所有子项已验或维护者明确接受延期时才整体关闭。

## 7. 顺序、职责与检查点

```text
T0 基线/文档 ─┬─ T1a契约 → T1b打包 → T1c冲突 ───────┐
              ├─ T2a/b扫描 ─────────────────────────┤
              ├─ T3a/b版面 ─────────────────────────┤
              ├─ T5缩放定位 → T4a/b/c书版 → T7b ────┤
              ├─ T6a/b证据/事务 → T7c/d ────────────┤→ T8逐书验收 → T10
              └─ T7a/e既有验收、T9提案决策 ─────────┘
```

- 一个集成负责人负责 cli.py、orchestrator.py、公共模型及文档协议；PDF任务共享文件顺序合入。
- 打包、卫生、版面可在独立 worktree 分工；前置契约先合入，再接消费者。
- **K1**：T0/T1/T6完成后检查协议、恢复和副本身份；**K2**：T2/T3/T7检查候选范围与硬门；
  **K3**：T4/T5/T7b检查实排；**K4**：T8逐书独立验收；**K5**：T10集成与远端证据。
- 任何实现者开工时读取技能目录并调用任务匹配 skill；本轮未分派子 agent。
- 接棒最小材料：本文、当前HEAD/dirty记录、对应 issue 正文、关联历史计划章节、该卡涉及源码/测试。

## 8. 实施登记表（执行方回填）

实施日期：2026-11-03。以下状态是本轮实跑结果，不引用旧计数代替。

| 任务 | 状态 | 交付证据 |
|---|---|---|
| T0 | 完成 | `template/work-root/AGENTS.md` 第5条改为按 `--help` 选 JSON（实测 `build`/`qa`/`ledger`/`g0`/`import`/`pdf` 有、`meta` 无）、退出 0 ≠ `released=true`、PDF 只与自身 `<pdf>.manifest.json` 对账；新增“模板按生成版本适用、升级先 diff”提醒。11-01 计划头部与计划索引回填 `5aee910`/`db20a42` 与 H2 blocked。`test_work_root`+`test_i18n` 15 passed。 |
| T1a/T1b/T1c | 完成 | 打包器写 `batch.json`（`auto-epublizer/batch/v1`：逐书 `book`/`version`/`source_sha256`/`artifacts[{path,sha256,bytes}]`/`report{sha256,released,released_reason}`/`pdf`，PDF 字段本轮为 `null`），`MANIFEST.md` 由同一数据导出并作为完成标记；拒绝同名已归档批次。归档器优先读 `batch.json`（缺 `MANIFEST.md` 记 `missing_manifest`），旧 Markdown 批次仍可解析；冲突核对**所有版本、顶层与 `.archive/` 两个位置**，身份按实际文件字节而非声明值；多书批次任一书仍为当前版本时整体 `held`，不拆目录。`test_archive.py` 20 passed、`test_work_root_tools.py` 20 passed。 |
| T2a/T2b | 完成 | 卫生扫描只在**中文语境**报拉丁残词，跳过引用片段/书名号内文；`~~~` 围栏与行内代码不参与引号配对；英文句点算终止标点；列表行不报半句/丢尾。`translation/notes.json` 解析失败改为结构化 `ValueError`（不再静默 0 问题）；`--unit` 按 `references[].unit` 只扫该单元引用的译注，输出 `coverage`（`units_scanned`/`units_skipped_kind`/`units_missing_translation`/`notes_scope`/`notes_scanned`/`notes_skipped`）。`test_hygiene.py` 13 passed，全程只读。 |
| T3a/T3b | 完成 | 段边界候选改为“等行距 + 首行缩进 + 上一行句末标点”即可成立，`evidence` 记录 `gap`/`indent`；新增 `raw_block`（原始块序号，过滤无坐标块后不重编号）、`chars_base=joined_block_text`、`chars_include_separator`、相邻块与跨页的 `with_raw_block`；跨页续段要求同栏。`test_layout.py` 10 passed，未改写任何文本。 |
| T4a/T4b/T4c | 完成（最小契约） | 单元角色经 `render_document(role=...)` → `<body data-aep-role="...">` 透传，PDF 读该属性生成 `role-*` class 并记入 `section_roles`；书名页/部分页按角色抑制页眉页脚（绝对页序不变），`section.role-part`/`role-titlepage` 居中且取消首行缩进。混合强调：纯 CJK `<em>/<i>` 转 `span.cjk-em` 并合并已有 class；混排节点保留 `<em>`，仅汉字段包 `cjk-em`，拉丁文仍为斜体。回归：`test_build.py::test_unit_role_is_carried_into_xhtml_body`、`test_pdfexport.py::test_titlepage_role_suppresses_header_and_folio`、`::test_mixed_script_emphasis_keeps_latin_italic_and_merges_class`。**未新增独立角色真相层**：角色来源仍是已确认的单元 `kind`，标题猜测只作兜底。 |
| T5 | 完成 | 两处根因均为 Chromium 收缩触发：①整页封面 `height` 超出可印高度 → `body > section.cover` 与 `section.cover` 加 `overflow: hidden`；②目录长引导点段落不可断行 → `p { overflow-wrap: anywhere }`。真实国标书（GB/T 4458.1-2002 副本）正文由 8.23pt 恢复 10.5pt、`diagnostics.status=pass`、`overflow_count=0`；另给文字字形 **0.2em 竖向**度量容差（水平仍 2pt）。回归：`test_pdfexport.py::test_full_page_cover_and_dot_leaders_do_not_shrink_body_text`、`test_pdfdiagnostics.py::test_font_metric_vertical_overshoot_is_tolerated`（9 passed）。 |
| T6a | **延期（未采纳本轮）** | 按需注释裁图需要页面几何基准与渲染接线（`structured/raw/pages/` 图与 PDF 页坐标对齐、裁切后登记与 QA 复算），属独立补齐项；本轮不做半成品，已在 `repair` 文档与本表登记，不作为已完成能力宣传。 |
| T6b | 完成 | `repair.zh.md`/`repair.md` 新增“修复职责分工”表：语义改文只走 `repair plan/apply`、边界重排只走 `align-propose/align-apply`、单元结构只走 `restructure`、状态只经 CLI、派生层由上游重建；并说明两种事务的未决日志守卫（`repair recover` / `align-apply --recover`）。i18n 双向校验通过。 |
| T7a–T7e | 完成 | 五个验收包实跑：149 passed（import/restructure/cli/review_ledger/review/preprocess）、85 passed（pdfexport/pdftoc/pdfdiagnostics）、145 passed（notes/notes_media_gate/glossary/source_evidence/synthetic_cases）、68 passed（align_blocks/align_rebuild/toc_page/toc_model/book_css/artifacts_digest）、100 passed（fingerprint/production_metadata/cover/cover_hanze/build）。合计 **547 passed**，无失败。 |
| T8 | **blocked** | `global-marx-history-and-critique`、`marxism-and-medieval-studies`、`tamozhennaya-politika-rossii` 三本书在本机无工作区、无源件，无法执行逐书重建与交付审计。**不以工具测试代替实书验收**；材料补齐后按 `delivery.md` 逐书独立复核（含副本 hash）。 |
| T9 | 完成（决定见 §9） | 10 项提案逐条给出“采用现状 / 延期 / 不采用”及理由；未获批准的延期项保持 pending，不以汇总单关闭代替决定。 |
| T10 | 完成 | 全量 `pytest -q`、外部工具门 `AUTO_EPUBLIZER_REQUIRE_EXTERNAL=1`、`ruff check`、`ruff format --check`、`i18n --check`/`--links`、`git diff --check` 见下行验收记录；计划与 `qa`/`workflow`/`repair` 中英文档同步。 |

### 验收记录（本轮实测）

- 全量：`AUTO_EPUBLIZER_REQUIRE_EXTERNAL=1 uv run --offline pytest -q` → **1300 passed, 1 skipped**
  （跳过项为 `test_processing_tools.py` 的“需要真实 RapidOCR”，本机未装；pandoc/epubcheck 走强制门，未跳过）。
- `ruff check .` 通过；`ruff format --check .` 401 files already formatted。
- i18n：`scripts/i18n.py --check` OK、`--links` OK。
- `git diff --check` 无空白错误。
- skip 口径：仅“本机缺 RapidOCR”一项环境性 skip 不计入通过数；`AUTO_EPUBLIZER_REQUIRE_EXTERNAL=1`
  下 pandoc/epubcheck 缺失会失败而非跳过；Chromium 相关 PDF 用例本机实际执行（85 passed 包）。

### 未决与未授权

- T8 三书实书验收：**材料缺失 blocked**，需提供工作区或源件。
- 真实 884MB outbox 迁移、远端 issue/PR 处置：本轮未获授权，未执行、未修改任何远端状态。
- 本轮改动尚未提交、未推送。

## 9. T9 提案决定（2026-11-03）

| 提案 | 决定 | 理由与验收 |
|---|---|---|
| 逐处术语例外（seq/note_id/occurrence/hash） | **采用现状** | 已有机制覆盖逐处豁免；同词其他位置仍报，T7c 复验 |
| 「禁止译法 / 允许固定复合词」新 schema | **延期** | 需先定义匹配语义（词边界、复合词优先级）与旧 CSV 兼容迁移，再单独立项 |
| 封面外部 PNG 意象 | **延期（显式本地扩展）** | 只接受工作区内登记资源（source hash/尺寸/路径/署名），不自动下载素材；未登记即报错 |
| 自动写 cover 单元 md/align | **不采用** | 生成封面走 `cover-generated.json` 登记与 build 接线；伪造 align 行违反逐句契约 |
| 源封面/生成封面自动回退 | **不采用自动回退** | 维持显式确认：`preprocessing/cover.json` 优先；生成封面必须显式跑 `cover` |
| EPUB 具体字体族 | **维持现状** | EPUB 主题保持 generic family；PDF 才做拉丁/CJK 具体回落 |
| `brief` 制作信息只保留权利字段 | **采用现状（brief 保留 rights）** | 现有 brief 已保留权利声明，不复活旧详表 |
| 成熟工作根「默认不补顶层文件」策略变更 | **维持现状 + 文档说明** | 模板已注明按版本 diff、不覆盖本地规则；改变默认行为需兼容迁移 |
| PyPI 发布配置 | **延期** | 需单独批准发布流程与许可证表述；本轮不配 |
| 环境索引改写 `uv.lock` | **不采用** | `doctor`/文档核对即可，镜像索引不改锁文件 |

每项未获批准前保持 pending，不以关闭汇总单代替决定。
