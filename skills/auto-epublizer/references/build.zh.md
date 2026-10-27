> **中文** | [English](build.md)

# Build（EPUB 封装）

`build` 命令把译文（缺省回退源文）封装为标准 EPUB 3，落 `output/`。

## 命令

```bash
auto-epublizer build [-o <out.epub>] [--theme standard|compact|spacious] [--workspace <dir>]
```

- 从 `translation/<rel_path>` 读译文（缺省回退 `structured/`）。

## 印刷版 PDF（`pdf` 命令）

```bash
auto-epublizer pdf [--workspace <dir>] [--size a5|32k|b5|16k] [--body-pt 10.5]
                   [--note-pt 8.5] [--line-height 1.55] [-o output/<slug>.pdf] [--json]
```

- **从已构建的 EPUB 派生**：解包 → spine 串成一份 HTML（`@page` 开本 + 正文五号 + 注文小五 +
  首行缩进 2 字 + 段间不留空）→ headless Chromium `--print-to-pdf` → PyMuPDF 加盖页脚页码与书签。
- 缺省大 32 开 A5 148×210 mm、版心 18/16/20/16 mm；注文去掉回链箭头、注号与注文同行；
  屏幕上的链接样式（蓝色/下划线）不进入印刷版。
- 书签取自 `nav.xhtml`（`<ol>` 嵌套深度即层级），页码按渲染后正文逐条检索并保持单调递增；
  长标题被换行截断时退回首 10 字匹配。
- 元数据取 OPF 的 `dc:title` / `dc:creator`；`role="trl"` 是译者，不写入 author。
- 依赖 `chromium` / `google-chrome`（可用 `AUTO_EPUBLIZER_CHROME` 指定路径）；找不到即报错，不静默降级。
- **派生件边界**：PDF 不进 `qa` 的 artifacts 摘要、不替代 EPUB、不动状态机。重排 PDF 之后要重跑
  `qa`，否则摘要覆盖 `output/` 会让报告一生成即被判过期。

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

- 构建时间戳用冻结值（非 `time.Now()`）；同一冻结工作区、相同构建版本/源码状态及运行时指纹下，两次构建字节一致。
- 结果按稳定原文序合并，不随并发完成顺序变化。
- 内部稳定 ID 不外泄到产物（脚注/尾注用确定性序号）。

## 元数据

DC 元数据来自 `publication.json.meta`：`dc:title`、`dc:creator`、`dc:language`（译文用
`target_language`，纯转换用源语言）、`dc:identifier`（isbn/uri/slug）、`dc:date`、
`dc:publisher`、`dc:rights`。

OPF 的 `aep:render-mode` 记录本次实际构建入口：`source`（纯源文）或 `translation`（译文优先，逐单元允许回退源文）。QA 按这个模式与当前输入重建逐注文宿主计划：首个 spine 引用确定宿主；无引用注文优先自身 source_locations 单元，其次有效 scope 单元，均无则拒绝猜测。只有宿主实际使用译文的注文才读取并校验译注摘要和完整文本，其他注文独立核对源文；完全未用到的旧或损坏译注不阻断源文输出。已登记注释的旧成品缺少有效模式时，须重新构建，不能猜测。

## 成品软件指纹

- OPF 写入 `generator` 与自定义 `aep:` 元数据（`aep:build` 保存结构化构建记录）；内容 XHTML 的 head 内写入 `auto-epublizer-build` 前缀的 JSON 注释，供离线识别。
- 指纹记录项目 `auto-epublizer`、[源码地址](https://github.com/Misaka0x26FE/auto-epublizer)、**当前实际构建版本**与可取得的源码 revision/dirty 状态，不把初始化时的 `meta.producer` 当成构建版本；不可取得的值明确为未知。
- Python、Pydantic 是本次构建运行时；其他工具只列成功解析时冻结的实际使用记录，不枚举已安装依赖。未知版本保持未知；历史工作区未记录的上游工具不从当前环境倒推（`processing_tools=null` 表示历史未知，`[]` 表示已知未使用额外外部解析工具）。MinerU API 按外部服务标识，不声称其服务内部运行某个开源版本或采用某个开源许可。
- 有 copyright 单元时，在其尾部追加独立软件声明，保留原版权内容；没有时生成独立制作信息页，设为非线性 spine（`linear="no"`），由 `copyright-page` 地标进入。该页不新增书稿单元，但作为**顶层条目**进入 nav/NCX 目录（`制作信息` / `Production information`，与页面标题同一语言开关），位置与其 spine 位置一致（首个非封面文档之前），使只能按目录导航的阅读器也能到达。
- 该声明（或制作信息页）在工具列表之前给出**出版与版权信息**块，取自 `publication.json.meta` 的 `title`/`creator`/`translator`/`publisher`/`date`/`rights`，只列非空字段；全部为空时整块省略，不留空标签。
- 工具列表内另加**生成模型（LLM）**条目：`meta.generation_tools` 由 `meta --generation-tools '<JSON 数组>'` 写入（每项 `{name, version, task, url, license}`，缺键容忍，`[]` 表示明确未使用生成模型），每条渲染为 `name version — task`，版本缺失如实标注「版本未记录」，不伪造。以上文案均按构建语言输出中/英两版（中文权威）。
- 只接收上述公开署名字段，未知键或非字符串/null 值在写回前拒绝，不把配置或凭据塞进清单。
  `None` 为历史未记录；`[]` 明确显示「明确未使用生成模型（agent 自报）」；名称/版本/任务
  均来自 agent 自报，不是程序探测结果，也不调用任何模型服务。改变元数据使旧报告失效。
- 软件许可仅说明制作软件，不授予或改变书稿、译文、图像的许可。指纹不是数字签名，可以移除；记录过程无遥测、无网络请求，不写机器路径、密钥或唯一跟踪 ID。
- 旧 `output.about_page` 是保留配置，不是这项强制构建指纹的开关，也不表示旧关于页功能已接线。
- QA 仅对有效结构化指纹注释作残留豁免；制作页须由 OPF 指纹声明、页内制作标记及一致的有效 JSON 指纹共同识别，不能仅按文件名或任意 `linear="no"` 豁免正文对账/目录检查。普通注释、伪造前缀或损坏 JSON 仍属 `E_RESIDUE`。
- 制作页目录按 OPF 的 nav/NCX 声明和完整包内路径独立核对；同名错目录、重复或非顶层入口
  报 `E_TOC_PRODUCTION_TARGET`。旧成品完全缺入口仅报 `W_TOC_PRODUCTION_MISSING`，
  不把它伪装成缺失源书单元，也不放宽源目录深度对账。

## 命名

- 默认：`output/<slug>.epub`
- `-o` 可覆盖输出路径。

## 说明

- **媒体引用边界**（2026-10 D 组修复）：构建只收集 `structured/raw/media/` **之内**（解析符号链接后仍在目录内）的媒体；`../…`、绝对路径、指向工作区外的符号链接一律**拒绝读取**并记入 `events.jsonl` 的 `media_dropped`，随后由 provenance 以 `E_MEDIA_EPUB_LOST` 阻断放行（不静默丢图）。
- **资源身份**：Markdown/pandoc 源文件路径中的 `%` 是字面字符；HTML 图片 URL 只解码一次；ZIP 成员名不解码。裸文件名、子目录及既有 `media/`、`raw/media/` 路由按实际源文件定位包内路径；注文门、普通正文 provenance 和通用 G4 使用相同的完整路径身份规则，不以 basename 集合豁免错目录图片。图片由媒体门核对，不把 HTML 图片标签当成正文；周围文字仍须逐段保全。
- **Manifest 标识**：媒体使用稳定顺序分配的合法唯一 XML ID，与资源文件名/URI 分离，避免特殊字符非法和目录路径碰撞；封面元数据关联实际 manifest 项，不从 ID 猜文件名。
- **代码与 raw HTML**：普通围栏代码完整保留（包括跨空行），转义后显示；其中的 HTML 标签、标题、媒体路径、脚注、锚点和容器标记不生成目录或媒体读取。源文本/Pandoc 解析不得把代码标题切章、把独立数字当页码删除；显式 Pandoc raw HTML 是另一条语法路径。
- **内联 SVG**：保留真实 XHTML SVG 命名空间，所属内容 manifest 项带 `svg` 属性；本地 SVG `image` 的 href/xlink:href 按上面的完整路径媒体身份核对。缺源媒体、缺 ZIP 项或同 basename 错目录均阻断放行；未绑定 XML 前缀必须失败，不静默转义或丢弃。代码中展示的 SVG/img 不是资源引用。
- **构建日志署名**（issue #40；不出网）：`EPUB 已生成` 行固定带工具名 + 版本 + 许可证 + 源码地址，工作区 `meta.producer` 与 `run_initialized` 事件给出同一标识，来源可机器判定。
- **主题**（`--theme` / `config.output.theme`）：`standard`（serif+1.7 行距+缩进+两端对齐+标题居中，
  默认）/ `compact`（sans-serif+1.4+无缩进）/ `spacious`（serif+2.0）。只控排版微调，
  无具体字体名/颜色/字号（audit 会拦：`E_THEME_FONT`/`E_THEME_COLOR`）。
- **封面**：cover 单元的首个图片自动成为 `cover-image`（`<meta name="cover">` +
  spine `linear="no"`）；无封面源图时 audit 提示 `W_NO_COVER`（provenance）。
- **注释**：标准 EPUB `noteref` + `footnote`/`endnote` 语义、完整内容、可解析链接与回链、资源身份和有效登记绑定均为强制离线核证项（见 `references/notes.md`）。是否弹窗由阅读器实现和用户设置决定；始终保留可读注释区及往返跳转 fallback。
- **目录层级**：源文标题层级（`level`）→ nav 嵌套 `<ol>` + NCX 嵌套 navPoint；
  **单元内子标题锚点**（2026-09-29 起）：单元内 h2+ 标题自动获得稳定 id
  （`{unit_id}-h{n}`；显式 `{#id}` 优先），以 `file.xhtml#anchor` 作为单元条目的
  子级进 nav/NCX——译文中应保留这些子标题（g0 `heading` 守恒门校验）；
  **目录深度投影**（`--nav-depth` / `config.output.nav_depth`，默认 3，1–6）：超出
  深度的单元/锚点不进 nav/NCX（仍在 spine 阅读顺序、锚点保留），封面单元不进目录，
  `dtb:depth` 为投影后实际深度（含锚点）；
  **制作信息页**（无 copyright 单元时生成）作为顶层条目置于目录首位（深度 1，不参与源文
  层级投影），与 NCX `playOrder`（自 1 起连续）同序。
- **图片**：只缩不放大居中 + 断页（`page-break-inside: avoid`）；独立图段（alt 非空）→
  `figure+figcaption` 图注。
- **语义标签**：引用 `>` → `blockquote`；诗行块 `|` → `p.verse`；`- ` → `ul`；
  有序列表仅当**编号从 1 起连续递增且用 `. `/`、` 分隔**时才渲染为 `<ol>`（此时自动编号恰与原编号一致）；
  其余 `N.`/`N、`/`N)` 起首的块——如校勘本异文注 `1) 2) 5)…`（数字是真实注号）——
  一律按普通段落输出并**保留原文数字**（`p.fnlist`），不得被 `<ol>` 自动编号改写。
- **表格**：md 管道表（`| a | b |` + 分隔行）与 pandoc 简单/网格表（成排 `---` 列界）
  渲染为 `<table class="data">`（`th`/`td` + 功能性边框）；单元格文字正常翻译，
  结构保持不变。**翻译时不要改动列界与分隔线**（G0 表格形状守恒）。
- 原图优先+补充层为后续扩展点。
