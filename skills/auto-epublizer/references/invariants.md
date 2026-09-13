# 不变量速查卡（invariants）

> **定位**：全部机器可验证契约的单一参考——排障、判读 qa 报告、放行决策前读这一份。
> 详细判读与修法在各阶段文档（review/qa/build）；本篇只做全集速查，两者冲突时以
> 代码与 docs/quality-control.md 为准。

## 1. 六道关一览

| 关 | 做什么 | 谁做 | 硬门 | advisory |
|---|---|---|---|---|
| G0 | 静态校验（align/长度/术语/标记守恒/脚注守恒） | CLI（`g0`/`import`） | terminology/marker/footnote | length |
| G1 | 逐段双语审校 | agent | — | — |
| G2 | 证据取证复核 | agent | — | — |
| G3 | 仲裁+修订+收敛 | agent | — | — |
| G4 | epubcheck + 解包审计 | CLI（`qa`） | 全部 E_* | W_* |
| G5 | 放行汇总（report.json） | CLI（`qa`） | 见 §2 | — |

## 2. G5 放行条件全集（`qa/report.py::generate_report`）

`released=true` 当且仅当全部满足：

| 条件 | 不过时的 `released_reason` |
|---|---|
| `g2_confirmed == 0` 或全部已修订（`g2_confirmed <= g3_patched`） | `unresolved_confirmed` |
| `g0_terminology_open == 0`（术语命中=真实缺陷） | `terminology_open` |
| `glossary_conflicts_open == 0`（术语冲突未裁决；裁决写回 glossary.csv 前不放行） | `glossary_conflict_open` |
| `g0_structure_open == 0`（marker/footnote/table/fidelity 违例） | `structure_open` |
| `catalog_unresolved_open == 0`（源盘点未决项；catalog.csv 存在时才检查） | `catalog_open` |
| `audit.ok`（G4 解包审计零 error） | `audit_failed` |
| `prov_ok`（coverage≈1.0 或 null、units_missing/media_lost/inserts_missing_files/toc_flat、findings 无 error 级） | `provenance_incomplete` |
| `epubcheck.ran`（jar 缺失=未验证不放行） | `epubcheck_not_run` |
| `epubcheck.errors == 0` | `epubcheck_errors` |

reason 判定优先级 = 上表自上而下（先 g0 硬缺陷 → 冲突 → 结构 → 审计 → 溯源 → epubcheck）。

## 3. G0 检查项（`auto_translator/review/g0.py::g0_unit_flags`）

| check | 语义 | 级别 |
|---|---|---|
| `align` | seq 连续 1..N、无空 src/tgt（违反阻断该单元 import） | 硬（阻断） |
| `terminology` | glossary source 出现而译文缺 target | **硬缺陷** |
| `marker` | `{fig:NNN}` 等标记 **单元级总量** src/tgt 一致 | **硬缺陷** |
| `footnote` | pandoc `[^label]` + 句末数字注码总量一致 | **硬缺陷** |
| `table` | 表格形状守恒（表数/逐表行列数；import **阻断**） | **硬缺陷（阻断）** |
| `fidelity` | align src ↔ structured 双向覆盖（S4.1） | **硬缺陷** |
| `length` | 长度比 `[0.30, 3.0]` | advisory |

守恒类是**单元级总量**比对：拆句/并句把标记挪到相邻行不误报，丢失必报。

## 4. G4 错误码速查（`qa/audit.py` + `qa/provenance.py`）

### 结构与打包（audit）

| 码 | 级 | 一句话处置 |
|---|---|---|
| E_NOT_EPUB | E | 非法 zip / 溯源读包失败 |
| E_ZIP_DUPLICATE | E | zip 条目重名（手改包损坏）→ 从译文重 build |
| E_MIMETYPE_FIRST/STORED/CONTENT | E | mimetype 首位未压缩/内容错 → 重 build |
| E_NO_CONTAINER / E_CONTAINER_OPF / E_OPF_MISSING | E | 容器或 OPF 缺失 → 重 build |
| E_SPINE_REF / E_MANIFEST_HREF | E | manifest↔spine 不一致 → 重 build |
| E_NAV_HREF / E_NCX_HREF / E_LANDMARKS_HREF | E | 导航链接悬空 → 查对应文档是否存在 |
| E_TOC_COVERAGE | E | spine↔nav 双向覆盖缺口 → 查章节标题层级（`output.nav_depth` 投影剔除的超深单元为预期豁免） |
| E_IMG_SRC | E | 本地图悬空 → 补 raw/media/ 后重 build |
| E_IMG_REMOTE | E | 图片外链 → 下载进包改本地引用 |
| E_UNSAFE_URL | E | javascript:/data: 注入 → 排查译文 HTML |
| E_THEME_FONT / E_THEME_COLOR | E | 具体字体名/字号/颜色 → 换主题，勿改 style |
| E_RESIDUE | E | HTML 注释残留 → 清理译文 |
| E_HEADING_SKIP | E | 标题跳级（h1→h3）→ 补中间层级 |
| E_COVER_META | E | 封面 properties 与 meta 互证失败 → 重 build |
| E_ANCHOR / E_FN_BACKLINK | E | 内部锚点/脚注回链悬空 → 查 noteref/footnote |
| E_BI_PAIRS | E | 双语 src/tgt 段落数不等 → 查 align |
| W_META_INCOMPLETE | W | DC 项缺失**或空白** → 预处理期应已用 `meta` 补 |
| W_NO_LANG / W_H1_COUNT | W | 缺 lang / h1 数≠1 |
| W_RESIDUE | W | markdown/pandoc 标记残留（`![` `**` `[^` 等） |
| W_IMG_NO_ALT / W_IMG_FORMAT / W_IMG_LARGE / W_IMG_RATIO / W_IMG_UNCOMPRESSED | W | 可访问性/兼容性/尺寸 |
| W_EPUB_SIZE | W | 总体积 >50MB |

### 溯源（provenance）

| 码 | 级 | 一句话处置 |
|---|---|---|
| E_UNIT_MISSING / E_UNIT_ORDER | E | structured↔translation↔spine 三边缺口/乱序 → 补译或重 build |
| E_MEDIA_LOST / E_MEDIA_ORDER | E | 译文丢图/图序乱 → 对齐源文图片引用 |
| E_MEDIA_EPUB_LOST | E | 译文引用的图未进成品（构建静默丢弃）→ 查 raw/media 与 `media_dropped` 事件 |
| E_FN_EPUB_LOST | E | 成品脚注数与译文不一致 → 查 `[^label]:` 定义后重 build |
| E_EPUB_PARA_LOST | E | 成品缺译文段落（`epub_coverage` < 1.0）→ 按 `unit:段` 定位重 build |
| E_ALIGN_MD_DRIFT | E | 译文正文与对照表不一致（一侧缺内容）→ 以 align 为准修 md 后重 import |
| E_TOC_FLAT | E | 有层级源的 nav 扁平 → 查单元 level 与标题 |
| E_INSERT_MISSING_FILE | E | inserts 指向的媒体缺失 → 重跑该单元 ingest |
| E_INSERT_BAD_SOURCE | E | inserts source 非法 → 修该 `<id>.json` |
| W_INSERT_NO_DESC / W_INSERT_NO_LATEX | W | 图注描述/公式 LaTeX 未补 → agent 补全后复跑 |
| W_NO_COVER | W | 无封面（权属不明可接受，见 publishing.md §2） |
| W_STRUCT_MISSING | W | structured 源文文件缺失 → 重 ingest |
| W_TOC_DEPTH | W | nav 深度序列与源不一致（按 `output.nav_depth` 投影后对账） |
| W_TOC_MISSING / W_NAMING | W | facts 源 TOC 缺条目 / 成品命名与 slug 不符 |
| W_DELIVERY_AUDIT_MISSING | W | 全单元 built 但无交付记录 → 按 references/delivery.md 执行交付审计 |
| W_REPAIR_UNRESOLVED | W | 语义整备有未决修复（repairs.jsonl unresolved）→ 能修则修，存疑的记录在交付记录 |

## 5. 工作区契约压缩版

- 状态机：`pending → split → analyzed → translated → aligned → reviewed → built`
  （`import` 推 translated→aligned；`import --reviewed` 推 aligned→reviewed；
  `build` 推 built；reviewed/built 跳过重导）。
- 权威真相：`publication.json`（不手编；元数据经 `meta` 命令写）、glossary.csv。
- import 阻断（errors）：缺文件、align 断号/空译文、**对照表 src 不在源文中**、
  **表格形状不守恒**。import 告警（warnings）：terminology/marker/footnote/fidelity
  前向缺块/length（硬缺陷类红色显示，漏修被 G5 兜底）。
- 术语三态：seed→candidate→conflict→confirmed；冲突外置
  `analysis/glossary_conflicts.jsonl`，**裁决写回前 qa 不放行**。
- 术语裁决写回后：对**全部已译单元**重跑 `g0`（旧译法违例当场清零）。

## 6. 构建约束

- 三主题：`standard`（默认）/`compact`/`spacious`；只排版微调，禁具体字体名/字号/颜色。
- 确定性构建：`dcterms:modified` 冻结为常量，同一输入必得同一 EPUB。
- EPUB 3：nav+NCX、每章恰一个 h1、脚注 noteref/footnote 全局序号+双向跳转、
  封面 cover-image+`linear="no"`、双语成对。
- 译者署名：`dc:creator(creator-trl)` + `role=trl`（`meta --translator` 写入）。
