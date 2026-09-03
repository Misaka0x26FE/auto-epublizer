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
| nav.xhtml + toc.ncx | ✅ | 目录层级符合源文件层级（见后） |
| 语义地标 landmarks | ✅ | frontmatter/bodymatter/backmatter 各取首个落地标 |
| 每文档 `xml:lang` + 恰好一个 `h1` | ✅ | 全文档一致 |
| 标题层级 h1–h6 语义 + 无跳级 | ⬜ | 不得 h1→h3 跳级 |
| **脚注语义化** | ⬜ | `noteref`/`footnote` + 全局序号 + 双向跳转（§6） |
| 封面 `cover-image` | ⬜ | `properties="cover-image"` + `<meta name="cover">` |
| 封面/目录页 `linear="no"` | ⬜ | 不进正文阅读顺序 |
| 目录锚点 | ⬜ | 每个 h2/h3 带稳定 `id` 供 nav 跳转 |
| 语义标签 | ⬜ | 引用 `blockquote`、诗歌 `verse`、列表 `ul/ol` 保留语义 |
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

### 当前实现的偏差（需修正）

现有 `build/__init__.py` 的 `_STYLE_CSS` 包含**非功能性样式**，须移除：

```text
font-family: Georgia, "Noto Serif CJK SC", ...   ← 删（不设字体）
line-height: 1.9                                  ← 移入主题层
font-size: 1.45em（h1）                            ← 删（不设字号）
text-indent: 2em（p）                              ← 移入主题层
text-align: justify（p）                           ← 移入主题层
margin: 4% 5%（body）                              ← 移入主题层
```

只保留：`img { max-width:100%; height:auto; }`、`p.imgp`（图片段居中不缩进）。

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

### 5.2 预置主题

不开放任意 CSS。预置三套极简主题，`--theme` / `config.output.theme` 选择：

```text
standard  → serif + normal 行距 + 缩进 + 两端对齐 + 标题居中（默认）
compact   → sans-serif + 1.4 行距 + 无缩进 + 左对齐（信息密集场景）
spacious  → serif + 2.0 行距 + 缩进 + 两端对齐（阅读舒适场景）
```

每套主题仅派生「排版微调」几个 CSS 属性，不引入字体名、颜色、字号。

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

### 7.2 实现影响清单

1. `build/__init__.py`：`_STYLE_CSS` 瘦身为功能性样式 + 主题变体表；`build_epub` 接受 `theme`。
2. `build/html.py`：`render_document` 只产出语义 XHTML，CSS 从模板/主题注入（解耦）。
3. 脚注语义化：新增「注码 → `noteref`/`footnote`」渲染 + 全局编号器（跨章状态）。
4. 封面 `cover-image`：新增封面处理（源图来自 `preprocessing` 识别的封面或用户提供）。
5. `linear="no"`、目录锚点 `id`、语义标签保留：随目录层级实现一并落地。
6. `qa/audit.py` 新增校验：主题 CSS 不含字体/颜色/字号（`E_THEME_FONT` 等）、脚注双向可跳、
   封面 `cover-image` 存在。

## 8. 后续实现清单（按优先级）

| 优先级 | 项 | 归属 |
|---|---|---|
| P0 | 脚注语义化（弹窗 + 全局序号 + 双向跳转） | 结构层 |
| P0 | 目录层级（嵌套 nav/NCX + 目录锚点 id） | 结构层 |
| P0 | `_STYLE_CSS` 瘦身（去字体/颜色/字号） | 呈现层 |
| P1 | 主题机制（预置三套 + `--theme` + `output.theme`） | 主题层 |
| P1 | 封面 `cover-image` + `linear="no"` | 结构层 |
| P2 | 语义标签保留（blockquote/verse/ul/ol） | 结构层 |
| P2 | audit 主题/脚注/封面校验 | 结构层 |

> 脚注语义化、目录层级、样式瘦身为本轮（P0）落地项；主题机制、封面为 P1；语义标签、
> 校验补强为 P2。具体任务拆解见 `docs/postprocessing-spec.md`。
