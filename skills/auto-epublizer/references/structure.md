# Structure（四层结构重建 + 溯源）

把归一化单元归类为出版物四层结构，清洗后落 `structured/`，作为翻译与封装的源文权威。

## 四层结构

```text
structured/
├── cover.md                        # 封面
├── frontmatter/{titlepage,copyright,dedication,foreword,preface,toc}.md
├── body/ch01.md ...                # 正文单元（翻译主战场）
├── backmatter/{afterword,appendix,notes,bibliography,index,glossary}.md
└── media/                          # 媒体资产
```

## 归类规则

标题关键词 → (region, kind)，例：

| 标题含 | region | kind |
|---|---|---|
| 封面 / cover | cover | cover |
| 书名页 / titlepage | frontmatter | titlepage |
| 版权 / copyright | frontmatter | copyright |
| 献词 / dedication | frontmatter | dedication |
| 他序 / foreword | frontmatter | foreword |
| 前言 / 自序 / preface | frontmatter | preface |
| 目录 / toc / contents | frontmatter | toc |
| 后记 / 跋 / afterword | backmatter | afterword |
| 附录 / appendix | backmatter | appendix |
| 参考文献 / bibliography | backmatter | bibliography |
| 索引 / index | backmatter | index |

未命中关键词 → `body` + `chNN`（顺序编号）。单元 ID 稳定（`ch01`、`front-preface`、`back-index`）。

## 清洗

- **页码剔除**：独立成段的页码（`12`、`- 8 -`、`第3页`）。
- **页眉页脚剔除**：按 `source_page` 分组，同一短文本在 ≥50% 页首/页末出现即剔除（`min_pages` 保护）。
- **EPUB 锚点/属性残留**：`read_epub` 在入库时已清除 `[]{#id}` 锚点、`{#id}` 属性、
  `[text]{.class}` 类属性与 `<br>`；若 `structured/` 仍见此类残留在标题里，说明走了
  pandoc 通用回退路径，按 `references/ingest.md`「EPUB 按 spine 切分」排查。
- **溯源**：每个 `Segment` 带 `meta.source_page`，PDF 每页有 `page-NNN.json` 对应。

## 契约

- 单元 = 翻译最小可管理单位；`Unit.meta` 存 `rel_path` 与 `region`（`set_units` 时写入
  `publication.json`），analysis/translation/build 都靠它定位文件。
- 标题层级（h1/h2）数量、段落块数量应与源文一致——**审校核对锚点**（g0.py 提供计数
  纯函数但未接入自动校验，属后续扩展点）。
- 插入元素（`{fig:NNN}` 等）标记数量守恒（G0 单元级总量守恒已接线，丢失即硬缺陷）；
  **md 表格形状守恒已接线**（表数/行列数，import 硬校验）；
  脚注/尾注引用↔定义配对与回链由 G4 审计（`E_FN_BACKLINK`/`E_ANCHOR`）覆盖。

## 单元边界重建（restructure 登记）

修复/重切导致**单元集合变化**（拆分、合并、新增、删除）时，内容级修改无需登记
（build/provenance 直接读 `structured/`），但边界级变更必须登记，否则
`publication.json.units` 与磁盘脱节：

1. 按真实章节手动重写 `structured/`（每个单元一个 md，首行 `# 标题`）；
2. 写 `preprocessing/structure.csv`（列 `id,region,kind,title,level,rel_path`；
   每行一个单元，`title` 必须等于该文件首行标题、`rel_path` 与 region 前缀一致）；
3. 运行 `auto-epublizer restructure`：校验（文件在、无孤儿 md、无重复 id）后更新
   `publication.json.units`；
4. 状态语义：同 id 且内容未变 → 保留状态；有变 → 回退 `split`（需重译重 import）；
   消失的 id → 输出孤儿产物提示（旧 translation/align 可清理）。

> 何时用：MinerU/OCR 层级混乱需重切、碎片单元合并、单单元丢 nav 需拆分。
> 详见 `references/repair.md` 与 `docs/semantic-repair.md` §3.3。

## 说明

分栏阅读顺序、复杂表格保形、脚注/尾注专项提取是复杂 PDF 场景，当前为后续扩展点；
基础四层归类 + 页眉页脚/页码剔除已实现。
