# 2026-10-23 Issue / PR 盘点与修复计划

状态：已实施（代码保存至 `f4d6c24`，各批提交和验证见 §6–11）；已推送隔离修复分支，最终交付证据见 §11。初始盘点及基线保留；原轮次未远端结单，用户追加授权的主线集成与结单见 §12。真实书人工核证不在本轮通用工具交付内。

## 1. 快照与证据边界

- 仓库：`Misaka0x26FE/auto-epublizer`；公开 API 返回 **18 个开放 issue、1 个开放 PR（#59）**，开放列表一页返回完毕。
- 当前本地 HEAD 与 PR59 的远端 main 基线均为 `08a8b1aa5d70eaa5bf742f5b68c7f09783464490`。
  工作树初始干净；本地 `origin/main` 跟踪引用落后一提交，不代表远端 main 仍落后，不能据此推送。
- PR59 head：`9e57d9ff8d0278d88ae57347fb993650f395212c`；29 文件，+1690/-56；非草稿，API 当时显示可合并、`mergeable_state=clean`。
- PR59 无已提交 review，head 的 check-runs 为 0。这不是完整 CI 状态证明，更不是测试通过证明；作者声明的 **852 passed / 1 skipped** 尚未由本轮独立重跑。
- `gh repo view` 返回 HTTP 401；已用无需认证的公开 REST API 读取开放列表、PR diff 和 #54–#58 评论。未读取凭证，未尝试远端写操作；认证修复不属于本轮。
- 本轮已运行：`uv run --offline --no-sync pytest -q tests/test_cli_contract.py tests/test_glossary.py tests/test_review.py tests/test_status_all.py tests/test_licensing.py`，**90 passed，4.01s**。
  这是当前 main 的分组基线，不是 PR59 验收，也不覆盖旧 issue 的全部关闭条件。
- 既有计划 `2026-10-14-review-and-repair.md` / `2026-10-15-review-backflow.md` / `2026-10-17-field-followups.md` 保留；本计划不重开已完成代码工作，不覆盖真实书待办。

## 2. 全量分诊矩阵

链接前缀：<https://github.com/Misaka0x26FE/auto-epublizer/issues/>；PR：<https://github.com/Misaka0x26FE/auto-epublizer/pull/59>。

| 条目 | 当前判断 | 处置与关闭条件 |
|---|---|---|
| #54 原样复制/短译/体例豁免/摘要 | main 与投稿补丁两层问题；PR59 声称覆盖 | 第一优先审查 PR59 的 import→G0→G5、失败退出码及 stale 链；逐项验收后再结单 |
| #55 图注与重复图 | PR59 改为 XML 和字节身份审计 | 核对空 alt、多 figure、引号、路径别名与正常图号；重复仍 advisory，不自动删图 |
| #56 注文/注号/孤注/NCX/nav | PR59 声称覆盖，但含需复现边界 | 注文完整性、显示号、孤注宿主、未登记源注和 nav 排除分别验收；不以机器零候选证明源书无注 |
| #57 审计假绿/不安全修复工具/证据 | 部分是工作根自写工具，非上游文件；PR59 仅落部分契约 | 保留开放；先定只读证据接口及安全修复接口，不复制本地缺陷脚本；人工音译正确性不由程序背书 |
| #58 源清点/双栏索引/跨页注文 | PR59 主要补操作边界，尚非完整工具实现 | 保留开放；保全来源坐标/源 TOC，独立源清点与成品全范围审计；语义判定由 agent 回源完成 |
| #48 制作页出版/版权/生成模型 | 新功能缺口，有 #53 补丁提案 | 单独批次实现元数据和可见声明；未知不猜，模型自报不引入任何 LLM 调用 |
| #49 制作页 nav/NCX 可达 | 与当前“仅 landmarks、不进正文目录”契约不同 | 先明确产品契约，再补 nav/NCX 顶层入口、独立对账和兼容测试；保持 linear=no |
| #53 #48/#49 可应用补丁 | issue 不是开放 PR，旧提交有历史重写背景 | 作为实现参考，不直接按旧 SHA 重放；在当前基线审查补丁；与 #48/#49 同批验收，不重复开发 |
| #50 机器接口与 --json 文档 | 接口方向提案；当前模板命令已未见“一律所有命令 --json” | 全库核对帮助/skill/模板；先采用准确列出已支持 --json 与权威产物的最小方案，新增 JSON 接口另定契约 |
| #33 ledger 折行/误扫模板 | 旧计划 E-1 已实现，当前 CLI/status 回归部分通过 | 精确回归 stdout/-o、窄终端、工具树与合法嵌套工作区；证据齐全后建议结单，不重写 |
| #34 源侧上标注码 | 已有候选、守恒与语义注释实现；特定真实书验收仍有缺材料记录 | 分开记录工具已完成与私有原书未验证；不把裸数字启发式直接升级为真注释，不搬注码迎合检查 |
| #35 历史冲突重复报告 | 当前代码已有 conflicts_new / conflicts_open 分离 | 验证 resolved 历史、已有 open、重复导入幂等和账本不被删除，再建议结单 |
| #36 BOM/显式术语路径/空结果 | 当前 CSV 已 utf-8-sig，CLI 已有术语计数 | 验证 BOM 等价、显式坏文件在写回前失败；沿用 cwd-relative，不引入存在性 fallback |
| #37 非语义注释仍放行 | N 阶段已实现，但 PR59 修复了未登记证据漏门；真实书迁移不等于代码完成 | PR59 合入前后分别验注册/缺注册/损坏清单/部分遗漏/错内容；真实书单列，不立即关闭整个历史问题 |
| #38 版面型疑点 | 当前已有 advisory 候选实现 | 核对正文、aside、后置单元覆盖及负例；不接受“所有空格/缺句号一律 error”，剩余覆盖与 #58 协同 |
| #39 短源长度比噪声 | 当前已有 min_src_chars=20；PR59 新增独立严重短译门 | 保留原比值 advisory 与短源保护；空译、极短非空译、体例依据分别回归，不以总比掩盖行级问题 |
| #40 AGPL/署名/PyPI | 当前已 SPDX、producer、构建署名/指纹；PyPI 属产品决定 | 核对当前证据后拆清已交付与不实施项；不加遥测、不替书稿改权利，不照抄旧条款推论 |
| #41 总审查计划 | issue 正文仍是早期规划快照，本地已有后续实施记录 | 作为总跟踪单回填代码证据/剩余真实书工作；不能因本轮盘点就宣称整体完成 |

## 3. 执行任务与依赖

本文件为本轮唯一新增任务清单，遵从仓库 `docs/plans/` 约定；不另建 tasks/ 或新远端 issue。
用户已授权按本计划实施修复、更新计划并推送。先在隔离分支验证，保留投稿历史；不自动关闭 issue，不修改真实书工作区。C 的目录可达契约按本计划落地；D 先固定最小接口及事务恢复策略，再验证实现。

### A. 优先：PR59 的独立合并审查

- [x] **A1 固定审查环境与实际基线**（无前置依赖；小）：在批准沙箱建立隔离 checkout，固定 base/head、确认导入路径确为该 checkout；读取全部 diff、测试和相关文档。
  验收：不覆盖作者历史或本地工作；记录 Python/uv/工具和准确 SHA；作者测试数字与本机证据分栏。
- [x] **A2 #54 硬门与时效链**（依赖 A1；中）：源码入口 `review/g0.py`、`qa/report.py`、`qa/artifacts.py`、`cli.py`；G0 参数传递相关调用位于 orchestrator。
  验收：复制正文、Unicode、标题后正文、内嵌注码、空译、严重短译均有正负例；import 失败退出非零、QA 拒绝错误放行；源语言=目标语言/代码/合法体例不误挡；改豁免、依据或 nav 使旧报告 stale。
  验证：`test_t12_gates.py`、`test_field_quality_followup.py`、`test_artifacts_digest.py`、`test_cli.py`；必要时按不变量再拆小任务，不一次改多门。
- [x] **A3 #56 注号与宿主**（依赖 A1；中）：`orchestrator.py` 的注释上下文装配、`qa/notes_audit.py`、`tests/test_notes.py`。
  验收：原印号与稳定 ID 分离；混合符号/数字注号不碰撞；孤注只能按可核证位置归位，未知不能假装已知；实体/代码/强调规范化不接受截短注文；缺登记和损坏 JSON 不静默跳过。
  验证：新最小反例先失败，再修复；检查实际 noteref/aside/href/backlink 和完整注文，不只断言计数相等。
- [x] **A4 #55 与导航独立审计**（依赖 A1；中，图像与导航可分两次实施）：`qa/audit.py`、`build/__init__.py` 及现有 provenance 消费者。
  验收：多 figure、空 alt、同字节多路径准确定位；合法纯数字图号不误挡；nav=no 保正文且不掩盖其他目录缺失；NCX plain label 保留真实目标锚点。
  验证：实际构建并篡改小型 EPUB，独立解析 XML；资源门继续拒绝包外/越界资源。
- [x] **A5 集成与合并建议**（依赖 A2–A4）：全套 pytest、Ruff、format、i18n 和真实无桌面 CLI/EPUBCheck 正负 smoke。
  验收：记录实跑命令、退出码、跳过原因和未验证项；保留投稿者提交，先提交审查结论，不自动合并或关闭 #54–#56。

**检查点 A**：每个发现有输入、实际行为、预期和最小修复；只有 diff 推论的条目仍标待复现。
不以 `mergeable=clean`、作者通过数字或单纯函数测试替代消费者验收。

### B. 清理历史状态与最小接口纠偏

- [x] **B1 #33–#40 / #41 证据对账**（可在 A 之后；小批逐条）：复用既有完成记录和相应测试；#34/#37 的真实书条件独立保留。
  验收：每条明确“代码完成/部分完成/待私有材料/产品决策”；只提出有证据的结单建议，不制造重复实现。
- [x] **B2 #50 命令能力矩阵**（无代码依赖；小）：核对 cli 帮助、work-root 模板和 workflow 说明。
  验收：调用示例均为实际支持命令；机器读取 status/doctor 的 --json 或 report 等既有权威产物，禁用对彩色摘要的决策解析；不直接写 publication 状态。
  验证：离线 CLI help/示例回归和 i18n/link 检查。若用户选择给 qa/ledger 增 --json，先定字段、stdout/stderr 和失败退出码，再单独实现。

### C. #48/#49/#53 制作页补全

- [x] **C1 元数据与声明**（A 完成后集成；中）：模型/CLI 元数据入口与 fingerprint，各自薄片提交。
  验收：None=历史未知、[]=明确未用；坏 JSON 写回前报错；只展示非空出版字段；模型信息明确自报，不推断未知版本，不改变书稿版权或指纹有效性约束。
  验证：模型兼容、CLI 往返、字段更新后报告时效、双语输出；明确 [] 的可见表达，不能内部记录“未使用”却展示为“未知”。
- [x] **C2 nav/NCX 制作页入口**（依赖 C1 和对契约变更的确认；中）：build 与 provenance 配套。
  验收：独立附页保留 linear=no、两个目录各一条入口、playOrder 连续、无伪正文单元；已有版权单元不重复插页；源目录投影仍严格校验。
  验证：源语言/译文、有/无版权单元、深层目录和旧指纹产品兼容；XML 正负样本加真实 EPUBCheck；拒绝只按 basename 或正则猜匹配导航身份。

同步文档：C 修改当前 AGENTS 中“仅 landmarks、不进正文目录”的约定及 build/QA/spec 对应中英章节；不能只合入 #53 补丁而保留矛盾契约。

### D. #57/#58 后续能力（先定接口，不自动扩张）

- [x] **D1 只读证据报告设计**（依赖 A 的统一证据语义；中）：确认是否扩展现有 evidence 命令；不预设新数据库或第二套发布状态。
  验收：每项绑定当前 source/结构/译文/成品摘要，区分 pass/fail/unknown/manual；未取得外部 sources 记 unknown；逐单元正文、完整注文、目录与副本按实际对象对账。
- [x] **D2 来源候选与全范围覆盖**（依赖 D1；按 PDF/EPUB/注释各拆小批）：先核实已有 pages/raw/breaks/notes-candidates 可提供哪些证据，再增缺口。
  验收：合成双栏/跨页样本保留真实可得 page/bbox/font/column/TOC；源注清点独立于已登记集合；残留普查包含 aside 与后置单元。跳号/栏界/页眉只出候选，不自动合并删除或补造注文。
- [x] **D3 安全修复协议**（依赖 D1，接口获确认后再实施）：基线摘要、source/target 身份、批准清单、只读 dry-run、全量预检、冲突拒绝、备份和幂等；先讨论多文件写失败的恢复策略，不能把逐文件原子替换当整体事务。
  验证：合成失败注入覆盖预检失败无写入、应用中断可恢复、重跑不重复包裹；不引入自动音译或自动语义裁决。

**检查点 D**：通用工具只证明机械事实；真实书的源页可读性、姓名译法、索引页码归属、注文尾部与源目录树仍须独立回源核证。

## 4. PR59 静态审查候选（尚未执行反例）

下列为原始候选，实际复现与处置见 §6；保留发现轨迹，不把原候选本身当结论。

1. `_display_number` 仅逐次填 used_numbers，未先保留全部原印数字号：符号注先分配 1、后遇原印 1，可能显示重号；`01` 与 `1` 的字符串唯一性也不等于显示整数唯一性。需验证实际渲染与语义。
2. 孤注宿主仍有 `host_unit or entries[0]` 回退，且 scope 可能先于 source_locations；与 #56 “只依据自身有效位置、不猜”验收存在张力。需测试位置缺失/冲突，不直接猜选一章。
3. `_CAPTION_FILENAME_SLUG` 可匹配纯数字，例如 `1`/`1955`；与 #55 “数字图号不误报”可能冲突。需构建真实图注反例后决定最窄判据。
4. 未登记注释扫描用裸子串 `[^ref-`，需验证 fence/inline code 的字面标记不会误挡；语言判据中 CJK 存在即跳过，也需验证混合文字不会掩盖复制正文。
5. `_norm_md` 新增多套与 renderer 同口径正则：需测合法多段/代码/转义的正确性，也需独立截短/等量错配反例，避免共享渲染逻辑自证或未来规则漂移。

## 5. 统一验证和完成规则

- 每次修复先最小失败回归，再补相邻合法负例；测试离线合成，不上传真实书稿，不访问 MinerU 或知识库远端。
- 在 `/tmp/opencode` 等批准沙箱做 CLI smoke，不改真实书工作区、用户源件或旧分发副本；不用 reset/clean 制造干净状态。
- 每批运行受影响测试、`uv run --offline --no-sync ruff check .`、`uv run --offline --no-sync ruff format --check .`；集成后全套 pytest。
- 文档中英正文先实质同步，再 finalize 及 `--check`/`--links`；历史计划按仓库约定仅中文。
- 工具缺失、外部源缺失、未执行语义审校分别记录，不以 unknown 充 pass，不把 skip 算验收完成。
- 计划/issue 状态只按实际完成证据回写；真实书验收未完成时 #41/#57/#58 及相关私有任务继续保留明确边界。

## 6. A 批实施与独立审查记录

- 隔离目录 `/tmp/opencode/aep-triage-20261023`，分支 `fix/issue-triage-20261023` 基于投稿 head `9e57d9f`；合并本地计划提交 `7dd9d1c`，保留投稿者所有原提交，不重写历史。
- 复用主 checkout 虚拟环境，但所有运行显式 `PYTHONPATH=src`；已实查 `auto_epublizer` / `auto_translator` 导入来自隔离目录。实际 Python **3.13.14**，不是推测为 3.12。
- OCR delegate preview/rule（无 LLM 调用）选择 9 个生产文件；本 agent 已审查这 **9/9**，无跳过；另手工审阅工具因类型/默认路径排除的 15 个文档和 5 个测试文件，即 PR 共 **29/29** diff，未委托子 agent。
- `tests/test_pr59_review.py` 首轮 **12 failed / 1 passed**：数字图号误挡、符号号占用后遇数字号碰撞、`01`/`1` 显示碰撞、`²` 触发 int 异常、孤注优先 scope 导致错章/无位置回书首、字面代码误触登记、中文标题掩盖复制正文、inline code 被严重短译门计数。
- 追加 **4 failed**：成品注文多出伪造正文仍被子串包含放过；源/目标语言和出版标题改变不使报告失效。最后补测 **1 failed**：同名注册 ref 在 fenced/inline code 中也被替换，成品出现重复引用 ID。
- 修复：预留全作用域数字号、登记拒绝规范化重号、decimal 与符号分开；孤注来源单元优先，未知宿主拒绝构建；标记提取/替换尊重代码边界；纯数字图号不作为文件名证据；语言门基于去家具/代码后的正文；摘要纳入元数据；注文去真正显示号/回链后完整规范化相等，独立图片可见图注同口径保留。
- 截短注文反例原本即被拒绝，未冒充新修复。新增导航消费者验证：nav=no 仍有 spine/正文且结构门通过，移除另一合法入口仍拒绝通过。
- 完整相等审计的合法负对照追加 **4 failed**（blockquote、fenced code、多反引号行内代码、非连续原印列表号）；修正独立 Markdown 文字提取，而非改回子串包含。相关 notes/render/media/PR59 组 **113 passed**。
- 分组验证：首次修复后 **209 passed**；代码标记替换与真实 nav 负例补修后，PR59/notes/build/review/i18n 相关组 **173 passed**。Ruff check 通过；format-check 发现新增长行后需格式化，最终结果见后续记录。
- 第一轮全套 **869 passed / 1 skipped，445.76 秒**（最后补加代码渲染/nav 测试之前）；此前 120 秒基线运行超时，不能写成通过。最终代码全套仍须在 A5/ship 回填。
- 真实无桌面 CLI：通过 init→notes register→meta→import --reviewed→g0→build→qa→status；EPUBCheck **5.2.1** 实跑返回 0、零 error、g4=pass、released=true/ok、stale=false。给同一成品注文追加伪造文字后，qa 为 released=false/notes_open，定位 `E_NOTES_CONTENT_MISMATCH`。合成现场位于 `/tmp/opencode/aep-cli-smoke-ylo5mcsi`；非真实书或阅读器验收。
- 所有 A 改动同步 notes/translation/qa 与 SKILL 路由中英文；i18n check/links 均 OK。B 的机器接口矩阵正在另批整理。
- 最终 A 全套 **875 passed / 1 skipped，326.88 秒**；唯一跳过 `test_processing_tools.py:70` 需要真实 RapidOCR，本机 doctor 明确该工具不可用。Ruff check/format 均通过（332 文件）；不把 OCR 跳过算成功。
- 后续补充语法合法但契约破损的 notes.json（`{}` / present+空 notes）两例 **2 failed**，修成必须通过源清单契约，不能当无注；相关 PR59/T12/notes/i18n **128 passed**。补修将随最终 ship 全套再次复验；不回退此前已完成项。
- A 主要补修保存点为 `8fd76d3`；保留 PR59 投稿历史。只在本地隔离分支集成，尚未远端关闭条目或覆盖真实工作区。

## 7. B 批证据对账（不远端结单）

`tests/test_import.py`、`test_status_all.py`、`test_glossary.py`、`test_review.py`、
`test_licensing.py`、`test_cli_contract.py`、`test_work_root_tools.py` 本轮合计 **129 passed**。
不是重新实现历史功能，而是核实已完成代码与开放 issue 的差距。

| 条目 | 当前可核验证据 | 剩余与结单建议 |
|---|---|---|
| #33 | stdout/-o 单行 ledger、工具树模板排除和合法 template 名工作区回归通过 | 工具缺陷可建议结单；不把历史用户文件损坏追认为已修复 |
| #34 | 上标/括号候选、缺号疑点和数字负例通过，语义引用门另有 notes 测试 | 特定原书源侧 45% 数字口径不当作本轮实测；私有验收缺材料仍开放跟踪 |
| #35 | 新增/当前 open 分离、历史 resolved 与重复导入回归通过 | 工具部分可建议结单；保留追加账本，不要求重裁 resolved |
| #36 | utf-8-sig/BOM 等价、显式 --terms 缺文件写前失败、零条可见回归通过 | 工具部分可建议结单；cwd-relative 路径契约保持，不实现含糊 fallback |
| #37 | notes 登记/导入/成品门及 A 的漏门补修验证 | 代码不等于历史书迁移；登记集合外源漏注继续由 #58/私有源清点处理 |
| #38 | 既有版面候选正负例已在 A 首轮全套通过 | 仍为 advisory，不采纳所有缺句号一律 error；全范围来源/残留证据由 D 接续 |
| #39 | min_src_chars、空译独立、三个 G0 调用链阈值回归通过 | 代码降噪已实现；A 的严重短译门是额外核证入口，不整体升格比例阈值 |
| #40 | 当前全源码许可头、SPDX/构建身份测试通过；有效制作指纹见既有 fingerprint 测试 | 代码部分已实现；不加遥测、不作法律保证，PyPI 发布不在本轮默认执行 |
| #41 | 本地旧计划已有实施记录，新计划分批记录当轮证据 | 线上正文旧快照不能代表现状；保留总体单与真实书待办，缺认证不冒充已回填远端 |
| #50 | CliRunner 实际 --help 核对 10 条：doctor/status/notes status/knowledge status 有 --json，其余 qa/build/ledger/g0/import/meta 没有 | 选文档方案：workflow 中英与工作根模板明确机器接口矩阵，不强行增加 CLI 参数或解析彩色输出 |

`qa` 退出 0 仅表示执行结束，不代表 released；机器读 report.json 并核 status 的 fresh/stale。
这一区分在模板和中英 workflow 中明确，且不授权 agent 手编 publication 状态。

## 8. 后续接口实现决策（实现前固定）

- C 参考分支已定位：投稿 `6a65147`（元数据/声明）与 `eae80c0`（导航），基线 `2d84670`。
  保留作者提交后在当前主线复核，不盲套旧 provenance 的 basename/正则匹配。
  新增生成模型字段只接受公开署名字段，不采集密钥或机器路径；`None` 与 `[]` 的显示
  必须有明确区别，元数据变更沿用 A 已补的摘要失效链。
- D1 拟扩展现有 `evidence` 命令组：只读 JSON 报告，不覆写 report/state/events；逐项
  `pass/fail/unknown/manual`，输入摘要、规则版本、scope 与样本分母齐全。外部 sources
  未给出记 unknown，源目录结构/译名/源页可读性保持 manual，不用启发式出语义通过。
- D2 只导出当前真实可得的 raw 页/块坐标、字体、已有 column 和源 TOC；无坐标或栏号
  明确 null，不伪造。候选关联返回全部匹配或歧义，不静默选第一条；相邻页须记录两端页号，
  缺页不冒充连续页。残留扫描覆盖语义注文和后置区，代码字面量继续排除。
- D3 采用显式修复计划，而不是索引音译器：精确旧/新字符串、文件基线哈希、单元及源证据、
  逐项批准、规则版本；禁止正则全局替换和修改 source/publication。默认 dry-run 完全只读。
  实际应用先生成全量候选并验证，再创建持久备份与事务日志；捕获写失败全量回滚。
  强制中断若留下未决日志，CLI 必须拒绝继续正常处理，显式 recovery 在验证当前文件仍为
  计划旧/新版本后恢复备份；有他人新改动则拒绝覆盖。不得宣称多文件瞬时原子可见。

## 9. C 批实施记录

- 保留作者提交：`6a65147` 重放为 `f6ed57f`，`eae80c0` 重放为 `406de54`；冲突仅为
  build 英文文档 i18n 戳，保留两侧实质文案后重新 finalize，不删除作者实现。
- C1 新公共入口反例先 **4 failed**；采纳补丁后独立测试仍 **4 failed**（明确未用不显示、
  任意键被写入、指纹只看外层类型）。补修 `a03afca`：共享公开字段校验覆盖模型/CLI/
  set_meta/指纹；`[]` 有可见自报非使用声明，None 保持历史未知。相关 **64 passed**。
- C2 独立测试先 **4 failed**；新增完整 OPF/nav/NCX 路径身份与顶层唯一入口检查，错目录
  不能用同 basename 冒充可达，旧完全缺入口保留 warning。源目录投影和 linear=no 保持。
- 制作页/元数据/fingerprint/provenance/build/CLI 合计 **128 passed**；i18n/架构组
  **20 passed**；Ruff check/format 均通过（334 文件）。AGENTS、模板 spec、build 和
  SKILL 路由中英已同步，不再保留“制作页不进目录”的矛盾约定。
- 无桌面真实 CLI 与 EPUBCheck5.2.1：`meta --generation-tools` 写入合成模型署名，实际
  制作页含模型与出版社，nav/NCX 均有制作页入口；正例 released=true/ok、stale=false、
  checker=0；同成品伪造追加注文仍被 notes_open 拦截。现场目录
  `/tmp/opencode/aep-cli-smoke-9dxsoxvb`；并非实书/阅读器验收。

## 10. D 批实施记录

- D3：`repair apply <plan>` 默认只读，`--apply` 才写入；严格字段、明确批准、单元身份、
  实算源件及证据摘要、唯一旧字串和逐文件基线。整组内存候选核源保真/align/md 漂移，
  保护原词、页码/标记/链接/代码/标题；拒绝 source/publication/人工表/EPUB 目标。
- D3 写前持久化包含全部旧/新字节与摘要的事务日志；文件与目录 fsync；普通异常整组
  回滚，强制中断留下 pending，普通工作区 CLI 拦截。`repair recover` 全量核当前版本
  及备份后恢复，有他人改动拒绝覆盖；不声称多文件瞬时原子或外部编辑器隔离。
- D3 首轮 **10 failed**（缺接口），实现后 **10 passed**；追加保护词元/源身份
  **6 failed** 后修复。最终 safe-repair **18 passed**（含只读字节快照、失败注入、
  中断/恢复/冲突和 CLI），连同证据/CLI/架构组 **53 passed**，另 i18n **12 passed**；
  Ruff check/format 通过（340 文件）。最终全套与真实 CLI 产品验收另见交付记录。

- D2：新增只读 `evidence source --json`，保留 raw 页/栏/坐标/字体、源 TOC 与全部
  候选匹配；重复位置明确 ambiguous，缺字段 null，代码不作注释候选。页边界含两端页号
  和全部 structured 定位，缺页或缺页号不当续文。全包残留普查含语义 aside 与非 spine
  后置文件；¬/$$ 只列 manual，不代替源注清点或语义裁决。
- D2 首组 **4 failed** 后通过；另补缺页号被误当 0→1 连续的 **1 failed** 并修复。
  重复定位/缺坐标/源 TOC 保留及受影响 notes/evidence/i18n/架构合计 **83 passed**；
  Ruff check/format 通过（338 文件）。双语说明及 SKILL 路由同步。

- D1：新增 `evidence report --json`，只读文件快照且不调用 QA/渲染器来构造正文期望；
  复用独立 Markdown 可见文字规范化、实际 XML、源对照保真和现有独立注释/资源门。
  实算源哈希、逐单元 src↔structured/md↔align/完整正文、登记注文、目录媒体与显式副本；
  source inventory、译名、栏序、源目录语义明确 manual，缺外部源/副本清单 unknown。
  未产生第二份 released 状态，报告绑定当前输入哈希和规则版本。
- D1 公共入口先 **4 failed**，再补伪造 align src 反例 **1 failed**；实现后 evidence/
  CLI/i18n/架构组 **29 passed**，含文件字节快照证明只读、缺副本/截短/伪源拒绝。

## 11. 交付核验与工作区恢复（2026-10-24）

- 原 `/tmp/opencode` 工作区被清空，但共享 Git 对象/分支仍完整；`f4d6c24` 可读取。
  从该提交恢复到 `/tmp/opencode/aep-triage-recovered-20261024`，本地分支
  `fix/issue-triage-recovered-20261024`。恢复初始树与 f4d6c24 完全一致，PR59 head
  `9e57d9f` 仍为祖先；未重写作者或本轮提交历史，未修改主 checkout。
- 清空前全套完成 **926 passed / 1 skipped，317.85s**；实际 CLI/EPUBCheck5.2.1 正例
  released/fresh，repair 干跑/批准应用/幂等/失效/重新登记构建放行链通过，伪造注文
  notes_open。原临时样本已消失，此处仅保留历史命令回执，不冒充当前仍有原样本。
- 恢复后重新核实 Python 导入来自恢复目录，EPUBCheck **5.2.1** 实际可用；Ruff 全仓
  check/format 再通过（340 文件）。重建 `/tmp/opencode/aep-recovered-smoke.py` 并重跑
  全套及独立子进程 CLI 产品验收，以新现场输出作为本次最终证据。
- 恢复后的实际 CLI 现场 `/tmp/opencode/aep-recovered-smoke-fkx4ssyx`：正例
  released=true/ok、checker=0、g4_audit=pass；源/副本证据无 fail，report/source
  和 repair dry-run 文件字节快照不变。repair 明确应用→幂等→报告 stale→import --force→
  build/qa 重新放行链通过。伪造注文负例 notes_open/E_NOTES_CONTENT_MISMATCH，
  evidence 同样退出1。制作页出版/模型署名与 nav/NCX 两入口实际核验通过。
- 恢复保存点 `bb6e45c7209a2cc82b9d4b39d2561567fabe9e5b` 已推送至 GitHub/Gitee 的
  `fix/issue-triage-20261023`，两端 ls-remote 均匹配；最终收尾文档将继续快进到同一分支。
- 恢复后全套再验：`env PYTHONPATH=src /home/misaka0x26fe/github/auto-epublizer/.venv/bin/python
  -m pytest -q` → **926 passed / 1 skipped，324.07s**；唯一跳过为真实 RapidOCR 缺依赖。
  全仓 Ruff check、format --check 通过（340 文件），收尾文档修改后 i18n **12 passed**，
  `git diff --check` 无问题。本轮修复清单 A–D 全部勾选，实书人工边界不计已验收。

### 目标—产物核对表

| 要求 | 实际产物与证据 |
|---|---|
| PR59 完整审查、硬门/失效链/注号/注宿主/字面量补修 | §6、8fd76d3/9ec11ae；test_pr59_review、test_notes、test_t12_gates；保留投稿祖先 |
| 历史 #33–#40/#41 对账、#50 真实机器接口 | §7、d911ced；10 命令 help 与129回归；双语 workflow、work-root 模板 |
| C 制作页公开署名、未知/未用区分、两目录入口 | §9、a03afca/32d3664（保留作者 f6ed57f/406de54）；production_metadata/navigation、fingerprint/provenance 测试 |
| D1 只读完整证据，区分未知与人工 | 7297984、quality_evidence.py；test_quality_evidence 的字节快照/截短/伪src/缺副本反例 |
| D2 页栏/TOC 全定位、独立候选、全包残留 | c34cf34、preprocess/source_evidence.py；test_source_evidence 的双栏、缺页、歧义、aside/非spine覆盖 |
| D3 精确批准、全量预检、持久备份、回滚恢复 | f4d6c24、safe_repair.py；test_safe_repair 的18条只读/失败注入/中断/冲突/幂等测试 |
| 双语 CLI/工作区/QC 契约、架构约束 | AGENTS/spec/SKILL 与 quality-evidence/build/workflow 中英；test_i18n、test_architecture_boundaries，零新依赖/LLM调用 |
| 全套、真实 CLI/EPUBCheck 正负验收 | 本节记录命令和现场回执；未将 GUI/真实书语义判断纳入机械通过 |
| 更新计划和索引、提交推送并核远端 SHA | 本计划与 docs/plans/README.md；最终提交及远端 SHA 在完成后登记 |

真实书源页、译名、索引栏序/页码及未登记源注清点仍为人工边界；未测阅读器 GUI，
既有真实 RapidOCR 测试缺依赖的跳过不计完成。没有修改用户书工作区、上传书稿/凭证，
没有远端关闭 issue/合并 PR，也不把代码完成说成 #41/#57/#58 所有实书工作完成。

## 12. 用户追加授权：主线集成与远端结单（2026-10-24）

用户在前轮交付后明确要求处理 PR 和 issue，因此本节追加远端操作，不改写前轮验收边界。
远端检查时 main 仍为 `08a8b1a`，PR59 仍 open/head=`9e57d9f`；两者都是已验证修复
HEAD 的祖先。保留原作者完整历史与补修提交，采用非强制快进推送至 main；不 squash，
不删除任何分支，不重置主 checkout。PR head 无 check-run/status（pending/0 不是失败，
也不冒充 CI 通过）；使用本轮完整 926 passed/1 skipped 与 CLI/EPUBCheck 实证。

`gh` 当前配置认证仍 401；不读取/打印凭证、不修改认证配置。Git 推送认证可用，因此采用
主分支提交的 GitHub closing references，随后通过公开 API 独立核 PR merged 与 issue state。

| 条目 | 本轮结单理由及保留边界 |
|---|---|
| #33 | ledger 原样输出与工作区发现回归已通过，详 §7 |
| #35 | 新增/当前 open/历史 resolved 冲突分离及幂等回归已通过 |
| #36 | BOM、显式缺文件报错、零术语可见；明确保留 cwd-relative，不采用模糊 fallback |
| #38 | 版面疑点已有 advisory 信号，D2 补齐全包残留范围；不把启发式升级成语义 error |
| #39 | 短源保护与空译独立回归通过；严重非空短译另设证据门，不放宽既有阻断 |
| #48/#49/#53 | 制作页出版/版权与自报模型、nav/NCX 顶层入口完成；保留作者补丁历史并补修身份核验 |
| #50 | 采用 issue 明确允许的文档方案(b)：列实际机器接口与权威产物，不承诺所有命令 --json |
| #54/#55/#56 | PR59 与独立补修、完整正文/注文/注号/图注/目录和 CLI 消费者回归及实际成品验收通过 |

以下仅引用跟踪，不加关闭关键词：

- #34：源侧广义注码仍是候选/人工核证，未用真实书证明原 issue 所述 45% 缺口全清。
- #37：登记/产品注释门已实现，但历史 691 条实书迁移与未登记源清点未验收。
- #40：SPDX/署名/离线指纹已有实现；PyPI 决定及法律解释不是本次代码修复的自动结论。
- #41：总体跟踪中的私有材料与实书验收尚未完成。
- #57/#58：只读证据与安全修复工具已实现；源页、姓名译法、索引栏序/页码及完整源注
  清点仍须独立人工核证，不用代码测试或本次合入证明这些书已修好。

### 远端执行结果

- 集成/结单提交 `db518e56a5b8e43837bea6e9b8344cbcca4cb4d7` 已非强制快进至
  GitHub 与 Gitee 的 main 和 `fix/issue-triage-20261023`；四个远端引用独立核验一致。
- GitHub 公开 PR API 实核 #59：`state=closed`、`merged=true`，
  `merged_at=2026-10-24T02:40:51Z`；GitHub 标记的合并提交为保留的历史 merge
  `99daab90a9547f007e8f543e5c3d19713246ef4f`，不是将作者工作挤掉的 squash。
- 公开 issue API 实核 **12 项 closed/completed**：#33/#35/#36/#38/#39/#48/#49/#50/
  #53/#54/#55/#56；**6 项仍 open**：#34/#37/#40/#41/#57/#58，恰与上表边界一致。
- 未修改认证配置；证据与处置依据通过关闭引用提交和本计划公开关联，未冒充已发送 API
  评论。仅文档/提交说明变动，i18n 再验12通过；代码仍是926 passed/1 skipped的验收树。
