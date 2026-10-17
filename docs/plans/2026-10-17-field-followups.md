# 2026-10-17 新增现场 issue 与 PR 修复

状态：已完成（集成补修 `5de1225`；#46 实现 `fced55f`、#47 实现 `25cfbd3`）。前序 PR42 已合并（`8850c51`）；本轮分别处理 #43/PR44、PR45、#46、#47，不把前序验收当成本轮证据。

## 1. #43 / PR44：相对工作区摘要

用户/投稿方报告是事实：相对 `store.dir` 与已带工作区前缀的成品路径被再次拼接，导致 QA 写出的摘要缺成品字节，而 status 复算读到字节，报告立即 stale，台账随之降级。保留 PR44 作者实现，保证保存和计算摘要使用同一规范引用；工作区内引用保持相对、外部引用绝对。路径转绝对不得提前消除用户选择的符号链接，否则后续重定向会脱离摘要证据。

验收：相对工作区默认输出、显式绝对成品、外部成品均能 QA→status 自洽；成品字节变化后 stale；实际 CLI 的 ledger 不再把新鲜放行误降级。旧报告不手改 released，须重新 QA 生成当前证据。

已观测：`tests/test_artifacts_digest.py` **14 passed**，两文件 Ruff check 与 format-check 通过。
真实无桌面 CLI 使用完整 EPUBCheck：相对工作区默认输出、显式绝对成品、外部成品及外部
符号链接四例均 `released=true`、checker=0、`stale=false`，实际 ledger 为 `released`。
切换 cwd 后用绝对工作区仍 fresh；仅把交付链接重定向到不同字节的合法 ZIP 后，
保留历史 released=true、stale=true，实际 ledger 退为 `built_not_released`。

已合并：PR44=`0b2c7a6`，投稿分支补修=`3c17de0`。保留作者提交；旧报告须重新 QA。

## 2. PR45：经验文档的适用边界

保留投稿历史与现场数字，修正通用化风险：字号不同不是分段完整的充分证据；首字母大小写/引号只是续文候选；DP 不是语义核证；原注不保证统一连续 `1..N`；一个合法注释可有多段，不能用段落数等于注数作最终验收。

从 raw 恢复 legacy 注释分段只是中间整备。最终仍须按 N 阶段抽取 notes.json、保留原位稳定引用、登记与译注摘要，并以标准 noteref/aside、内容、媒体和回链验收，不以转义编号的普通段落代替弹窗注释。

已合并：PR45=`05db7b8`，边界补修=`1a75f19`；i18n check/links 均通过。
历史实书数字仍标明投稿方记录，不冒充本机重新验证。

## 3. #46：增加分段疑点检测口

只增加 advisory，不自动切注或阻断放行。利用实际构建输入的权威 notes 单元或显式注释语义上下文，对段落数/注号候选数失衡、长段多注号给出文件、段序、计数与最长段证据，指向 raw 核证。普通正文列表与代码不得被猜成注释区；一个多段注文合法。身份/内容/href/backlink 仍由独立 N 硬门负责。

验收：真实构建的小型摊平样例出现定位告警；正常分段、正文数字、代码和合法多段注有负例；warning 不使原本合格的产品变成 hard failure。

实现=`fced55f`。集成实测另发现真实渲染器会把 `1. … 2. …` 变成单个 `<ol><li>`，
只数 `<p>` 会漏报；已把独立/叶级 `<li>` 纳入文本块并增加列表索引与最长块证据，
排除带子段/子列表的容器重复计数。代码负例改用真实 raw HTML fence，不用已被转义的伪代码标签；
删除完整 finding 字典快照/转发相等断言，改验消费者可定位证据和独立 N 门优先级。

已观测：advisory、notes、qa、artifacts_digest 四组 **118 passed**。真实无桌面 CLI
与完整 EPUBCheck 的五例均 released=true、checker=0：源侧摊平注释准确告警（独立 li=1、
候选=8、最长块=676）；实际改用正常译文构建不告警；普通正文数字、代码字面、合法
登记注释均不告警，后者 notes_findings=[]。未跑投稿方的 19 本真实书。

## 4. #47：随工作根分发四个工具

- `pack_outbox.py`：整批核验当前 released/ok 且非 stale；按报告选择成品，复制后逐件 SHA-256 对账，全部成功才写清单；不覆盖完整或中断批次，不因没有 translation 否定合法 source conversion。
- `build_ledger.py`：机器列只取真实 CLI ledger，按稳定工作区键及表头搬回批次/领域/摘要/最后修改等人工列；重复运行幂等，不把词数误当领域。
- `check_doc_links.py`：核对根规范与过程文档的真实相对文档/脚本/目录链接；忽略外链、代码示例、显式占位和 EPUB 内部件名；断链定位且非零退出。
- `check_tracked.py`：实际核对跟踪/磁盘/忽略/未跟踪/缺失；按独立精确子路径允许规则识别意外忽略；不自动 git add，也不建议把秘密直接加进仓库。

脚本为标准库实现、路径可参数化，随既有 work-root 模板生成；状态与摘要继续由 CLI 权威计算，不复制第二套实现。

实现=`25cfbd3`。集成复现并修复：Markdown 脚注正文被误认路径、内嵌 fence info
误关外层代码示例、普通 `.html` 真断链被忽略、清单写满失败却留下 `MANIFEST.md`
完成标记。清单改为同目录临时文件写完后原子发布，失败保留中断现场但不发布完成标记。
消费者测试 **14 passed**；OS 文件大小上限用于验证写失败边界，不作为实际 EPUB 放行证据。

真实工作根 smoke 另外暴露并修复两类集成缺口：

- CLI 原始台账未转义书名的 `|`、反斜线和换行，导致保守搬运器拒绝合法元数据。
  修复权威 `render_ledger` 的序列化，不让工具猜拆列；已保留 failing-before/passing-after
  消费者回归，并删除旧固定表头/提示语快照测试。
- 原样生成的规范把扩展名字面 `.md` 当文件引用，且把单书 `references/user/` 写成
  工作根相对路径。修正路径识别与规范的工作区占位路径，并将常用台账命令迁移到
  保留人工列的工具；新增真实生成→台账建立→引用有效→删台账即失败的生命周期回归。

已观测的脚本运行（均脱离桌面）：

- 真实 CLI 生成工作根，两本无译文源语言转换，经完整 EPUBCheck 返回 0、QA released=true。
- 报告绑定非默认成品，整批实际复制与 SHA256/清单逐件一致；stale 或文件名冲突时批次不创建，
  既有完整与中断批次不覆盖。
- 真实 ledger 的含竖线/反斜线书名可解析，人工 `\|` 摘要/领域/批次/修改日保留，二次重算幂等。
- 原样模板文档通过；脚注正文与嵌套围栏不误报，删除普通 HTML 目标准确报断链。
- 独立 Git 索引实测：精确允许 docs/__pycache__ 与 outbox/*/epub，拒绝 .tr/ 与 outbox 中其他
  文件；未跟踪/跟踪但缺失准确定位，检查前后索引未变。

修复台账转义后的 work-root/status_all 组合 **21 passed**；新增生成器生命周期回归已纳入最终全套通过。

## 5. 集成纪律

PR44、PR45 均保留投稿者提交，修复后正常快进推送原 PR 分支再合并；#46 检测与 #47 工具独立提交。两个独立工作片使用隔离 worktree；集成负责人统一执行消费者回归、真实无桌面 CLI/脚本 smoke、Ruff、i18n，并按实际证据回写此记录、关闭 issue、同步 GitHub/Gitee。历史真实书不在本轮自动迁移范围。

## 6. 最终验收记录

- `python -m pytest -q`：**802 passed、1 skipped，229.91 秒**。
- `ruff check .`：通过；`ruff format --check .`：**325 files already formatted**。
- `scripts/i18n.py --check` / `--links`：均 OK；QC、QA、工作根、SKILL 路由双语同步。
- #43 路径/符号链接、#46 注释警告及负例、#47 四脚本的实际 CLI/Java/Git smoke 如上。
  消费边界的合成报告与 OS 限额夹具不是实书放行证据；真实 smoke 使用完整 EPUBCheck。

本轮不改真实书工作区、不代替原页逐注核证，也不宣称阅读器弹窗实测通过。
注释语义拆分、标准注册与独立 N 硬门仍按既有契约执行；advisory 不会自动修书或放宽放行。

## 7. 合并与发布

- PR44 已合并：`0b2c7a63107b85acbdec57ec5861c8bdcec48948`。
- PR45 已合并：`05db7b8185987b846a248390ade1d71057578722`。
- 集成补修 `5de1225bc5421e77db56bdd46b9e5d5698fadf2d` 已推送 GitHub 与 Gitee main。
- #43 已随 PR 关闭；#46、#47 已附实测证据并关闭：
  [#43 验收](https://github.com/Misaka0x26FE/auto-epublizer/issues/43#issuecomment-6235387546)、
  [#46 验收](https://github.com/Misaka0x26FE/auto-epublizer/issues/46#issuecomment-6235387514)、
  [#47 验收](https://github.com/Misaka0x26FE/auto-epublizer/issues/47#issuecomment-6235387512)。
