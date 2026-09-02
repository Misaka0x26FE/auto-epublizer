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
- **溯源**：每个 `Segment` 带 `meta.source_page`，PDF 每页有 `page-NNN.json` 对应。

## 契约

- 单元 = 翻译最小可管理单位；`Unit.meta` 存 `rel_path` 与 `region`（`set_units` 时写入
  `publication.json`），analysis/translation/build 都靠它定位文件。
- 标题层级（h1/h2）数量、段落块数量应与源文一致（G0 校验锚点）。
- 插入元素（`{fig:NNN}` 等）标记数量守恒；脚注/尾注引用↔定义配对（G0/G4 校验）。

## 说明

分栏阅读顺序、复杂表格保形、脚注/尾注专项提取是复杂 PDF 场景，当前为后续扩展点；
基础四层归类 + 页眉页脚/页码剔除已实现。
