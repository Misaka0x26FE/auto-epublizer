# 后处理规范：内容完整性 / 媒体 / EPUB 结构 的验收与实现

本文档规定翻译/导入完成后、交付前（`build` → `qa` 区间）的**后处理验收标准与实现计划**。
覆盖三大类：**内容完整性与溯源**、**媒体位置与样式**、**EPUB 结构与目录层级**。

> 范围边界沿用：只负责**交付质量**（准确/完整/一致/规范/结构正确/可复现），不做
> 价值观/政治/思想性判断。样式规范以 `docs/epub-template-spec.md` 为准，本文只负责
> 「验收与校验」，不重复定义样式。

## 1. 定位

后处理不是新阶段，而是对现有 **G4/G5（+ 部分 build/G0）** 的规格化补全。三道验收
分别落在：溯源归 G0/G5、媒体归 build+G4、结构归 G4。

## 2. 三大类验收标准与现状差距

### 2.1 内容完整性与溯源

> 目标：仓库内容齐全无缺漏，翻译后的每个部分都能追溯到原文。

| 验收项 | 现状 | 缺口 / 动作 |
|---|---|---|
| 逐句溯源锚点 | ✅ `align/<id>.jsonl` 每行 `{seq,src,tgt,note}` | — |
| 对照表完整性 | ✅ G0 `check_alignment`（seq 连续、src/tgt 非空） | — |
| 结构守恒 | ✅ G0（段落块/标记/脚注/标题 1:1） | — |
| **三边对账**（structured↔translation↔output） | ⬜ | 新增：逐单元三边存在、顺序一致、无遗漏/多余 |
| **媒体溯源**（图片数量/顺序与源文一致） | ⬜ | 新增：译文图片引用 vs 源文，防丢图/多图/错位 |
| **逐段溯源覆盖率** | ⬜ | 新增：structured 每段 ↔ align 全覆盖，产出 `provenance_coverage` |
| **源文勘误留痕** | ⬜ | `apply_corrections` 命中项写入 align `note`（如 `corr:IDG→IDF`），区分译错/源错 |

### 2.2 媒体位置与样式

> 目标：图片插入到原文对应位置；能全尺寸就全尺寸，不能则等比例缩放居中。

| 验收项 | 现状 | 缺口 / 动作 |
|---|---|---|
| 图片不溢出 + 居中 | ✅ `max-width:100%` + 居中 + 不放大 | 语义确认见 epub-template-spec §4 |
| 字节收集 + 去悬空 | ✅ `collect_media` | — |
| **尺寸策略显式化** | ⬜ | 「只缩不放大」写为唯一策略；超宽/超高/大图审计告警 |
| **位置溯源** | ⬜ | 图片在译文中的相对顺序与源文一致（并入 2.1 媒体溯源） |
| 图注 caption / alt | ⬜ | 图注 `<figcaption>`；alt 空值告警（可访问性） |
| 封面 `cover-image` | ⬜ | 见 epub-template-spec §3 |
| 格式兼容 | ⬜ | `.avif`/`.webp` 兼容性告警 |

### 2.3 EPUB 结构与目录层级

> 目标：EPUB 合法，目录齐全，层级符合源文件。

| 验收项 | 现状 | 缺口 / 动作 |
|---|---|---|
| epubcheck 0 error | ✅ | — |
| G4 解包审计 | ✅ mimetype/container/OPF/nav/NCX/landmarks/img 悬空/URL/lang/h1 | — |
| **目录层级** | ⬜ | nav/NCX 当前扁平单层，源文 h2/h3 不进目录 |
| **TOC 对账** | ⬜ | preprocess 抽的源 TOC vs nav 条目对照，漏条目告警 |
| 脚注双向跳转 | ⬜ | 见 epub-template-spec §6（脚注语义化） |
| 标题无跳级 | ⬜ | h1→h3 跳级告警 |

## 3. 数据契约

### 3.1 溯源审计（新增，零 token 纯函数）

输入 `structured/<id>.md` + `translation/align/<id>.jsonl`，输出每单元：

```json
{
  "unit_id": "ch01",
  "segments_total": 42,
  "segments_covered": 42,
  "missing_segments": [],
  "media_src": 3,
  "media_tgt": 3,
  "media_lost": [],
  "media_order_ok": true
}
```

### 3.2 report.json 扩展（G5）

```json
{
  "provenance_coverage": 1.0,
  "units_missing": 0,
  "units_order_ok": true,
  "media_lost": 0,
  "toc_missing": [],
  "toc_flat": false
}
```

## 4. 分阶段实现计划

### P0 — 结构 / 溯源 / 目录层级（✅ 已完成 2026-09-04）

1. ✅ **目录层级**（链路补全，信息已在 `SourceUnit.meta["heading_level"]`）：
   - ✅ `structure/rebuild.py`：`rebuild_structure` 把 `heading_level` 写进 entry（`entry["level"]`）
   - ✅ `orchestrator`/`store`：level 存进 `Unit.meta`，`structure_entries` 回填
   - ✅ `build/__init__.py`：`_render_nav` 嵌套 `<ol>`、`_render_ncx` 嵌套 `<navPoint>`（含 `dtb:depth`）
   - ✅ 目录层级审计：`E_TOC_FLAT`（源有层级 nav 扁平）/ `W_TOC_DEPTH`（深度序列不一致）
     ——在 `qa/provenance.py`（需对照源 level，非 audit_epub）
   - PDF 源：单 unit 无层级，依赖 agent 在 preprocessing 切分并登记 level（CLI 提供机制）
2. ✅ **三边对账**：`qa/provenance.py`（`E_UNIT_MISSING`/`E_UNIT_ORDER`），接入 `qa`
3. ✅ **媒体溯源**：`E_MEDIA_LOST`/`E_MEDIA_ORDER`
4. ✅ **逐段覆盖率**：`provenance_coverage` 进 report.json（无翻译产物为 null）
5. ✅ **源文勘误留痕**：`detect_corrections` + `annotate_correction_notes`；
   translate 与 import 两路径均写 align `note` 前缀 `corr:wrong→right`
6. ✅ **TOC 对账**：facts 源 TOC vs 单元标题 → `W_TOC_MISSING`（warning 线索）
7. ✅ **脚注语义化**：`noteref`/`footnote` + 全局序号 + 双向跳转（`FootnoteState`）
8. ✅ **样式瘦身**：`_STYLE_CSS` 去字体/颜色/字号/行距/缩进/对齐（回归测试锁定）

### P1 — 媒体位置 / 样式 / 主题（✅ 已完成 2026-09-04）

- ✅ 主题机制：预置三套极简主题（`standard`/`compact`/`spacious`）+ `--theme` +
  `config.output.theme`（epub-template-spec §5）；audit 拦截具体字体名/字号/颜色
  （`E_THEME_FONT`/`E_THEME_COLOR`）
- ✅ 封面 `cover-image`（`<meta name="cover">` + spine `linear="no"`）+ `W_NO_COVER` 对账
- ✅ 媒体审计：超宽/超高/大图（`W_IMG_RATIO`/`W_IMG_LARGE`）、alt 空值（`W_IMG_NO_ALT`）、
  格式兼容（`.webp`/`.avif` → `W_IMG_FORMAT`）
- ✅ 图注 `<figcaption>`：独立图段（alt 非空）→ `figure+figcaption`
- 尺寸策略「只缩不放大」：已在 P0 样式瘦身时作为功能性规则锁定（回归测试）

### P2 — 补充项（✅ 已完成 2026-09-04）

- ✅ 可访问性：标题无跳级（`E_HEADING_SKIP`）；alt 空值（P1 已做 `W_IMG_NO_ALT`）、lang（原有 `W_NO_LANG`）
- ✅ 残留检查：HTML 注释（`E_RESIDUE`）/ markdown·pandoc 标记（`W_RESIDUE`：`![` `**` `:::` `{.` `[^`）；
  源语言字符残留属语义判断，归 G1 审校（agent 任务），不做确定性检查
- ✅ 元数据完备：creator/date/publisher/rights 缺失 → `W_META_INCOMPLETE`（告警，供 agent 补全）
- ✅ 双语溯源：`build --bilingual` src/tgt 段落数成对（`E_BI_PAIRS`）
- ✅ 内部链接：内部锚点可解析（`E_ANCHOR`，含 noteref→footnote）+ 脚注回链（`E_FN_BACKLINK`）
- ✅ 体积审计：EPUB 总体积（`W_EPUB_SIZE`，50MB）+ 单图未压缩（`W_IMG_UNCOMPRESSED`，2MB）
- ✅ 命名规范：成品文件名以 slug 为前缀（`W_NAMING`，qa 接线）；spine 顺序 = 源顺序（P0 provenance 已覆盖）
- ✅ 图片断页：`page-break-inside: avoid`（功能性样式）

## 5. 放行条件扩展

现有 G5 放行条件（`g2_confirmed==0 或全部修订` + `epubcheck 0 error` + `audit pass`）
基础上新增：

- `provenance_coverage == 1.0`（每段可溯）
- 三边对账零 error、媒体溯源零 error
- 目录层级零 `E_TOC_FLAT`（有层级源）
- 插入内容文件零缺失（`inserts_missing_files == 0`，pdf-content-spec §9：
  每个插图/表格/公式可回溯原始地址 `{page,bbox,xref,method}` 且媒体文件在盘）

## 6. 测试计划

每项加最小回归测试（沿用 tempfile + FakeClient 离线惯例）：

- 目录层级：带 h1/h2/h3 的 markdown → 断言 nav 嵌套 `<ol>` + NCX 嵌套 navPoint + 不报 `E_TOC_FLAT`
- 三边对账/媒体溯源/覆盖率：缺失/乱序/丢图 fixture → 断言对应 error code
- 脚注语义化：注码 → `noteref`/`footnote` + 全局连续序号 + 双向 href 可解析
- 样式瘦身：断言 `_STYLE_CSS` 不含 `font-family`/`font-size`/`color`
- 主题：`--theme compact` → 断言注入对应排版属性
- 封面/figcaption/alt/残留：单项断言
- 全量 `uv run pytest -q` + `ruff` 回归

## 7. 与 epub-template-spec 的关系

| 文档 | 回答 |
|---|---|
| `epub-template-spec.md` | EPUB **应该长什么样**（三层规范、主题、注释标准化） |
| 本文档 | 后处理**怎么验收、怎么实现**（验收标准、审计、实现计划） |

本文档的 2.2（媒体样式）与 P0/P1 中涉及样式的项，具体样式取值以 `epub-template-spec.md`
为准，本文档只描述「校验动作」与「实现落点」。
