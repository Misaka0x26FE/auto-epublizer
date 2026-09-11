# EPUB 非线性 spine 项（表格/图表）与标题锚点残留

## 判据（什么时候会命中）

用 `preprocess`/`init` 处理 **EPUB** 源时，若出现以下任一现象：

1. **表格/图表数据丢失**：正文里只剩 caption 链接（如
   `[*Table 1.1* ...](...._table_1.xhtml){#...#t1}`），grep 表体数值（如 `4,235`、`911`）
   在 `structured/` 里找不到。根因：pandoc 只读线性 spine 项，表格文件在 OPF 里是
   `<itemref ... linear="no"/>`，被跳过。
2. **标题被锚点污染**：单元标题形如
   `[]{#200..._Part08.xhtml#ncx_12}1 WHAT IS TOBACCO? [The botany...]{.small}`，
   会直接进 EPUB 章节标题与目录。
3. **前置辅文被切碎**：按 ATX 标题切分时，没有 `<h1>` 的 spine 项（版权页、献词）
   正文被并入前一个标题单元，标题与内容错位；前置辅文全部落到 `body/chNN`。

判据一句话：**单元数明显多于目录条目、或标题含 `[]{#`、或正文表格数值缺失** → 命中。

## 处置

优先升级到带 `read_epub` 的版本（见 `src/auto_epublizer/ingest/epub_reader.py`）：

- **按 OPF spine 切分**：pandoc 对每个线性 spine 项恰好输出一行独立锚点
  `[]{#<href basename>.xhtml}`（实测稳定，用 `grep -nE '^\[\]\{#.*\.xhtml\}$'` 可验证），
  以它为边界即「一个 spine 项 = 一个单元」。任一锚点缺失/乱序时回退按标题切分。
- **标题清洗**：删 `[]{#id}`、`{#id}`、`[text]{.class}`（保留文本）、`<br>`；标题取值顺序
  nav/NCX 标签 → 清洗后 `<h1>` → `<title>` → 顶层 `<div class>`（如 dedication）→「正文」。
  注意清洗函数**不得去行首空白**，否则破坏网格表格缩进。
- **非线性项内联**：把 `linear="no"` 的 XHTML 单独用
  `pandoc -f html -t markdown --wrap=none` 转 md，在正文中**恰好是指向该项的独立
  caption 链接段**处替换内联；正文内嵌的普通交叉引用（长句里的 `[Table 1.1](...)`）不动；
  找不到引用时追加到最末单元。

无 `read_epub` 时的手工兜底：解包 EPUB，读 `OEBPS/*.opf` 的 `<spine>`，对照
`manifest` 找出 `linear="no"` 的表格文件，逐个 `pandoc` 转 md 后按表号并入对应章节，
再清标题锚点——但这属于临时修补，结构（单元边界）仍不对，应推动升级。

## 验证

- 单元数 ≈ 线性 spine 项数（`facts.md` 结构清单与 NCX 目录数量级一致）。
- `grep -rl "\[\]{#" structured/` 无命中。
- 抽样 grep 原书表格数值（本例 `4,235`）出现在 `structured/body/<章>.md`。
- `structured/frontmatter/` 出现 copyright/dedication/titlepage，而非碎落 body。
- 回归测试：`tests/test_epub_reader.py`（纯函数 + zipfile 最小夹具 + pandoc 集成）。

## 来源与去向

- 来源：真书 dogfooding《Tobacco In History: The Cultures of Dependence》（Jordan Goodman，
  26 个线性 spine 项 / 15 个 `linear="no"` 表格项）。
- 去向：已修复（`read_epub` + `tests/test_epub_reader.py`）；`load.py` 中 `.epub` 路由到
  `read_epub`，结构异常回退 `read_pandoc`。
