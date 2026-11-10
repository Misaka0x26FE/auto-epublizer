> **中文** | [English](epub-template-spec.md)

# EPUB 文件规范：无样式标准模板 + 有限主题

本文档规定 `auto-epublizer` 产出的 EPUB 3 文件的**形态规范**：内容与呈现分离，呈现权
交给阅读系统，只保留功能性最小样式，并预留克制的主题选项。它是「后处理规范」
（`docs/postprocessing-spec.md`）中媒体/样式验收标准的依据。

### 成品软件来源与书稿权利边界

构建必须在 OPF 写 `generator` 和自定义 `aep:` 元数据（结构化记录为 `aep:build`），并在内容 XHTML head 内写 `auto-epublizer-build` JSON 注释。记录包含项目名 `auto-epublizer`、[项目 URL](https://github.com/Misaka0x26FE/auto-epublizer)、当前构建版本及可取得的源码 revision/dirty；初始化 `meta.producer` 不是当前构建身份。

实际构建入口另记为 OPF `aep:render-mode`：`source` / `translation`。`translation` 允许逐单元源文回退。注文的源/译选择服从其实际宿主；QA 使用成品声明的模式重建期望并验证实际内容。已登记注释的成品缺失或存在歧义模式时须重建，不猜测、不豁免版本绑定；此字段不是数字签名。

Python/Pydantic 描述构建运行时；其他工具仅使用成功解析时冻结的记录，不将已安装依赖冒充实际使用。未知版本明确未知，历史工作区缺记录不从当前安装环境倒推；MinerU API 是外部服务，不宣称其内部开源版本或许可。

有 copyright 单元时，在原内容尾部追加独立软件声明，不替换作者/译者版权；没有时生成独立制作信息页，采用非线性 spine（`linear="no"`）、`copyright-page` 地标及 nav/NCX 顶层入口，不新增书稿单元。声明展示非空出版/版权字段及 agent 自报的生成模型；历史未知与明确未使用分开，不推测版本。软件许可不授予或改变书稿、译文、图像的权利。旧 `output.about_page` 仍是保留配置，不是强制指纹的开关，也不代表旧关于页功能已接线。

指纹可离线读取，无遥测、无网络请求，不含机器路径、密钥或唯一跟踪 ID；它不是数字签名，可移除。QA 仅豁免有效结构化指纹注释；独立制作页须同时满足 OPF 指纹声明、页内制作标记和一致的有效 JSON 指纹，不能仅凭文件名或 `linear="no"` 豁免内容对账/目录检查。普通残留注释、伪造前缀、损坏 JSON 仍报 `E_RESIDUE`。详见 `skills/auto-epublizer/references/build.md`。

## 1. 设计理念

> EPUB 3 的设计哲学是「内容与呈现分离」：结构层决定导航与无障碍，呈现层交给阅读器。

三条原则：

1. **几乎无样式**：默认模板不设字体、颜色、字号，只保留防止内容溢出的功能性样式。
2. **有限主题**：个性化只通过「预置的极简主题」表达，不开放任意 CSS，不破坏多阅读器兼容。
3. **标准注释**：注释一律采用 EPUB 3 标准注释语义（`epub:type="noteref"`/`"footnote"`），
   章内数字序号，支持双向跳转；弹窗呈现由阅读器决定。

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
| **目录深度投影** | ✅ | nav/NCX 最多嵌套 `output.nav_depth` 层（默认 3，1–6）；超深单元不进目录，但保留在 spine 阅读顺序与锚点；封面单元不进目录 |
| 语义地标 landmarks | ✅ | frontmatter/bodymatter/backmatter 各取首个落地标 |
| 每文档 `xml:lang` + 恰好一个 `h1` | ✅ | 全文档一致 |
| 标题层级 h1–h6 语义 + 无跳级 | ✅ | `E_HEADING_SKIP` 校验（P2） |
| **脚注语义化** | ✅ | `noteref`/`footnote` + `[N]` 注码 + 章内独立编号 + 双向跳转（§6） |
| 封面 `cover-image` | ✅ | `properties="cover-image"` + `<meta name="cover">` + spine `linear="no"` |
| **无源封面时的生成封面** | ✅ | `cover` 写 `structured/raw/media/cover-generated.png` 并登记 `preprocessing/cover-generated.json`，build 据此写 `properties="cover-image"` + `<meta name="cover">`；已确认的 `preprocessing/cover.json` 永远优先；设计摘要变化时重绘；封面不进译文校验（不影响 G0/align/单元状态） |
| 封面/目录页 `linear="no"` | ✅ | cover 单元内容文档不进正文阅读顺序 |
| 目录锚点 | ✅ | 单元级嵌套 + **单元内子标题锚点**（`file.xhtml#anchor`，`{unit_id}-h{n}` 稳定 id） |
| 语义标签 | ✅ | 引用 `blockquote`、诗行块 `p.verse`、`- ` 列表 `ul` 保留语义（P2）；`<ol>` 仅用于**编号从 1 起连续且用 `. `/`、` 分隔、且至少两条**的块——其余 `N)`/`N.`/`N、` 起首块（如校异注）保留原文数字（`p.fnlist`），不得被自动编号改写。单条 `1. …` 是注文段落而非单项列表：`<ol>` 会带来列表缩进/悬挂样式，而阅读器对同文本段落的呈现与注文场景一致（#61 取舍） |

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

### 4.1 功能性规则清单（2026-11-03 冻结）

以下规则是「没有它内容会溢出、不可读或语义丢失」的最小集合，位于呈现层最前，
主题层与按书样式**不得**回退它们（图片限宽、表格边框、注区分离）：

| 选择器 | 实际声明 | 功能理由 |
|---|---|---|
| `img` | `max-width:100%; height:auto; page-break-inside:avoid` | 大图等比例缩到版心、不跨页裁断；小图不放大 |
| `p.imgp` | `text-indent:0; text-align:center` | 图片段不参与正文首行缩进 |
| `figure.imgfig` | `margin:1em 0; text-align:center` | 图注块居中；字号/颜色仍由阅读器决定 |
| `p.verse` | `text-indent:0` | 诗行保留手动换行，不加首行缩进 |
| `blockquote` | `margin:0.5em 0 0.5em 1.5em` | 引文缩进层级可辨；不设字号/字体 |
| `section.footnotes` | `margin-top:2em` | 章末注区与正文分离 |
| `table.data` | `border-collapse:collapse; margin:1em auto` | 表格居中、单元格边界可读 |
| `table.data th/td` | `border:1px solid #999; padding:0.2em 0.5em; text-align:left` | 无边框表格在多阅读器下不可读；`#999` 是不随主题变化的固定灰 |

规则优先级（同一元素多条命中时）：按书样式 > 主题层 > 本表；同层内后声明者胜，
class 选择器（`p.imgp`/`p.verse`）优先于元素选择器（`p`）。按书样式受白名单限制，
不得用 `@media`/`@font-face` 等绕过本表；响应式与字体控制属于阅读器职责。

### 4.2 阅读器控制边界与已知限制（冻结）

- **关闭作者样式**：只保证结构（标题层级、段落、表格结构、注释 `noteref`/`aside`/回链）
  与链接可访问；图片缩放、表格边框、注区间距均不保证。这是阅读器行为，不视为产物缺陷。
- **字号放大（含 200%）**：流式重排，正文与图片限宽继续生效；复杂宽表可能横向滚动，
  首期以「内容完整可访问」为通过条件（P4 实测阅读器行为）。
- **暗色模式**：本模板不设正文颜色；表格功能性边框 `#999` 与图片内嵌白底不随主题反转，
  记为已知限制，P4 以实机截图核对是否影响可读性。
- **组件串扰（已知，P3 处理）**：主题 `p` 规则同时命中引文内段落、注文 `aside` 内段落与
  表格单元格内段落；`standard`/`spacious` 下这些组件首行同样缩进 2em，
  `p.verse` 只取消缩进、不取消主题段距。P3 将以组件作用域限定规则；在此之前，
  本规范不把「组件各自独立」写成已实现事实。

### 当前实现的偏差（✅ 已修正 2026-09-04）

`build/__init__.py` 的 `_STYLE_CSS` 已完成瘦身：移除 `font-family`、`font-size`、
`line-height`、`text-indent: 2em`、`text-align: justify`、标题居中等非功能性样式，
只保留功能性规则（`img` 限宽、`p.imgp` 图片段居中、`section.footnotes`），
并有回归测试锁定（禁止 font-family/color/font-size/line-height/justify 回潮）。

## 5. 主题层（有限个性化）

**边界**：主题只控排版微调，绝不碰字体/颜色/字号（阅读器领地）。2026-11-04 起
**主题不声明 `font-family`**（用户指令：EPUB 不设置、不内嵌字体），字族完全交由阅读器默认。

### 5.1 可选维度

| 维度 | 取值 |
|---|---|
| 行距密度 | `compact`(1.4) / `normal`(1.7，默认) / `spacious`(2.0) |
| 段间距 | 紧 / 标准（默认）/ 松 |
| 首行缩进 | 中文缩进 2em（默认）/ 无缩进（西式） |
| 对齐 | 两端对齐（默认）/ 左对齐 |
| 标题呈现 | 居中（默认）/ 左对齐 |
| 脚注方式 | 弹窗（默认，标准）/ 章末列表（老阅读器降级） |

### 5.2 预置主题（✅ 已实现 2026-09-04）

不开放任意 CSS。预置三套极简主题，`--theme` / `config.output.theme` 选择：

```text
standard  → 1.7 行距 + 缩进 + 两端对齐 + 标题居中（默认）
compact   → 1.4 行距 + 无缩进 + 左对齐
spacious  → 2.0 行距 + 缩进 + 两端对齐 + 标题居中
```

每套主题仅派生「排版微调」几个 CSS 属性，不引入字体名、颜色、字号；
audit 拦截违规（`E_THEME_FONT`：具体字体名/字号；`E_THEME_COLOR`：颜色）。

### 5.3 三主题的实际声明（2026-11-03 冻结）

下表是**当前构建产物 style.css 中逐字存在的声明**（`build/__init__.py`），
不是设计意图：

| 主题 | 实际声明 |
|---|---|
| `standard` | `body{line-height:1.7}`；`p{text-indent:2em;text-align:justify;margin:0 0 0.6em 0}`；`h1,h2,h3,h4,h5,h6{text-align:center}` |
| `compact` | `body{line-height:1.4}`；`p{margin:0 0 0.8em 0}` |
| `spacious` | `body{line-height:2.0}`；`p{text-indent:2em;text-align:justify;margin:0 0 1em 0}`；`h1,h2,h3,h4,h5,h6{text-align:center}` |

> 2026-11-04 用户指令：EPUB **不设置、不内嵌字体**，`body` 不再声明 `font-family`；
> 主题只保留行高/缩进/对齐等排版微调，字族完全交由阅读器默认。

措辞冲突的解释（冻结）：

- §5.1 是**维度设计表**，不是逐项 CLI 开关。当前仅以三套预设暴露组合结果，
  不提供单独调「标题居中/段间距」的参数；需要时按新选项评审（兼容性与摘要绑定）。
- `compact` 的「无缩进 / 左对齐」**不是显式声明**：未声明 `text-indent` 时取初始值 0，
  未声明 `text-align` 时取 `start`（与书写方向一致）。阅读器默认值差异是已知风险，
  P3 将改为显式声明后再把该措辞当契约。
- §5.2 的「行距密度 compact(1.4)/normal(1.7)/spacious(2.0)」对应 `line-height`；
  「段间距紧/标准/松」当前只落在三套预设的 `p` 下边距（0.8em / 0.6em / 1em），不单独暴露。

### 5.4 主题与按书样式的来源顺序（冻结）

```text
_STYLE_CSS（§4.1 功能性规则）
  → theme_css(standard|compact|spacious)（本节）
    → book_css（白名单受限：缩进/段距/行距/对齐等，禁字体名、字号、颜色、@media、@font-face、URL）
```

三者按上述顺序拼接进单个 `OEBPS/style.css`；后段同特异性声明覆盖前段。
产物时效仍由样式摘要参与判定：主题或按书样式变化必须重新构建并重跑摘要校验，
历史发布记录不覆盖。`tests/fixtures/typography/` 的样本册与基线用于在改动前后对照。

### 5.5 EPUB 验收矩阵（拟定，P4/P8 实测后才可称已支持）

| 层次 | 取值 | 状态 |
|---|---|---|
| 浏览器模拟宽度 | 320 / 600 / 768 CSS px，三主题，默认与 200% 字号 | 待 P4 |
| 阅读栈 | Thorium 与 KOReader（记录实际版本） | 未实测 |
| 暗色模式 / 字体替换 | 代表性样本 | 未实测 |
| 结构验收 | EPUBCheck 零错误 + 注释/媒体/目录/内容对账 | 每次构建强制 |

浏览器宽度模拟不等于电子墨水设备实测；同一引擎的两个软件不算不同渲染栈。
缺环境记 unknown，报告须列明实际运行与未运行组合。


## 6. 注释标准化（标准弹窗 + 章内序号）

- 正文注码（句末注码）→ `<a epub:type="noteref" role="doc-noteref" id="ref-N" href="#fn-N">[N]</a>`（上标）
- 注释正文 → 章末集中区 `<section epub:type="footnotes">`，条目
  `<aside epub:type="footnote" id="fn-N" role="doc-footnote"><p>[N] … <a epub:type="backlink" href="#ref-N">↩</a></p></aside>`
- **章内序号**：每章从 `[1]` 起独立编号（构建期为每单元新建 `FootnoteState`）；
  id 在各自 XHTML 文档内作用域唯一。
- **双向跳转**：注码 → 注释（前进），注释回链（`#ref-N`）→ 注码（后退）；
  回链是通用兜底（Kindle KDP 要求，不支持弹窗的阅读器靠它返回）。
- **兼容性**：支持弹窗的阅读器可弹窗显示；不保证所有阅读器弹窗，注码跳转与章末内容仍须可访问（`<aside>` 位于章节末尾）。
- 与 `{fig:NNN}`/`{table:NNN}` 区分：后者是**图/表占位标记**（插入元素），不走脚注语义。
- **必需离线验收**：CLI 独立审计和 epubcheck 不依赖桌面；必须核验 noteref/aside 语义、href、全部回链、登记图及版本绑定一致性，并逐项核证注文内容与资源，登记图为 none 时也须零对零对账。五项语义质量门保持强制，不因无桌面豁免内容或结构缺陷。
- **条件性阅读器抽查**：有 GUI 时记录阅读器名称、版本及弹窗/跳转/返回观察；无 GUI 明示「阅读器未实测」，不因此阻塞交付，也不冒称兼容实测通过。

## 7. 配置与实现影响

### 7.1 配置

`config.output` 的呈现与结构开关：

```yaml
output:
  theme: standard        # standard | compact | spacious
  nav_depth: 3           # 目录最大嵌套深度（1–6，投影：超深单元不进目录）
```

### 7.2 实现影响清单（✅ 全部落地）

1. ✅ `build/__init__.py`：`_STYLE_CSS` 瘦身为功能性样式 + `_THEMES` 主题表；`build_epub` 接受 `theme`/`cover_media`/`nav_depth`。
2. ✅ `build/html.py`：`render_document` 只产出语义 XHTML（含 blockquote/verse/ul/ol），CSS 从模板/主题注入（解耦）。
3. ✅ 脚注语义化：`FootnoteState` 章内编号 + `[N]` 注码 + noteref/footnote 渲染 + 回链。
4. ✅ 封面 `cover-image`：cover 单元首个图片自动识别 + `<meta name="cover">` + `linear="no"`。
5. ✅ 语义标签保留 + 断页/图注样式（目录为单元级嵌套 + 单元内子标题锚点，2026-09-29 起）。
6. ✅ `qa/audit.py`：`E_THEME_FONT`/`E_THEME_COLOR`/`E_COVER_META`/`E_HEADING_SKIP`/
   `E_RESIDUE`/`W_RESIDUE`/`W_META_INCOMPLETE`/`E_ANCHOR`/`E_FN_BACKLINK`/
   `W_EPUB_SIZE`/`W_IMG_UNCOMPRESSED`；溯源审计 `W_NO_COVER`/`W_NAMING`。
7. ✅ 目录深度投影：`nav_toc_entries`（封面排除 + `nav_depth` 截断）→ nav/NCX。
   nav.xhtml 声明两个语义分开的 meta：`<meta name="nav-depth" content="A"/>` = **渲染后实际
   深度** A（与 NCX `dtb:depth` 同源，对外如实）、`<meta name="nav-projection" content="K"/>`
   = **投影上限** K；qa 审计以 K 为准重建期望集（用 A 会让扁平/错误构建自证「期望扁平」、
   漏报 `E_TOC_FLAT`）。`nav_exempt` 豁免 `E_TOC_COVERAGE`。

## 8. 后续实现清单（按优先级）

| 优先级 | 项 | 归属 |
|---|---|---|
| P0 ✅ | 脚注语义化（弹窗 + 双向跳转；2026-09-13 起为 `[N]` 章内序号） | 结构层 |
| P0 ✅ | 目录层级（嵌套 nav/NCX + `dtb:depth`，level 链路补全） | 结构层 |
| P0 ✅ | `_STYLE_CSS` 瘦身（去字体/颜色/字号，回归测试锁定） | 呈现层 |
| P1 ✅ | 主题机制（预置三套 + `--theme` + `output.theme` + audit 校验） | 主题层 |
| P1 ✅ | 封面 `cover-image` + `linear="no"` + `W_NO_COVER` 对账 | 结构层 |
| P2 ✅ | 语义标签保留（blockquote/verse/ul/ol） | 结构层 |
| P2 ✅ | audit 补强（标题跳级/残留/锚点回链/元数据完备/体积） | 结构层 |
| P2 ✅ | 目录深度投影（`output.nav_depth` + 封面不进目录 + 覆盖审计豁免） | 结构层 |

> P0/P1/P2 已于 2026-09-04 全部落地（详见 `docs/postprocessing-spec.md` §4）；
> 目录深度投影与 `[N]` 章内序号于 2026-09-13 落地（`docs/plans/2026-09-13-toc-depth-footnotes.md`）；
> 单元内子标题锚点目录 + 标题层级保真/守恒（PDF level≥2 书签、g0 heading 门）于
> 2026-09-29 落地（`docs/plans/2026-09-29-nav-depth.md`）。
