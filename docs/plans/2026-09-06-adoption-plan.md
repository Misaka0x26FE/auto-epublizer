# 计划：跨项目审查借鉴吸收（epub-builder + traditional-translation）

> 状态：**实施中**（2026-09-06 立项；同日扩写为逐项技术设计版，未动代码）。
> 来源：对 `~/github/epub-builder`（Go 姊妹项目）与 `traditional-translation` skill
> 的只读调研（两份审查报告，41+27 项对照），合并去重后分四批落地。
> 本文档是实施的权威依据：每项含现状代码锚点、技术设计、调用点、测试设计与文档同步清单。

## 背景

auto-epublizer 经全面文档-代码一致性审查（`ba04880`）后，与两个同源演化项目对照，
发现核心缺口集中在：

- **语义闭环最后一环**：术语冲突裁决无兜底（conflicts.jsonl 的 open 条目不进任何关卡）；
- **import 登记校验薄弱**：g0.py 已实现的守恒纯函数未接线；align 的 `src` 与
  `structured/` 原文无绑定校验；
- **译者署名/元数据确认通路缺失**：翻译书不记译者；元数据补全只能在 QA 期发现；
- **发布环节整体空白**：管线止于 `qa` 放行，权属/隐私/署名零覆盖。

epub-builder 的元教训：**每个事故沉淀为「带错误码的不变量 + 会失败的测试」**——
本项目 g0.py 里"历史实践提炼但未接线"的纯函数正是最现成的应用对象。

## 已定决策（用户拍板）

1. **译者署名默认规则**：用户无特殊说明时，译者 = **当前操作 CLI 的 agent 框架名称**
   （opencode 处理写 `OpenCode`，豆包处理写 `DouBao`，以此类推）；用户特殊说明则用
   用户指定名。CLI 无法探测 agent 框架（同 doctor 的 multimodal/search），走
   **agent 自报**路线：CLI 提供字段与写入口（`meta` 命令），skills 文档写明自报规则。
2. **落地方式**：先立本计划，再分批逐个实现；每批一次提交（回归测试 + ruff 全绿）。

## 原则边界（全程不变）

- 唯一 LLM 原则：全部借鉴项均为零 token 确定性校验或纯文档，不新增任何 LLM 调用。
- 学 epub-builder 的**校验**而非其**交换格式**：md + align.jsonl 对 agent 友好，保留；
  借鉴 hash 绑定 / 守恒不变量 / 生命周期门禁的**机制**。
- 不借鉴项（调研已否决）：observation-only 源登记（facts.* 更强）、packet JSON 交换格式、
  plan 操作语言（结构由 CLI 确定性派生）、AIProvenance 模型溯源、Calibre 工具链。

---

## S1 CLI 批·放行门与守恒接线

### 1.1 未决术语冲突进 G5 放行门

**现状锚点**：`orchestrator.import_translations`（orchestrator.py:369-462）在 import 时
把冲突**追加式**外置到 `analysis/glossary_conflicts.jsonl`（`write_conflicts_jsonl`，
csv_io.py:108，每行 `GlossaryConflict.as_jsonl()`，含 `status` 字段，默认 `"open"`）；
`read_conflicts_jsonl`（csv_io.py:120）返回 `list[dict]`（按 source+proposed_target 去重）。
但 `orchestrator.qa`（orchestrator.py:536）与 `generate_report`（qa/report.py:47）**完全不读
该文件**——同一术语两种译法可并存到成品。

**技术设计**：

1. `qa/report.py`：
   - `QaResult` 新增字段 `glossary_conflicts_open: int = 0`（放在 `g0_terminology_open`
     之后，注释「术语冲突未裁决数：真实缺陷，必须清零才能放行」）。
   - `generate_report` 新增关键字参数 `glossary_conflicts_open: int = 0`，透传进 QaResult。
   - `released` 条件追加 `and glossary_conflicts_open == 0`。
   - `released_reason` 判定链在 `terminology_open` 之后插入：
     `elif glossary_conflicts_open: reason = "glossary_conflict_open"`。
     完整顺序：`ok → terminology_open → glossary_conflict_open → structure_open（S1.2 加）→
     unresolved_confirmed → audit_failed → provenance_incomplete → epubcheck_not_run →
     epubcheck_errors`。
2. `orchestrator.qa`：在调 `generate_report` 前统计——
   ```python
   from auto_translator.glossary import read_conflicts_jsonl

   conflicts_open = sum(
       1
       for c in read_conflicts_jsonl(store.analysis_dir / "glossary_conflicts.jsonl")
       if c.get("status") == "open"
   )
   ```
   作为 `glossary_conflicts_open=conflicts_open` 传入。
3. `cli.py qa` 输出：G0 告警行追加 `术语冲突 open：{report['glossary_conflicts_open']}`。

**测试设计**（tests/test_qa.py）：
- `test_generate_report_glossary_conflict_blocks_release`：audit ok + epubcheck ran/0 错 +
  provenance 干净 + `glossary_conflicts_open=2` → `released is False`、
  `released_reason == "glossary_conflict_open"`。
- 现有 `test_generate_report_released_when_clean` 天然回归（默认 0 不阻断）。
- 集成侧（tests/test_import.py 追加）：造 `glossary_conflicts.jsonl`（status=open 一行）
  + 跑 `orch.qa` → report 里 `glossary_conflicts_open == 1`（需先 build 一个最小 epub）。

**文档同步**：AGENTS.md 六道关 §6 放行条件；docs/quality-control.md §2 G5 放行条件 +
report.json 示例字段；skills qa.md 放行条件表、review.md G3 裁决段（「裁决写回前
qa 不放行」）；S3.2 invariants.md 一并收录。

### 1.2 标记/注码守恒接线为 G0 硬错误

**现状锚点**：`review/g0.py` 已有纯函数 `count_markers`（`_MARKER_RE = \{\w+:\d+\}`，
匹配 `{fig:NNN}` 等插入标记）与 `count_footnote_refs`（`_FOOTNOTE_REF_RE`，句末标点后
1-3 位数字，PDF 文字层注码表示）；但 `g0_unit_flags`（g0.py:194）只跑
align/length/terminology 三类。脚注在 structured md 里还有第二种表示：pandoc 语法
`[^label]` 引用 / `[^label]: 文本` 定义（build/html.py:30-31 的 `_FN_REF`/`_FN_DEF`，
渲染为 EPUB 弹窗脚注）——两种表示都要守恒。

**技术设计**：

1. `review/g0.py` 新增：
   ```python
   _FN_PANDOC = re.compile(r"\[\^[^\]\s]+\]")  # pandoc 脚注引用/定义统一计数


   def count_footnote_marks(text: str) -> int:
       """统计 pandoc 脚注标记（[^label] 引用与定义）数量。"""
       return len(_FN_PANDOC.findall(text or ""))
   ```
2. `g0_unit_flags` 改为**单元级总量守恒**（不做行级比对——拆句/并句会把标记挪到
   相邻行，行级比对会误报；总量守恒恰好对应「一个都不能丢」）：
   - 循环内累计 `sum_marker_src/tgt = count_markers(src/tgt)`、
     `sum_fn_src/tgt = count_footnote_refs(src/tgt) + count_footnote_marks(src/tgt)`；
   - 循环后：
     ```python
     if sum_marker_src != sum_marker_tgt:
         flags.append(
             G0Flag("marker", "插入标记数量不守恒", {"src": sum_marker_src, "tgt": sum_marker_tgt})
         )
     if sum_fn_src != sum_fn_tgt:
         flags.append(G0Flag("footnote", "脚注标记数量不守恒", {"src": sum_fn_src, "tgt": sum_fn_tgt}))
     ```
   - 函数签名不变（仍是 `rows + glossary` 纯函数），三个调用点
     （import/g0_check/_collect_g0_flags）零改动即生效。
3. `qa/report.py`：
   - `QaResult` 新增 `g0_structure_open: int = 0`（注释：标记/脚注守恒违例数，
     真实缺陷）。
   - `generate_report` 计算
     `g0_structure_open = sum(1 for f in flags if f.get("check") in ("marker", "footnote", "table", "fidelity"))`
     （table/fidelity 由 S4.1/S4.2 加入同一计数器，预留）。
   - `released` 追加 `and g0_structure_open == 0`；reason 链在 glossary_conflict_open
     之后插 `elif g0_structure_open: reason = "structure_open"`。
4. `orchestrator.import_translations`：warned 收集条件
   `if f.check in ("length", "terminology")` 扩为
   `("length", "terminology", "marker", "footnote", "table", "fidelity")`
   （import 期仍是告警不阻断——与 terminology 同语义：当场修最好，漏修被 G5 兜底）。
5. `cli.py`：
   - `import_cmd` 红色告警判定 `w["check"] == "terminology"` 扩为集合
     `{"terminology", "marker", "footnote", "table", "fidelity"}`；汇总行加
     「其中硬缺陷 X 条（术语/标记/脚注/保真/表格）」。
   - `g0` 命令：`n_term` 之外再计 `n_structure`，输出行同步；红色判定同上集合。

**测试设计**（tests/test_review.py + test_qa.py）：
- `test_g0_marker_conservation_flag`：rows=3 行，src 共 2 个 `{fig:1}`/`{fig:2}`，
  tgt 只剩 1 个 → 1 条 `check=="marker"`；src/tgt 数量相等 → 0 条。
- `test_g0_footnote_conservation_flag`：① pandoc 式：src 含 `text[^1]` 与
  `[^1]: note`，tgt 丢定义 → `check=="footnote"`；② 数字式：src `"end.12"`，
  tgt 无注码 → `check=="footnote"`；③ 拆句场景：src 行 1 含 `[^1]`，tgt 把 `[^1]`
  放到行 2（总量相等）→ 0 条（防误报回归）。
- `test_qa.py::test_generate_report_structure_blocks_release`：flags 含
  `check=="marker"` 一条 → `released is False`、`released_reason == "structure_open"`。

**文档同步**：g0.py 模块 docstring 的「接线状态」段（三类 → 五类）；AGENTS.md 六道关
§1（G0 检查项加标记/脚注守恒）与 §6；docs/quality-control.md §2 G0 表加两行 +
放行条件；skills review.md G0 行与验收阈值表、translation.md「特殊段处理」提标记
不可丢、qa.md 放行条件表。

### 1.3 G4 四小检查

**现状锚点**：`qa/audit.py::audit_epub`（audit.py:72-326）。① `names = zf.namelist()`
（L82）未查重复条目；② `<img src>` 外链在两处被 `_HTTPS.match(src): continue` 跳过
（L153 悬空检测、L197 媒体审计）——外链图直接放行；③ nav 只查 href 可解析（L128），
不查 spine↔nav 覆盖；④ `W_META_INCOMPLETE`（L264-276）只查标签 needle 存在，
不查非空。

**技术设计**（全部在 `audit_epub` 内，追加/修改四处）：

1. **`E_ZIP_DUPLICATE`**（插在 §1 mimetype 检查后）：
   ```python
   from collections import Counter

   dupes = [n for n, c in Counter(names).items() if c > 1]
   for d in dupes:
       result.add("error", "E_ZIP_DUPLICATE", f"zip 条目名重复：{d}")
   ```
   zip 规范允许同名条目（后者遮蔽前者），构建器不会产生但手改包可能——重复即内容
   不可信。
2. **`E_IMG_REMOTE`**（§4b 循环，L153 的 `_HTTPS` 跳过改为报错）：
   ```python
   if _HTTPS.match(src):
       result.add(
           "error", "E_IMG_REMOTE", f"img src 为外部链接（媒体必须打包进 EPUB）：{name} -> {src}"
       )
       continue
   ```
   L197 媒体审计循环的 `_HTTPS` 跳过保留（外链已在 4b 报 error，此处无需重复）。
   依据：EPUB 阅读器普遍离线，远程资源 = 丢图；epubcheck 也会报 remote resource，
   本检查让无 jar 环境也自足。
3. **`E_TOC_COVERAGE`**（§4 nav 检查后新增双向覆盖）：
   - 解析 nav.xhtml 的 toc 区：`re.search(r'<nav[^>]*epub:type="toc"[^>]*>(.*?)</nav>',
     content, re.DOTALL)`（无 epub:type 时回退整个 `<nav>`，与 provenance.py
     `_nav_depths` 同策略）；收集其中 `href="([^"]+)"` 去掉 `#fragment`，按
     `(Path(nav).parent / href).as_posix()` 归一 → `nav_docs: set[str]`。
   - spine 侧：复用已有的 `spine_idrefs` + `manifest_ids`，补一个
     `id2href: dict[str, str]`（从 `<item>` 的 id/href 对构建，provenance.py
     `_spine_docs` 同款解析），`spine_docs = [id2href[r] for r in spine_idrefs]`
     归一到包内路径。
   - 双向比对（排除 `nav.xhtml`/`landmarks.xhtml` 自身与封面文档——封面
     `linear="no"` 不要求进 nav）：
     - spine 文档不在 nav_docs → error，`f"spine 文档未进目录：{doc}"`；
     - nav href 不在 spine_docs → error，`f"nav 条目不在 spine：{href}"`。
   - 均归并 code=`E_TOC_COVERAGE`（每缺失项一条，message 分上述两种措辞）。
4. **`W_META_INCOMPLETE` 查非空**（§10 改判定）：
   ```python
   missing_meta = [
       tag
       for tag in ("dc:creator", "dc:date", "dc:publisher", "dc:rights")
       if not re.search(rf"<{tag}>\s*\S[^<]*</{tag}>", opf)
   ]
   ```
   （标签缺失**或**内容空白都算 missing；code/message 不变。）

**测试设计**（tests/test_qa.py，正反各一）：
- `test_audit_zip_duplicate`：`zipfile.ZipFile` 对同名 `writestr` 两次构造坏书 →
  `E_ZIP_DUPLICATE` 存在且 `not result.ok`。
- `test_audit_remote_img_blocks`：render_document 一篇含
  `<img src="https://example.com/x.png"/>` 的文档 → `_make_epub` 组包 →
  `E_IMG_REMOTE` 存在；本地图正常书（现有 `test_audit_valid_epub`）不误报。
- `test_audit_toc_coverage`：正常 build 的书 nav/spine 双向齐 → 无该码；再手工从
  zip 移除 nav.xhtml 中某章 `<li>`（重打包）→ `E_TOC_COVERAGE` 报「spine 文档未进
  目录」；反向在 nav 里塞一条指向非 spine 文档的 `<li>` → 报「nav 条目不在 spine」。
- `test_audit_meta_empty_value`：OPF 手工替换 `<dc:date>2026</dc:date>` 为
  `<dc:date></dc:date>` → W_META_INCOMPLETE 含 dc:date；正常书不含。

**文档同步**：docs/quality-control.md §2 G4 审计码清单 + postprocessing-spec.md
§4 P2 码表补四码；skills qa.md 错误码表补四行（含义+处置一句话：远程图→改本地
路径重新 build；nav 覆盖→查 translation md 标题层级缺失）。

---

## S2 CLI 批·译者署名与元数据确认

### 2.1 译者署名通路（`meta` 命令 + OPF 输出）

**现状锚点**：`PublicationMeta`（workspace/models.py:60-78）有 `creator` 无 `translator`；
OPF 渲染在 `build/__init__.py::_render_opf`（L165-166：
`<dc:creator>{escape(meta.creator)}</dc:creator>`，无 id 属性、无 role 声明）；
publication.json 只经 CLI 命令推进（红线：agent 不手编）——所以补元数据必须有 CLI
写入口，现状没有（init 只在初始化时写一次嗅探值）。

**技术设计**：

1. `workspace/models.py`：`PublicationMeta` 在 `creator` 后加
   `translator: str | None = None`（docstring：译者；默认由 agent 按框架名自报，
   见 skills/preprocessing.md）。
2. **新命令 `auto-epublizer meta`**（cli.py + orchestrator.py）：
   ```
   auto-epublizer meta [--title T] [--creator C] [--translator X]
                       [--publisher P] [--date D] [--rights R]
                       [--workspace DIR] [--config PATH]
   ```
   - `orchestrator.set_meta(store, *, title=None, creator=None, translator=None,
     publisher=None, date=None, rights=None) -> dict`：`pub = store.load_publication()`，
     对每个非 None 参数 `setattr(pub.meta, k, v)`（空串视为清空该字段），经 store
     的既有保存路径落盘（与 `set_unit_status` 同一原子写入口），
     `store.log_event("meta_update", fields=[改动的字段名])`，返回
     `{"updated": [字段名列表], "meta": pub.meta.model_dump()}`。
   - `cli.py`：typer 选项全 `str | None`；输出「元数据已更新：title, translator」。
   - 该命令同时是 S2.2 元数据核对与 3.5 译者署名的唯一写入口（init 不加
     `--translator`，避免两个入口）。
3. **OPF 渲染**（`_render_opf`）——EPUB 3 规范的 creator+role 写法：
   ```python
   if meta.creator:
       m.append(f'    <dc:creator id="creator-aut">{escape(meta.creator)}</dc:creator>')
       m.append('    <meta refines="#creator-aut" property="role" scheme="marc:relators">aut</meta>')
   if meta.translator:
       m.append(f'    <dc:creator id="creator-trl">{escape(meta.translator)}</dc:creator>')
       m.append('    <meta refines="#creator-trl" property="role" scheme="marc:relators">trl</meta>')
   ```
   （原作者标 `aut`、译者标 `trl`；两 id 全包唯一；convert 路径 translator 为空则
   整段不输出，单语转换书不受影响；双语/纯译 EPUB 均生效——渲染层不区分。）
4. audit 不加新码（translator 可选，不进 W_META_INCOMPLETE）。

**测试设计**：
- tests/test_build.py `test_build_epub_translator_creator_role`：
  `meta=PublicationMeta(..., creator="Author", translator="OpenCode")` → OPF 含
  `id="creator-trl"` 的 dc:creator、`refines="#creator-trl"` 的 role meta 且值为
  `trl`；`translator=None` → 无 `creator-trl`；`creator` 有值时含 `creator-aut`
  + role `aut`。
- tests/test_cli.py `test_meta_command_updates_fields`：CLI runner 调
  `meta --translator OpenCode --publisher "Test"` → publication.json 里两字段更新、
  events.jsonl 追加 `meta_update` 事件；再跑一次 `meta --translator ""` → 清空。
- epubcheck 兼容性由现有 e2e（有 jar 时）覆盖 refines 语法。

**文档同步**：AGENTS.md 标准流程命令清单加 `meta` 一行 + 六道关无涉说明；
docs/configuration.md 无新配置；skills workflow.md 命令总览、preprocessing.md
（元数据核对→`meta` 写回）、translation.md（交付前署名）各补；README 命令速览加一行。

### 2.2 元数据「确认而非推断」前移到预处理期

**现状锚点**：facts 嗅探的元数据来自源文件（PDF/EPUB/DOCX 自带 metadata，常错/缺/
乱码）；`W_META_INCOMPLETE` 在 qa 期才告警（太晚且只查非空不查真伪）；
facts.py 的 `agent_todo` 列表（facts.py:142-）是 facts.md 待办清单的唯一数据源，
`render_facts_md`（facts.py:304-306）逐条渲染 `- [ ] {todo}`。

**技术设计**：
1. `preprocess/facts.py` 的 `agent_todo` 列表头部插入一条：
   ```
   "元数据核对：对照源文版权页/题录核实 facts 嗅探的 title/creator/publisher/date/
    rights（嗅探值仅是推断，常错常缺；存疑处询问用户；确认/补全后用
    auto-epublizer meta 写回 publication.json；译者署名默认=你的 agent 框架名，
    如 OpenCode/DouBao，用户指定名优先）"
   ```
2. skills/preprocessing.md §2 完成判据前加一小节「元数据核对」（含上述规则与
   `meta` 命令用法）；qa.md 的 `W_META_INCOMPLETE` 处置行改为「应在预处理期已核对，
   QA 期再报即回溯补」。

**测试设计**：tests/test_preprocess.py 现有 facts 断言追加：`facts["agent_todo"][0]`
含「元数据核对」；`facts.md` 文本含 `- [ ] 元数据核对`。

**文档同步**：同上 skills 两处 + AGENTS.md 预处理段提一句（facts 待办含元数据核对）。

---

## S3 文档批（纯 skills，零代码）

### 3.1 新增 `references/publishing.md`（发布/隐私/署名 gate）

**结构设计**（新文件，约 120 行）：

1. **定位**：`qa` 的 `released=true` 只代表**交付质量**合格 ≠ 可发布；发布是
   agent+用户的语义与法律决策，本 reference 是发布前 gate 清单。
2. **发布前 gate（按序执行，任一不过即停）**：
   - **权属基础确认**：确认原书再分发许可（公有领域/授权/自译自发布）；不确定 →
     默认私有仓库或停下问用户；记录权属结论进发布说明。
   - **隐私扫描**：发布树扫 API key/token 模式、绝对本地路径（`/home/`、`C:\Users\`）、
     用户个人数据；`git log -p` 抽查历史无上述内容；report.json/events.jsonl 不含
     敏感路径；**`.gitignore` 不能移除已跟踪文件**（需 `git rm --cached`）；
     封面/插图权属与原书一致。
   - **README 署名记录**：模板含原书题录（书名/作者/版次/ISBN/来源语言）、权属
     声明、译者署名（= publication.json 的 translator，默认 agent 框架名）；
     不虚报 builder 未实际输出的元数据、不虚列贡献者。
   - **成品验证**：从发布渠道下载已传资产、核对校验和（sha256）、至少一个阅读器
     打开验证渲染。
3. **发布操作**：tag 规范 `<slug>-v<N>`；纠错发新版本、**不强推已发布 tag**；
     **禁止在有源文件的目录 `git add -A`**（防 source/ 工作区误提交）；发布记录
     （版本/日期/变更）追加到仓库。
4. **封面 gate**：确认可再分发后才使用封面（facts.media.cover_candidates 有候选
     数据）；权属不明 → 无封面交付（`W_NO_COVER` 可接受）。
5. 尾部链接 invariants.md（放行条件全集）与 review.md（G5 判读）。

**配套**：SKILL.md 路由表加行「要发布/分发成品（GitHub release/私有分发）→
`references/publishing.md`」；manifest.json 的 references 数组加 `"publishing"`。

### 3.2 新增 `references/invariants.md`（不变量速查卡）

**结构设计**（新文件，约 100 行，单一参考供校验/排障时读）：

1. **六道关一览表**：关卡 / 谁做（CLI vs agent）/ 硬门 / advisory。
2. **G5 放行条件全集**（对齐 `qa/report.py::generate_report` 代码）：
   `confirmed_resolved`、`g0_terminology_open==0`、`g0_structure_open==0`（S1.2）、
   `glossary_conflicts_open==0`（S1.1）、`epubcheck.ran and errors==0`、`audit.ok`、
   `prov_ok`（coverage≈1.0/units_missing/media_lost/toc_flat/inserts_missing_files/
   findings 无 error 级）+ `released_reason` 七值枚举表（ok/terminology_open/
   glossary_conflict_open/structure_open/unresolved_confirmed/audit_failed/
   provenance_incomplete/epubcheck_not_run/epubcheck_errors）及各自处置指引。
3. **G0 硬错误 vs advisory 清单**：硬（terminology/marker/footnote/fidelity/table）vs
   advisory（length）——各自含义与修法一句话。
4. **G4 错误码速查表**：audit.py 全部 E_*/W_*（含 S1.3 四新码）+ provenance.py 的
   E_UNIT_*/E_MEDIA_*/E_TOC_FLAT/E_INSERT_*/W_*，三列：码 / 级别 / 一句话处置。
   （实现时从代码逐条提取，qa.md 现有表为底稿。）
5. **工作区契约压缩版**：状态机七态+推进命令、目录树（AGENTS.md 工作区契约的
   精简引用）、`import` 阻断（结构性错误）vs 告警（硬缺陷类 advisory）边界。
6. **构建约束**：三主题枚举、冻结时间戳（确定性构建）、双语成对、无样式模板红线。

**配套**：manifest.json references 加 `"invariants"`；SKILL.md 路由加行「校验失败
排障 / 放行条件 / 错误码速查 → invariants.md」；qa.md/review.md 头部加「速查见
invariants.md」防两处漂移（详细判读留在各自文档，速查卡只做索引层）。

### 3.3 SKILL.md 编号红线清单

在 SKILL.md「唯一 LLM 原则」段后新增「不可协商红线」小节（8 条，编号引用）：

1. 不手编 `publication.json`——状态只经 CLI 命令推进（import/g0/qa/meta）。
2. `source/` 与 `references/user/` 绝不改动。
3. 结构（切章/标题层级）翻译前定稿；中途改动必须重走受影响单元（重 ingest +
   重译），旧译文不作数。
4. G0 术语命中/标记守恒/源保真/表格形状是**缺陷不是建议**，放行前必须清零；
   长度比才是 advisory。
5. EPUB 不是真相源——发现成品问题改 `translation/` + `align/` 后重新 build，
   不手补成品文件。
6. `qa` released ≠ 可发布：发布前必须过 `publishing.md` 的权属+隐私 gate。
7. 唯一 LLM 原则：CLI 零 token；一切语义判断由你完成，禁止引入任何 LLM API 调用。
8. 译者署名默认=你的 agent 框架名（OpenCode/DouBao…），用户指定名优先（经
   `meta --translator` 写入）。

### 3.4 传统工作区指纹路由边界

SKILL.md 路由表加一行 + workflow.md「阶段路由」开头加一段：

> 目录含 `split/`、`split_translated/`、`.progress`、根 `GLOSSARY.csv`、
> `_analysis.md`、`_understanding.md` 等传统指纹 → **停下**：这是 traditional-
> translation skill 的文件式工作区；要么换用该 skill 续跑，要么与用户确认迁移。
> 迁移 = 以 `source/` 原文件重新 `init`/`preprocess` 的**语义重做**；legacy 译文与
> 报告只作对照证据（可参考其译法），**禁止**把 legacy 文件直接拷进 publication.json
> 工作区或当 canonical ID 使用。

### 3.5 操作纪律补句（四处）

| 文件 | 位置 | 补句内容 |
|---|---|---|
| translation.md | 「术语三态闭环」图后 | 「裁决写回 glossary.csv 后，对**全部已译单元**重跑 `g0`——旧译法违例当场清零，不要只查新译单元。」 |
| ingest.md | 「注意事项」末尾 | 「对 structured/ 做批量改写（清洗/OCR 修正）后，抽首/中/尾代表页与 raw/ 页证据（page-NNN.json 或页图）对照，防批量清洗静默吞内容。」 |
| review.md | 「G1 问题类型」前 | 「抽样策略：小书（≤10 单元）全审；大部头按章节类型 × 高风险特征分层抽样，高风险必审——论证密集/表格脚注引文密集/多语材料/OCR 存疑段（对齐 risks.md 与 units/<id>.md 的风险标注）/复杂版式/**每章首尾单元**；其余随机抽查。」 |
| preprocessing.md | §2 完成判据附近 | 「译者署名：capabilities.md 自报你的 agent 框架名（OpenCode/DouBao…）；用户指定名优先；核对元数据时经 `meta --translator` 写入。」 |

### 3.6 manifest 版本门禁（收尾）

**现状**：manifest.json **已有** `minimum_cli_version: "0.1.0"`（调研时已确认），
缺的只是 SKILL.md 的执行步骤。补：SKILL.md「Route Before Acting」首段加一句——

> 先跑 `auto-epublizer version`，若低于本目录 `manifest.json` 的
> `minimum_cli_version`，停止并提示用户升级 CLI（skill 与 CLI 契约不兼容）。

---

## S4 大件批

### 4.1 align 源绑定校验（源保真 fidelity）——**做（首选）**

**现状锚点**：align 行的 `src` 是 agent 手写（translation/align/<id>.jsonl，
`{"seq","src","tgt","note"}`），`check_alignment`（g0.py:176）只查 seq 连续与非空；
`qa/provenance.py` 的逐段覆盖率（`_paragraphs` L76-83：跳标题行、按空行切块；
`_norm` L71-73：去全部空白）只在 **qa 期**做 structured→align 的**单向**块级覆盖，
且 agent 改写/杜撰 src（反向）完全无检测；import 期零源校验。

**技术设计**：

1. **新模块 `auto_translator/review/fidelity.py`**（纯函数，依赖方向合规：
   auto_epublizer → auto_translator）：
   ```python
   def norm_text(text: str) -> str:
       """归一化：去除全部空白字符（与 provenance._norm 同规则，抽公共）。"""


   def content_blocks(structured_md: str) -> list[str]:
       """正文块：按空行切，跳标题行（#开头）、空块、纯 HTML 注释块。"""


   def all_lines(structured_md: str) -> list[str]:
       """全部非空行（含标题行）——反向匹配语料。"""


   def fidelity_flags(structured_md: str, rows: list[dict]) -> list[G0Flag]:
       """双向源保真（块级）：
       前向（漏译/漏抄）：每个 content_block 的 norm 不在
         "".join(norm(r['src']) for r in rows) 中 → warning 级语义的
         G0Flag("fidelity", "源文块未进对照表", {index, head: 前40字})
         （可能是合法剔除——版权残句/页眉残留，provenance 在 qa 给总量视角）。
       反向（抄错/改写/杜撰）：每行 norm(src) 不在 "".join(norm(all_lines))
         中 → G0Flag("fidelity", "对照表 src 不在源文中（疑抄错/改写）", {seq})。
       """
   ```
   匹配语义说明（写进 docstring）：块级拼接子串匹配天然容忍拆句/并句/句序调整；
   勘误先例**只改 tgt** 并用 note `corr:` 留痕（g0.py `annotate_correction_notes`
   契约「不改 src/tgt 文本」），src 若被「顺手修正」会被反向检查抓出——这正是要抓的。
2. **g0.py 接线**：`g0_unit_flags` 新增可选参数
   `structured_md: str | None = None`；非 None 时在函数末尾
   `flags.extend(fidelity_flags(structured_md, rows))`。保持纯函数、缺省 None 时
   行为不变（向后兼容）。
3. **orchestrator 三个调用点**（都持有 store 与 unit）：
   - `import_translations`：读 `structured_path = store.structured_dir / rel_path`
     （rel_path 相对 structured/，与 translation 镜像同路径），文件存在则传
     `structured_md=structured_path.read_text(encoding="utf-8")`；fidelity 的
     **反向**违例进 errors（阻断登记：对照表 src 造假不可信），**前向**缺块进
     warned（advisory，同 marker 语义）。
   - `g0_check` / `_collect_g0_flags`：同样传 structured_md，全部 fidelity flag
     计入 flags（check="fidelity"）。
4. **provenance.py 重构去重**：删本地 `_norm`/`_paragraphs`，改
   `from auto_translator.review.fidelity import norm_text, content_blocks`（调用点
   两处替换）；coverage 聚合逻辑不变。单一实现防两处规则漂移。
5. **report/CLI**：fidelity 并入 `g0_structure_open` 计数（S1.2 已预留 "fidelity"
   在集合里）与 cli.py 红色判定集合；无需新增字段。

**边界情况（设计已覆盖，写入测试）**：标题行不进前向语料但进反向语料（agent 把
标题作为 seq 1 的 src 不误报）；`{fig:NNN}` 行/图片行/表格行都是普通块（在两侧
语料中）；版权残句合法剔除只触发前向 advisory 不阻断。

**测试设计**（tests/test_review.py 新增 `test_fidelity_*` + test_import.py）：
- 双向干净（dogfooding 式样例）→ 0 flag。
- 反向：src 行 `"First sentence here, friend!"`（源文是 `"First sentence here."`）
  → 1 条 fidelity flag；集成：import 该单元 → failed.errors 含「不在源文中」。
- 前向：structured 三段、align 只覆盖两段 → 前向 flag；import 仍成功（warned）。
- 标题作为 align 首行 src → 反向无 flag（回归防误报）。
- provenance 重构回归：现有 test_provenance.py 全绿即验证替换正确。

**文档同步**：AGENTS.md 六道关 §1（G0 加「源保真」）+「能力分工」提一句；
quality-control.md §2 G0 表加行；skills translation.md（align 契约强调 src 原样
摘抄）、review.md（G0 检查项）、qa.md（structure_open 处置）。

### 4.2 表格形状守恒——**做**

**现状锚点**：表格经 `ingest/tables.py` 双路径提取成 md 管道表格进 structured；
agent 整表翻译时改列数/丢分隔行/转义管道符出错，G0/构建/epubcheck 都定位不到
「表格结构被译坏」。epub-builder 的 `mergeTable`（形状+源单元格锁定）证明该不变量
价值；我们以**校验**而非交换格式落地。

**技术设计**（`review/g0.py` 新增三个纯函数 + orchestrator 接线）：

1. ```python
   _SEP_LINE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")

   def _count_cols(line: str) -> int:
       body = line.strip().strip("|")
       return len(re.split(r"(?<!\\)\|", body))

   def parse_md_tables(md: str) -> list[dict[str, int]]:
       """解析管道表格 → [{"rows": R, "cols": C}]。行含 | 且非空为表格行；
       连续表格行块的第 2 行须是分隔行才算表；跳过 ``` 围栏内的行；
       转义管道 \\| 不计列。"""

   def table_shape_flags(src_md: str, tgt_md: str) -> list[G0Flag]:
       """表格数不等 → 1 条 flag；逐表 rows/cols 不等 → 各 1 条
       G0Flag("table", "表格形状不守恒", {index, src: "RxC", tgt: "RxC"})。"""
   ```
2. **接线**：orchestrator 新增私有助手
   `_unit_doc_flags(store, unit) -> list[G0Flag]`：读
   `store.structured_dir / rel_path` 与 `store.translation_dir / rel_path`（均存在
   才比对），返回 `table_shape_flags(src_md, tgt_md)`。
   - `import_translations`：结果并入 **errors（阻断）**——表格形状坏了=译文文档
     结构性损坏，必须修了才能登记（严于 marker/fidelity 的 advisory，理由：
     坏表格会直接进 build 产物）。
   - `g0_check` / `_collect_g0_flags`：并入 flags（check="table"，进
     `g0_structure_open`）。
3. **report/CLI**：check="table" 已在 S1.2 预留的集合内，零额外改动。

**测试设计**：test_review.py——`test_parse_md_tables`（基本表 3 行 4 列；无分隔行
的 `|` 行不算表；围栏内不算；`\|` 转义不增列）；`test_table_shape_flags`（同形
→ 0；tgt 少一行 → 1 条含 `"2x4"`/`"3x4"`；tgt 多一张表 → 1 条）。test_import.py
集成——译文表格坏 → import failed 含「表格形状」。

**文档同步**：quality-control.md G0 表加行；skills translation.md「特殊段处理」的
表格段加「形状必须与源一致（行列数/分隔行），import 会硬校验」；structure.md
契约行同步。

### 4.3 结构冻结门禁——**暂不做（记录理由与重开条件）**

**完整设计（若重开时照此实现）**：`Publication` 加 `structure_frozen: bool = False`
+ `frozen_at: str`；新命令 `freeze`（要求全部单元 ≥ split；写 frozen 标记 +
log_event）与 `unfreeze`（清标记并提示「structured 改动后受影响单元需重走」）；
`import_translations` 开头校验未冻结即报错（提示先 freeze，等价于「标题定稿后才
开译」的机器化）；`_render_opf` 不变（dcterms:modified 已确定性冻结）。

**否决理由**：4.1 源保真 + provenance 覆盖率已能在事后确定性地抓出「结构变更后
的陈旧译文」（块不匹配 → fidelity/coverage 违例 → G5 阻断），freeze 的增量价值
只剩「事前阻止」；而代价是每本书多两个必经命令（freeze/unfreeze）、忘记 freeze
会让 import 直接失败——工作流摩擦大于收益，且尚无「翻译中途改 structured 导致
成品混入新旧结构」的实际事故。

**重开条件**：dogfooding/实战出现上述事故 ≥ 1 次，或引入 agent 可改结构的机制
（如未来 inserts 重排）时，按上述设计实现。

### 4.4 SourceCatalog 源完整性契约——**做最小形态（排在 4.2 后）**

**现状锚点**：完整性保障现只有译侧（provenance_coverage / units_missing /
toc_missing）+ facts 的源 TOC；「源里有但没收录」的**源侧**盘点（尤其护封/腰封/
书脊等有意不进 EPUB 的实体元素、被排除项的理由留痕、未决项阻断交付）无任何
机器契约。epub-builder 的 SourceCatalog（included/physical/unresolved 三态 +
`E_SOURCE_ITEM_UNBOUND`/unresolved 阻断 release）验证了该模式。

**技术设计（最小形态）**：

1. **契约文件**：`preprocessing/catalog.csv`（agent 在预处理期撰写，**可选**——
   不存在则全部检查跳过，零破坏）。列：
   `item,kind,status,locator,unit_id,note`
   - `item`：源内条目名（TOC 标题/图号/表号/脚注号/实体元素名）；
   - `kind`：`toc|figure|table|footnote|section|physical`；
   - `status`：`included`（已收录）| `physical`（实体书元素，有意不进 EPUB，
     如护封/腰封/书脊）| `excluded`（有意排除，note 必填理由）| `unresolved`
     （未决，阻断交付）；
   - `locator`：绝对定位（页码/href/bbox）；
   - `unit_id`：included 时必填（收录到哪个单元）。
2. **读取与校验**（新函数放 `orchestrator.py`，复用 csv 标准库）：
   `read_catalog(store) -> list[dict] | None`（文件不存在返回 None；列缺失/取值
   非法 → `OrchestrationError`，中文提示行号）。
3. **status 接线**：`orchestrator.status` 返回值加
   `catalog: {present: bool, items: int, included_bound: bool, unresolved: int}`
   ——included 行的 unit_id 必须存在于 publication.units（不存在 →
   `included_bound=False`，stale 提示 `catalog_binding_broken`）。
4. **qa 接线**：catalog 存在时，`generate_report` 新增
   `catalog_unresolved_open: int`（status=unresolved 条数）；
   `released` 追加 `and catalog_unresolved_open == 0`；reason 链加
   `catalog_open`（位置在 provenance_incomplete 之后）。included 未绑定不进
   放行门（status/stale 已提示，属登记错误而非内容缺失）。
5. **agent 撰写指引**：preprocessing.md 待办加「源盘点：写 preprocessing/catalog.csv，
   逐项声明源内容去向（含 physical/excluded 的留痕理由）」；todo.md 模板加源盘点节。

**测试设计**：test_import.py 或新 test_catalog.py——catalog 不存在 → qa 不受影响
（回归）；catalog 含 2 条 unresolved → qa report `catalog_unresolved_open==2`、
`released_reason=="catalog_open"`；included 指向不存在 unit → status
`included_bound=False`；kind/status 非法值 → OrchestrationError。

**文档同步**：AGENTS.md 工作区契约（preprocessing/ 产物列表加 catalog.csv）+ 六道关
§6；postprocessing-spec.md §5 放行条件加一条；skills preprocessing.md/qa.md/
invariants.md。

### 4.5 错误码目录 + `{code,severity,path}` 结构化 issue——**暂缓**

**设计草图**：`G0Flag` 加 `code: str = ""`（如 `G0.TERM_MISSING`/`G0.MARKER_LOST`）
与 `severity: str = "warning"`；report.json 的 g0_flags/provenance_findings 统一
`{code, severity, path, message}`；skills 文档给码表。**暂缓理由**：report.json 的
消费方（skills 文档、CLI 输出、agent 判读）刚在 `ba04880` 全量对齐 check/message
结构，立刻再改一轮契约的迁移成本 > 收益；错误码化的真实收益（按码自动路由修复）
要等 4.1/4.2 落地、硬错误类别稳定后再收割。**重开条件**：S4 前两项落地后，
若 skills 排障文档出现 ≥2 处需要按码索引的表格，或引入自动化修复路由时。

### 4.6 inserts 生命周期（draft/reviewed）+ 媒体 sha256 复核——**暂缓**

**设计草图**：`InsertRecord` 加 `status: str = "draft"`；provenance 统计非
reviewed 的 formula latex / figure content_desc → 新码 `W_INSERT_NOT_REVIEWED`
（release 期升 error，学 epub-builder 的 `E_SUPPLEMENT_NOT_REVIEWED`）；媒体侧
ingest 时在 inserts index 或 media 目录记 sha256，qa 复核比对（`E_ASSET_HASH`）。
**暂缓理由**：`inserts_missing_files` 已进放行门，desc/latex 的空值已有 W 级提醒
+ translation.md 补全指引；生命周期门禁的增量是「确认 agent 审过」而非「填过」，
当前单 agent 工作流下二者几乎等价。**重开条件**：出现 content_desc 已填但质量
不合格流入成品的事故，或工作流引入多轮独立审校时。

---

## 实施顺序与提交约定

S1（一次提交）→ S2（一次提交）→ S3（一次提交）→ S4.1 → S4.2 → S4.4（各一次提交）
→ 4.3/4.5/4.6 维持暂缓记录。每批：Conventional Commits、回归测试先行（能失败的
最小测试）、`uv run pytest -q` + `ruff check .` + `ruff format --check .` 三绿、
受影响 skills 文档同步（AGENTS.md 契约）。S3 虽纯文档也单独成提交，便于回溯。

## 验收

- 每批三绿（pytest/ruff check/ruff format）。
- S1 后：术语冲突 open / 标记丢失 / 脚注丢失 / zip 重复 / 远程图 / nav 缺覆盖 /
  空元数据 各自阻断放行或报 error（各配正反测试）。
- S2 后：`meta --translator OpenCode` → EPUB OPF 含 `creator-trl` + role `trl`；
  convert 单语书无 translator 输出；facts.md 待办首项=元数据核对。
- S3 后：publishing/invariants 两份新 reference + manifest references 更新 +
  SKILL 红线 8 条 + 指纹路由行 + 四处纪律补句 + 版本门禁步骤。
- S4.1 后：改写 src 的 align 被 import 阻断；漏段被 fidelity 前向告警；provenance
  与 fidelity 共用同一 norm/blocks 实现。
- S4.2 后：译文表格形状损坏被 import 阻断 + g0/qa 报 structure_open。
- S4.4 后：catalog 存在且 unresolved>0 时 qa 阻断；不存在时零影响。
- 全部完成后：回写本文件状态与 plans/README.md 索引；跨批共性经验（如「守恒类
  检查必须单元级总量比对防拆并句误报」）沉淀 lessons/ 一篇并互相引用。

## 状态回写

| 阶段 | 状态 | 提交 |
|---|---|---|
| S1 放行门与守恒接线 | 规划中 | — |
| S2 译者署名与元数据 | 规划中 | — |
| S3 skills 文档批 | 规划中 | — |
| S4.1 align 源绑定校验 | 规划中 | — |
| S4.2 表格形状守恒 | 规划中 | — |
| S4.3 结构冻结 | 暂缓（理由与重开条件见 §4.3） | — |
| S4.4 SourceCatalog 最小形态 | 规划中 | — |
| S4.5 错误码目录 | 暂缓（见 §4.5） | — |
| S4.6 inserts 生命周期 | 暂缓（见 §4.6） | — |
