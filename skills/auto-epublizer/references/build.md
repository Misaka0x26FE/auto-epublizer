# Build（EPUB 封装）

`build` 命令把译文（缺省回退源文）封装为标准 EPUB 3，落 `output/`。

## 命令

```bash
auto-epublizer build [--bilingual] [-o <out.epub>] [--workspace <dir>]
```

- 单语：从 `translation/<rel_path>` 读译文（缺省回退 `structured/`）。
- 双语：`--bilingual` 按 `align/` 对照表渲染源/译交错，输出 `<slug>-bi.epub`。

## EPUB 3 组件

| 文件 | 说明 |
|---|---|
| `mimetype` | `application/epub+zip`，zip 首位、不压缩 |
| `META-INF/container.xml` | 指向 `OEBPS/content.opf` |
| `OEBPS/content.opf` | manifest/spine/DC 元数据/`dcterms:modified` |
| `OEBPS/nav.xhtml` | EPUB 3 导航（toc） |
| `OEBPS/toc.ncx` | NCX（向后兼容） |
| `OEBPS/landmarks.xhtml` | frontmatter/bodymatter/backmatter 地标 |

## 确定性

- 构建时间戳用冻结值（非 `time.Now()`），同一冻结工作区两次构建字节一致。
- 结果按稳定原文序合并，不随并发完成顺序变化。
- 内部稳定 ID 不外泄到产物（脚注/尾注用确定性序号）。

## 元数据

DC 元数据来自 `publication.json.meta`：`dc:title`、`dc:creator`、`dc:language`（译文用
`target_language`，纯转换用源语言）、`dc:identifier`（isbn/uri/slug）、`dc:date`、
`dc:publisher`、`dc:rights`。

## 命名

- 纯译文：`output/<slug>.epub`
- 双语：`output/<slug>-bi.epub`
- `-o` 可覆盖输出路径。

## 说明

封面（`properties="cover-image"`）、脚注/尾注双向跳转、NCX 嵌套层级、原图优先+补充层为后续
扩展点，当前未实现。
