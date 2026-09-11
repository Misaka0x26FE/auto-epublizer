# 2026-09-11 EPUB 读取器：按 spine 切分 + 非线性项内联

状态：已完成

## 背景

用真书《Tobacco In History: The Cultures of Dependence》（Jordan Goodman）验证 EPUB 管线，
发现三类缺陷（详见 `skills/auto-epublizer/lessons/2026-09-11-epub-nonlinear-spine-tables.md`）：

1. **15 张表格数据丢失**：表格文件在 OPF 里是 `linear="no"` 的独立 spine 项，pandoc 跳过，
   正文只剩 caption 链接；`grep 4,235 structured/` 无命中。
2. **标题锚点污染**：`# []{#..._Part08.xhtml#ncx_12}...1 WHAT IS TOBACCO? [The botany...]{.small}`
   直接成为章节标题/目录。
3. **前置辅文切碎**：`parse_markdown_units` 按 ATX 标题切分，无 `<h1>` 的 spine 项（版权页）
   正文并入前一标题单元；标题污染使关键词分类失效，前置全部落 `body/chNN`。

关键实测：pandoc 对每个线性 spine 项恰好输出一行独立锚点 `[]{#<href basename>.xhtml}`，
按 spine 顺序排列，可作可靠切分边界。

## 实施

- 新增 `src/auto_epublizer/ingest/epub_reader.py`：
  - `read_epub_package`（container→OPF、manifest/spine、DC 元数据、nav/NCX 标签）；
  - `clean_pandoc_residue`（清 `[]{#id}`/`{#id}`/`[text]{.class}`/`<br>`，保行首空白）；
  - `split_by_spine_anchors`（按锚点切分，缺锚点/乱序返回 None）；
  - `read_epub`（一项一单元 + 非线性项在 caption 链接段内联 + 标题回退链；异常回退按标题切分）。
- 修改 `ingest/load.py`：`.epub` → `read_epub`，`EpubError` 时回退 `read_pandoc`。
- 导出 `read_epub` / `EpubError`。
- 测试 `tests/test_epub_reader.py`（纯函数 + zipfile 最小夹具 + pandoc 集成，pandoc 缺失时 skip）。

## 验证记录

- 真书入库：单元 31 → **26**（= 线性 spine 项数）；标题为
  `COVER PAGE`/`TITLE PAGE`/`COPYRIGHT PAGE`/`Dedication`/各章全名/`PART I`/`GLOSSARY`/`BIBLIOGRAPHY`；
  `4,235` 等表体已进 `structured/body/`；`grep '\[\]{#' structured/` 无命中；
  `frontmatter/` 为 titlepage/copyright/dedication。
- `uv run pytest -q`：260 passed（含新增 6 例）。
- `uv run ruff check .` / `ruff format --check .`：通过。

## 文档同步

- `skills/auto-epublizer/references/ingest.md`：新增「EPUB 按 spine 切分」小节 + 路由表更新。
- `skills/auto-epublizer/references/structure.md`：清洗节补锚点残留说明。
- `skills/auto-epublizer/lessons/2026-09-11-epub-nonlinear-spine-tables.md` + lessons 索引。

## 后续扩展点

- 跨章交叉引用（`[Chapter 2](#Part10.xhtml)`）在输出 EPUB 中会成为失效内部链接，
  需在翻译/封装阶段处理（转纯文本或重建锚点）；本次未接线。
- 非线性项若含图片且相对路径无法解析，当前不复制媒体（本书表格无图）。

## 追加（同日）：表格渲染 + 元数据审计修复

真书翻译过程中发现两处与此直接相关的问题，一并修复：

1. **build 不渲染表格**：`markdown_to_xhtml` 无表格分支，`parse_md_tables` 也只认管道表，
   导致 pandoc 简单/网格表（本书 15 张统计表）以纯文本呈现。已在
   `build/html.py` 增加 `_maybe_render_table`：支持 md 管道表与 pandoc 简单/网格表
   （按 `---` 列界切片，`===` 行前为表头）→ `<table class="data">`，并在 `_STYLE_CSS`
   加功能性边框。测试 `test_build.py::test_markdown_to_xhtml_renders_{simple,pipe}_table`。
2. **审计元数据误报**：S2 译者署名使 build 输出 `<dc:creator id="creator-aut">`（带属性），
   而 `qa/audit.py` 用 `<dc:creator>` 无属性正则检测，导致每本书都误报
   `W_META_INCOMPLETE：dc:creator`。已改为允许属性（`<dc:creator(?:\s[^>]*)?>`），
   测试 `test_qa.py::test_audit_meta_creator_with_attributes`。
