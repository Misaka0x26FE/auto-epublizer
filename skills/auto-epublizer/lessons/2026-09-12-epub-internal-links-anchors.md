# EPUB 内部链接 / 页码锚点 / 标题 id：pandoc 源文件前缀必须按 spine 重写

## 判据（什么时候会命中）

用 `init`/`convert` 处理**带索引、目录交叉引用、页码锚点的 EPUB**（学术/非虚构书常见）时，
成品可能出现以下任一现象：

1. **正文页码锚点全丢**：源 XHTML 的空锚点 `<a id="page_311"></a>`，经 `pandoc -f epub`
   变成行内 `[]{#ch17.html#page_311}`（**带源文件名前缀**）。若清洗正则无差别删除
   `[]{#...}`，成品里成百上千个页码锚点消失，索引跳转目标不存在。
2. **内部链接变非法 URI**：`pandoc -f epub`（整本）给内部链接额外加前导 `#`：
   源 `href="ch17.html#page_311"` → `[311](#ch17.html#page_311)`，含两个 `#`，
   epubcheck 报 RSC-020/RSC-005。注意 `pandoc -f html`（单文件）**不**加前导 `#`，
   两者行为不同，别用单文件结论推断整本。
3. **链接目标整体错位（RSC-012）**：链接里的 `ch17.html` 是**源文件名**，成品按 spine
   重切后以单元 id 命名（`ch19.xhtml`），且前置辅文会造成整体偏移（本例偏移 2）。
   不重映射则文件都找不到。
4. **标题 id 丢失**：源 `<h2 id="ch02">` → `## 标题 {#ch02.html#ch02 .h1}`，若把
   `{#id}` 当 pandoc 残留删掉，front-toc 的章锚点 `chNN.xhtml#chNN` 失去落点。

判据一句话：**成品 epubcheck 报 RSC-012/RSC-020，或解包后 `grep 'href="#[^"]*#'`
有命中、或索引链接数远大于实际 `<a id>` 锚点数** → 命中。

关键实测（pandoc 3.1.x，`-f epub` 整本）：

| 源 XHTML | pandoc 输出 |
|---|---|
| `<a id="page_311">`（行内） | `[]{#ch17.html#page_311}`（可能带 `.class`） |
| `<a href="ch17.html#page_311">311</a>` | `[311](#ch17.html#page_311)`（前导 #） |
| `<h2 id="ch02">` | `## 标题 {#ch17.html#ch02 .h1}` |
| spine 项边界 | 独立成行 `[]{#ch17.html}`（**无 #fragment**） |

## 处置

区分「spine 边界标记」与「正文导航锚点」，二者形似但去留相反：

- **边界标记**：独立成行、id 整体是文件名且**无第二个 `#`**（`[]{#ch17.html}`）——删除
  （`_strip_anchor_lines` + `clean_pandoc_residue` 用 `[^}#]` 排除带 fragment 的锚点）。
- **正文锚点 / 链接 / 标题 id**：一律**保留并按 spine 重写**，分两层做：

  1. ingest 切块时当前 spine 文件名已知（`strip_self_file_prefix`）：把指向**自身文件**的
     引用去前缀——`[]{#ch1.xhtml#ncx_1}`→`[]{#ncx_1}`、`[x](#ch1.xhtml#p)`→`[x](#p)`、
     `{#ch1.xhtml#h .h1}`→`{#h}`；首个标题行用 `_parse_heading_line` 拆出
     （纯标题, 标题 id, 前导页码锚点），标题 id 存 `unit.meta.heading_id`（h1 用），
     前导页码锚点作为正文第一个锚点段保留。
  2. structure 阶段 `classify_units` 已分配最终单元 id，再由 `structure/links.py`
     `rewrite_internal_links` 做**全局**映射（依据各单元 `meta.spine_href` 建
     「源 basename → 单元 id」表）：跨单元 `[x](#ch17.html#p)`→`[x](ch19.xhtml#p)`，
     同单元→`#p`；空锚点/标题 id 只取 `#` 后纯 fragment 并丢弃 class；外部协议
     （http/mailto）与查无映射的目标原样保留，不猜测。

- build 端（`build/html.py`）：`[]{#id}` 渲染为 `<a id="id"></a>`，标题末尾 `{#id}`
  渲染为 `<hN id="id">`（`_split_heading_id`）；`_render_markdown` 用
  `# 标题 {#heading_id}` 让章 h1 带上源锚点 id。

**反例（本次 bug 的根源）**：旧清洗用 `\[\]\{#[^}]*\}` 无差别删锚点、用 `\{[.#][^}]*\}`
连 `{#id}` 一起删——这会把索引赖以跳转的全部落点删掉。锚点不是 pandoc 噪声，
是书的导航结构。

## 验证

- 解包成品：`grep -roh 'href="#[^"]*#' OEBPS | wc -l`（非法双 #）为 **0**；
  `grep -rohE 'href="[^"]*\.html' OEBPS`（残留源文件名）为 **0**。
- **链接目标闭包**（最硬指标）：枚举每个 `href="file#frag"`，断言 frag 出现在目标文件
  的 `id=` 集合中。本例《Tobacco》修复后内部链接 1838 条、缺失 0（修复前缺失上千）；
  页码锚点 347 个全部恢复。
- `structured/` 中页码锚点为纯形态 `[]{#page_N}`、章 h1 为 `# 标题 {#chNN}`，
  无 `.html/.xhtml` 源文件名残留。
- epubcheck：0 errors / 0 warnings（RSC-005/012/020 全消）。
- 回归测试：`tests/test_epub_reader.py`（清洗/自身前缀/标题解析）、
  `tests/test_links.py`（前导#、spine 偏移、同/跨单元、外部、无映射、锚点与标题 id）、
  `tests/test_build.py`（锚点与标题 id 渲染）。

## 来源与去向

- 来源：真书 dogfooding《Tobacco: A Cultural History...》（Iain Gately），30 个 spine 项、
  正文存在两格偏移（ch03 单元 = 源 ch01.html）、索引含 1700+ 页码交叉引用。
- 去向：已修复（`ingest/epub_reader.py` 锚点保留与标题解析、新增 `structure/links.py`、
  `structure/rebuild.py` 接线、`build/html.py` 锚点/标题 id 渲染）并补单测。
- 关联：取代 `2026-09-11-epub-nonlinear-spine-tables.md` 中「删 `[]{#id}`、`{#id}`」的
  旧表述——那只适用于纯边界标记，正文导航锚点必须保留。
