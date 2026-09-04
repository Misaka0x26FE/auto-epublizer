# EPUB 文件规范：无样式标准模板 + 有限主题

本文档规定 `auto-epublizer` 产出的 EPUB 3 文件的**形态规范**：内容与呈现分离，呈现权
交给阅读系统，只保留功能性最小样式，并预留克制的主题选项。它是「后处理规范」
（`docs/postprocessing-spec.md`）中媒体/样式验收标准的依据。

## 1. 设计理念

> EPUB 3 的设计哲学是「内容与呈现分离」：结构层决定导航与无障碍，呈现层交给阅读器。

三条原则：

1. **几乎无样式**：默认模板不设字体、颜色、字号，只保留防止内容溢出的功能性样式。
2. **有限主题**：个性化只通过「预置的极简主题」表达，不开放任意 CSS，不破坏多阅读器兼容。
3. **标准注释**：注释一律采用 EPUB 3 标准弹窗注释（`epub:type="noteref"`/`"footnote"`），
   全书统一数字序号，支持双向跳转。

## 2. 三层框架

```text
结构层（骨架，完全标准化，与样式无关）  ← 合法性与无障碍核心，阅读器据此导航
呈现层（几乎无样式 = 模板默认）          ← 只保留功能性最小样式
主题层（有限个性化）                     ← 克制开关，绝不碰字体/颜色/字号
```

## 3. 结构层（完全标准化）

结构层是 EPUB 合法性的核心，全部确定性生成，与样式无关。已完成 ✅ / 待补 ⬜：

| 项 | 现状 | 规范要求 |
|---|---|---|
| mimetype / container / OPF | ✅ | mimetype 首位未压缩、内容恰为 `application/epub+zip` |
| nav.xhtml + toc.ncx | ✅ | 目录层级符合源文件层级（level 链路已通，嵌套渲染已落地） |
| 语义地标 landmarks | ✅ | frontmatter/bodymatter/backmatter 各取首个落地标 |
| 每文档 `xml:lang` + 恰好一个 `h1` | ✅ | 全文档一致 |
| 标题层级 h1–h6 语义 + 无跳级 | ✅ | `E_HEADING_SKIP` 校验（P2） |
| **脚注语义化** | ✅ | `noteref`/`footnote` + 全局序号 + 双向跳转（§6，已落地） |
| 封面 `cover-image` | ✅ | `properties="cover-image"` + `<meta name="cover">` + spine `linear="no"` |
| 封面/目录页 `linear="no"` | ✅ | cover 单元内容文档不进正文阅读顺序 |
| 目录锚点 | ✅ | 单元级嵌套（源文标题已切分为单元，h1–h6 锚点随层级实现覆盖） |
| 语义标签 | ✅ | 引用 `blockquote`、诗行块 `p.verse`、列表 `ul/ol` 保留语义（P2） |
| 双语版 src/tgt 各自 `lang` | ✅ | 每段标注源/目标语言 |

## 4. 呈现层（无样式默认模板）

默认模板只保留**功能性样式**，其余交给阅读器：

| 项 | 规范 | 说明 |
|---|---|---|
| 字体 | **不设** | 用阅读器字体 |
| 颜色 | **不设** | 由阅读器处理（含夜间模式） |
| 字号 | **不设** | 标题只用相对层级 h1–h6，无 pt/px |
| 图片 | `max-width:100%` + 居中 + 不放大 | 功能性：防止图片溢出，小图原尺寸、大图等比例缩放 |
| 强调 | `strong`/`em` 语义 | 渲染交阅读器默认 |
| 链接 | `a href` 语义 | 危险 URL（javascript:/data:）降级纯文本 |

### 当前实现的偏差（✅ 已修正 2026-09-04）

`build/__init__.py` 的 `_STYLE_CSS` 已完成瘦身：移除 `font-family`、`font-size`、
`line-height`、`text-indent: 2em`、`text-align: justify`、标题居中等非功能性样式，
只保留功能性规则（`img` 限宽、`p.imgp` 图片段居中、`section.footnotes`），
并有回归测试锁定（禁止 font-family/color/font-size/line-height/justify 回潮）。

## 5. 主题层（有限个性化）

**边界**：主题只控排版微调，绝不碰字体/颜色/字号（阅读器领地）。唯一「字体相关」例外是
**泛化字族基调**——用 `serif`/`sans-serif` 族名而非具体字体名，由阅读器映射到自己的字体。

### 5.1 可选维度

| 维度 | 取值 |
|---|---|
| 字族基调 | `serif`（默认）/ `sans-serif` |
| 行距密度 | `compact`(1.4) / `normal`(1.7，默认) / `spacious`(2.0) |
| 段间距 | 紧 / 标准（默认）/ 松 |
| 首行缩进 | 中文缩进 2em（默认）/ 无缩进（西式） |
| 对齐 | 两端对齐（默认）/ 左对齐 |
| 标题呈现 | 居中（默认）/ 左对齐 |
| 脚注方式 | 弹窗（默认，标准）/ 章末列表（老阅读器降级） |

### 5.2 预置主题（✅ 已实现 2026-09-04）

不开放任意 CSS。预置三套极简主题，`--theme` / `config.output.theme` 选择：

```text
standard  → serif + 1.7 行距 + 缩进 + 两端对齐 + 标题居中（默认）
compact   → sans-serif + 1.4 行距 + 无缩进 + 左对齐
spacious  → serif + 2.0 行距 + 缩进 + 两端对齐
```

每套主题仅派生「排版微调」几个 CSS 属性，不引入字体名、颜色、字号；
audit 拦截违规（`E_THEME_FONT`：具体字体名/字号；`E_THEME_COLOR`：颜色）。

## 6. 注释标准化（标准弹窗 + 全局序号）

- 正文注码（句末数字注码）→ `<a epub:type="noteref" id="nr-N" href="#fn-N">N</a>`
- 注释正文 → `<aside epub:type="footnote" id="fn-N" role="doc-footnote">`
- **全局序号**：全书跨章连续编号（1, 2, 3, …），不按章重排。
- **双向跳转**：注码 → 注释（前进），注释回链（`#nr-N`）→ 注码（后退）。
- **降级**：支持弹窗的阅读器弹窗显示，不支持的退化为章末列表（`<aside>` 本就位于章节末尾）。
- 与 `{fig:NNN}`/`{table:NNN}` 区分：后者是**图/表占位标记**（插入元素），不走脚注语义。

## 7. 配置与实现影响

### 7.1 配置

`config.output` 扩展 `theme` 字段：

```yaml
output:
  theme: standard        # standard | compact | spacious
  mono: true
  bilingual: false
```

### 7.2 实现影响清单（✅ 全部落地）

1. ✅ `build/__init__.py`：`_STYLE_CSS` 瘦身为功能性样式 + `_THEMES` 主题表；`build_epub` 接受 `theme`/`cover_media`。
2. ✅ `build/html.py`：`render_document` 只产出语义 XHTML（含 blockquote/verse/ul/ol），CSS 从模板/主题注入（解耦）。
3. ✅ 脚注语义化：`FootnoteState` 全局编号器 + noteref/footnote 渲染。
4. ✅ 封面 `cover-image`：cover 单元首个图片自动识别 + `<meta name="cover">` + `linear="no"`。
5. ✅ 语义标签保留 + 断页/图注样式（目录为单元级嵌套，无单元内子标题锚点需求）。
6. ✅ `qa/audit.py`：`E_THEME_FONT`/`E_THEME_COLOR`/`E_COVER_META`/`E_HEADING_SKIP`/
   `E_RESIDUE`/`W_RESIDUE`/`W_META_INCOMPLETE`/`E_ANCHOR`/`E_FN_BACKLINK`/`E_BI_PAIRS`/
   `W_EPUB_SIZE`/`W_IMG_UNCOMPRESSED`；溯源审计 `W_NO_COVER`/`W_NAMING`。

## 8. 后续实现清单（按优先级）

| 优先级 | 项 | 归属 |
|---|---|---|
| P0 ✅ | 脚注语义化（弹窗 + 全局序号 + 双向跳转） | 结构层 |
| P0 ✅ | 目录层级（嵌套 nav/NCX + `dtb:depth`，level 链路补全） | 结构层 |
| P0 ✅ | `_STYLE_CSS` 瘦身（去字体/颜色/字号，回归测试锁定） | 呈现层 |
| P1 ✅ | 主题机制（预置三套 + `--theme` + `output.theme` + audit 校验） | 主题层 |
| P1 ✅ | 封面 `cover-image` + `linear="no"` + `W_NO_COVER` 对账 | 结构层 |
| P2 ✅ | 语义标签保留（blockquote/verse/ul/ol） | 结构层 |
| P2 ✅ | audit 补强（标题跳级/残留/锚点回链/双语成对/元数据完备/体积） | 结构层 |

> P0/P1/P2 已于 2026-09-04 全部落地（详见 `docs/postprocessing-spec.md` §4）。
