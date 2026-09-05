# Lessons（实战经验沉淀）

本子目录存放**真实工作（处理真实书籍/源站）中针对特定情况的经验**，区别于
`references/`（面向每本书的常规操作指引）。每篇 lessons 对应一种**具体源站/脏源/
边界情况**，供下游 agent 遇到同型情况时直接对照处置。

## 与 references 的分工

| 目录 | 回答 | 触发 |
|---|---|---|
| `references/` | 每本书每步怎么做 | 按阶段只读一份（SKILL.md 路由表） |
| `lessons/` | 这个特殊情况遇到过，怎么判、怎么修 | 只在**源站/脏源/边界情况**匹配时读 |

## 约定（写前必读）

1. **经验是「判据 + 处置」，不是结论**：必须写清「怎么判断命中该情况」与「怎么处置/验证」，
   不照抄某次修复的最终字符串——下游 agent 据判据自行适配。
2. **每篇一篇一主题**：命名 `YYYY-MM-DD-<主题>.md`，只覆盖一种特定情况。
3. **必带「复现/验证」段**：如何本地重放该情况（如最小 fixture），确保经验可自证、不空谈。
4. **引用可读代码位置**：涉及 build/provenance 等行为时给 `file:line`，并标注是否已在
   主仓库修复（`已修复` 或 `见 plans/xxx`）。
5. **用户数据不入门**：不含真实书源/译文/密钥；fixture 一律 tempfile 或匿名化。

## 索引

| 文档 | 主题 | 状态 |
|---|---|---|
| [2026-09-05-baka-tsuki-html-figures.md](2026-09-05-baka-tsuki-html-figures.md) | Baka-Tsuki 源站 HTML 的插图段结构（figure>a>img 三行）在 ingest/build 的保真与复原 | 已修复（1766e7a 等）+ 经验留存 |
| [2026-09-05-scanned-pdf-mineru-first.md](2026-09-05-scanned-pdf-mineru-first.md) | 扫描件 PDF：MinerU 最优先（换行/插图识别），传统 OCR 只识别字符需 agent 逐页阅读兜底 | 已落地（ingest/mineru.py）+ 经验留存 |
| [2026-09-05-scanned-pdf-operations.md](2026-09-05-scanned-pdf-operations.md) | 扫描件实操：>200 页分批/合并、**别脚本化拆分（agent 手动拆）**、单单元构建丢 nav、围栏代码块缺支持 | 经验留存（豆包四轮实测） |
| [2026-09-05-agent-translation-workflow.md](2026-09-05-agent-translation-workflow.md) | agent 主进程翻译工作流：每 3–5 单元 build 验证、标题先定稿、Write 工具代替 heredoc、G0 告警不能全当噪声 | 经验留存（GT1/GT2/On Lisp 实测） |
