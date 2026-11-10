> **中文** | [English](build.md)

# Build（EPUB 封装）

`build` 命令把译文（缺省回退源文）封装为标准 EPUB 3，落 `output/`。

## 命令

```bash
auto-epublizer build [-o <out.epub>] [--theme standard|compact|spacious] [--workspace <dir>]
```

- 从 `translation/<rel_path>` 读译文（缺省回退 `structured/`）。

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

## 目录页来源模型（D1，只读）

`auto-epublizer evidence toc --workspace <dir> --json` 导出两份**分开**的来源：

- `nodes`：结构视图——`unit`/`parent`/`order`/`level`/`label`/`href`；单元内子标题锚点带
  完整 `file.xhtml#fragment`。目录页是结构视图，不是译文段落，允许按单元树重排、改条目边界。
- `original`：目录单元逐行的原本条目（`line`/`text`/`label`/`page`/`page_kind`），只有
  **完全同名**才绑定目标（`unit_exact`/`anchor_exact`）；重复或找不到记 `ambiguous`/`unresolved`，
  `§` 段没有正文锚点时记 `section_anchor_absent`，不从 `§` 字样自动造标题。
- `unresolved`：缺目标、多义或缺锚点的条目，逐条给行号与原因。
- `page_display`：只有 `preprocessing/page_numbers.csv` 声明 `original` 时才显示原书页码；
  未声明或 `none` 一律留空，不冒充原版页码。

原版目录行只作来源证据；生成可点击目录页与独立对账见 D2（build 生成 + lint）。

## 目录页生成与独立对账（D2）

`build --toc-page` / `output.toc_page: true` 打开后，`toc` 单元不再照抄源目录行：

- 按单元树 + 单元内子标题锚点渲染分级 `<nav epub:type="toc" data-aep="generated-toc">`；
  标签取已译单元标题，条目顺序与 nav/`output.nav_depth` 投影一致；可点链接带
  `file.xhtml#fragment`。
- 页码只读 `preprocessing/toc_pages.csv`（`unit,page`）：缺省不显示，缺行不猜；
  非法/重复/未知单元直接报错。
- 成品带 `data-aep="generated-toc"`，`provenance` 识别后跳过该页的 md 段落探针，改用
  **独立期望树**（从 publication 单元与 md 锚点重算）核对顺序/层级/标签/href，
  findings 记 `report.json.toc_page_findings`（advisory，不单独阻断放行）：
  `toc_compressed`（`<p>` 内 ≥2 个 `<br/>`）、`toc_no_links`、`toc_count`、
  `toc_entry_*`、`toc_missing_pages`。
- 原目录中未被结构树覆盖的条目**不得丢失**：生成器把它们保留为无链接的
  `span.toc-plain` 条目（不再有页码/链接），独立期望树同样包含这些条目。
- **阻断项**（`provenance_findings` 的 error，直接使放行失败）：`E_TOC_SOURCE_LOST`
  （原目录条目在成品目录中缺失）、`E_TOC_BROKEN_LINK`（目录链接指向不存在的文档，
  或 `#fragment` 在目标文档中不存在）。其余结构差异仍是 `toc_page_findings` advisory。
- 生成器不读取自身成品做判定；目录页是结构视图，允许重排，但仍须与独立期望树逐条一致。

## 说明

- **媒体引用边界**（2026-10 D 组修复）：构建只收集 `structured/raw/media/` **之内**（解析符号链接后仍在目录内）的媒体；`../…`、绝对路径、指向工作区外的符号链接一律**拒绝读取**并记入 `events.jsonl` 的 `media_dropped`，随后由 provenance 以 `E_MEDIA_EPUB_LOST` 阻断放行（不静默丢图）。
- **资源身份**：Markdown/pandoc 源文件路径中的 `%` 是字面字符；HTML 图片 URL 只解码一次；ZIP 成员名不解码。裸文件名、子目录及既有 `media/`、`raw/media/` 路由按实际源文件定位包内路径；注文门、普通正文 provenance 和通用 G4 使用相同的完整路径身份规则，不以 basename 集合豁免错目录图片。图片由媒体门核对，不把 HTML 图片标签当成正文；周围文字仍须逐段保全。
- **Manifest 标识**：媒体使用稳定顺序分配的合法唯一 XML ID，与资源文件名/URI 分离，避免特殊字符非法和目录路径碰撞；封面元数据关联实际 manifest 项，不从 ID 猜文件名。
- **代码与 raw HTML**：普通围栏代码完整保留（包括跨空行），转义后显示；其中的 HTML 标签、标题、媒体路径、脚注、锚点和容器标记不生成目录或媒体读取。源文本/Pandoc 解析不得把代码标题切章、把独立数字当页码删除；显式 Pandoc raw HTML 是另一条语法路径。
- **内联 SVG**：保留真实 XHTML SVG 命名空间，所属内容 manifest 项带 `svg` 属性；本地 SVG `image` 的 href/xlink:href 按上面的完整路径媒体身份核对。缺源媒体、缺 ZIP 项或同 basename 错目录均阻断放行；未绑定 XML 前缀必须失败，不静默转义或丢弃。代码中展示的 SVG/img 不是资源引用。
- **构建日志署名**（issue #40；不出网）：`EPUB 已生成` 行固定带工具名 + 版本 + 许可证 + 源码地址，工作区 `meta.producer` 与 `run_initialized` 事件给出同一标识，来源可机器判定。
- **主题**（`--theme` / `config.output.theme`）：`standard`（1.7 行距+缩进+两端对齐+标题居中，
  默认）/ `compact`（1.4+无缩进）/ `spacious`（2.0）。只控排版微调，不声明 font-family（2026-11-04），
  无具体字体名/颜色/字号（audit 会拦：`E_THEME_FONT`/`E_THEME_COLOR`）。
- **按书样式**（`--css` / `config.output.css`）：工作区内受限 CSS（如
  `preprocessing/book.css`），追加在主题层之后。只允许缩进/段距/行距/对齐/字重等排版属性；
  具体字体名、字号、颜色、背景、`@` 规则与 `url()` 一律拒绝（`E_THEME_*`；外部引用另有
  `E_THEME_EXTERNAL`）。路径必须是工作区内相对文件（解析符号链接后仍在界内），上限 64 KiB；
  构建事件记 `book_css_used`（path/sha256），样式最终随 EPUB 字节进入 `artifacts_digest`。
- **封面**：cover 单元的首个图片自动成为 `cover-image`（`<meta name="cover">` +
  spine `linear="no"`）；无封面源图时 audit 提示 `W_NO_COVER`（provenance）。
  **扫描件封面**（#63）不自动取第 1 页图：`evidence source --json` 的 `cover_candidates`
  只是候选（页号/块号/魔数格式/字节摘要）；agent 核证后写
  `preprocessing/cover.json`（`{"file": "structured/raw/media/…", "evidence": "…"}`，两项必填），
  build 才按既有 cover-image 路径登记（媒体字节原样）；声明 cover 单元却无可解析图片 →
  `events.jsonl` 记 `cover_without_image`，`status --json` 的 `cover.missing=true`。
- **注释**：标准 EPUB `noteref` + `footnote`/`endnote` 语义、完整内容、可解析链接与回链、资源身份和有效登记绑定均为强制离线核证项（见 `references/notes.md`）。是否弹窗由阅读器实现和用户设置决定；始终保留可读注释区及往返跳转 fallback。
- **目录层级**：源文标题层级（`level`）→ nav 嵌套 `<ol>` + NCX 嵌套 navPoint；  **单元内子标题锚点**（2026-09-29 起）：单元内 h2+ 标题自动获得稳定 id
  （`{unit_id}-h{n}`；显式 `{#id}` 优先），以 `file.xhtml#anchor` 作为单元条目的
  子级进 nav/NCX——译文中应保留这些子标题（g0 `heading` 守恒门校验）；
  **目录深度投影**（`--nav-depth` / `config.output.nav_depth`，默认 3，1–6）：超出
  深度的单元/锚点不进 nav/NCX（仍在 spine 阅读顺序、锚点保留），封面单元不进目录，
  `dtb:depth` 为投影后实际深度（含锚点）；
  **制作信息页**（无 copyright 单元时生成）作为顶层条目置于目录首位（深度 1，不参与源文
  层级投影），与 NCX `playOrder`（自 1 起连续）同序。
- **Markdown 解析**：通用行内/块级语法由 `markdown-it-py` 的 token 解析（嵌套强调、
  引用式链接、嵌套列表、带括号图片路径），项目特有的 Pandoc 锚点、原注号、诗行、表格、
  脚注与 raw HTML 仍走专用分支；代码跨度**逐字保留**（含换行与强调符号），不交给
  通用解析改写。
- **图片**：只缩不放大居中 + 断页（`page-break-inside: avoid`）；独立图段（alt 非空）→
  `figure+figcaption` 图注。
- **语义标签**：引用 `>` → `blockquote`；诗行块 `|` → `p.verse`；`- ` → `ul`；
  有序列表仅当**编号从 1 起连续递增且用 `. `/`、` 分隔**时才渲染为 `<ol>`（此时自动编号恰与原编号一致）；
  其余 `N.`/`N、`/`N)` 起首的块——如校勘本异文注 `1) 2) 5)…`（数字是真实注号）——
  一律按普通段落输出并**保留原文数字**（`p.fnlist`），不得被 `<ol>` 自动编号改写。
  **单条编号块**（只有一行 `1. …`）同样按段落输出：书末注文的单条注文不是单项列表，
  `<ol>` 会给它加上列表缩进/悬挂样式（#61；取舍见 `docs/epub-template-spec.zh.md`）。
- **表格**：md 管道表（`| a | b |` + 分隔行）与 pandoc 简单/网格表（成排 `---` 列界）
  渲染为 `<table class="data">`（`th`/`td` + 功能性边框）；单元格文字正常翻译，
  结构保持不变。**翻译时不要改动列界与分隔线**（G0 表格形状守恒）。
- 原图优先+补充层为后续扩展点。

## 印刷版 PDF（`pdf`，派生件）

```bash
auto-epublizer pdf --workspace <dir> [--epub <path>] [-o <out.pdf>] \
  [--size a5|32k|b5|16k] [--body-pt 10.5] [--note-pt 8.5] [--line-height 1.55] \
  [--no-bookmarks] [--strict] [--json]
```

- **定位**：EPUB 仍是交付格式；PDF 是每次从 EPUB 重新生成的派生件，不手改、不回写。
  `artifacts_digest` **不遍历 `output/`**，所以重排 PDF 不需要重跑 `qa`，也不会让报告过期。
- **输入**：缺省取 `output/<slug>.epub`；包文档只经 `META-INF/container.xml` 定位；解包拒绝
  绝对路径、`..` 与符号链接；spine 文档缺失直接报中文错误，不静默少页。
- **资源**：每章按章节目录重定位 `src`/`href`（子目录章节的 `../media/x.png` 不会错配）；
  远程/包外引用丢弃并在 `notes` 留痕；`script`/`on*` 一律移除。
- **封面身份**：优先使用包内 cover 地标/语义文档，或与登记 cover-image 精确对应的封面文档，封面可为非线性 spine 项；只有封面图登记时生成独立印刷封面页。其余非线性附件不自动纳入；存在多个封面身份时报错，不按文件名含 cover 猜测，也不重复添加。SVG 封面保留图形与已有文本。
- **封面与页码**：封面置于绝对第 1 页且无页脚号；无封面时正文首页从 1 编号，并保留版心边距。封面用毫米版面而非 100vh，保留 0.5mm 纸张取整余量，避免图像越过实际纸边。 **页眉页脚角色（E4）**：封面无页眉页脚；每个区段首页不重复页眉；后续正文页页眉为区段章名，按可用宽度截断并加 `...`；页脚始终是 PDF 绝对页序，隐藏封面页码不重编号，书签/目录页码不受影响。
- **图版**：图片高度由开本、上下边距、图注字号/行距预留计算，紧跟标题的大图另留标题空间。短图注与图版同页；超长图注可续页，图片不重复绘制。同一图片在源文中合法引用多次仍保留多次，不以资源去重代替呈现对账。（E3：A5/32 开图版均只绘一次、不越出纸面；`h1`–`h4` 保持 `page-break-after: avoid`，不让标题落成孤页。）
- **定位标记清除**：仅移除定位文字，不擦除覆盖区的图像像素或矢量图形；URL 资源路径只解码一次并重新编码供浏览器使用，`#` 等文件名字符不被当成 fragment。
- **宽表与实测诊断**：表格限定版心宽度，单元格允许换行，表内段落继承表字号，不按列数任意缩小字体。`--json` 的 `diagnostics` 分别报告 body/notes 的请求字号、实测字号、源/命中字符数与分布：通过源段落前缀绑定 PDF span，取字符加权众数；至少命中 24 个归一化字符、众数占比 ≥60% 才记 measured。正文/注文前缀同形、样本不足或未匹配均为 unknown，不靠全书中位数猜测正文。混排字体：正文族拉丁优先（Nimbus Roman→Liberation Serif→DejaVu Serif），再回落 CJK（Noto Serif CJK SC→Songti）；EPUB 主题仍用 generic family。诊断按 FontDescriptor 实际族名统计 latin/cjk 用字：拉丁字落在 CJK 族记 `W_PDF_FONT_LATIN_USES_CJK`，CJK 字落在拉丁族记 `W_PDF_FONT_CJK_USES_LATIN`（缺字体/错回落的可定位信号）。
- **严格模式**：实测字号相对请求值偏差 >5%、纸张尺寸偏差 >1pt，或正文/图片超出版心 >2pt，记具体 finding（含页码/bbox，越界样例最多 100 条但总数/页集合完整），在 `notes` 提示；CJK 行尾收标点（`）〕】》」』，。；：？！` 等）悬出右边距不超过 0.62em 时记 advisory `W_PDF_PUNCT_HANG`，不计入越界错误（悬挂是排版常态）；超过该幅度或含正文文字仍记 `E_PDF_OVERFLOW`。`--strict` 遇已确认 error 非零退出并保留旧 PDF。未知字号保持 unknown，不冒充已测通过；诊断不等价于全部图文、矢量图形、表格语义或字形可读性的人工验收。
- **书签与目录页码**：只读 OPF 的 `properties="nav"` 且只取 `epub:type="toc"`。区段起始页由不可见定位标记确定（映射后 redaction 清除）；目录行和片段书签用完整 `href#fragment` 身份绑定到真实 id 处注入的锚点，取最终 PDF 的绝对页序，不按整页标题子串或区段起始页猜。目录最多三遍渲染收敛；跨块长题名按合并后的完整标签匹配，`Contents`/`§` 等无页码提示行不参与配对，页码位数变化整体替换旧数字，`§` 条目按标签而不是位置对应；未定位条目保留源数字并在成品该行明确标注「原版页码，未定位」且记 error，收敛失败记 `E_PDF_TOC_UNSTABLE`。OPF3 `meta refines` 的译者不进 author。目录页（D2 生成）按「题名 + 点线 + 右对齐页码」排版，长题名换行后点线与页码仍贴末行；改写后的目录片段按 HTML 序列化，不能用 XML 自闭合 `<span/>`（否则会吞掉后续节点、点线布局失效）。
- **索引/CIP/中文强调（E5）**：区段标题为 `Index`/`索引`（含人名/地名/主题索引）时排两栏，`h1` 跨栏；`Copyright`/`CIP`/`版权` 区段段落取消首行缩进；`<em>`/`<i>` 内含汉字时改为 `span.cjk-em`（正体加粗），拉丁语义强调仍保留斜体。
- **出版元数据**：`dc:publisher`、`dc:date`、`dc:rights`、`dc:language`、`dc:subject`、`dc:description`、`dc:identifier` 原样写入 XMP（`dc:rights` 不截断）；`dc:creator` 中作者进 `dc:creator`、译者进 `aep:translators`。Info 只写标准短字段：`/Title`←`dc:title`、`/Author`←作者（分号连接，不含译者）、`/Subject`←描述、`/Keywords`←主题（分号连接）；`/CreationDate`、`/ModDate` 是**生成时间**，不冒充 `dc:date` 出版日期。空字段保持空，不补造。
- **派生清单与核对**：每次成功排版写 `<pdf>.manifest.json`（schema、源 EPUB/PDF 的 sha256 与字节数、PDF 页数、实际参数、Info/XMP 读回、目录与诊断摘要）。`pdf --json` 回传同一份 `artifact`。`auto-epublizer pdf-verify --pdf <path> [--json]` 重算源 EPUB 与 PDF 字节；PDF 被改动、清单损坏或源件缺失时非零退出。PDF 与清单都在 `output/`，仍不进入 EPUB `artifacts_digest`，所以重排不改报告状态，靠派生清单对账。
- **参数**：正文 4–24 pt、注文 4–20 pt、行距 1.0–3.0；非有限/越界直接拒绝。输出与输入
  同路径拒绝；Chromium 缺失/超时（240 s）/非零退出/产物非 PDF 都是中文错误，失败不留下
  半成品，也不破坏既有旧 PDF。

### 版式契约（2026-11-03 冻结）

以下是当前 `PrintStyle` 与 `CSS_TEMPLATE` 的**实际取值**，样本册与基线据此验收；
改动这些数值属于版式变更，须同时重跑 P1 样本与 §5 阈值检查。

| 项 | 取值 |
|---|---|
| 开本 | `a5` 148×210（默认）/ `32k` 130×184 / `b5` 176×250 / `16k` 185×260 mm |
| 页边距（上/外/下/内） | 18 / 16 / 20 / 16 mm（`@page`，封面首页 `margin:0`） |
| 正文 | 10.5 pt，行距 1.55，首行缩进 2em，两端对齐，段间距 0 |
| 注文 | 8.5 pt，行距 1.4，`aside p` 缩进 0、下边距 0.3em |
| 标题 | h1 1.8× / h2 1.43× / h3 1.19× / h4–h6 1.05× 正文字号；行高 1.35/1.4/1.45；段前/段后 h1 1.1/0.9em、h2 1/0.7em、h3 0.9/0.5em、h4 0.8/0.4em |
| 引文 | 0.9× 正文字号、行高 1.5、左缩进 1.5em |
| 表格 | 0.86× 正文字号，`table-layout:fixed`，单元格 `overflow-wrap:anywhere`，表内段落继承字号且缩进 0 |
| 图版高度预算 | `高 − 上 − 下 − 4mm − 3×注文字号×行距×(25.4/72)`；紧跟 h1–h3 的图再减 3 行标题高度，下限 1mm |
| 分页 | `h1–h4 { page-break-after: avoid }`；`figure/table/aside { page-break-inside: avoid }`；`section.chapter { page-break-after: always }` |
| 索引 / CIP / 中文强调 | 索引两栏且 `h1` 跨栏；CIP 段落缩进 0；汉字 `<em>` 转 `span.cjk-em` 加粗 |

已冻结的**已知缺陷**（P5 修，不在本轮改）：

- 引文容器字号 0.9×，但引文内 `p` 被全局 `p` 规则重新设成正文字号并保留 2em 缩进——
  子元素覆盖父容器，实际引文与正文同号且缩进；
- 全局 `p { overflow-wrap:anywhere }` 为长串兜底，同时允许英文单词任意处断开；
- `widows`/`orphans` **未声明**，实际行为取 Chromium 默认（2/2）；不得在文档中写成
  「已保证至少两行」。

### 判定口径（拟定，P7b 实测前只作候选）

| 指标 | 判据 | 证据 |
|---|---|---|
| 标题孤立 | 能容纳时标题后至少同页两行正文；样本违规为 0 | PDF 位置读回 + 页图 |
| 孤行寡行 | 普通段落跨页两端尽量各 ≥2 行 | `widows`/`orphans` + 读回 |
| 图注关系 | 短图注与图同页；长图注首段随图、后续顺序完整 | 图 bbox + 文字映射 |
| 异常留白 | 普通正文页底空白 > 版心高度 30% 记候选（章末/部分页/图版页排除） | 页图 + 页尺寸 |
| 断词与节奏 | 普通拉丁词避免任意字符断行，长 URL 可断；无持续异常字间拉伸 | 样本前后对照 |
| 缩进层级 | 正文/引文/注释/表格/索引各自一致且不串扰 | 计算样式 + PDF 读回 |

上表阈值是**拟定值**：当前没有实书或样本实测记录，不得当作已通过结果引用；
升级为放行门禁须先经 P7b 负例稳定。

### 印刷支持矩阵（目标，未实测）

| 维度 | 取值 | 状态 |
|---|---|---|
| 开本 | A5（默认）与 32 开 | 每次样本构建 |
| 正文字号 | 10.5 pt 与 12 pt | 待 P5 实测 |
| 渲染环境 | 固定 Chromium 版本、固定字体文件摘要 | 记录于报告 |
| 阅读实测 | 首/中/尾 + 图表/注文高风险页 | 待 P9 实书 |
