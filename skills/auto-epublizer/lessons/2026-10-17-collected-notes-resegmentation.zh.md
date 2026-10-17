> **中文** | [English](2026-10-17-collected-notes-resegmentation.md)

# 书末注释被按页摊平：多条注挤成巨型段落

> 日期：2026-10-17　来源：交付后校对反馈（工作根 `sample-notes-a`）
> 历史状态：作者报告已在工作根侧用 `preprocessing/tools/rebuild_notes.py` 修复；该工具不在本仓库。
> 下列现场数字均为作者报告，不是本次仓库修订的本机实测，也不代表已通过当前 N 阶段验收。

## 触发场景与候选判据

书末统一注释区（collected endnotes），尤其每章重起 `1. 2. 3. …` 的体例。
作者报告一书有 148 条注、12 个章组，却仅有 14 个成品段落，最长段超过 7000 字，仍曾 `released=true`。

只在已确认的注释单元或显式注释语义区中比较：成品段落数远少于同口径 Markdown
注号形态候选数，或长段中含多个 `N. ` 形态，值得逐段核证。数字必须带文件与段索引。
候选不是注条数；引文中的 `vol. 2.`、书目编号等也会命中。不能据此阻断发布、自动切注，
更不能把全书数字或文件名含 notes 当作注释身份依据。

## 原始证据与语义判断

1. 查看 `structured/raw/page-*.json` 及对应原页：作者报告一页的区标题字号 `27.5`、
   分章标题 `15.0`、注文 `11.25`。字号差异只是分类线索，**不能证明 raw 分段完整**。
   必须核对文字、坐标、阅读顺序、缩进及前后页，确认是否仍有合并块、漏块或重复块。
2. MinerU 路径查看 `structured/raw/mineru/content_list.json` 的 `type`
   （如 `text`/`page_footnote`/`header`/`footer`/`list`/`image`）及原页；类型也不是语义裁决。
3. 作者使用 `fs >= 20`、`14 < fs < 20`、`10 < fs <= 14` 分类区标题、章标题和注文。
   这只是该书的校准值，不可泛化为所有书的规则。
4. 原始行首 `^\d{1,2}\.\s` 比任意句中 `N. ` 更可靠，但仍只是候选边界。
   作者报告 `‘Nation: 4. Le nationalisme’`、`‘Nation: 3. Nation et idéologie’` 被句中切分误伤。
   行首也可能是引文、列表或跨页碎块；需 agent 对照原文逐注判断。
5. 小写、大写或引号开头**都不能自动裁决**跨页续句或注内新段。保留原书合法的多段、列表、
   引文和媒体；不能为追求一注一段把它们合并。

## 修复：候选重建后必须进入规范 N 阶段

1. 以原始证据和已核证源注为依据恢复边界。作者报告行首法得到 148 条 / 12 章组、无跳号；
   `1..N` 连续只是本书的自检规则。其他书可能续号、重起、跳号或使用非数字标号，必须记录
   原书证据，不能补造、删除或重排注释来凑连续。身份与显示编号分离。
2. 摊平译文可用已核证源注作模板生成单调 DP 对齐**候选**。作者曾按句中 `N. ` 切碎片，
   使用首碎片号不符 `100000`、号对但前非句末标点 `200`、多吞碎片 `800` 的代价。
   这些是现场启发式，不是通用正确性规则；用末碎片评分曾造成 2 处错配。
   agent 必须逐注核证候选的内容、边界和位置，不得直接接受 DP 结果。
3. 中间修复若修改 Markdown 和 align，两把门仍适用：translation md ↔ align `tgt` 文档一致性，
   align `src` ↔ structured md 源保真。作者报告漏改 align `src` 一次产生 148 条发现。
4. **legacy 重分段只是中间修复，不是最终交付**。按 [notes.zh.md](../references/notes.zh.md)
   提取完整 `structured/notes.json`，保留合法多段/媒体；恢复正文原位 `[^ref-ID]`，
   逐候选处置并 `notes register`，建立稳定 `note_id`/`ref_id`、scope 与双向位置证据。
   译注进入 `translation/notes.json` 并绑定源注 digest，import 后构建标准 noteref/footnote 弹窗链接。
5. 最终验收按 note/ref 身份、完整内容、媒体、href 与逐引用 backlink 核对；独立 N hard gate
   保持不变。**不要求 `<p>` 数等于注条数**；一条合法注可有多个段落或列表。

## 复现与核证清单

- 使用匿名 fixture，不把真实书源/译文复制到仓库。历史作者报告不是本机验证证据。
- 从最终 EPUB 用项目 XML parser 读取已确认的注释区，记录文件、段索引、段长和注号形态数；
  与实际构建输入的同口径 Markdown 比较，而非尚未渲染的译文。
- 回到 `structured/raw/` 与原页逐条确认边界、跨页续块和引用位置；字号仅辅助。
- 检查该书有证据的标号范围；保持 G0（包括 heading、terminology）、双向源保真和 N gate。
- 重建工具必须幂等，从不可变输入读取；作者报告首版读回旧输出，产生 `## ## 序言` 及空标题。
- 最终检查每个 note/ref 的内容、媒体、标准链接与回链，不以段数代替完整性验收。

## 历史修复中的两个坑

1. 作者报告 4 处行末连字符 `self-`/`World-`/`Christian-`/`anti-` 都是真复合词，需保留为
   `self-contradiction`、`World-Economy`、`Christian-non-Christian`、`anti-capitalism`。
   不可由此推导所有行末连字符都保留或都删除；必须按原文核证。
2. 普通 `1. …` 段可能触发 `build/html.py` 的 `_OL_MARK` / `_OL_LINE` 有序列表规则。
   作者在 legacy 修复中用 `1\. ` 避免自动编号，并要求源 md、align `src`、译文 md 同步。
   **转义编号的普通 `<p>` 不是规范注释交付**；最终仍须走上述 N 阶段。

## 代码位置与当时的检测缺口

- 列表渲染：`src/auto_epublizer/build/html.py`；标题守恒：`src/auto_translator/review/g0.py`。
- 双向源保真：`src/auto_translator/review/fidelity.py`；规范注释流程：上述 notes reference。
- 工作根重建脚本：`workspaces/<slug>/preprocessing/tools/rebuild_notes.py`（不在本仓库）。
- 作者报告时 `qa/audit.py` 尚无 collected-notes 未分段 advisory；另 9 本有同类候选
  （其中两本分别 75 段、29 段）。这是历史检测缺口，不能当作这些候选都已核证的结论。

## 当前检测入口（#46）

现已由生产 `qa` → `audit_epub` → `report.json.audit.findings` 提供
`W_COLLECTED_NOTES_UNSEGMENTED` warning；权威 notes 构建输入或显式集合语义区才扫描。
data 保留文件/段索引、候选数、段数、最长段与 `structured/raw/` 核证指针。
阈值、实际源/译文选择及误报/漏报边界见 [qa.zh.md](../references/qa.zh.md)。
它只给候选，不自动切注、不直接阻断；最终仍按规范 N 身份/内容/媒体/链接验收。
