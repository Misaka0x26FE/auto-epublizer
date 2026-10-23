> **中文** | [English](quality-evidence.md)

# 证据与安全修复契约

## 只读命令

`auto-epublizer evidence report --workspace <dir> --json [--epub <path>]
[--external-source <file>] [--copy <expected.epub> ...]` 重做当前证据，不运行 QA、不写
report/state/events。JSON 含规则版本、输入摘要、每项 scope、`pass/fail/unknown/manual`
及实际证据；存在 fail 时退出 1，但未知/人工项不伪装通过。

源件身份实算；逐单元核 src↔structured、md↔align 和独立规范化的完整成品正文；注文按
当前登记及成品渲染模式独立核验。目录/媒体使用既有机械门，源目录语义仍待人工回源。
不提供外部源件或预期副本时记 unknown；显式副本缺失即 fail。该报告没有 released 字段，
不能替代 QA、源注清点或语义验收。报告默认 stdout，调用方若保存应自己选择新文件。

`auto-epublizer evidence source --workspace <dir> --json` 只读导出原始页块、真实可得的
page/bbox/font_size/column、facts 中源 TOC、单元角色及独立源注候选。缺失精度为 null，
重复匹配全部列入 raw_matches 并标 ambiguous，不取首个位置；代码字面量不作注释候选。
页边界同时列两端页号与全部单元/块定位，缺页号或不连续时不宣称续文候选。
raw/facts 未提供的信息不从文件名或字体阈值猜测；源注是否齐全仍须逐页人工核证。

`evidence report` 的 product_residue 扫描全包 XHTML/HTML（含语义 aside 和非 spine
后置文件），排除 code/pre 的字面量；¬/$$ 只列 manual 候选，不自动改写或定性错误。

## 1. 分清证明对象

- `qa released` 证明已知机器契约；不证明全译、译名正确、索引栏序正确、源书无漏注。
- 已登记注条=aside 数只覆盖登记集合。源清点另查原印注号/页边界/注文区字体与版位；
  跳号只是候选，不补造。跨页注头与尾须以源页位置配对，不能仅以相似词匹配。
- 词元袋保全不证明顺序、次数、块归属；同单元重复、抽取器差异均不自动 explained。
- 乱码文本层不证明页面空白/不可辨；声明视觉核证前必须实际渲染并读图。
- `src==tgt` 全量数含标题、图片、定位、著录，不等于漏译数；统计须声明范围、归一化、
  aside 是否排除、分母、快照摘要。正文、索引、书目、注释分别清点，不按数字批量搬移。

## 2. 结构与索引

先源页→栏→行还原条目及页码续行，再冻结结构，再核译名。源 TOC、正文单元、nav 顶层、
子标题与 landmarks 分开对账。页眉回声候选不等于可删除源块；伪表格不能只删标签。

索引与书目分开；用户要求「中文首词＋原词括注」时不得整单元保留原文豁免。
正文「中文（原文）」正则摘取只产生**候选**，可能夹入动词、职务、地点和近似人名。
必须逐条核源名、正文译名及交叉引用目标，保留原词检索；不凭有汉字/映射表无空值验收。
音译、异名对应和讹形修复属于 agent 语义任务，程序不自动裁定。

## 3. 修复工具的最低契约

### 已实现的精确修复入口

```bash
auto-epublizer repair apply approved.json --workspace <dir>          # 只读预检
auto-epublizer repair apply approved.json --workspace <dir> --apply  # 明确写入
auto-epublizer repair recover --workspace <dir>                     # 回滚未决组
```

三个入口成功输出 JSON、失败退出 1。计划严格拒绝未知列，结构如下（摘要必须是真实 SHA-256）：

```json
{
  "schema_version": "1", "rule_version": "safe-repair-1",
  "source_sha256": "<registered and actual source SHA-256>",
  "edits": [{
    "unit": "ch01", "path": "translation/body/ch01.md",
    "sha256": "<original file SHA-256>",
    "old": "旧译名", "new": "新译名", "approved": true,
    "evidence": {"path": "source/book.pdf", "sha256": "<evidence SHA-256>", "page": 7}
  }]
}
```

目标仅限当前单元登记的 structured/translation Markdown 及 translation/align JSONL；
不接收 source、publication、术语/人工表或 EPUB。每文件一条非空、唯一精确替换，
多处修改须先人工形成唯一的大字串，不做全局正则替换。译文须提交一致的 md/align。
整组内存预检源保真、align 完整性和 md/align 漂移，保守保护注码、插入标记、链接、
数字、代码及标题层级；原文拉丁词不得删除。合法但超出此边界的编辑需独立处理和审计，
不放宽此工具来迁就。源证据页码只记录批准依据，不证明工具已阅读源页。

实际写入先在 `preprocessing/repair-transactions/<plan-sha256>.json` 持久化全部旧/新字节
及摘要，再逐件替换，文件及目录 fsync 后才登记 applied。普通写失败整组回滚；强制中断
保留 pending。普通工作区 CLI 拒绝未决事务，只有显式 recover 可恢复；恢复先整组核验
当前仅含旧/新版本，出现他人新改动或备份损坏则拒绝，绝不覆盖。保留日志，不手删绕过。
已应用计划重跑核目标版本后返回 already_applied。锁仅协调遵守工作区锁的进程；不保证
任意外部编辑器隔离，不声称多文件瞬时原子。Windows 不提供 POSIX 目录 fsync。

入口不推进 publication 状态、不手补 EPUB。应用后按范围重新 import（已 reviewed/built
用 --force）或 notes register/restructure，再 build、qa 及独立交付审计。

1. 输入计划逐项含：单元/源位置、原字串、拟改字串、证据文件及页码、批准状态、
   原文件 SHA-256、工具/规则版本。机器候选和已批准条目分开。
2. 不覆盖已有人工表。未知列、重复键、缺译、歧义、未批准项、基线变化明确拒绝，
   不猜「第一个候选」；保留 UTF-8 无 BOM，术语表仍遵守其独立 8 列契约。
3. **全量预检在写盘前完成**：先在内存生成全部 md/align（必要时 `.tr`）改动，
   校验源保真、漂移、标记/页码/链接及原词保全，所有文件均通过才进入提交阶段。
4. 干跑不写文件、状态或账本。实际应用采用明确的事务/备份恢复机制；多文件
   `os.replace` 逐件成功不是整组原子事务，必须支持中断恢复，失败不得遗留半组新文件。
5. 重跑幂等，拒绝重复包裹、别名全局替换、正则前缀碰撞。索引 Unicode 首字母、引号、
   断词及页码续行均有坏样本测试；测试先失败再修复，不能以放宽判据制造通过。
6. 禁止手编 publication.json。书稿修改通过 CLI 登记，重新 build/qa 后才验成品；不手补 EPUB。

## 4. 审计生成器与裁决器

每项输出 `pass/fail/unknown/manual`、实际命令/输入摘要、覆盖范围、检查版本和证据。
未执行不勾选，不固定写「无缺陷」。重做/沿用逐项记录；沿用必须绑定当前输入及规则，
旧 explained 不得覆盖新发现，规则变更要求复核或明确失效。

- source 身份实算并比登记；外部 sources 缺失是 unknown，多候选是歧义，均不称三方一致。
- 四方对账用实际正文/align/成品内容与位置；H1 命中、块数相等、恒真式均不能替代。
- 导航按解析后的同一包内路径域逐条对标签/目标/层级，不能一侧带 OEBPS/ 一侧不带。
- 译注去真实回链/标签后须非空、完整同口径相等；空串和双向子串包含不是完整性判据。
- 残留普查覆盖正文、语义注、前后置区域；非中文著录可能合法，不与漏译混算。
- 副本逐件校验预期文件、hash、审计绑定；缺目录/文件即失败。已有 MANIFEST 跳过
  复制不代表重新核验。先确认 report 未过期，再打包；保留旧副本不改，新版本独立目录。

## 5. 操作与公开反馈

隔离 worktree 修改 CLI；不覆盖用户工作区、不执行广泛 checkout/reset/clean。
只暂存本任务文件；并行会话导致全仓非零不是丢弃其工作的理由。不得上传书稿、源图或密钥。

复用另一个 worktree 的虚拟环境时设 `PYTHONPATH=src` 并核导入位置，避免 editable install
测错仓。i18n finalize 只更新戳，**不翻译正文**；必须真实同步两种语言再跑全套测试。

源清点/索引语义未做、GUI 未测和超出启发式能力的事项如实保留；issue/PR 记录已修范围和
剩余风险，不把文档承诺或单元测试冒充书稿验收。
