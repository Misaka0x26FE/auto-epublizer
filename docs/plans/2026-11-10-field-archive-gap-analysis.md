# translate.tar.gz 实战归档 → 本仓差距分析与改进方案

状态：**已实施（16 项落地，未提交）**　｜　立项日 / 复核 / 实施日：2026-11-10

本次修订：区分候选与确认缺陷；重排任务依赖；补齐验收、兼容、回退及发布证据要求。
§1–§6 保留归档发现与来源，§7 是实施顺序，§11–§13 是后续执行契约；尚未实施的建议不得记为已有能力。

分析对象：`~/Downloads/translate.tar.gz`（13.4 GB，解包 9.1 GB）
基线：本仓 `main` = `c9df339`（2026-11-04）；归档内 `auto-epublizer` clone = `origin/main 56720e7`（2026-11-03）
+ 两条本地未推送提交 + 未提交工作树改动。

本轮**只做分析**：不改 `src/`、不改工作区、不提交修复。所有数字均由归档内实物重算，
每条结论附文件路径/命令，便于复核。

---

## 0. 一句话结论

归档暴露的问题**不是「文档没写全」，而是三件更贵的事**：

1. **归档独有资产需要保全和评估**：归档有本仓未收录的 PDF/封面/字体提交及工作树改动；
   `407d2b4` 删除了 `_CELL_ATX` 修复及对应检测、测试。保全先于迁移，历史实现仍须重新验证。
2. **机械对账不代表语义验收**：`length` 告警占报告句数 **19.6%**，其中 99.1% 为
   `ratio<0.30`，提示长度口径可能失配，但尚未证明全部为误报。注文中
   **6,806 / 16,199 条（42%）目标文本无汉字**，属于待核候选，不等同于未译数量。
   `notes_audit` 能证明「成品 == 登记文本」，尚未独立证明登记文本符合翻译体例。
3. **重复脚本提示工作流减负机会**：637 个工作区 Python 脚本共 95,774 行，
   包含分块、对照、覆盖对账与结构重建等需求。应先区分通用工具、单书修复、探索脚本及重复副本，
   再决定哪些进入 CLI；文件数量不直接等于功能缺口或可节省代码量。

---

## 1. 归档里到底有什么（实测规模）

| 部分 | 规模 | 性质 |
|---|---|---|
| `translate/workspaces/` | **52 个工作区**，1,585 单元，153,458 条 align 行 | 真实生产语料 |
| `translate/docs/` | 339 个文件 / 16 MB，58 篇顶层 md、62 个工具脚本 | 过程文档 + 可复用工具 |
| `translate/workspaces/*/preprocessing/tools/` | **637 个 .py / 95,774 行 / 4.17 MB**，392 个不同文件名 | 每书自建补丁工具 |
| `translate/reviews/` | 3 批跨书深查（metrics / verification JSON） | 跨书审计快照 |
| `translate/auto-epublizer/` | `56720e7` + 3 条未推送提交 + 3 个未提交文件 | 仓库快照 |
| `translate/AGENTS.md` | 300 行，含 **26 条「跨书判据与陷阱」速查表** | 最高密度经验 |

工作区报告汇总（`report.json` 逐本重算）：

| 指标 | 值 |
|---|---|
| 工作区数 / 有 `report.json` | 52 / 52 |
| `released=true` | **49**（`ok`） |
| 未放行 | 3（`terminology_open` ×2、`structure_open` ×1） |
| G0 告警总数 | **40,147**（其中 `length` **30,303**、`terminology_exempt` 5,173、`language_exempt` 4,082） |
| `g4_audit` 全库 | 52/52 `pass`，epubcheck errors 全 0 |
| G4 解包 warning 总数 | **861**（`W_PARA_UNCLOSED` 363、`W_NOTE_IN_PHRASE` 303、`W_H1_COUNT` 49 …） |
| provenance finding 总数 | **2,422**（`W_INSERT_NO_DESC` 951、`W_INSERT_NO_LATEX` 684、`W_PARA_UNCLOSED` 363 …） |
| `report.json` 体量 | 合计 **13.0 MB**，单本最大 **2.1 MB**（cambridge-history-south-africa-2） |

---

## 2. P0 — 正确性缺陷（有复现证据）

### P0-1 注文语言核验缺口：6,806 条零汉字候选待核证

**证据链（代码 + 数据双向）**

`src/auto_epublizer/qa/notes_audit.py:390-397`：

```python
t = target_by_id.get(nid)
if t is not None and str(t.get("target_markdown") or "").strip():
    expected_md = str(t["target_markdown"])
else:
    expected_md = str((note_by_id.get(nid) or {}).get("source_markdown") or "")
```

只要 `target_markdown` **非空**，就按目标文本核对；其中写的是源语言原文时，
成品渲染的也是同一段外文，于是「成品 == 登记」→ 通过。

归档 `translation/notes.json` 全库重算（16,199 条注文）：

| 现象 | 条数 | 占比 |
|---|---|---|
| `target_markdown` **无任何汉字** | **6,806** | **42.0%** |
| `target_markdown` 与 `source_markdown` **逐字相同** | 3,364 | 20.8% |
| 无汉字且像说明性散文（≥10 词、≥2 句末） | 2,021 | 12.5% |

逐本（无汉字 / 总注数）：

| 书 | 无汉字注文 | 总注 | 备注 |
|---|---:|---:|---|
| `pod-znakiem-krola-daniela` | 2,024 | 2,215 | 91% 零汉字候选，`released=true/ok` |
| `unlikely-allies` | 1,221 | 1,292 | 94%，其中 1,221 条与源逐字相同 |
| `stalins-commandos` | 888 | 1,036 | `released=true/ok` |
| `cambridge-history-south-africa-2` | 723 | 740 | 98% |
| `vanguard-of-the-imam` | 545 | 946 | 58% |
| `prague-spring-and-its-aftermath` | 411 | 840 | 99 条散文型；与归档审查结论一致 |
| `sorel-presentation-textes-choisis` | 235 | 235 | 100%；`released=true/ok` |

**另有历史审查线索**：归档 `docs/审查-布拉格之春-20261106.md` P1-2 已写明
「848 条注文整层未译、246 条含说明性文字」，并且该结论明确指**门禁全部复现通过、内容层未达验收**。
该记录与本轮 840 条登记注的统计范围并不完全一致，应先核对版本和分母，再逐条确认内容。

**修订方案**：结构完整性、语言风险候选、逐条核验结论三层分开。机器只做确定性预筛；
agent 依据原页和翻译体例判定应译、原文保留或部分翻译。适用范围内未完成核证的候选阻断发布，
错误含义为「待核验」，不用 `E_NOTES_UNTRANSLATED` 暗示机器已证明未译。
候选需覆盖源译相同、外语正文占比异常等信号，避免「添一个汉字即通过」。
逐条处置绑定 note_id、源译摘要、规则版本、理由及证据；内容变化后处置失效。
原有成品文本/图片/回链对账保持独立，转换不翻译及同语种处理须显式分流。

**验收**：合成真译文、照搬散文、纯著录、混合语种、代码/公式/图片注及一字汉字掩饰案例；
验证候选、处置、失效和最终 released 状态。全库只读回算报告新增待核项，
不预设恰有几本应被阻断，不以原放行数量为正确性目标。

---

### P0-2 `write_structured` 写入**未清洗**单元：页眉/页码进 `structured/`

**已复现**（最小 fixture，3 页、每页页眉 + 页码 + 正文；清洗规则现要求 >=5 页页码证据，3 页单元页码会保留为候选）：

```
# Chapter 1
BOOK TITLE
1
Body paragraph on page 1.
BOOK TITLE
2
Body paragraph on page 2.
...
```

`src/auto_epublizer/structure/rebuild.py:95` 已经算出 `cleaned = clean_unit(cls.unit)`，
但 `write_structured`（同文件 `:110-124`）写盘时用的是 **`unit.segments`**：

```python
unit = units[index]  # 未清洗
target.write_text(_render_markdown(unit.title, unit.segments, ...))
```

后果：`strip_page_numbers` / `clean_header_footer` 只影响 `entries` 的 `title`，
**正文里的跨页页眉、页码原样留在 `structured/`**，再流进翻译与成品。

**归档侧的代价是可见的**：
`workspaces/cambridge-history-south-africa-2/preprocessing/tools/rebuild_structure.py`
开头 12 行注释就是在骂这件事（"emits `doc.units[index].segments` — the *uncleaned* unit"），
并且被迫用 span 级 PyMuPDF 证据重建。同样的重建脚本在 9 个工作区各写了一份。

**修订方案与验收**：先验证清洗器的正文保留能力，再接通 cleaned segments 写盘。
当前 `strip_page_numbers` 按数字文本形态剔除，需覆盖正文独立数字、年份、诗歌编号、
表格和代码等反例；`classify_units` 的启发式 titlepage 与 `clean_unit` 按标题重判也须对齐。
只对有足够版式依据的家具实施删除，证据不足时保留并报候选；记录删除位置、依据和原始身份。
最后验证上述页眉 fixture 确实清除，同时链接、媒体、标题层级及书名页保持不变。
既有工作区仅预览重建差异，显式确认后才注册，不连带覆盖 translation/align。

---

### P0-3 渲染层修复被 `407d2b4` 静默回归（`_CELL_ATX` + `单元格ATX` 检测口）

**证据（提交史）**

| 提交 | 日期 | 动作 |
|---|---|---|
| `64517f3` | 2026-10-07 | 新增 `_CELL_ATX` / `_cell()`、`_MD_RESIDUE` 的「单元格ATX」、测试 `test_table_cell_strips_atx_marker` |
| `407d2b4` | 2026-10-17 | **删除**上述三样（`git show` 可见 `-_CELL_ATX`、`-def _cell`、`-def test_table_cell_strips_atx_marker`），提交正文为空，无替代、无记录 |

**今天实测**：

```text
| **## 小节标题** | |   →   <th><strong>## 小节标题</strong></th>
_MD_RESIDUE 匹配: 无  →  检测层同样漏
```

这正是归档 `docs/缺陷修复清单-20261008.md` P1-2 记录的形态（BLP 附录 2
`| **## 议会工党主席，1906—22** | |`）。归档当时的结论是「修法：`_cell()` 只吃紧贴行首或紧贴
markdown 标记之后的 ATX 标记」，而本仓现在**连检测口都没有**——符合归档反复强调的
「检测层与渲染层同时漏」是最危险组合。

**修订方案与验收**：先区分确认的解析污染与表格合法字面符号。
已确认污染可在结构修复层处理；来源不明的表格 ATX 先报候选，不按符号一律删除。
是否恢复渲染兼容逻辑，以来源契约和反例测试决定。覆盖 `# 1`、`C#`、转义井号、
行内/围栏代码及强调包裹的井号；检测器与渲染器独立验证。
使用行为回归防复发，不守卫某个私有正则名称必须存在。

---

### P0-4 `length` 判据的语言对口径：19.6% 的对照句在报警

**全库实测**（30,303 条 `length` 告警的 `ratio` 分布）：

| 指标 | 值 |
|---|---|
| 分母（`report.json` 的 `total_sentences` 合计） | **154,239** |
| 告警率 | **19.6%**（30,303 / 154,239） |
| （另：`translation/align/*.jsonl` 实际行数合计） | 153,458 |
| `ratio < 0.30` 占告警 | **99.1%** |
| ratio 中位数 | **0.269** |
| p5 / p95 | 0.186 / 0.297 |

逐本（≥20 字符源行的 `ratio<0.30` 占比）：`victory-in-vietnam` **65.7%**、
`cambridge-history-south-africa-2` 35.7%、`pentagon-papers` 26.5%、
`history-of-british-labour-party` 15.6%、`longest-war` 10.4%。
（同一本内该占比与全库告警率口径不同：这里是「该书全部长句」的分母，故数值高于 19.6% 的整体告警率。）

这些是被现行低比值规则选中的告警，其低值分布本身不能证明误报。
语言对字数差异是需校准的合理假设。`docs/quality-control.zh.md` 已承认「英→中长度比天然偏低，实测大量误报」，
但默认阈值仍是 `0.30 / 3.0`，且 `min_src_chars=20` 只保护**极短源行**。
归档 26 条速查表里也没有解决它——它一直是 advisory 噪声。

**风险**：大量低比值告警增加核验负担，可能淹没真实缺失信号；报告单本可达 2.1 MB。

**修订方案**：规则校准和报告展示拆成两个任务。按语言对、内容类型、句长分层，
同时抽取告警及未告警样本，由 agent 核证正常压缩、真实缺失、分句差异与解析问题。
比较字符比、词数与目标文字数等候选指标，不预设 0.55–1.6 或其他未经验证阈值。
独立保留空译文与严重短译门，不以减少告警数量代替质量指标。
报告可提供摘要，但完整 finding 仍须保留为有版本、可定位、纳入摘要校验的明细产物，
先盘点消费方，再设计兼容读写契约。

**验收**：离线校准集与独立验证集分开，记录抽样方法、分母和各类误报/漏报；
合成删除、截短和错配案例保持检出。全库回算只输出聚合统计，不把真实书籍语料加入测试库。

---

### P0-5 归档里有三条**只存在于工作树**的改动，本仓完全没有

归档 `auto-epublizer` 的 git 状态（`git --git-dir=... --work-tree=. status`）：

```text
 M src/auto_epublizer/build/__init__.py      # 主题 CSS 去掉 font-family（2026-11-04 用户指令）
 M src/auto_epublizer/cover_hanze.py          # 新增 dossier 意象
 M uv.lock                                    # 索引源被改成腾讯镜像（1532 行噪声）
```

外加未推送提交 `770ae20` / `223206e`（合并为 `c9067f6`），本地 **`git cat-file` 全部 MISSING**：

| 归档有、本仓无 | 价值 |
|---|---|
| `_clear_markers` 改**按 span bbox 精确 redaction** | 本地用 `search_for` 矩形涂，会连带删相邻字/残留 `AE`（归档注释明写实测过） |
| `AEP_PDF_RUNNING_FONT`（TrueType 嵌入书眉/页码） | 纯 CJK 页眉走内置 `china-s`；CFF/OTF 在 Chromium 下会 Type 3 丢字 |
| `AEP_PDF_FONT` 字体栈 + `"Noto Serif CJK SC TTF"` 优先 | 本地 PDF 字体栈缺 TTF 项 |
| `AEP_PDF_COLOPHON` + `section.colophon` CSS | 印刷版可带制作信息与版权页 |
| 封面页剔除自动 `<h1>` / `<figcaption>` | 否则封面印出标题与图注 |
| `section.cover p/figure` 尺寸 `!important` | 封面整页铺满 |
| `cover_hanze` `dossier` 意象 | 十款批量封面补丁（`translate/docs/tools/cover_hanze_batch11.patch`，482 行新增）里另有 10 个意象 |
| 主题 CSS **不设 font-family** | 归档 `translate/AGENTS.md` 记为 **2026-11-04 用户指令**；本仓 `docs/epub-template-spec.zh.md` §5.3 + `tests/test_build.py:517` 仍**断言** `font-family: serif` |

> 这一条应**先保全再评估合入**：这些是当前已知归档独有资产，且已有生产运行记录
> （归档 `docs/审查-十本新书新标准-20261103.md` 的封面可复现性一节记录了 `iran-reframed`
> 重生成后逐字节相同）。尚未证明不存在其他备份，也未证明每项适合直接迁移。
> 提交、工作树改动、补丁与镜像锁文件噪声分开登记；保全不等于 cherry-pick 或功能验收。

---

## 3. P1 — 工作流能力缺口（工作区已用 95,774 行脚本代偿）

按归档 `workspaces/*/preprocessing/tools/*.py` 的**出现频次**归并（637 文件 / 392 名）：

| 频次 | 工作区脚本 | 本仓等价能力 | 判定 |
|---:|---|---|---|
| 34 | `make_align.py` | `align-propose` / `align-apply`（块→seq 提案） | **部分**：提案 ≠ 直接由 md 生成 align；各书 34 份口径不一 |
| 17 | `assemble_unit.py` | 无 | **缺**：`.tr/<unit>/NNN.zh.md` 分块译文按序拼回 + 5 项校验 |
| 15 | `dump_blocks.py` | 无 | **缺**：按单元导出编号块供分批翻译 |
| 11 | `check_unit_coverage.py` | `provenance` 覆盖率 | **部分**：它查「align 行数 == 源段数」的独立对账 |
| 11 | `guard.py` | 无统一等价 | **缺**：单元级红线自检（块数/非文本块逐字节/表格形状） |
| 10 | `fix_abs_media_paths.py` | `resolve_media_path` 已有重复根前缀 + basename 兜底（实测可解析 `/home/agent/...`） | **已修**（建档 `20261008` P2-1 已进 CLI） |
| 9 | `rebuild_structure.py` | 无 | **缺**：span 级证据重建 `structured/`（P0-2 的上游病根） |
| 9 | `normalize_zh.py` | `hygiene`（只读候选） | **部分**：可逆的中文排版归一（数字↔CJK 空格等）无写入口 |
| 8 | `check_offset.py` | 无 | **缺**：±3 邻域锚点平移检测块号错位 |
| 8 | `resync_tr.py` | 无 | **缺**：`structured/` 改动后同步 `.tr` 权威层 |
| 8 | `fix_footnote_codes.py` / `fix_missing_confirmed_names.py` / `apply_glossary_first_mention.py` | 部分（`repair apply` 通用替换） | **部分**：可拼出，但需手写计划 |
| 6 | `sync_align_from_md.py` | `align-apply` | **已覆盖** |
| 5 | `render_pdf.py` | `pdf` 命令 | **已覆盖** |

**修订结论**：优先验证分块作业需求（dump → 分批译 → assemble → align → 覆盖对账）。
归档有 15 个工作区采用 `.tr` 权威层，但本仓已有 translation 构建输入与 align 对照契约，
第一版 chunk 应是带源摘要的作业暂存，不新增第三个译文权威层。
先定义块身份、过期判定、冲突和事务写入，再做命令面；旧 `.tr` 通过显式导入适配。
`±3` 邻域锚点检测只能补充定位，不能替代稳定块身份与全文对账。

---

## 4. P1 — 归档 issue 诉求逐条比对（哪些已落地、哪些仍空）

### 4.1 `translate/docs/issue-工作区目录结构提案.md`（上游 issue #30，6 项缺口）

| 缺口 | 本仓 | 证据 |
|---|---|---|
| AZW3/MOBI 白名单 | **已实现** | `preprocess/sniff.py:24-36` 含 `.azw3/.mobi`（经 calibre） |
| `preprocess --force` 原地重建 | **已实现** | `cli.py:921` |
| `--json` 被 Rich 折行 | **已实现** | `_emit_plain` / `_emit_json` 的 `soft_wrap` |
| 长任务进度到 stderr | **已实现** | `--progress` |
| 结构粒度体检（中位数/Unknown 占比） | **已实现** | `preprocess/facts.py:82-104` |
| `--original` 归档交付原件 | **已实现** | `cli.py:914` |

→ **6/6 已落地**；本章只需在 skills 里补一句「已随 CLI 提供」，不必再立项。

### 4.2 `translate/docs/feedback-issue-72-note-audit-20261027.md`（9 项）

逐项汇总：**3 已实现 / 2 部分实现 / 4 缺失**；以本表为准。

| 诉求 | 本仓 | 证据 |
|---|---|---|
| 1 `evidence notes`：按 `notes.json` 几何框给**每条**注文出源页证据 | **缺** | `evidence` 子命令只有 layout/toc/source/page-numbers/report/breaks/partition |
| 2 多权威层事务（含 notes + chunk） | **部分** | `safe_repair` 覆盖 `structured/translation/align/notes`，但**明确拒绝**派生 chunk（无 chunk 概念） |
| 3 逐处术语例外（unit/seq/occurrence + 证据） | **已实现** | `glossary/csv_io.py:106-190` 的 `TerminologyExemption` locator 行 + `g0.py` occurrence 分支 |
| 4 目录/索引页码口径 + 重复目录检测 | **已实现** | `preprocess/page_numbers.py`、`toc_model.py:153`、`evidence page-numbers --duplicate_toc_candidates` |
| 5 制作信息详略级别 | **半实现** | `fingerprint.software_section(detail="brief")` 存在，但 **`build/__init__.py:778` 调 `software_page(...)` 不传 `detail`**，config 无开关（`grep "detail=" src/auto_epublizer/{build,orchestrator,cli}` = 0） |
| 6 `uv sync --locked` 镜像索引失败要可诊断 | **缺** | `doctor.py` 无 registry/镜像检查；分析期间曾观察到本仓 lock 被环境改写，已恢复该次自行产生的改动，不能作为持续脏状态引用 |
| 7 成熟工作根执行骨架不新增顶层文件 | **缺** | 实测 `work-root --dry-run` 在已有 `AGENTS.md`+`workspaces/` 的目录里 created 11 项（含 `README.md`、`config.example.yaml`） |
| 8 入库对账支持「声明式忽略 + 理由」 | **已实现** | `template/work-root/docs/check_tracked.py` 的 `--allow 'pattern|reason'` / `--allow-file` |
| 9 源文实印疑误一等公民登记 | **缺** | `grep -r "errata" src` = 0 |

### 4.3 `translate/docs/feedback-issue-20261027-quality-audit.md`（6 项）

| 诉求 | 本仓 | 判定 |
|---|---|---|
| 1 短英文残留候选 + 逐项处置 | `hygiene` 有 `primitive_word` 候选，**无处置记录**（不记 accept/reject 与理由） | 半实现 |
| 2 残句/占位语候选 + 原页证据 | `hygiene` 有 `half_sentence`/`tail_loss`；`evidence breaks` 给页边界候选 | 半实现 |
| 3 数字注号→`ref_id`→`note_id` 绑定核验 | `notes register` + 成品 notes gate 逐条对账 | **已实现** |
| 4 公式/图版**误分类排除**证据路径 | 只有 `W_INSERT_NO_DESC` / `W_INSERT_NO_LATEX` advisory；没有「非独立公式→排除」的显式处置 | **缺** |
| 5 排版候选按单元类型分流 + 处置理由 | `hygiene` / `audit` 有候选，无 disposition 落盘 | 半实现 |
| 6 人工审查契约（not_run / sampled / full、candidate / confirmed / resolved、分母口径） | `review/ledger.py` 有 `scope`(`full`/`units`)、`open/unknown/inconsistent`、`contract`；**无 not_run/sampled 枚举、无抽样分母字段** | 半实现 |

---

## 5. P1 — 归档最可直接迁移的资产：26 条跨书判据

`translate/AGENTS.md`「跨书判据与陷阱（速查）」来自生产实践；下表仅是关键词定位结果，
**不把命中率解释为能力覆盖率**，未命中项需继续按行为和契约核实。
关键词命中矩阵（`grep -rl` 于 `skills/references/*.zh.md` + `lessons/*.zh.md` + `docs/*.zh.md`）：

| 判据 | 本地命中 |
|---|---|
| CSV 首字节不得 BOM | 1（skills/quality-evidence） |
| 跨书共享基准只放工作根 `references/` | 1 |
| 术语表 8 列 / `\|` 别名 / 含源语原形 | 1 |
| `import --terms` 按 source 合并非替换 | 0（仅「import --terms」用法 7 处，未写合并语义） |
| 改 `translation` 必须同步 `align`（`E_ALIGN_MD_DRIFT`） | 7 |
| 改 `structured` 必须同步 `.tr`（`resync_tr`） | **0** |
| 怀疑块号错位用 `check_offset`（肉眼漏 1/3） | **0** |
| 审查成品先做**字符类普查**再反查构建器 | **0** |
| PDF 目录用绝对页码（封面=1） | **0** |
| 可见 markdown 垃圾三类（`]{#id}` / 缩进标题 / `$$`） | 5 |
| 页眉「标题回声块」正解是从译文删该块 | 3 |
| 注释单元分段在 `raw/page-*.json` 的块级 `font_size` | 4 |
| `1. …` 单块会被当 `<ol>`，须转义 `1\.` | 2 |
| 繁体判定必须 zhconv 逐字比对 | 1 |
| 中文直引号**按对判定**，不可全局替换 | **0** |
| `git add -A` 后 `git ls-files` vs `find` 对账 | **0** |
| 判断真交付：看 `translation/body/*.md` 文件数（译前空跑会留空壳） | 3 |
| `qa`/`status`/`ledger` 传**绝对路径** | 12（但未写「相对路径=摘要过期」的原因） |
| `repairs.jsonl` 的 `evidence` 必须单文件存在 | 9 |
| 放宽判据后**必须重跑全库** | **0** |
| 结构未冻结不得开译 | 2 |

**迁移原则**（与归档一致）：**改一次就要读的**进 `skills/references/invariants.zh.md` / `workflow.zh.md`；
**遇到才查的**进 `skills/lessons/`；**根规范级**的进 `template/work-root/AGENTS.md`。

---

## 6. P2 — 方法论级资产：证明「门禁会失败」

归档 `translate/docs/tools/audit_criteria_negative_test.py`（2026-10-21）：
把工作区复制成临时副本，**逐项注入 6 类缺陷**，断言对应判据真的报错，并保留「基线零误报」。

它记录的 5 条「更正前的判据会怎样」全是本仓同类风险：

| 注入 | 旧判据的失效方式 |
|---|---|
| 删一个正文块 | 块数项写成恒真式 → 报「不一致单元 0」 |
| 注文目标截短（成品仍全文） | `want in got or got in want` 子串包含 → 判一致 |
| 成品 nav 标签改写 | 两侧键口径不一致 → 恒假，结构上不可能非零 |
| `source/` 被改动 | 只核**首文件** sha256 |
| 根 `sources/` 缺件 | 缺件仍判「三方一致 ✅」 |

本仓已有大量负向测试；这里补的是统一的门禁验收矩阵与跨层发布验证，
不声称现有测试均未证明失败路径。每项修复从正常基线、单缺陷注入开始，
验证预期 finding、最终阻断和恢复；无需等到最后再另建整套框架。

---

## 7. 优先级与落地顺序（复核后）

P0/P1 标题保留为原发现分类，执行以本表及 §11 的依赖为准。

| 阶段 | 任务 ID | 交付 | 阶段出口 |
|---|---|---|---|
| A 证据校准与保全 | A1–A2 | 可重跑统计、证据清单、归档补丁保全及逐项迁移评估 | 区分实测/候选/历史记录；基线摘要齐全 |
| B 小范围正确性 | B1–B4 | 清洗保留测试与写盘、媒体身份、表格 ATX 契约 | 正常/注入/恢复端到端验证；无静默内容损失 |
| C 注文核验闭环 | C1–C3 | 原页证据、候选处置契约、import/QA 发布接线 | 处置过期重开；转换与翻译分流；全库只读影响报告 |
| D 工作流减负 | D1–D3 | 分块暂存、事务 assemble、成熟根保护、实印疑误登记 | 故障恢复与旧格式显式迁移通过 |
| E 校准与展示 | E1–E4 | 长度评估、报告摘要、制作信息、doctor 及逐项资产迁移 | 校准效果有独立验证；消费方兼容；配置入口一致 |

负向测试、文档更新和恢复验证是每项任务的组成部分，不再作为末尾补项。
顺序表示建议主线；A 后独立的 B/C 证据工作可交错进行，但不得跳过各自依赖。
工作区破坏性变更不属于本计划的自动执行范围，真实书籍仅作只读评估或显式批准的副本实验。

> **不建议本轮做**：把 52 本书的内部语料入库或做回归基线（版权与体积都不合适）。
> 只做**统计口径**（分布/计数/比率），不搬原文。

---

## 8. lessons 沉淀与复核

本轮已新增注文核验及门禁负向测试两篇 lessons；其中注文篇的「零汉字即未译」及
「比例大于零即可定性」措辞须随 C2 修订，先于新门禁实施，不将其作为已确认结论引用。
双语索引同步；经验条目应写清候选、语义结论和版本范围的区别。

按归档 `lessons/README.zh.md` 的三段式（判据 / 处置 / 复现验证），主题清单：

1. `字符类普查`：报告层看不见的形态（`{#`、`<p>#`、`$$`、裸 `\`、单元格 ATX）+ 反查构建器能力；
2. `恒真式判据`：任何「不一致单元 0」先问「它有没有可能非零」；
3. `判据变更必须重跑全库`（不是只看新判据抓到什么）；
4. `绝对路径判「能否解析」而非「长得对不对」`（`/home/agent` vs `/home/hermes`）；
5. `git 忽略是最安静的失败`（`git ls-files` vs `find` 对账；先分清「有意排除」与「静默丢失」）；
6. `分块作业的块数 ≠ 块块对应`（`check_offset` 的锚点平移判据）；
7. `注文层「非空即已译」是假绿`（本仓 P0-1 复盘）。

---

## 9. 复核入口（全部只读、可重跑）

```bash
# 归档解包（本机已解到 /tmp/opencode/arc）
tar -xzf ~/Downloads/translate.tar.gz -C /tmp/opencode/arc \
  --exclude='*/.venv' --exclude='*/__pycache__' --exclude='*/.git' --exclude='*/node_modules'

# 1) 工作区报告汇总（放行/告警/溯源）
python3 - <<'PY'
import json,glob,collections
rel=collections.Counter(); codes=collections.Counter(); n=0
for p in sorted(glob.glob('/tmp/opencode/arc/translate/workspaces/*/report.json')):
    d=json.load(open(p)); n+=1
    rel[(bool(d.get('released')), str(d.get('released_reason')))]+=1
    for f in (d.get('g0_flags') or []):
        if isinstance(f,dict): codes[f.get('check')]+=1
print(n, rel.most_common(), codes.most_common(8))
PY

# 2) 注文语言风险候选统计（不等于未译数量）
python3 - <<'PY'
import json,glob,re
from pathlib import Path
CJK=re.compile(r'[\u4e00-\u9fff]')
tot=no=identical=0
for p in sorted(glob.glob('/tmp/opencode/arc/translate/workspaces/*/translation/notes.json')):
    workspace=Path(p).parents[1]; tr=json.load(open(p)); ns=tr.get('notes') or []
    st=json.load(open(workspace/'structured/notes.json'))
    tm={x['note_id']:(x.get('target_markdown') or '').strip() for x in ns}
    for x in st.get('notes') or []:
        a=(x.get('source_markdown') or '').strip(); b=tm.get(x['note_id'],'')
        tot+=1
        if b and not CJK.search(b): no+=1
        if a and a==b: identical+=1
print('notes',tot,'no-CJK',no,'identical',identical)
PY

# 3) length 告警分布（尚未标注真实误报率）
python3 - <<'PY'
import json,glob,statistics
r=[]; tot=0
for p in glob.glob('/tmp/opencode/arc/translate/workspaces/*/report.json'):
    d=json.load(open(p)); tot+=int(d.get('total_sentences') or 0)
    for f in (d.get('g0_flags') or []):
        if isinstance(f,dict) and f.get('check')=='length':
            x=(f.get('data') or {}).get('ratio')
            if isinstance(x,(int,float)): r.append(x)
r.sort(); print('sentences',tot,'flags',len(r),f'{len(r)/tot:.1%}',
                'median',statistics.median(r),'<0.30',sum(1 for v in r if v<0.30)/len(r))
PY

# 4) 表格 ATX 现象复现（是否修复须按字面内容契约判断）
uv run pytest tests/test_lazy_heading_block.py -q      # 现状 14 条，缺单元格 ATX
uv run python - <<'PY'
from auto_epublizer.build.html import markdown_to_xhtml
print(markdown_to_xhtml("| **## 小节标题** | |\n|---|---|\n| a | b |\n"))
PY
```

---

## 10. 本轮结论边界

- 已做：归档结构索引、52 工作区报告重算、注文/长度/告警三类统计、26 条判据的本地命中矩阵、
  issue #30/#72/quality-audit 逐条比对、4 个本仓缺陷的最小复现、work-root 与 media 解析实测。
- 未做：**没有**逐句语义审校，**没有**判定任何一本书的译文质量；不宣称「错误率」。
- 未改：`src/`、任何工作区、任何 `report.json`、归档内容（只在 `/tmp/opencode` 解包副本上读）。
- 真实书籍全文、句对、原页不进入测试库；本文已包含定位用书名和路径，不应宣称完全匿名。

## 11. 可执行任务契约

任务均为待办，以下完成标准不是完成声明。接口名、错误码和产物名为设计槽位，
须在各任务开工时依据现有领域服务与 schema 确认，避免在 CLI/orchestrator 堆积领域逻辑。
每个任务先添加最小失败用例，后实现；文档与双语更新可作为同一逻辑任务的配套小步。

### A1 — 校准统计与证据分母

- **依赖**：无。落点：本计划、归档只读统计入口。
- [ ] 重跑 §9 修正脚本；报告缺文件、重复/空 note_id、缺失/额外目标注文，不能静默跳过。
- [ ] 区分报告句数、实际 align 行数、有效行数及生成时间；154,239 与 153,458 的差额未查清前不共用分母。
- [ ] 登记输入路径、SHA-256、命令、版本与统计范围；7 本高风险书按著录/散文/混合类型分层核验，明确抽样而非全检。
- **验证**：同一输入重复运行计数一致；缺文件和重复 ID 合成案例能显式失败；候选数不冒充缺陷数。

### A2 — 归档资产保全与分项评估

- **依赖**：A1 的证据记录格式。落点：批准的保全目录及迁移清单，不改原归档。
- [ ] 单独保全未推送提交、未提交功能 diff、独立封面 patch，记录 hash 与基线；排除凭证、书籍正文和镜像 lock 噪声。
- [ ] 各项标记「采纳/重做/暂缓」及理由，识别依赖和与当前主线冲突；保全成功不记为迁移成功。
- [ ] 验证保全件可在沙箱重建或应用于对应基线，不提交、不推送，除非后续另获明确要求。
- **验证**：清单与实际文件 hash 对账；原始归档未变；功能项与锁文件变化独立。

### B1 — 清洗器保留契约

- **依赖**：A1。落点：`structure/classify.py`、结构测试。
- [ ] 增加数字正文、年份、诗歌/章节编号、表格、代码、封面/书名页及无页定位案例。
- [ ] 对齐最终分类与清洗豁免；纯文本数字模式不足以证明为页码，证据不足保留并输出候选。
- [ ] 删除项保留来源位置和判据，原始 segment 身份不被重新编号掩盖；清洗重复运行稳定。
- **验证**：家具应删案例与正文应留案例同时通过；内部链接和媒体来源定位保持可追溯。

### B2 — 接通清洗结果写盘

- **依赖**：B1。落点：`structure/rebuild.py`、init/preprocess 集成测试。
- [ ] 清洗结果在归类/写盘间有单一明确传递方式，不在不同路径重复采用不同清洗口径。
- [ ] 三页家具 fixture 从 init 到 structured 真实落盘正确；标题层级、heading_id、媒体与内部链接保留。
- [ ] 旧工作区先预览差异；显式重建后经现有注册入口更新状态，不手改 publication.json、不覆写译文。
- **验证**：API 与 CLI 均覆盖；二次运行幂等；中断不留下半登记的状态。

### B3 — 媒体完整身份与迁移映射

- **依赖**：A1。落点：`media_paths.py` 及 build/QA 调用方。
- [ ] 精确路径解析与旧路径迁移分开；严格对账中目录错误不靠 basename 静默替换。
- [ ] 显式映射携带原引用、目标资源身份、理由及可用摘要；多个候选或身份冲突输出诊断。
- [ ] 覆盖同名不同目录、错误目录、旧绝对路径、URL 单次解码、路径穿越与 symlink 越界。
- **验证**：错图注入导致最终 QA 不放行；合法映射可复现，图片字节与 manifest 身份独立核对。

### B4 — 表格 ATX 的字面内容契约

- **依赖**：A1。落点：`build/html.py`、`qa/audit.py`、表格/标题测试。
- [ ] 为污染修复与合法字面内容分别定义输入证据；不以恢复 `_CELL_ATX` 为目标。
- [ ] 污染案例有检测与修复闭环；合法井号、编号、代码及转义内容保留。
- [ ] 渲染和残留检测使用独立预期；测试最终 XHTML，不只测试正则命中。
- **验证**：正常→单缺陷→恢复；渲染器替换后行为契约仍成立。

### C1 — 注文原页证据与覆盖清单

- **依赖**：A1。落点：现有 evidence 域服务、CLI、notes 测试。
- [ ] 按 note_id 导出源文件摘要、页码口径、几何区域及原页定位；无几何证据时明确 unknown，不虚构。
- [ ] 一注跨页、多栏、一注多引、图片注有覆盖记录；区分原页证据与 OCR/登记文本自证。
- [ ] 不擅自联网或修改源；大书按 note_id/页范围导出，命令保持只读。
- **验证**：合成多页注可追溯；缺页/过期摘要有显式状态；导出数与登记数按同口径对账。

### C2 — 注文候选与逐条处置 schema

- **依赖**：C1。落点：notes 领域模型/校验、候选服务、相关 lessons 双语版。
- [ ] 定义适用模式、语言对、候选版本、note_id、源译摘要、结论、理由及证据；不套用以 unit 为身份的术语豁免表。
- [ ] 机器预筛与 agent 判定分开；原文保留也须逐条核证；一字汉字不消除其他风险信号。
- [ ] 源译或相关体例变化后重新核验；重复、孤立、伪造证据定位有契约错误；旧记录不自动当作已审。
- **验证**：真译文/著录/散文/混合/非文本/同语种/转换模式矩阵；逐字段变化验证处置失效。

### C3 — import 到最终发布的注文接线

- **依赖**：C2。落点：import、notes QA、报告摘要/发布判定。
- [ ] import 提前提示待核；QA 按适用范围阻断未闭合候选，语义含义是待核验而非机器断言未译。
- [ ] 保持成品内容、媒体、引用、回链对账独立；已核证不能抵消截断或错配。
- [ ] 核验产物及规则版本纳入报告有效性摘要；旧 released 报告保留历史，新 QA 明确显示规则升级影响。
- **验证**：正常→照搬/截断注入→处置或修复→重新 import/build/qa；直接断言 released 与原因，不能只断言 finding。

### D1 — 分块暂存导出与身份契约

- **依赖**：B2；格式/定位契约同时参考 C2。落点：translation 领域模型、导出服务。
- [ ] chunk 仅是作业暂存，不增加权威层；关联 unit、块身份、源摘要、顺序、非文本保真信息及 schema 版本。
- [ ] 源文变更后明确过期；重导出不覆盖已译暂存；块身份变化提供显式映射或冲突。
- [ ] 明确拆分/合并与现有句级 align 的关系，合法一对多不按行数相等误报；旧 `.tr` 只显式导入。
- **验证**：缺块/重复/错序/旧摘要/合法拆合案例；导出不修改正式 translation/align。

### D2 — assemble 事务与覆盖对账

- **依赖**：D1。落点：现有 repair/事务服务与 align/import 注册入口，避免另造状态机。
- [ ] 先预检，再生成 translation+align；检查非文本字节、表格形状、来源覆盖和目标正文一致性。
- [ ] 正式译文有新编辑时输出冲突，不由旧 chunk 覆盖；邻域错位检测只作候选补充。
- [ ] 定义暂存、原子替换、失败恢复/回滚与幂等登记边界；多文件事务使用可恢复日志，不宣称多个 rename 等于整体原子。
- **验证**：每个写入边界故障注入；恢复后要么原版本要么完整新版本，无半套或重复事件登记。

### D3 — 独立工作流小项（分开交付）

- **依赖**：成熟根保护依赖 A1；实印疑误登记依赖 C2 的证据失效模式，但不复用语义结论。
- [ ] 成熟 `work-root` 默认只报告缺项，显式补齐才写入；新根、部分根、重复运行及用户同名文件分别测试。
- [ ] `errata` 定义原文实印、原页证据、建议读法和影响位置；不重写不可变 source，不把登记疑误直接当作已确认修复。
- [ ] 两项分别更新引用指南，避免同一大补丁混合交付。
- **验证**：dry-run 零写入、用户文件字节不变；errata 摘要过期和未核证条目有明确状态。

### E1 — 长度规则校准

- **依赖**：A1。落点：离线评估记录、`review/g0.py`、配置与对应测试。
- [ ] 预先固定分层抽样和误报/漏报评价方法；包含旧规则未告警样本，校准集与验证集分开。
- [ ] 新阈值只有在独立验证达到开工时书面确定的质量门槛后启用；数据不足保留旧规则，报告不确定性。
- [ ] 空译和严重短译独立保留，人工核证仍由 agent 执行；真实书籍仅输出聚合指标。
- **验证**：给出样本量、分母、误报/漏报及新旧比较；合成缺失类零退化，告警率不作为单一通过条件。

### E2 — 报告摘要与完整明细

- **依赖**：A1，独立于 E1 是否启用新规则。落点：报告 schema、写入方、status/ledger 等消费方。
- [ ] 先枚举消费方，定义 schema 版本与旧格式读取；摘要不截断真实 finding 总数。
- [ ] 完整明细稳定排序、可定位、可流式读取；摘要绑定明细摘要，缺件/篡改使证据过期。
- [ ] 双产物事务恢复及历史报告行为明确；测量体积与内存，不预先承诺缩减比例。
- **验证**：新旧消费契约、计数对账、明细丢失与篡改注入、重复运行稳定。

### E3 — 制作信息与 doctor（独立小项）

- **依赖**：A2 的配置评估。
- [ ] 制作信息 detail 使用现有配置入口，默认值兼容；与 PDF colophon/EPUB 制作页避免重复。
- [ ] doctor 默认离线检查 lock 索引与环境配置，联网探测单独显式启用；URL 凭证脱敏，不修改 lock 或打印密钥。
- [ ] 分别交付配置测试与诊断测试，不与字体/封面功能混合。
- **验证**：旧配置行为不变、缺省/显式 detail 覆盖；离线 fixture 覆盖索引冲突与含认证 URL。

### E4 — 归档功能逐项迁移

- **依赖**：A2；制作信息项依赖 E3。每个子项单独实现、验证与回退，不整体 cherry-pick。
- [ ] PDF redaction 覆盖邻字、旋转、合字、跨 span 和链接；字体覆盖缺失回退与 CJK 完整性。
- [ ] PDF 封面/colophon 和 EPUB 去 font-family 分开验收，规范与阅读器预期对齐；环境变量与配置优先级明确。
- [ ] 新封面意象固定输入可复现；只在原书无封面且已有生成封面流程适用时使用，不替换真实源封面。
- **验证**：PDF 文本提取与页面视觉均检查，不能用提取文本替代视觉；封面确定性验证；受影响 EPUB 外部工具检查通过。

## 12. 共用验收、兼容与回退

1. **单任务闭环**：正常基线通过 → 单缺陷注入触发预期诊断/发布状态 → 修复后恢复；
   检查结果来源独立，禁止用同一归一化函数生成预期和实际而掩盖相同错误。
2. **证据状态**：`not_run / sampled / full` 明确区分，记录检查范围、分母和版本；
   `candidate / confirmed / resolved / retained` 的确切枚举在领域 schema 中落实，非本计划自创第二套发布台账。
3. **状态与摘要**：新增核验产物、映射、规则版本进入既有有效性计算；历史报告不覆写，
   过期报告不能代表当前发布。只经现有 CLI 入口推进状态，事件重试不重复计入。
4. **迁移与回退**：新旧 schema、缺省行为、升级影响在开工前写清；先对沙箱副本 dry-run，
   显式应用前保留原版本及摘要。回退不得靠关闭新门禁宣称通过；恢复数据/代码后重新运行适用验证。
5. **全库评估**：先合成回归，再少量高风险副本，最后 52 工作区只读统计影响；
   不因规则升级自动修改真实译文、不把旧 released 数量作为验收目标。解析/语言结论均附范围与未知项。
6. **工程命令**：每项跑受影响 pytest、`uv run ruff check .`、`uv run ruff format --check .`；
   阶段出口跑全量离线 pytest。涉及 EPUB/PDF 的任务另跑实际外部工具与视觉检查，缺工具记未验证而非通过。
   文档改动执行 `uv run python scripts/i18n.py --check`、`--links` 及 `tests/test_i18n.py`；
   使用 frozen/locked 环境避免无关 lock 改写。禁止新增内部 LLM 调用，继续满足架构边界测试。
7. **文档与范围**：命令、工作区、QC 改动同步对应 skills/reference 与 SKILL 路由，中文权威源与英文派生同步。
   26 条经验逐项核实后分流到 invariants/lessons/template；不机械复制已过时的 `.tr` 权威层规则。
   不修改本轮之外的用户工作、不提交或推送，除非用户另行要求。

## 13. 阶段出口与尚待定案项

- [ ] **A 出口**：复核脚本可重跑，统计范围/摘要齐全，归档独有资产可恢复；完成证据校准后再更新思源阅读版。
- [ ] **B 出口**：正文保留、家具清除、媒体完整身份及表格字面契约通过；无隐式重建真实工作区。
- [ ] **C 出口**：候选→原页核证→处置→失效→发布闭环通过；书目与非文本注不被一律判未译。
- [ ] **D 出口**：分块正式写入可恢复且不产生第三权威层；成熟根/疑误登记各自验收。
- [ ] **E 出口**：长度阈值有独立验证或明确暂缓；报告无证据丢失；迁移项逐项有接受/暂缓记录。

尚待在对应任务设计时定案：候选检出边界与规则版本、处置产物 schema、chunk 块身份算法、
多文件事务日志复用方式、报告消费方兼容期、长度核验样本量及质量门槛、各归档功能的采纳决定。
这些不是交由实现者默填的细节：每项须先给最小接口/样例/反例并完成设计复核，再开始实现。

### 本次计划修订验证（不代表实施任务完成）

- 修正后的注文统计脚本实际只读重跑：`notes 16199 no-CJK 6806 identical 3364`，与原统计数一致。
- 文档中 4 个 Python 片段通过语法解析；16 个任务 ID 唯一。
- `git diff --check` 与 `uv run --frozen python scripts/i18n.py --check` 通过。
- 本次仅修订本计划；未执行 src 修复、真实工作区迁移、全量语义审校或思源更新。
  前版思源阅读报告仍待按 A 阶段证据校准结果更新，不是本修订的同步副本。

---

## 14. 实施记录（2026-11-10）

状态：**16 项任务均已落地并有测试证据；未提交、未推送**。本节只记录「做了什么、
怎么验」，语义结论仍受 §10 边界约束。

| 任务 | 交付 | 验证 |
|---|---|---|
| A1 | `scripts/archive_census.py` + §[归档普查口径](2026-11-10-archive-census.md)；区分报告句数与 align 行数、ID 契约与缺文件 | 只读重跑 52 工作区：154,239 / 153,458（差 781 未解释）、16,199 注文、0 重复/空 ID、0 error |
| A2 | `docs/plans/assets/2026-11-10-archive/`：PDF/主题/封面补丁 + MANIFEST（hash、采纳/重做/暂缓） | 清单 hash 与实际文件一致；不含书籍正文/凭证 |
| B1 | 页码/页眉清洗改为证据制：显式/装饰页码、页序递增链才删；裸数字保留并出候选；`kind` 豁免对齐 | `tests/test_structure.py` 24 passed（年份保留、候选、书名页） |
| B2 | `write_structured` 写清洗后段；`structure-clean.json` 台账；`preprocess --force --dry-run` 只读预演 | `tests/test_structure.py` + `tests/test_cli.py` dry-run 只读；幂等 |
| B3 | `media_paths.py` 精确/兼容分级；`media-map.json` 显式迁移（ref/member/reason/sha）；QA/注文门不 basename 兜底 | `tests/test_media_identity.py` 7 passed；`test_notes_media_gate.py` 阻断/映射双例 |
| B4 | 表格单元格 ATX 污染剥离 + `W_CELL_ATX` 独立检测；`# 1`/`C#`/代码保留 | `tests/test_tables.py` 10 passed |
| C1 | `evidence notes`：逐条注文源页证据 → `preprocessing/notes-evidence.json`；缺坐标显式 unknown | `tests/test_source_evidence.py` 15 passed |
| C2 | `note_review.py`：`missing_target`/`identical_to_source`/`no_target_script` 候选；处置绑定源/目标摘要；`notes review` | `tests/test_note_review.py` 5 passed（失效重开、规则版本、未知 ID） |
| C3 | QA 接入 `notes_review_open`；`not_run` 也阻断；报告字段含 open/stale/ids | `tests/test_release_truth_table.py` 新增两例 |
| D1 | `chunks.py` 导出：块身份 + 源摘要 + 不覆盖已有分块；`chunk export` / `import-tr` | `tests/test_chunks.py` 4 passed（围栏不切、旧 .tr 数量校验） |
| D2 | `assemble` 预检（源摘要/块数/标题）+ 事务写入 translation/align + 日志恢复 | 同上：预检不写、事务恢复回滚 |
| D3 | `work-root` 成熟根只报告缺项；`errata` 登记（proposed/confirmed/rejected，证据必填） | `tests/test_work_root.py` 成熟根零写入；`tests/test_errata.py` 3 passed |
| E1 | `length_calibration.evaluate`：误报/漏报评估；**默认阈值不变**（无标注对照集） | `tests/test_length_calibration.py` 3 passed；`docs/quality-control.zh.md` 记录决策 |
| E2 | `g0_summary` + `g0-details.jsonl`（稳定排序、sha256 绑定、总数不丢） | `tests/test_report_summary.py` 2 passed |
| E3 | `output.software_detail` 接线；`doctor` 检查 lock registry vs `UV_INDEX_URL`（只暴露主机名） | `tests/test_config.py`、`tests/test_doctor.py` 各新增一例 |
| E4 | PDF：字体栈/页眉字体/封面 h1+figcaption 剔除/colophon/span bbox redaction；EPUB 主题去 font-family；`dossier` 封面 | `tests/test_pdfexport.py`、`tests/test_cover_hanze.py`；版式基线/token 已显式重录 |

阶段出口：全量 `pytest -q` 1353 passed / 3 skipped（首轮）→ 修正版式/i18n 基线后
`tests/test_i18n.py`、`tests/test_typography_*` 29 passed；`ruff check`、`ruff format --check` 通过。

尚未完成/明确保留：A1 七本书的逐条语义核验；E1 阈值调整（无标注样本）；A2 十款封面
补丁的逐项迁移；`chunk` 的旧 `.tr` 导入只做数量/覆盖预检，不做逐句对齐。

### 14.1 独立审查后的修复（2026-11-10）

独立子代理按 §11/§12 逐项复核后，修复了以下问题（均有回归测试）：

| 审查发现 | 修复 | 验证 |
|---|---|---|
| P0：照搬原文后加一个汉字即可清除注文候选 | 增加 `low_target_script`（汉字占字母+汉字比例 <0.5 且字母 >=10） | `tests/test_note_review.py::test_single_han_character_does_not_clear_candidate` |
| P0：`errata import --apply` 覆盖整本台账 | 按 `(unit, locator)` 合并；同批重复报错；空批次拒绝覆盖 | `test_apply_merges_batches_and_rejects_empty_overwrite` 等 |
| P1：`preprocess --force --dry-run` 仍写 raw/ 且可能走 MinerU | 预览传 `store=None`、禁用 MinerU；测试断言 `store is None` | `test_preview_rebuild_does_not_write_raw` |
| P1：`note-review/media-map` 未进入报告有效性摘要 | 两者加入 `artifacts_digest` 输入清单 | `test_note_review_and_media_map_changes_invalidate_report` |
| P1：相对 workspace + 注文图片 `member()` 崩溃 | `member()` 对两边都 `resolve()` | `test_member_accepts_relative_media_root` |
| P1：源文变更后重导出静默改写索引 | `export` 拒绝改写并提示 `chunk reset`；新增 `reset` 归档旧块 | `test_reexport_after_source_change_requires_explicit_reset` |
| P1：年份/编号序列被当页码删除 | 只认与页序偏移 0–3、跨 >=5 页的链 | `test_strip_page_numbers_keeps_year_sequence` |
| P1：`software_detail=brief` 对版权页无效 | `stamp_document(..., detail=...)` 接线 | `test_stamp_document_detail_applies_to_visible_copyright_section` |
| P1：`.tr` 导入无测试 | 新增预览/应用/数量不符用例 | `test_import_tr_preview_apply_and_count_mismatch` |
| P2：assemble 覆盖手工修订 | 正式译文不同则拒绝，`--force` 才覆盖 | `test_assemble_refuses_to_overwrite_hand_edited_translation` |
| P2：规则版本升级复用旧处置 | 条目内记录 `rule_version`，不符不继承 | `test_note_review` 规则版本用例 |
| P2：同语种/未核证 inventory 误阻断 | 同语种 `applicable=False`；inventory 未核证显式 `inventory_unverified` | `test_note_review`（缺失 review 仍阻断） |
| P2：事务日志相对路径、坏日志静默 | 日志写绝对路径；`recover` 返回 errors 并退出 1 | `test_assemble_rolls_back_when_write_fails` |
| P2：索引路径可越界 | `source_rel`/块文件名白名单校验 | `test_tampered_index_paths_are_rejected` |
| P2：`.tr` 声明超出实际覆盖 | §14 改为已补测试；MANIFEST 不再宣称视觉验收 | — |

**明确暂缓/未验证**（不是通过）：
- PDF 封面 h1/figcaption 剔除、colophon、页眉字体嵌入的**页面视觉比对**未做；只有代码审查与
  局部单测。计划 E4 的视觉证据要求仍未满足。
- 52 个工作区的注文候选只做统计与合成 fixture；**未逐条回原页**，因此不宣称任何一本书
  「整层未译」。
- `translated` 处置在仍有信号时仍被拒绝；这是有意的防假绿设计，文档已说明。
- `chunk` 的块级 align 会改变 `total_sentences` 口径；尚未在真实书上评估影响。

### 14.2 复核轮修复（2026-11-10）

| 复核发现 | 修复 | 验证 |
|---|---|---|
| `low_target_script` 把汉字计入分母，正常中文注含拉丁名即误报 | 分母改为 ASCII 拉丁字母 + 汉字，拉丁 >=3 才判 | `test_normal_chinese_note_with_latin_name_is_not_flagged` |
| 短交叉引用（See p. 5 / Ibid.）加一个汉字仍可清除候选 | 阈值改为拉丁 >=3 | `test_short_cross_reference_with_one_han_is_still_a_candidate` |
| `chunk recover` 可被伪造日志引导删除工作区外文件 | 日志存工作区相对路径；恢复前解析并限制在 `translation/` 下，越界报错 | `test_recover_rejects_journal_paths_outside_translation` |
| `max_chars`/规则版本变化仍会破坏索引 | 与源摘要一起拒绝改写，先 `reset` | `test_reexport_rejects_changed_max_chars` |
| `unit_id` 未校验（`..`） | `_safe_name` 统一拒绝 | `test_reset_rejects_non_unit_id` |
| assemble 只检查 md，不检查 align | translation md 与 align 任一有编辑都拒绝，`--force` 才覆盖 | `test_assemble_refuses_to_overwrite_hand_edited_align` |
| 同语种分流不可达 | `language` 为空时用 `detect_source_language` 采样 | `test_same_language_skips_language_gate` |
| `inventory` 未核证静默关闭语言门 | 显式 `inventory_unverified`，按注文数阻断 | `test_inventory_unverified_does_not_silently_pass` |
| 条目级规则版本不继承缺测试 | 补测试 | `test_entry_rule_version_change_reopens_without_inheriting` |
| errata 旧行缺 `source_sha256` 永不 stale / confirmed 被降级 | 缺字段计 stale；confirmed 不被 proposed 覆盖 | 代码与 `test_apply_merges...` |
| 3 页页码 fixture 与文档「>=3 页」不一致 | 统一为 >=5 页、偏移 0–3；文档与计划同步 | `test_structure.py` 5 页页码 |

仍明确保留（未通过）：
- 3 页单元或前置页偏移 >3 的真实页码会保留为候选，不自动删除（保守策略）。
- 诗歌编号恰好等于页序且跨 5 页仍可能误删；属于无法用纯版面证据区分的残余风险。
- 事务日志仍可被伪造为 `translation/` 内的其他文件；只保证不越出译文目录。
- PDF 页面视觉、52 本书逐条语义核验、真实 `.tr` 分布仍未验证。
