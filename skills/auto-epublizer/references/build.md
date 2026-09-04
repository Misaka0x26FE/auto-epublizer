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

- **主题**（`--theme` / `config.output.theme`）：`standard`（serif+1.7 行距+缩进+两端对齐+标题居中，
  默认）/ `compact`（sans-serif+1.4+无缩进）/ `spacious`（serif+2.0）。只控排版微调，
  无具体字体名/颜色/字号（audit 会拦：`E_THEME_FONT`/`E_THEME_COLOR`）。
- **封面**：cover 单元的首个图片自动成为 `cover-image`（`<meta name="cover">` +
  spine `linear="no"`）；无封面源图时 audit 提示 `W_NO_COVER`（provenance）。
- **脚注**：`[^label]` → 标准弹窗注释（noteref/footnote），全书跨章全局连续编号 + 双向跳转。
- **目录层级**：源文标题层级（`level`）→ nav 嵌套 `<ol>` + NCX 嵌套 navPoint（`dtb:depth`）。
- **图片**：只缩不放大居中 + 断页（`page-break-inside: avoid`）；独立图段（alt 非空）→
  `figure+figcaption` 图注。
- **语义标签**：引用 `>` → `blockquote`；诗行块 `|` → `p.verse`；`- `/`1. ` → `ul/ol`。
- 原图优先+补充层为后续扩展点。
