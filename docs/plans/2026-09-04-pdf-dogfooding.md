# 计划：真书 dogfooding——PDF 内容提取管线实战验证

> 状态：**规划中**（2026-09-04 立项）。前置：计划 C（S2–S4）已落地，但只过了
> 合成 fixture 测试；阈值与判据未经真实书籍检验。

## 1. 背景与问题

新管线的能力——书签 TOC 切章、多栏阅读顺序、插图路由（整页/内嵌/扫描背景守卫）、
表格双路径、公式三特征检测、inserts 溯源审计——全部只在 `tests/` 的合成 PDF 上验证过。
合成 fixture 无法暴露：真实排版的字 号分布、伪书签（目录级书签 vs 正文书签）、
表格线残缺、公式字体多样性、扫描件混合文字层等真实情况。

## 2. 选书标准（三类各至少一本）

| 类型 | 要求 | 验证重点 |
|---|---|---|
| 有书签 TOC 的文字层 PDF | level-1 书签 ≥ 5 条；章节页码准确 | 切章边界 vs 书签、frontmatter 归属、页码区间 |
| 含图表/公式的学术 PDF | 有线框表格、编号公式、插图 | 表格 md 质量/裁剪图触发、公式检测查准查全、多栏阅读顺序 |
| 扫描件（可选） | 无文字层或 OCR 文字层 | OCR 五档路由、扫描背景不提取、OCR 域不误触发整页路由 |

来源：本地藏书或用户提供的无版权文件；**绝不提交真实书籍文件进仓库**（测试一律 tempfile）。

## 3. 执行步骤

1. `auto-epublizer doctor [--ping]`——记录环境快照；
2. `auto-epublizer preprocess <book.pdf>`——读 facts.md（书签/扫描/乱码判定 +
   路由提示是否正确），按 skills 写 preprocessing/ 七件套；
3. `auto-epublizer init`（或 convert 只验 ingest）——检查 `structured/raw/`：
   - `page-NNN.json` blocks 顺序（双栏页人工比对阅读顺序）；
   - `raw/media/`：内嵌图/整页图/裁剪图的数量与命名（`pNNN-imgNN` / `pNNN-page.png`）；
   - `raw/inserts/`：id 命名、index.jsonl 快照、公式记录 `latex: null`；
4. `auto-epublizer convert`（不翻译，快速走 build + qa）——检查 EPUB 内图片、
   `qa` 的 inserts 审计发现与 `prov_ok`；
5. 抽查误报/漏报：表格检测误触发（把正文段落判成表格）、公式误报（居中短行）、
   插图漏提（内联小图 < 32px 被装饰过滤是否合理）；
6. 回填：确认/调整的阈值写回 `docs/pdf-content-spec.md` §7（改动走常规提交）；
   发现的缺陷按最小回归测试补 `tests/`。

## 4. 验收标准

- 三类书的验证记录（可写 `docs/testing-<book>.md` 或直接在本文档追加「验证记录」节）；
- spec §7 阈值与真实书的偏差已回填或有明确「维持默认」结论；
- 暴露的缺陷转化为可失败的回归测试并修复；全量回归 + ruff 双检通过。

## 5. 本轮不做

- 翻译/审校全流程（G1–G3）的实战验证——另一轮 dogfooding 单独立项
- 扫描书 OCR 语种/质量调优（依赖具体 OCR 引擎）
- 真实书籍文件入库（永远不做）
