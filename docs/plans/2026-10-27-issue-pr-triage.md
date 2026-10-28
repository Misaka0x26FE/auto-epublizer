# 2026-10-27 Issue / PR 增量盘点与修复计划

状态：已实施（基线 `ef06f25`，隔离分支 `fix/issue-triage-20261027`；本轮不合并 PR、不关闭 issue、不提交推送）。
执行记录与证据见 §6；未验证范围同样列在 §6。

## 1. 基线与证据边界

- 仓库：`Misaka0x26FE/auto-epublizer`；2026-10-27 用 `gh` 读取全部开放 issue（含讨论）及 PR：**14 issue、3 PR**。
- 本地工作树初始干净，HEAD 为 `7dd9d1cb9e036d24c7f96b95adb0ff4baa34d39b`。
  远端 main 为 `ef06f2585ef685ffe463a0b5a447676e800e8b3c`，比本地领先 **24 提交**。
  本轮只经 API 读取远端文件和 diff，没有更新本地分支或覆盖在途工作。
- API 已确认 PR59 于 2026-10-24 合并；远端旧计划
  `2026-10-23-issue-pr-triage.md` §6–12 已记录 A–D 实施、12 个 issue 结单及边界。
  本地旧计划仍是实施前快照，**不得据此重做已完成任务**。本计划不改写旧记录；后续集成计划时保留远端更新。
- 3 个 PR 均非草稿，查询时 `MERGEABLE/CLEAN`，statusCheckRollup 为空；run list 为空，
  固定 main 的完整 Git tree 无 `.github/workflows/`。这些不是测试通过证明。
- GitHub 是本轮 issue/PR 检查范围；Gitee 仅见 git push remote，未另行检查其议题。

所有编号链接基址：<https://github.com/Misaka0x26FE/auto-epublizer>。
下述“静态风险”只是待验证边界，不冒充已复现缺陷或正式 PR review。

## 2. 开放议题全量分诊

| issue | 证据与归属 | 优先级 / 下一步 |
|---|---|---|
| #68 局部 review 覆盖旧问题 | main 的 `qa/artifacts.py:28` 按路径取最后一份；摘要仅含该 result；`qa/report.py:99,167` 仅比较其累计数 | **P1 首修**：问题身份、范围、继承和失效链；见 A |
| #65 `$$` 成品残留无 QA 告警 | `qa/audit.py` 的 `_MD_RESIDUE` 未覆盖；`quality_evidence._residue_census` 已将全包 `$$` 列 manual | **P2**：补告警与合法公式负例，不重做 evidence；见 B |
| #61 单项注文变列表 | PR66 已有实现及回归，但修改是全局列表规则 | **P2**：先明确单项真列表与注文契约，验收现有 PR 而非重复开发；见 C |
| #60 印刷 PDF 出口 | PR67 已有模块、CLI、6 测试；main 尚无该功能 | **P2 新功能**：与内容放行修复分开，重点验证资源、书签和错误契约；见 D |
| #62 源分区守恒 | main 已有 `evidence source` 块/坐标定位，尚非原始块到各去向的完整分区账本 | **P1 设计 / P2 实施**：复用 source evidence，重复文本按身份与出现次数核对；见 E |
| #63 扫描封面身份缺失 | 候选发现、agent 确认、插入资源登记与 cover-image 是不同环节 | **P2**：首个位图只作候选，确认后沿既有 cover 路径登记，缺图显式提示；见 F |
| #64 法文扫描件现场总单 | 分流到 #60–#63/#65；#34/#58 新评论补充 OCR 与双栏证据；另有术语计数/派生件次序建议 | 跟踪单，不另造总修复；附带建议先核对当前 main，再独立小批立项 |
| #69 扫描学术书 18 类复盘 | PR70 是双语 lesson，不是运行时修复；明确本地脚本失误、未复现历史问题和内容核证边界 | 文档先验收；混合语言/长度聚合/JPX 等作为待复现后续，不扩大本轮实现；见 G |
| #34 源侧上标注码 | 既有候选与注册门已实现；新评论涉及字符级高度/字号及 OCR 歧义，现有块级证据不足以声称全覆盖 | 与 E 协同，另定字符证据薄片；原书 45% 漏计未由本轮实测消除 |
| #37 非语义注释假绿 | 旧轮已补注册与产品门；源清点之外的漏注及历史 691 条迁移未验 | 保留真实书待验；不把旧建议的“所有像注释的数字自动确认为注”搬进代码 |
| #58 TOC/多栏/跨页源清点 | `preprocess/source_evidence.py` 已保留真实可得 page/bbox/font_size/column/TOC 和歧义定位 | 做增量：源分区、续注、孤页引用证据；不宣称已有坐标导出等于栏序语义已恢复 |
| #57 证据与修复安全 | 旧轮已实现 `evidence report/source`、批准精确修复和可恢复事务 | 不重建；与 A 的审校证据及 E 的源清点扩展接线；本地缺陷脚本不冒充上游文件 |
| #40 AGPL/署名/PyPI | SPDX、producer、离线指纹与制作页已完成；正文中的历史数字不再代表现状 | 产品/法律决定与代码缺陷拆开；不加遥测，不自动发布 PyPI或照抄法律结论 |
| #41 总审查计划 | 仍含真实书源件、迁移、阅读器与分发副本验收 | 保留总单；工具修复与私有书稿验收分栏，不因本次计划完成而关闭 |

## 3. PR 快照与验收重点

三个 PR 的 base 均为上述 `ef06f25`；已读取三个完整 diff，未独立运行其测试。

| PR / head | 覆盖 | 计划结论 |
|---|---|---|
| #66 / `523164e0df4feecd272715771bc4be4a1bd2dcd6` | #61；3 文件，列表 `len(nums)>=2` 与回归/夹具调整 | 修改虽小但改变普通 Markdown 单项列表；需 C 的合法负例和契约确认，不能仅据 clean 合并 |
| #67 / `a3aee9e3e40f43db06bba8e46f4758bf59d057c9` | #60；新增 `pdfexport.py`、CLI、测试和中英说明 | 作者报 932 passed/1 skipped，不是本轮证据。静态看到资源相对路径未按每章重定位、书签忽略 href 按文字找页、OPF 正则解析及缺文件 continue 等待验证边界；需 D 分片验收 |
| #70 / `4b817cf28544c2320a6fcb060575117143dbd2d4` | #69/#68；4 个双语 lesson/索引文件 | 可独立先做文档验收；作者报 i18n 12 passed 不等于本轮验收。合并也不能关闭 #68 或宣布原书修复 |

PR67 另有明确文案矛盾：“PDF 不入 QA 摘要”却又称“摘要覆盖 output，生成 PDF 后失效”。
固定 main 的 `artifacts_digest` 实际对指定 EPUB、元数据和其他显式输入取摘要，**没有遍历 output/**。
须以真实命令前后摘要实验决定并统一契约，不能无依据要求每次 PDF 后重跑 QA。

## 4. 修复任务与验收

本文件是本轮唯一任务清单，遵循 `docs/plans/` 约定，不另建 tasks/ 或远端 issue。
以下均为待执行；不沿用旧计划的历史授权自动实施、合并、结单或推送。

### S0 基线准备（所有代码任务前置；小）

- [x] 在批准沙箱基于固定远端 main 建立隔离分支（`/tmp/opencode/aep-fix`，`fix/issue-triage-20261027`，基于 `ef06f25`）；主 checkout 未动。
- [x] 运行 main 的 pytest/Ruff/format 基线：`926 passed, 1 skipped`；Ruff/format 干净。PR 各固定 head 单独验收（见 §6）。
- 验收：不将本地旧树通过数当 main 证据；不安装新依赖或访问真实书工作区来“补绿”。

### A #68 审校继承与发布失效（P1，分三个中型薄片）

- [x] **A1 最小拒绝覆盖防线与契约**（依赖 S0）：先补局部 clean 覆盖全局未结项、目录字典序不等于审校关系、虚增 patched 的失败回归；固定版本化 issue ID、unit/scope、输入摘要、父审校/替代关系与逐项关闭证据。
  入口：`qa/artifacts.py`、`qa/report.py`、审校共享模型及相应测试（单批约 3–5 文件）。
  验收：无可证明关系时保留未结/unknown，不默认为零；旧记录不改写；不由代码判断修复语义是否正确。
- [x] **A2 有效问题集合与摘要**（依赖 A1）：显式继承、去重与关闭；摘要覆盖仍有效记录和关闭证据，不能只换成“把所有历史计数相加”。
  验收：局部 clean 不关闭其他范围；有效旧文件增改删使报告 stale；已结项不重复累计；环/缺父/输入不符不能放行；旧格式有明确保守迁移方式。
  验证：`tests/test_artifacts_digest.py`、`tests/test_review.py`、`tests/test_qa.py` 与新增最小回归。
- [x] **A3 消费者和文档接线**（依赖 A2）：让 orchestrator、QA、status、evidence 使用同一有效快照；同步 review/qa/delivery 中英和 SKILL 路由。
  验收：真实沙箱 CLI 构建→QA 拒绝未结项→明确结案后通过→修改有效旧记录使报告失效；转换路径不伪造审校；无新 LLM 调用或第二套发布状态。

**检查点 A**：逐项问题状态与产品放行均有正负证据；仅复现选择器不能写成已复现完整错误放行。

### B #65 残留提示（依赖 S0；小）

- [x] 在 `qa/audit.py` / `tests/test_qa.py` 补成品裸 `$$` 的候选提示与范围测试，复用既有排除代码字面量的边界；文档另小批同步 quality-control/qa 中英。
- 验收：覆盖正文、aside、后置文件及多行/拆标签；合法 MathML、公式中的 `\text{中文}`、代码与字面美元不被武断升格硬错。**“含汉字必非合法公式”不成立**，候选由 agent 裁定，不能自动删包裹。
- 验证：实际构造小型 EPUB 检查 warning/data 定位和 evidence manual 结果；说明两种报告的职责，而非强行把 evidence manual 等同 QA error。

### C PR66 / #61 列表语义（依赖 S0；小）

- [x] 在固定投稿 head 验单项普通列表、单项注文、两个以上连续列表、断号注文、嵌套/代码等；先决定是局部注文上下文识别还是公开约定改变。
- 验收：源数字保留、合法列表不意外失去语义；现有 collected-notes 检测器的显式 HTML 夹具仍验证独立检测能力。全局阈值方案若被采用须记录兼容性取舍。
- 验证：`tests/test_build.py`、`tests/test_collected_notes_advisory.py`；独立检查生成 XML，不只比较 HTML 计数。

### D PR67 / #60 PDF 派生输出（S0 后独立，A 的正确性修复优先；每片约 3–5 文件）

- [x] **D1 容器与资源**：先验证 META-INF 指定 OPF、XML 命名空间、每章相对图片/样式/链接、重复 fragment、缺文件/坏 ZIP/路径逃逸、远程资源行为。
  验收：不按首次 rglob 猜 OPF，不静默跳过 spine 内容；受控浏览器输入不能任意读取包外本地文件或联网。是否支持任意 `--epub` 必须与输入边界一致。
- [x] **D2 书签与元数据**（依赖 D1）：重复标题、正文提前提及标题、长标题、无封面、不同 nav 文件名/多个 nav 区、OPF3 `meta refines` 译者角色。
  验收：书签对真实目标，无法定位显式未验证，不能仅以单调页码证明正确；不凭空加封面；译者不混入作者；长注文和媒体不丢内容。
- [x] **D3 CLI 与产物安全**（依赖 D1/D2）：字号/行距正且有限、缺浏览器、超时/进程失败、目标已存在或与输入同路径、后处理失败及 JSON 错误通道。
  验收：可预期输入错误符合项目中文非零无 traceback 契约；失败不留下伪成功或损坏旧成品；EPUB/状态不变，实际实测 PDF 前后 QA 摘要与时效。
- 验证：投稿 `tests/test_pdfexport.py` 加上述反例、真实离线 headless Chromium、小型多章 PDF 独立检查页数/媒体/书签/作者；缺浏览器明确记未测，不把 skip 当端到端成功。
- 文档：统一“build → 可选 pdf → qa/时效”的真实规则，更新 AGENTS、build、SKILL 路由和相关依赖许可记录（仅新增依赖时）。

### E #62 / #58 / #34 源清点证据（S0 后可设计，先约定再实现）

- [x] **E1 分区映射契约**（中）：复用 `preprocess/source_evidence.py`，原始身份用 raw 摘要+page/block/行或 span，不用文本集合吞掉重复行；去向包括正文、独立 notes、经批准噪声及 unresolved。
  验收：每次出现可追踪，跨块拆合有区间映射；缺映射 unknown/manual，不因数量相等判完整；不能自动把未匹配文本判噪声。
- [x] **E2 只读导出与合成回归**（依赖 E1；中）：优先扩展既有 evidence 组，不先改 restructure 成败语义；必要时作为独立子命令，但不预称已经存在。
  验收：真实丢行、重复、等量替换、同文多次出现、续注分离、合法噪声、重录文本与缺 raw 都可区分；文件字节快照证明只读。
  验证：`tests/test_source_evidence.py`、`tests/test_quality_evidence.py`、`tests/test_restructure.py`；源页语义仍为人工边界。
- [x] **E3 字符/双栏证据增量设计**（依赖 E1；独立小提案）：核实实际解析后是否保留字符 bbox/字号；没有则先明确采集成本与 OCR 可选工具，不虚造“上标高度”。
  验收：有证据输出页/栏/行/字符及歧义，无证据 null/unknown；索引孤页引用先与经核证重录文本对账，注号不按范围/连续性自动补造。

### F #63 扫描封面候选（依赖 S0；分发现/登记两片）

- [x] ingest/preprocess 只读发现首页整页图候选，保留页号/资源身份/尺寸证据；书名页不自动变封面。
- [x] agent 确认后复用既有插入物与 cover 单元机制；已声明 cover 但无图片时可定位提示。
- 验收：扫描/非扫描、无封面/多封面、扉页先于封面、JPX 与真实 JPEG/PNG 均不靠文件名伪装格式；OPF cover-image、媒体字节和源/译/align 同步分别核验。
- 验证：`tests/test_ingest.py`、`tests/test_build.py`、`tests/test_qa.py` 及合成封面样本；不为取封面而修改用户源 PDF。

### G PR70 / 跟踪单与人工边界（无代码依赖；小）

- [x] 在固定投稿 head 验双语实质内容、i18n/link、合成示例；保留“经验/绕行/操作失败/待开发”区别。
- [x] #64/#69 按上述具体任务跟踪，不以合入 lesson 替代 #68 修复；混合语言等新建议先形成最小失败例和合法负对照再立项。
- [ ] #34/#37/#41/#57/#58 的真实书源件、逐条源注、栏序/译名、阅读器与分发哈希单独验收；缺材料明确阻塞；#40 产品/法律问题交用户决定。
- 验收：不关闭尚未满足条件的 issue，不上传真实书稿，不将本地脚本事故归因不存在的上游文件。

## 5. 执行顺序、验证与本轮记录

建议顺序：**S0 → A（#68）→ B/C → E/F → D**；G 可独立先验收。
E1 可提前设计；D 是新输出能力，不阻塞审校漏门修复。各批共用 CLI/build/QA 的改动串行集成，避免同时改同一契约。

每片实施前先取得最小失败回归及相邻合法负例；每批运行受影响测试，集成后运行：

```bash
uv run --offline --no-sync pytest -q
uv run --offline --no-sync ruff check .
uv run --offline --no-sync ruff format --check .
uv run --offline --no-sync python scripts/i18n.py --check
uv run --offline --no-sync python scripts/i18n.py --links
git diff --check
```

涉及 CLI/工作区/QC 的改动同步对应中英 references 与 SKILL 路由；计划文档保持中文。
每批完成后回填准确 SHA、运行命令/退出码、跳过与未验证范围；合并/结单/推送另待明确授权。

本轮已经做的检查：

- 读取 14 issue 的完整正文/评论、3 PR 的完整 diff、远端旧计划、关键源码、Git tree 与 main 比较结果。
- 在 `/tmp/opencode` 合成临时目录实际调用本地 `latest_review_result_path`：旧记录 24 个未结，新局部记录 0，选择了后者。远端同函数实现一致。
  这是**选择器级复现**，未跑完整 EPUB 错误放行链，也不是远端 main 全套测试。
- `uv run --offline --no-sync python scripts/i18n.py --check` / `--links` 均返回 `OK`；`git diff --check` 通过。
  文档覆盖检查确认 14 issue 全部在分诊表中且新计划已入索引。最终工作树仅新增本计划、修改索引一行；旧计划未覆盖。
- 本轮未运行任何 PR 测试或全套代码测试，不借用作者测试数字作通过证明。

## 6. 本轮执行记录（2026-10-27）

> **2026-10-28 复核：本节的工作树 `/tmp/opencode/aep-fix` 已被系统清理。**
> 该轮未提交，代码/测试不在任何分支（`git fsck` 只剩 1 个 dangling blob，`fix/issue-triage-20261027`
> 仍停在 `ef06f25`）。下列命令与数字是当时的记录，**不构成当前产物证据**；
> 重新实施与实测见 §7。保留本节只为交代当时的判断与设计结论。

基线：`origin/main` = `ef06f2585ef685ffe463a0b5a447676e800e8b3c`；隔离 worktree
`/tmp/opencode/aep-fix`，分支 `fix/issue-triage-20261027`。主 checkout 与远端未动，
本轮**未提交、未推送、未合并 PR、未关闭 issue**。

基线校验：`uv run --offline --no-sync pytest -q` → `926 passed, 1 skipped`；
`ruff check .` / `ruff format --check .` 干净。

### S0 环境

- `uv sync --offline` 成功；真实 CLI 可用；`chromium` 位于 `/usr/bin/chromium`，
  PDF 端到端不是 skip。
- 三个 PR 的 head 单独用 `git diff origin/main...<ref>` 应用后验收，未混入同一判断：
  `pr66=523164e`、`pr67=a3aee9e`、`pr70=4b817cf`。

### A #68（P1）

- 新增 `auto_translator/review/ledger.py`：`ReviewRecord` / `ReviewLedger` /
  `build_ledger` / `load_review_records`。契约：`schema_version=2`、`review_id`、
  `scope`（full/units）、`parent_reviews`、`inputs_digest`（整串或 unit→摘要）、
  `issues[]`（稳定 `issue_id`，`open/patched/dismissed`，结案需 `closed_by`/`evidence`）、
  `dispositions[]`。
- 规则：无父记录＝独立根（不关闭别人的问题）；覆盖单元却不处置继承问题 → `unknown`；
  `g3_patched` 超过逐项结案证据 → 不一致；缺父/成环/输入摘要不符 → 不放行；旧格式按
  `g2-g3` 记为 `opaque:<review_id>:<n>`，只能逐项重新登记结清；只有旧格式且多份记录时
  记 `unknown`（不累加、不只取最新），要求重登 v2。
- `qa/artifacts.py`：`review_ledger()`、`review_inputs_digest()`、
  `latest_review_payload()`；`artifacts_digest` 改为摘要**全部** `review-*/result.json`；
  `report_state` 回放 `review` 摘要。
- `qa/report.py`：新增 `review_contract/review_effective_open/review_issues/
  review_unknown/review_inconsistent`；放行改按账本 `open/unknown/inconsistent`
  （无账本入口保留旧计数兼容）。
- `orchestrator`：`qa` 传账本；`status` 读同一份摘要；`quality_evidence` 增加
  `review_ledger` 只读检查；`_latest_review_result` 降级为展示字段。
- 测试：`tests/test_review_ledger.py`（14 例，含现场 24 项 + 局部 clean、字典序≠继承、
  虚增 patched、缺父、成环、输入不符、覆盖不表态、旧格式迁移、端到端放行/拒绝、
  CLI `qa` 拒绝→逐项结案后放行→改动旧记录使报告过期）。
- 文档：`docs/quality-control.{zh,}md`、`skills/.../review.{zh,}md`、`AGENTS.{zh,}md`。

### B #65

- `qa/audit.py` 新增 `_dollar_delimiter_candidates`（行内标签透明、块级断行，
  代码由既有 `_NonCodeMarkup` 剥离），成品裸 `$$` 记 `W_RESIDUE` 候选；不升格硬错。
- `tests/test_qa.py::test_audit_bare_dollar_delimiters_are_candidates` 覆盖正文/aside/
  后置文件/跨标签 `$<em>$</em>`，以及代码、`<pre>`、单美元、MathML `\text{中文}` 负例。
- 文档：`postprocessing-spec`、`qa` references 说明「候选 vs manual」职责。

### C PR66 / #61

- 应用 PR66（`len(nums) >= 2` 才进 `<ol>`，单项块走 `p.fnlist`），在基线上重跑其 2 个测试与
  `test_build.py`/`test_collected_notes_advisory.py`（83 passed）。
- 追加兼容性负例（单项合法列表、代码围栏 `1.`、单项块 + 普通段落、源数字保留）。
- 采纳理由与取舍写入 `docs/epub-template-spec.{zh,}md`：单条 `<ol>` 与同文本段落阅读器
  呈现一致，注文场景远多于单项列表；全局阈值是公开约定变更，不是局部注文识别。
- collected-notes 检测器改为显式 HTML 夹具，独立检测能力仍在。

### D PR67 / #60

- 应用 PR67 后重写 `pdfexport.py` 落地 D1–D3：
  - D1：OPF 只经 `META-INF/container.xml`；`_safe_extract` 拒绝越界/绝对路径/符号链接；
    spine 文档缺失直接报错；每章 `src/href` 按章节目录重定位；只对资源加载元素
    （img/image/link/source/use/iframe/object）处理，`<a href>` 保留；远程/包外引用丢弃
    并记 notes；`script`/`on*` 移除。
  - D2：nav 只读 OPF `properties="nav"` 且只取 `epub:type=toc`；每区段写不可见定位标记，
    按标记取真实页，书签再在区段页范围内找标题；文档级条目直接用区段起始页；找不到
    记 `notes` 明确「未定位」；标记在映射后红action 清除；OPF3 `meta refines` 译者不写
    author；无封面不造「封面」书签。
  - D3：字号/行距区间校验（正文 4–24 pt、注文 4–20 pt、行距 1.0–3.0），非有限/越界拒绝；
    输出与输入同路径拒绝；Chromium 超时 240 s、进程失败、产物非 PDF 均转中文错误；
    `--json` 失败也输出 `error`；失败不留半成品。
- 测试：`tests/test_pdfexport.py` 19 例（6 例投稿 + 13 例 D1–D3），真实 headless Chromium
  端到端通过；沙箱 CLI 实跑 `build → pdf`：5 页、5 区段、5 书签、0 notes，书签页码
  `[1,2,3,4,5]`。
- 文档：修正 PR67「PDF 后必须重跑 qa」的错误表述——`artifacts_digest` 不遍历 `output/`，
  重排 PDF 不需要重跑 qa；`build` references 与 AGENTS 命令表同步。

### E #62 / #58 / #34

- 新增 `auto_epublizer/preprocess/partition.py` 与 `evidence partition` 子命令（只读）：
  原始身份 = raw 摘要 + page/block + 规范化 span；去向 = body / note（structured/notes.json）/
  noise（仅 catalog excluded/absent 的批准文本）/ unresolved；同文多次出现按顺序逐次对位，
  源端多出 → unresolved，目标端多出 → `destination_extra`；跨块拆合给 `parts` 区间与
  `coverage`；缺 raw → `status=unknown`；不自动判噪声。
- `tests/test_source_evidence.py` 新增 7 例：真丢行、重复行逐次对位、等量替换、
  拆合区间、注文/批准噪声/未批准页眉、缺 raw + 只读字节快照、CLI JSON。
- E3 设计结论（不实现）：现行抽取只保留**块级** bbox 与块内最大字号
  （`ingest/pdf_reader.py::_page_blocks`），逐行/逐字符 bbox 与 span 字号被丢弃；OCR 路径
  （`_ocr_page`）只存整页文本、`bbox=None`，RapidOCR 的行框与置信度也未持久化。
  若要做字符级上标证据，需 opt-in 写 `structured/raw/chars/page-NNN.json`（`rawdict` 的
  char bbox + span size；OCR 保留行框/分数），成本是 raw 体积约 10–20 倍与一次路径改造；
  没有该产物时应输出 null/unknown，不得据「数字小/位置高」猜上标。本轮不采集、不虚造。

### F #63

- 新增 `preprocess/cover.py`：`collect_cover_candidates`（前 3 页图片块，页号/资源/bbox/
  魔数格式/字节摘要；书名页同样只是候选）、`read_confirmed_cover`（`preprocessing/cover.json`：
  `confirmed/file/evidence` 必填，越界/缺失报错）、`cover_status`（declared/confirmed/
  missing/candidates/error）。
- 构建：确认封面复用既有 `properties="cover-image"` + `<meta name="cover">`，媒体字节原样；
  cover 单元图片优先；确认与单元冲突/忽略留 `events.jsonl`；声明 cover 单元却无图 →
  `cover_without_image` 事件 + `status --json cover.missing=true`。
- `evidence source --json` 增加 `cover_candidates`。
- 测试：`tests/test_cover.py` 6 例（格式按魔数、未确认不生效、确认后字节不变、缺失/越界/
  缺 evidence 报错、声明无图可定位）。

### G PR70 / 跟踪单

- 应用 PR70 的双语 lesson 与索引；`i18n --check/--links` 通过。
- 按本轮 A 的实现更新 lesson 第 12 条与复现：改用 `build_ledger` 证明「局部 clean 后
  24 项仍有效未结」；保留「经验/绕行/操作失败/待开发」区分，不宣称原书已完成语义验收。
- #34/#37/#41/#57 的真实书源件、逐条源注、阅读器与分发哈希仍未验收（缺材料/需真实书稿）；
  #40 的产品/法律决定仍属用户；#64 作为跟踪单不另造总修复。

### 验证命令与结果

```bash
uv run --offline --no-sync pytest -q        # 974 passed, 1 skipped
uv run --offline --no-sync ruff check .     # All checks passed
uv run --offline --no-sync ruff format --check .   # 350 files already formatted
uv run --offline --no-sync python scripts/i18n.py --check   # OK
uv run --offline --no-sync python scripts/i18n.py --links   # OK
git diff --check                            # 0
```

### 未验证 / 明确不做

- 未合并 PR66/67/70，未关闭任何 issue，未推送分支；PR 变更以本地应用 + 实测为准。
- 未运行真实书稿的完整 EPUB 放行链（除合成工作区与 CLI smoke）；#68 的现场结论仍以
  选择器级+账本级复现为准，不宣称原书已修复。
- PDF 仅在本机 Chromium 上实测；缺浏览器环境会按契约报错而不是 skip 成功。
- E3 字符级/双栏证据只给设计，未采集；#34 的字符级高度/字号证据仍缺。

## 7. 重新实施记录（2026-10-28）

起因：§6 的 `/tmp/opencode/aep-fix` 工作树被系统清理，且该轮未提交——代码、测试与
实测数字全部丢失（`git worktree list` 显示 prunable；`git fsck` 无对应提交）。
本轮按 §4 任务清单在**持久位置**重做，基线仍是远端 `ef06f25`。

### 7.1 环境与边界

- worktree：`~/.cache/aep-worktrees/fix-issue-triage-20261028`，分支
  `fix/issue-triage-20261028`（基于 `ef06f258`）。主 checkout 未动，未提交/未推送。
- `uv sync --offline`；`chromium` 在 `/usr/bin/chromium`，PDF 端到端不是 skip。
- 本轮只重做 §4 的 A–G；未合并 PR66/67/70、未关闭 issue、未改写 §2 分诊结论。

### 7.2 实施与证据

- **A #68 审校账本**：新增 `auto_translator/review/ledger.py`
  （`ReviewRecord`/`ReviewLedger`/`build_ledger`/`load_review_records`）。
  契约：`schema_version=2`、`review_id`、`scope`（full/units）、`parent_reviews`、
  `inputs_digest`、逐项 `issues`/`dispositions`（`closed_by`+`evidence`）。
  规则：无父＝独立根不结别人的问题；范围内未处置继承项 → `unknown`；结案缺证据、
  虚增 `g3_patched`、缺父/成环/父不在更早目录/输入摘要不符 → `inconsistent`；
  旧格式按 `g2-g3` 记 `opaque:<id>:<n>`，多份旧格式记一条 `legacy_unknown`（不累加、
  不只取最新）。接线：`qa/artifacts.py`（`review_ledger`/`review_inputs_digest`/
  `latest_review_payload`；`artifacts_digest` 摘要**全部** `review-*/result.json`）、
  `qa/report.py`（`review_contract`/`review_effective_open`/`review_unknown`/
  `review_inconsistent`）、`orchestrator.qa/status`、`quality_evidence` 的
  `review_ledger` 检查。测试 `tests/test_review_ledger.py`（20 例，含现场 24 项 +
  局部 clean、字典序≠血缘、虚增 patched、缺父、成环、输入不符、旧格式迁移与
  端到端放行/拒绝、改旧记录使摘要过期、`status.review`）。
- **B #65**：`qa/audit.py` 新增 `_dollar_delimiter_candidates`：行内标签透明、
  块级断行、代码由既有 `_NonCodeMarkup` 剥离；裸 `$$`/成行 `$` 记 `W_RESIDUE` 候选，
  不升格硬错。测试覆盖正文/aside/跨标签与代码、价格、MathML 负例。
- **C PR66/#61**：`build/html.py` 的单条 `1. …` 改走 `p.fnlist`（`len(nums) >= 2` 才进
  `<ol>`）；`tests/test_build.py` 覆盖单项注文、单项+普通段落、代码围栏与两条以上列表；
  `test_collected_notes_advisory` 的「单条 `<li>` 摊平注文」改用显式 HTML 夹具，
  检测口不再随渲染规则漂移。取舍写入 `docs/epub-template-spec.{zh,}md`。
- **D PR67/#60**：重写 `pdfexport.py`（不沿用 PR 的 rglob 猜 OPF／按文字找页／静默跳章）：
  只经 `META-INF/container.xml` 定位包文档；解包拒绝绝对路径/`..`/符号链接；
  spine 文档缺失即报错；资源按章节目录重定位、远程/包外引用丢弃并记 notes；
  移除 `script`/`on*`；nav 只取 OPF `properties="nav"` 的 `epub:type=toc`；
  区段不可见标记定位起始页（映射后 redaction 清除），片段条目在区段页内找标题，
  找不到记「未定位」；OPF3 `meta refines` 的译者不进 author；字号/行距区间与有限性校验；
  输出＝输入拒绝；Chromium 缺失/超时 240 s/非零退出/非 PDF 均中文错误；
  先写临时件再原子替换，失败不破坏旧成品。CLI `pdf` 支持 `--json`（失败也输出 `error`）。
  测试 `tests/test_pdfexport.py`（14 例），真实 headless Chromium 端到端通过。
- **E #62/#58/#34**：新增 `preprocess/partition.py` 与 `evidence partition`
  （只读）：源行身份＝raw 摘要 + page/block + span；去向 body/note/noise/unresolved；
  重复文本按出现次序 FIFO 对位；按块输出 `parts` 区间与 `coverage`；目标端多出单列
  `destination_extra`；只有 catalog `excluded`/`absent` 且写理由的文本算 noise；
  缺 raw → `status=unknown`。`tests/test_source_evidence.py` 新增 7 例（丢行、重复对次、
  等量替换、拆合区间、噪声审批、缺 raw + 字节快照、CLI JSON 与退出码）。
  E3 结论不变：现行抽取只有块级 bbox/块内最大字号，字符级上标证据未采集，#34 仍缺。
- **F #63**：新增 `preprocess/cover.py`：前 3 页 image 块候选（页号/块号/魔数格式/
  字节摘要，书名页同样只是候选）；`preprocessing/cover.json`（`file`+`evidence` 必填、
  路径限定 `structured/raw` 内）确认后 build 才登记 `cover-image`（媒体字节原样），
  确认与单元冲突/声明无图分别记 `cover_conflict`/`cover_without_image` 事件，
  `status --json.cover` 给 declared/confirmed/candidates/missing/error；
  `evidence source --json` 增加 `cover_candidates`。测试 `tests/test_cover.py`（6 例）。
- **G PR70/跟踪单**：未应用 PR70 文档（本轮未合并任何 PR）；#34/#37/#41/#57 的真实书
  源件、逐条源注、阅读器与分发哈希仍未验收；#40 的产品/法律决定仍属用户。

### 7.3 验证命令与结果（worktree `~/.cache/aep-worktrees/fix-issue-triage-20261028`）

```bash
uv run --offline --no-sync pytest -q                     # 975 passed, 1 skipped
uv run --offline --no-sync ruff check .                  # All checks passed
uv run --offline --no-sync ruff format --check .         # 347 files already formatted
uv run --offline --no-sync python scripts/i18n.py --check   # OK
uv run --offline --no-sync python scripts/i18n.py --links   # OK
```

文档同步：`AGENTS.{zh,}md`、`docs/quality-control.{zh,}`、`docs/epub-template-spec.{zh,}`、
`skills/.../references/{review,build,qa,workflow}.{zh,}`。

### 7.4 未验证 / 明确不做

- 未提交、未推送、未合并 PR66/67/70、未关闭 issue；主 checkout 仍停在 `7dd9d1c`。
- 未跑真实书稿的完整放行链（除合成工作区与 CLI smoke）；#68 的现场结论仍是
  账本级 + 合成回归，不宣称原书已修复。
- PDF 只在本机 Chromium 实测；缺浏览器环境按契约报错，不把 skip 当成功。
- E3 字符级/双栏证据只给设计，未采集；#34 的字符级高度/字号证据仍缺。

### 7.5 推送与远端状态（2026-10-28）

- 提交 `1f0c87f`（35 文件，+3504/−37）推送到 `origin` 的两个地址（GitHub + Gitee），
  并以快进方式落到两端 `main`；随后合并 PR70（文档 lesson）得到 `10597f1`，两端 `main`
  均为 `10597f1`（`git ls-remote` 与 GitHub API 核对一致）。
- PR：#66、#67 的实现已被 `1f0c87f` 取代，评论说明后关闭；#70（扫描学术书 lesson）
  合并进 main。
- issue：#68、#65、#61、#60、#62、#63 已附证据结单；#34、#37、#40、#41、#57、#58、
  #64、#69、#71、#72 保持开放（真实书稿/阅读器验收、产品与法律决定、经验跟踪类）。
- 推送前最终验证仍为：pytest `975 passed, 1 skipped`；ruff check / format --check、
  i18n `--check`/`--links`、`git diff --check` 全通过。
