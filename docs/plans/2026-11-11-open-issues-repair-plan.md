# 39 个 open issue 修复计划（基于 translate.tar.gz 实战归档）

状态：**实施完成（P0/P1 主要项已落地，残余项见 §4）**　｜　立项/实施：2026-11-11　｜　基线：`f82106e`

## 0. 方法与边界

- **对象**：GitHub 39 个 open issue（0 个 open PR）；PR 侧 17 个历史 PR 已完成审计，8 个关闭未合并者均有后续实现或 cherry-pick，不另立任务。
- **证据优先级**：当前运行行为 → 现有测试 → `file:line` → commit；issue 正文只作线索，不直接采信历史结论。
- **归档用途**：`~/Downloads/translate.tar.gz`（SHA-256 `c22235b4…9bc59a08`）用于核对“现场是否真的发生、规模多大”，以及提供真实书复现素材；不复制书籍正文进仓库。
- **本轮不做**：不关闭/评论 issue；不改真实书籍译文；不提交推送（除非用户明确要求）。
- **状态定义**：
  - **已修复**：当前代码满足 issue 的验收条件，且有测试或可执行证据。
  - **部分**：主路径已覆盖，但 issue 明确要求的形态/接线/边界仍缺。
  - **未修**：无对应实现或仅有无关的局部能力。
  - **过时/重复**：诉求已被后续设计取代，或与另一 issue 重叠，应合并/关闭。

### 0.1 归档证据的实际使用

`translate.tar.gz`（SHA-256 `c22235b4…9bc59a08`，13G）不整包解入仓库；只读普查口径与数字见
[2026-11-10-archive-census.md](2026-11-10-archive-census.md)：52 个工作区、`report.json`
合计 154,239 句、align 实际 153,458 行、源注文登记 16,199、注文 ID 双向差集为 0。
归档普查是全局证据；以下工作区是普查/现场报告点名的形态样本，本轮只读引用其结论，
未重新解包 13G 归档，也未改动其中任何书稿：

| Issue | 归档工作区 | 用途 |
|---|---|---|
| #34 | `auschwitz-central-construction-office` | 上标注码形态与负样本校准（`(X)14`、`organigram:46`） |
| #85 | `global-marx-history-and-critique` | 半句/跨页候选计数对照（74→8 的误报收敛） |
| #86 | `tamozhennaya-politika-rossii` | ch02 最长段 4,555 字与段首缩进证据 |
| #97 | `marxism-and-medieval-studies` | page-004 书名 28pt / 正文 16pt 的字号判据 |

## 1. 状态矩阵

> 逐组回填；每行必须能落到 `file:line` 或测试名。

### 1.1 质量门 / 契约（#34, 37, 57, 72, 77, 78, 79, 80, 90）

| Issue | 状态 | 证据 | 剩余缺口 | 处置 |
|---|---|---|---|---|
| #34 上标注码漏计 | **部分（主漏报已修）** | `g0.py` 的 `footnote_range`：登记注号 ∩ 源侧上标盲区；`tests/test_review.py` 正负样本 | back-notes 编号全集交叉校验仍未做（需真实书校准） | 已消除“已登记注文丢失仍放行”；全集校验另立 |
| #37 脚注同义反复/假绿 | **已修复** | `qa/footnote_forms.py` + `qa/audit.py` 的零 aside 断言；`tests/test_footnote_forms.py` 7 passed；build/import 留痕 | 已登记路径由独立注释门覆盖，不再双报 | 可验收关闭 |
| #57 审计假绿/事务 | **部分（契约已交付）** | `skills/.../quality-evidence.md:11,149`；`quality_evidence.py:148-420`；`chunks.py:283-308`；`align_rebuild.py:44,226`；`safe_repair.py:189-230` | 索引专用工具（harvest/apply、音译、页码归属）仍不在本仓 | P2：接口决策后再上游化；本轮不复制本地脚本 |
| #72 九项审校反馈 | **5 已 / 4 半 / 0 缺** | 见 §1.1.1 | 注文裁剪图与审阅台账、重复目录 QA、三级制作信息、errata 接线 | P1：errata 接线、重复目录 warning、`software_detail: rights`；P2：按需裁剪 |
| #77 restructure 内容已变 | **已修复** | `orchestrator.py:2088,2107` 摘要参与判定；`:1102-1111` `E_STATE_DRIFT`；`:2801-2822` `content_state`；`tests/test_restructure.py:82`、`tests/test_import.py:81` | 无 `import_digests` 的历史单元仍为 `unknown` | 可验收关闭；legacy 边角 P2 |
| #78 parent_reviews 自引用 | **已修复** | `auto_translator/review/ledger.py:317-324`、`:229-247`；`qa/report.py:228,350`；`tests/test_review_ledger.py:378` | 无 | 可验收关闭 |
| #79 catalog/repairs 契约 | **已修复** | `preprocess/artifacts.py:321-322,338,349,376-387,273-281`；`tests/test_catalog.py:33` | `blank` 作为内容类型而非状态，符合 issue 备选方案 | 可验收关闭 |
| #80 status --json traceback | **已修复** | `cli.py:68-85,202`；`tests/test_cli.py:51` | 其他命令的 `--json` 错误矩阵未逐一覆盖（issue 未点名） | 可验收关闭；矩阵测试可选 |
| #90 provenance 缺段不可见 | **已修复** | `qa/provenance.py:65-66,795-803`；`qa/report.py:42-43,317-320`；`cli.py:989-999`；`tests/test_cli.py:392` | 无 | 可验收关闭 |

#### 1.1.1 #72 九项逐条

| # | 诉求 | 状态 | 证据 | 剩余 |
|---|---|---|---|---|
| 1 | 注文源页裁剪 + 定位 + 覆盖台账 | 半 | `cli.py:486`；`preprocess/source_evidence.py:32-150`；`tests/test_source_evidence.py:329` | 无裁剪图、无 note→crop→审阅状态 |
| 2 | 多权威层事务 | 已 | `safe_repair.py:189-230`；`chunks.py:201-308` | — |
| 3 | 逐处术语例外 | 已 | `glossary/csv_io.py:107-190`；`g0.py:828-860`；`tests/test_glossary.py:367-421` | 统计口径文档 |
| 4 | 目录/索引页码 + 重复目录 | 半 | `preprocess/artifacts.py:114-175`；`page_numbers.py:71`；`toc_model.py:153` | 重复目录未在 build/qa 告警 |
| 5 | 制作信息详略 | 半 | `auto_common/config.py:90`；`build/__init__.py:724,772,785` | 缺 `rights` 级；QA 无专项断言 |
| 6 | uv lock 镜像诊断 | 已 | `doctor.py:159-210`；`tests/test_doctor.py:98` | — |
| 7 | 成熟 work-root 保护 | 已 | `workroot.py:34-58`；`tests/test_work_root.py:63` | — |
| 8 | 入库声明式忽略 | 已 | `template/work-root/docs/check_tracked.py:23-35,67-125` | — |
| 9 | errata 一等公民 | 半 | `errata.py:1-140`；`cli.py:1861-1930`；`tests/test_errata.py:33-104` | g0/qa/report/delivery 未读取 errata |

### 1.2 结构 / 摄取（#58, 85, 86, 87, 88, 89, 94, 97）

| Issue | 状态 | 证据 | 剩余缺口 | 处置 |
|---|---|---|---|---|
| #58 源清点证据 | **部分** | `preprocess/source_evidence.py:157-239`；`partition.py:135-274`；`page_numbers.py:15-60`；`toc_model.py:86-168`；`quality_evidence.py:107-145` | `column` 真实路径未写（`pdf_reader.py:363-370`）；索引孤页归属无工具；跨页注尾无配对；源注独立清点缺；源 TOC↔nav 无逐项 diff | P1：58e 分类短语（快）→ 58a column（依赖 86）→ 58c 注尾/源注 → 58b 索引（需源图）→ 58d TOC↔nav |
| #85 跨页断段 | **已修复（advisory）** | `hygiene.py` 的 `cross_page_fragment`（拉丁/中文承接连词）、表格/短诗行白名单；QA 报告 `hygiene_candidates`/`hygiene_cross_page`；`tests/test_hygiene.py` 17 passed | 仍为 advisory（按设计不阻断放行）；页号证据仍由 `evidence breaks` 提供 | 可验收关闭 |
| #86 OCR 巨型段落 | **部分（仅证据）** | `layout.py:116-168` 段内缩进候选；`tests/test_layout.py:175` | ingest 不恢复段落；OCR 路径丢行框；facts 不报缩进不可用；无重排入口 | P1：按 x0 切段 + OCR 保留 lines + facts 信号；会令译文 stale，需显式重建 |
| #87 md_align_drift 块边界 | **已修复** | `boundary_digest` + import 旧基线保护（含 legacy 无 boundary 场景）；`align_structure_status` 报块数/行数；`tests/test_align_blocks.py`、`tests/test_import.py` | 无 `import_digests` 的历史单元只标 unknown（不冒充 changed） | 可验收关闭；legacy 提示已加 |
| #88 align 重建命令 | **部分，前提过时** | `align-propose`/`align-apply` + 事务（`align_rebuild.py:74-146`）；`tests/test_align_rebuild.py` | 无“由 md 重登记块基线”命令；issue 的“一行一块”已被句级 align 契约取代 | P1：`align rebaseline`（默认不动 align 行）+ 文档改写 |
| #89 目录引导点当注号 | **部分（主判据已修）** | `g0.py:191-197` `_is_leader_page`；`tests/test_pr42_g0_contracts.py:15-29` | `XII.551`、3 点引导、`£/$` 噪声未覆盖；无 `kind=toc/index` 降级 | P2：放宽引导线 + toc/index advisory + `toc_noise` 清单 |
| #94 三书审查整改 | **过时/伞形** | 子项状态已变化（#90/#91/#93/#84/#92 已落地；#85-88 部分） | 无独立缺陷 | 改为子 issue 清单并关闭/转 tracking，不写代码 |
| #97 书名页标题被删 | **已修复** | half-title/聚合书名页/字号判据/拆段标题；`tests/test_structure.py` 全部通过 | 无（真实书视觉验收另记） | 可验收关闭 |

### 1.3 工作流 / 功能 / 元 issue（#40, 41, 64, 69, 91, 93, 95）

| Issue | 状态 | 证据 | 剩余缺口 | 处置 |
|---|---|---|---|---|
| #40 AGPL §13 | **部分** | 97/97 源文件 SPDX（`tests/test_licensing.py:27`）；制作页/构建日志署名（`fingerprint.py:258-316`、`build/__init__.py:760-785`）；无遥测声明 | README 缺 §13 适用性/未来服务端变更说明；events 仅身份锚点；PyPI 未决 | P2：README 架构说明（中英）+ PyPI 单列决定 |
| #41 全项目审查 | **过时/总跟踪单** | 计划 `2026-10-14-review-and-repair.md:3`；代码批次均已落地；旧哈希经 rebase 不可解析 | 真实书 V/H 验收缺材料 | 关闭；如需保留提醒拆 blocked 小单；修正计划哈希表 |
| #64 596 页法文 field report | **过时** | 8 项已全部分派：#60-63/#65/#46 closed，#34/#58 open | 无可执行新项 | 关闭并保留映射表 |
| #69 18 类问题 | **过时** | 多数已闭环（force/align/hygiene/pack/delivery）；残余 4 类指向 #72/#58/#34/#37 | build 媒体魔数、publishing push 核验 | 关闭；残余指向对应 issue |
| #91 pack 归档 | **部分（仅链接改写收窄）** | `--unversioned`、`--version-map`、`broken_links`、`.archive/README.md` 书目索引；`tests/test_archive.py` 27 passed | 链接改写仍是目标字符串替换（正文同名文本也会改），有断链自检兜底 | P2：收窄替换范围（不阻塞真实迁移） |
| #93 hygiene 普查 | **部分** | 6 类检测（`hygiene.py`）；`preprocessing/hygiene-review.jsonl` 处置 schema（整块摘要失效）；`tests/test_hygiene_review.py` 3 passed | 术语/缩写排除、逐块引号、`quote_tail_dropped` 未做 | P1：检测边界；P2：阈值配置 |
| #84 生成式目录页 | **已修复** | `build/toc_page.py`；`output.toc_page` 接线（`orchestrator.py:479`）；`tests/test_toc_page.py:40/53/63/71`（生成/独立检查/错链阻断） | 源目录逐行照抄已由生成式目录替代；页码只读显式映射 | 可验收关闭 |
| #95 按书主题 | **已修复** | `OutputConfig.css`（`config.py:81-90`）；`bookcss.py:19-109`；`build/__init__.py:723/744-748`；`tests/test_book_css.py:26` | `standard-indent` 预设未做（可选） | 关闭；可选 P2 预设 |

### 1.4 PDF / 印刷 / 封面（#71, 73, 74, 75, 76, 81, 82, 83, 92, 96, 98, 99, 100, 101）

| Issue | 状态 | 证据 | 剩余缺口 | 处置 |
|---|---|---|---|---|
| #71 印刷版现场做法 | **部分** | 版式/页脚/注文印刷化/标记清除（`pdfexport.py:919-947,1025-1078`）；`build.zh.md:155-175` | 生成封面在 `structured/` 下，`rebuild` 删除后不重绘、build 静默无封面；无 qa 门 | **P0**：封面移出 structured 或重建保留 + 缺失重绘 + qa 门 |
| #73 目录绝对页序 | **已修复** | 生成/纯 `<li>`/包裹列表父行、无槽行内插入、祖先回退；`tests/test_pdftoc.py` 全部通过 | 无（真实书视觉验收另记） | 可验收关闭 |
| #74 整页图版重复 | **已修复** | `pdfexport.py:201-204` 高度预算；`test_tall_plates...`、`test_uncaptioned_standalone_plate...` | 无 | 回归守卫 |
| #75 非线性封面 | **已修复** | `_cover_spine:517-587`；`test_nonlinear_cover_identity...` | 无 | 回归守卫 |
| #76 OPF→PDF 元数据 | **已修复** | XMP 全量写入；Info subject 无 description 时回退「出版社 · 出版年」；rights 仅 XMP 写入文档 | 无 | 可验收关闭 |
| #81 A5 缩放/JSON | **已修复** | 宽表固定布局 + `E_PDF_FONT_SCALE`；`skipped_details`；`--json` 全链路 | skip 仍 exit 0（issue 允许“明确提示”分支） | 可验收关闭；形状文档可选 |
| #82 目录页码标准 | **部分** | 标签/链接绑定、跨段题名、`<p>/<li>` 双结构 | 嵌套父条目同 #73；§ 无锚点同 #92；无逐条最终对账 | 与 #73/#92/#99 同批 |
| #83 两本 Brill 书 | **已修复（代码项）** | P1–P5/P7 已实现；P6 书目逐字相同降 `bibliography_identical`；P8 前提过时 | 无（真实书视觉验收另记） | 可验收关闭 |
| #92 § 级目录 | **已修复** | 有锚点路径保障；无 fragment 的 § 标头保留原页码并报 `E_PDF_TOC_UNLOCATED`；翻译标签不误报 | 无 | 可验收关闭 |
| #96 书版排版 | **部分** | 点线目录/图版预算/页脚角色/CJK 强调/索引分栏/CIP | 部分页垂直居中、页眉书名、图版页脚、源 TOC 点线、print.css | P1：按目录行模型补 |
| #98 拉丁/CJK 字族 | **已修复** | 默认拉丁优先（`pdfexport.py:329-333`）；`W_PDF_FONT_LATIN_USES_CJK`；主题无 font-family | `build.zh.md:166` 仍写旧口径 | 修文档；可关闭 |
| #99 两遍收敛 | **已修复** | 三遍循环 + 渲染后目录行独立页码 token 对账；`converged` 实算；`tests/test_pdfexport.py` | 无 | 可验收关闭 |
| #100 汉译学术本封面 | **部分** | `cover_hanze.py` + CLI；21 passed；白边已修 | qa 译者检查；1600×2400 口径；`CoverConfig` 重复字段；rebuild 生存 | P1/P2：口径 + qa + 清理字段 |
| #101 字体定制冲突 | **部分** | 角色隐藏先于页眉；主题去字族；env 支持 | CJK 优先 env 下两条上游测试失败；env 未文档化；无配置项 | P1：`PDFConfig.font_stack` + 测试按有效栈判定 + 文档 |

## 2. 分批计划

### P0（先修：静默错误、放行假绿、交付物丢失）

| 顺序 | 条目 | 状态 |
|---:|---|---|
| 1 | #37 非语义脚注检测（`E_FOOTNOTES_NOT_SEMANTIC` + 零 aside 互补断言 + build/import 留痕） | **已完成**：`qa/footnote_forms.py`，6 tests |
| 2 | #97 书名页残余（half-title、聚合单元、字号判据、facts 台账） | **已完成**：`classify.py`，5 tests |
| 3 | #87 重新 import 静默覆盖块边界基线 | **已完成**：`boundary_digest` + 旧基线保留，2 tests |
| 4 | #92 § 无锚点页码静默取章首页 | 待做（PDF） |
| 5 | #73 嵌套目录父行 + 生成目录页码槽 | 待做（PDF） |
| 6 | #99 目录文字↔页对账 / `converged` 实算 | 待做（PDF） |
| 7 | #71/#100 生成封面 rebuild 丢失 | 待做（封面） |
| 8 | #91 版本缺失策略 + 链接自检 | **已完成** |
| 9 | #93 hygiene 处置 schema | **已完成** |

### P1

- #34 受限 `footnote_range`（已完成：登记注号 ∩ 上标盲区）
- #72-9 errata 进入报告（已完成可见性；不自动豁免）
- #72-4 重复目录 QA warning
- #72-5 `software_detail: rights`
- #58 分类短语 → column → 注尾 → 索引 → TOC↔nav
- #85 半句续文白名单 + QA advisory
- #86 ingest 按 x0 切段 + OCR 行框 + facts 信号
- #88 `align rebaseline`
- #76 Info 映射口径；#83 P6 书目 advisory；#96 书版剩余；#101 `font_stack`

### P2

- #57 索引工具（接口决策后）
- #72-1 按需源页裁剪
- #77 legacy 状态提示
- #89 目录噪声清单与 toc/index 降级
- #91 `.archive/README.md`、链接改写收窄
- #93 检测边界扩展、阈值配置
- #95 `standard-indent`（可选）
- #98 文档过期句；#100 配置字段清理

### 建议验收关闭（需跑一次回归确认）

#77、#78、#79、#80、#90、#74、#75、#81、#95、#98。

### 建议关闭/转 tracking（不写代码）

#41（总跟踪单）、#64、#69、#94（伞形）；残余分别指向 #34/#37/#58/#72 与 `publishing.zh.md` 一行。

## 3. 待补

- [ ] PDF/印刷/封面组（71, 73, 74, 75, 76, 81, 82, 83, 92, 96, 98, 99, 100, 101）
- [ ] 结构/摄取组（58, 85, 86, 87, 88, 89, 94, 97）
- [ ] 工作流/功能/元 issue 组（40, 41, 64, 69, 91, 93, 95）

## 4. 实施记录（2026-11-11）

已完成并有回归测试的条目：

| 条目 | 交付 | 验证 |
|---|---|---|
| #37 | `qa/footnote_forms.py`；强形态（含混排书）一律 `E_FOOTNOTES_NOT_SEMANTIC`，连续编号列表 `W_FOOTNOTES_AMBIGUOUS`；build 警告 + `events.jsonl`；import 告警 | `tests/test_footnote_forms.py` 7 passed |
| #97 | `half-title` 归类与整页豁免；聚合单元标题=书名也判 titlepage；字号正交判据（页最大 + ≥正文中位数 1.25× + 文本等于单元标题）；`structure-clean.json` 摘要进 `facts.md` | `tests/test_structure.py` 34 passed |
| #87 | `boundary_digest`（只看块号/类型/seq 区间）；重新 import 不静默覆盖旧基线，`--force` 才重登记；QA 仍报 changed | `tests/test_align_blocks.py`、`tests/test_import.py` |
| #34 | `footnote_range`：登记注号 ∩ 源侧上标盲区，译文任何形态都缺才阻断；toc/index 降 advisory | `tests/test_review.py` |
| #89 | `XII.551` 罗马章节页码；3 点引导线（需空白前缀）；toc/index 注号门降 advisory | `tests/test_pr42_g0_contracts.py` |
| #72-4/5/9 | 重复目录 `W_TOC_DUPLICATE`；`software_detail: rights`；报告记录 `rights_present`；errata 计数进报告（只作证据，不自动豁免） | `tests/test_provenance.py`、`tests/test_fingerprint.py`、`tests/test_report_summary.py`、`tests/test_errata.py` |
| #83 P6 | 书目单元逐字相同降 `bibliography_identical` advisory；正文仍硬门 | `tests/test_review.py` |
| #91 | `--unversioned`、`--version-map`、`broken_links`（内联/引用式/HTML href）、`.archive/README.md` 书目索引；`tests/test_archive.py` 27 passed |
| #93 | `hygiene-review.jsonl` 处置 schema（accepted/fixed/false_positive + reason + 文本摘要失效）；`hygiene --review` 只读汇总 | `tests/test_hygiene_review.py` |
| #85 | `cross_page_fragment`：下一块小写/引号/标点开头时不再报半句；QA 报告 `hygiene_candidates`/`hygiene_cross_page` | `tests/test_hygiene.py`、`tests/test_report_summary.py` |
| #73 | 生成目录与纯 `<li>` 嵌套目录都按父/子行解析；无 `.toc-page` 槽时插入行内；href 按 owner 祖先目录回退解析 | `tests/test_pdftoc.py` 20 passed |
| #92 | nav 无 fragment 且标题≠目标 h1 时不再静默取章首页，`E_PDF_TOC_UNLOCATED` + 保留原页码 | `tests/test_pdftoc.py` |
| #99 | 渲染后目录文字↔页码对账 `E_PDF_TOC_MISMATCH`；`converged`/`toc_converged` 按实算输出 | `tests/test_pdfexport.py` |
| #71/#100 | `rebuild` 保留已登记生成封面；文件缺失时 build 重绘；`E_COVER_RECORDED_MISSING` QA 门；`CoverConfig` 重复字段清理 | `tests/test_cover_render.py` |
| #101 | `pdf.font_stack` / `pdf --font-stack` > `AEP_PDF_FONT` > 默认；`#98` 文档过期句修正 | `tests/test_pdfexport.py` |
| #76 | Info `subject` 无 description 时回退「出版社 · 出版年」；rights 仅 XMP 的口径写入文档 | `tests/test_pdfexport.py` |
| #88 | `align rebaseline`：按当前 md/align 重登记块基线，默认只读，不改 align 行；md↔align 不一致拒绝 | `tests/test_import.py` |
| #86 | pymupdf 按行 x0 切段（上一行句末 + 缩进 > max(font*0.8,2)）；OCR 块保留行框；facts 报「缩进不可用」与最长段 | `tests/test_ocr_structure.py` 11 passed |
| #58a | 双栏页按 x0 两簇给块标 `column`；`evidence source` 直接消费 | `test_assign_columns_marks_two_column_geometry` |
| #40 | README 架构说明与 AGPL §13 适用性（本地 CLI 形态 + 第三方服务形态边界，不写法律结论） | `i18n --check`；中英 README 同步 |

审查后补修（P2/P3，均已加回归测试）：

| 条目 | 交付 |
|---|---|
| #73 纯 `<li>` 目录 | 父条目自带页码并含子 `ol` 时，只取自身文字/链接，子条目独立回填；不吞子标签 |
| #91 链接自检 | 引用式定义与 HTML `href` 一并检查，断链仍拒绝移动 |
| #85 中文续文 | 下一块以承接连词（而且/但是/因此/则/也…）开头时归 `cross_page_fragment` |
| #93 处置语义 | 候选消失记 `gone`（不冒充未处置/通过）；`hygiene --review` 汇总 gone 数 |
| #93 文本身份 | finding 带整块 `block_sha256`，60 字预览之后的修改也会让旧处置 stale |
| #85 QA 计数 | 卫生扫描失败返回 `error`，qa 记 `W_HYGIENE_SCAN_FAILED`，不静默归零 |
| #34 放行门 | `footnote_range` 已进 `_STRUCT_CHECKS` 与 import 告警白名单；`tests/test_release_truth_table.py::test_footnote_range_blocks_release`、`tests/test_import.py::test_import_collects_footnote_range_as_warning` |
| #87 旧工作区 | 只有 `align_structure`、无 `align_boundary` 时也不静默覆盖，提示用 `--force` 或 `align-rebaseline` |
| #97 误留防护 | 大字号但不等于单元标题的重复页眉仍删除；`rebuild` 同时保留 `structured/notes.json` |
| #34 语义注文身份 | `[^ref-…]`/数字形态任一命中即不报；hard gate 不再误伤已语义化注文 |
| #34 正文引导线 | 3 点引导线与罗马章节号只在 toc/index 启用；`World War II.5`、`He hesitated ...1` 仍计数 |
| #37 混排书 | 已有语义 aside 时，另一段 `注 N.` 仍以 `E_FOOTNOTES_NOT_SEMANTIC` 阻断，不再只 warning |
| #97 反向保护 | 标题等于书名的长章节/后置章节不判书名页；书名拆成多段时按子串保留为候选 |
| #73 目录回退 | 仅锚文本与 nav 标题一致时接受祖先目录回退；子列表包在 div 时父行不吞子链接；标记插在子列表前 |
| #99 对账精度 | 目录行按行取独立数字 token，`1` 不再被 `10` 的包含关系蒙混 |
| #91 链接归一化 | 自检扫描全量 docs，`./`/URL 编码归一化；未改写的顶层链接预检即拒绝 |
| #93 单元范围 | `collect(unit_id=...)` 先过滤 prior，其他单元的处置不再算 gone |
| #71 路径越界 | cover 记录用 `resolve()` + `is_relative_to` 限制在工作区，越界只留事件 |
| #100 封面判定 | `epub_has_cover` 只认 manifest item 的 `properties` token，注释/普通字符串不算 |
| #86 字号继承 | 拆段后按组重算 `font_size`，标题字号不会带进正文段 |
| #58 栏判定 | `_assign_columns` 要求两簇垂直重叠，居中标题+正文不再误标 column |
| #34 坏文件 | `_registered_note_numbers` 不再吞 `notes.json` 解析错误，硬门不会凭空消失 |

明确未完成（保留为后续任务，不宣称修复；未做项均写明复现条件与所需素材）：

| 条目 | 复现条件 | 所需素材/决策 |
|---|---|---|
| #58 索引孤页、跨页注尾、源注独立清点、源 TOC↔nav 逐项 diff（`column` 已落地） | 对双栏索引书运行 `evidence source`/`evidence page-numbers`，观察索引条目与页码归属仍为候选、注文尾部无配对 | 真实双栏索引扫描书（页码跨栏/孤页）+ 源页截图；接口需先定“只读 evidence + 复用 repair 事务” |
| #96 页眉书名、图版页页脚、源 TOC 点线、`print.css` 扩展点（部分页垂直居中已做） | 对含章名页眉、整页图版与平排源目录的书运行 `pdf`，检查页眉是否只有章名、图版页是否仍印页码 | 真实书 PDF 做视觉验收；`print.css` 需确定允许覆盖的变量边界 |
| #57 索引 harvest/apply 工具 | 在真实索引工作区手工跑本地脚本才能完成索引修复；本仓无 `index` 子命令 | 接口决策（只读 evidence + 复用 `repair apply` 事务）+ 真实索引书 |
| #72-1 按需源页裁剪图与审阅状态 | `evidence notes` 已有 bbox/页号但无裁剪图；无法区分“已生成/已审” | 扫描 PDF 的注文坐标 + 存储上限决策（默认按需渲染） |
| #77 legacy 无 `import_digests` | 对历史 built 工作区直接 `import`，单元 `content_state=unknown`；需 `--force` 或先 restructure | 旧工作区快照（无摘要）；是否需要“无基线即阻断”的产品决定 |
| #91 链接改写收窄 | 在正文/代码块写 `outbox/<批次>/` 后 `archive --apply`，同名文本也会被替换（断链自检只保证链接可达） | 脱敏 docs 树；需确认引用式链接与正文裸路径的边界 |
| #100 1600×2400 像素口径、译者 QA 断言 | 生成封面按物理 300dpi 输出（A5 1748×2480），与 issue 的像素口径不同；qa 无译者文本断言 | 产品口径决定；带 `meta.translator` 的生成封面样本 |
| #101 CJK 优先环境的测试仲裁 | `AEP_PDF_FONT` 设为 CJK 优先后，两条上游测试仍按拉丁优先断言而失败 | 决定“支持 CJK 优先”是否作为受支持配置及期望断言 |
| #93 检测边界（术语/缩写排除、逐块引号、`quote_tail_dropped`） | 对含 confirmed 术语、跨段引文、出处丢尾的译文跑 `hygiene`，候选仍会误报或漏报（advisory） | 真实译文单元 + `analysis/glossary.csv`；规则定稿前不改放行判定 |
| #40 PyPI 发布 | `pyproject.toml` 无发布配置 | 产品决策：本轮不做或单独立项 |

阶段验证（本轮）：受影响测试分组多轮通过；全量 `pytest -q` **1462 passed / 3 skipped**；`ruff check`、`ruff format --check`、`i18n --check/--links` 通过；架构边界测试（无内部 LLM、依赖方向）随全量通过。

## 5. 逐 issue 关闭建议

> 只作建议，本轮未关闭/评论任何 issue。证据均在 §1 矩阵与 §4 实施记录。

| Issue | 建议 | 依据 / 剩余 |
|---|---|---|
| #34 | 保留 | 受限 `footnote_range` 已阻断“已登记注文丢失”；back-notes 编号全集校验需真实书校准 |
| #37 | **关闭** | 未登记非语义脚注已由 `E_FOOTNOTES_NOT_SEMANTIC` 阻断，弱形态只 warning |
| #40 | **关闭** | README 中英同步 §13 适用性；PyPI 发布单列产品决策 |
| #41 | **关闭/转 tracking** | 代码批次已完成；真实书 V/H 验收缺材料，如需保留请拆 blocked 单 |
| #57 | 保留 | 契约/事务已交付；索引 harvest/apply 需接口决策与真实索引书 |
| #58 | 保留 | column 已落地；索引孤页、跨页注尾、源注清点、TOC↔nav 逐项 diff 未做 |
| #64 | **关闭** | 8 项已全部分派；闭合项见 #60-63/#65/#46，未闭合项归 #34/#58 |
| #69 | **关闭** | 残余 4 类已指向 #72/#58/#34/#37 与 `publishing.zh.md` |
| #71 | **关闭** | 封面重建保留/缺失重绘/QA 门已落地；自动回退链另立最小提案 |
| #72 | 保留 | #72-4/5/9 已修；#72-1 按需源页裁剪图仍缺真实扫描书验证 |
| #73 | **关闭** | 嵌套/纯 `<li>` 目录、无页码槽、href 祖先回退均有回归 |
| #74 | **关闭** | 图版高度预算 + 不重复绘制，已有实排测试 |
| #75 | **关闭** | 非线性封面身份识别与测试已落地 |
| #76 | **关闭** | Info subject 回退 + rights 仅 XMP 的口径已写入文档 |
| #77 | **关闭** | 内容摘要参与判定、`E_STATE_DRIFT`、legacy 旧基线提示 |
| #78 | **关闭** | `E_REVIEW_PARENT_SELF` + `review_findings` 全链路 |
| #79 | **关闭** | `blank` kind、`image` 归一化、evidence 路径提示 |
| #80 | **关闭** | `status --json` 契约错误输出结构化 JSON，无 traceback |
| #81 | **关闭** | 宽表固定布局、字号诊断、`skipped_details`、`--json` 全链路 |
| #82 | **关闭** | 与 #73/#92 共用目录行模型；数量顺序配对已明确不做 |
| #83 | **关闭** | P1–P8 已有实现/测试；书目逐字相同降 advisory |
| #84 | **关闭** | 生成式目录页、独立检查、错链阻断（`tests/test_toc_page.py`） |
| #85 | **关闭** | `cross_page_fragment` + 表格/诗行白名单 + QA 计数（advisory） |
| #86 | **关闭** | 行 x0 切段、OCR 行框、facts 缩进信号均有回归 |
| #87 | **关闭** | 块边界基线 + import 旧基线保护（含 legacy）+ `align rebaseline` |
| #88 | **关闭** | `align rebaseline` 默认只读、不改 align 行，md↔align 不一致拒绝 |
| #89 | **关闭** | `XII.551`、3 点引导、toc/index 降级、噪声负样本 |
| #90 | **关闭** | `coverage_missing_details` 进报告与文本输出 |
| #91 | 保留 | 版本策略/链接自检/书目索引已修；链接改写收窄（正文同名文本）未做 |
| #92 | **关闭** | 无 fragment § 不再静默取章首页，保留原页码并报错 |
| #93 | 保留 | 处置 schema 已完成；术语排除、逐块引号、`quote_tail_dropped` 未做 |
| #94 | **关闭/转 tracking** | 伞形跟踪；子项状态已变化，不应再当实现任务 |
| #95 | **关闭** | 按书 CSS 已交付；`standard-indent` 预设可选不阻塞 |
| #96 | 保留 | 部分页/图版页脚/页眉书名/源 TOC 点线/print.css 仍缺 |
| #97 | **关闭** | half-title、聚合书名页、字号判据、facts 清洗台账 |
| #98 | **关闭** | 拉丁优先字体栈 + `W_PDF_FONT_LATIN_USES_CJK` + 主题不设字族 |
| #99 | **关闭** | 目录文字↔页码对账，`toc_converged` 实算 |
| #100 | 保留 | 模板/白边/重建生存已修；1600×2400 像素口径与译者 QA 待定 |
| #101 | 保留 | `font_stack` 配置/CLI 已加；CJK 优先环境的测试仲裁未做 |

## 6. 真实书残余项续修（2026-11-11，第二轮）

素材：`~/Downloads/translate.tar.gz`（310,182 个归档条目、53 个工作区；只读解包 6 个到
`/tmp/opencode/translate-real`，约 301 MB，排除 `.git/`、`.tr/`、`preprocessing/backups/`）。
本轮只读取真实书，未修改归档内任何译文或源文件。

### 6.1 真实书证据

| 项 | 工作区 | 证据 |
|---|---|---|
| #58 索引条目/定位 | `marxism-and-medieval-studies` | 源 PDF 407 页；索引 104 条、定位 102 条；索引页 `404–406`；双栏 |
| #58 索引条目/定位 | `history-of-british-labour-party` | 源 PDF 320 页；索引 1,013 条、定位 628 条；索引页 `302–316`；孤页 0 |
| #58 索引条目/定位 | `unlikely-allies` | 源 PDF 367 页；索引 827 条、定位 746 条；索引页 `352–364`；页 65 正文页误判已消除 |
| #58 源 TOC↔nav | `unlikely-allies` | `translation/frontmatter/toc.md` 16 条 vs `output/unlikely-allies.epub` nav 23 条：匹配 11、仅印刷 5（标题改写/异名/notes 未进 nav）、仅 nav 12、歧义 0、href 缺失 0 |
| #58 源注独立清点 | `cambridge-history-south-africa-2` | raw 页 423 个注文候选块、724 个注号；注册 740 条；跨页注尾候选 0 |
| #58 源注独立清点 | `unlikely-allies` | 875 个候选块、1,297 个注号；注册 1,292 条；跨页注尾候选 11 |
| #58 源注独立清点 | `pod-znakiem-krola-daniela` | 1,969 个候选块、1,871 个注号；注册 2,215 条；跨页注尾候选 22 |
| #96 印刷页眉/页码 | `unlikely-allies` | `pdf` 生成 475 页、22 区段、24 书签；偶数页 225 页页眉均为书名，奇数页 228 页为章名/结构标题；唯一整页图像页为封面且无页码 |
| #100 封面口径 | 合成 A5 样本 | 300 dpi 实出 1,749×2,481 px（物理 148×210 mm；测试允许 ±2 px），不是固定 1600×2400 画布；译者行 `OpenCode 译` 进入登记文本 |
| #101 CJK 优先 | 环境变量 | `AEP_PDF_FONT='"Noto Serif CJK SC", "Nimbus Roman", serif'` 下字体测试 2 passed |

索引页性能：`history-of-british-labour-party` 从逐页 `get_text("dict")` 约 97 秒降到 6.1 秒；
`marxism-and-medieval-studies` 3.5 秒；`unlikely-allies` 3.6 秒。做法是先取纯文本判页，只对
索引页做行框抽取。

### 6.2 实现与回归

| 条目 | 交付 | 验证 |
|---|---|---|
| #58 索引证据 | `preprocess/index_evidence.py` + `evidence index`；条目拆分按从右往左消费页码 token（长行不灾难性回溯）、`98-9`/`212-13` 展开、年份不冒充页码；索引页须版头标题行（正文 “card index” 不再误判）；输出孤页/缺页/重复标签/双栏/行框 | `tests/test_index_evidence.py` 15 passed |
| #58 源 TOC↔nav | `preprocess/toc_diff.py` + `evidence toc-diff`；印刷目录优先译文、页码可独立成行、引号/编号归一化、逐项 matched/printed_only/ambiguous/nav_only/href 缺失 | `tests/test_toc_diff.py` 7 passed |
| #58 源注/注尾 | `preprocess/note_inventory.py`；整页注文页跨页识别、正文脚注小字号+页脚位置、重复页脚/目录点线/大写版式排除、连续页注尾配对（连字符/无终止标点）与重复尾过滤；`evidence source` 输出 `note_inventory`/`note_tail_pairs` | `tests/test_note_inventory.py` 7 passed |
| #57/#72-1 | `preprocess/note_render.py`；`evidence notes --render [--dpi/--max-crops/--mark-reviewed]`：按需局部裁剪、同摘要复用并保留审阅、重渲染换图归零审阅、`deferred/page_only/missing_page/source_missing` 显式；索引修复仍走既有 `repair apply` 事务，不新增写入路径 | `tests/test_note_render.py` 6 passed |
| #96 | `stamp_folios` 偶数页书名/奇数页章名、`plate`/`titlepage`/`part` 隐藏页眉页脚；整页图版判定；`PrintStyle.print_css` + `--print-css`/`pdf.print_css`（禁 `</style>`、`@import`、远程 URL，上限 256 KiB）；源目录点线转 `.toc-row` 三段 | `tests/test_pdfexport.py` 76 passed、`tests/test_build.py` 57 passed |
| 排版基线 | 源目录点线改为 `.toc-dots` 布局后，PDF 文本层少 11 个点字符（21 页、三主题 EPUB 摘要不变）；按测试约定显式重录 `tests/fixtures/typography/baseline.json`，未自动重录 | `tests/test_typography_fixtures.py` 8 passed |
| #91 | 链接改写只动内联/引用式/HTML `href|src` 目标，跳过正文同名文本、围栏与行内代码；apply 与预检共用同一函数 | `tests/test_archive.py` 28 passed |
| #93 | confirmed 术语（含别名 token）与全大写缩写不报 `primitive_word`；引号内逗号/破折号收尾报 `quote_tail_dropped`；整单元引号失衡时补逐块位置 | `tests/test_hygiene.py` 20 passed |
| #100 | 封面登记新增 `pixels`（物理尺寸×dpi）；测试断言 A5@300dpi 与译者行 | `tests/test_cover_render.py` |
| #101 | 字体测试显式清除环境变量，CJK 优先配置与默认拉丁优先并行受支持 | `tests/test_pdfexport.py -k font_stack`（含 CJK 环境） |
| #40 | README 中英新增「分发方式（PyPI 决策）」+ `pyproject.toml` 注释：不发布 PyPI，`uv build` 仅供内部/私有渠道 | `i18n --check/--links` |

### 6.3 本轮后的关闭建议变化

| issue | 建议 | 依据 |
|---|---|---|
| #58 | **可关闭** | 双栏索引孤页/定位、源 TOC↔nav 逐项 diff、跨页注尾、源注独立清点均有真实书证据与回归 |
| #57 | **可关闭** | 接口决策落地：只读 `evidence index` + 既有 `repair apply` 事务；不再单列 harvest/apply 工具 |
| #72 | **可关闭** | #72-1 按需裁剪、存储上限、审阅状态、真实 PDF 渲染验证完成 |
| #91 | **可关闭** | 链接改写收窄为仅目标，正文/代码同名文本不再被替换 |
| #93 | **可关闭** | 术语/缩写排除、逐块引号定位、`quote_tail_dropped` 均落地（advisory 规则） |
| #96 | **可关闭** | 页眉书名、图版页页脚、源 TOC 点线、print.css 扩展点均有实现与实排证据 |
| #100 | **可关闭** | 像素口径写入登记并有断言；译者行断言落地 |
| #101 | **可关闭** | CJK 优先环境测试不再依赖环境默认，受支持配置有断言 |
| #40 | **可关闭** | PyPI 决策已写入中文权威 README、英文同步与 pyproject 注释 |

阶段验证（第二轮）：全量离线 `pytest -q` **1513 passed / 3 skipped**（979.80s）；
`ruff check`、`ruff format --check`（453 files）、`i18n --check/--links` 通过；
`test_architecture_boundaries.py` + `test_i18n.py` 20 passed。未提交、未推送、未关闭/评论 issue。

仍未完成、继续保留：`#77`（legacy 无 `import_digests` 的产品决定）等本轮未列入的项；
本轮不宣称 `#58` 的索引**语义正确性**，工具只输出候选与定位证据。
