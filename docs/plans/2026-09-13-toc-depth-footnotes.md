# 2026-09-13 标准输出模板：导航深度投影 + 注释样式

状态：实施中

## 背景

对照两份真实 EPUB（`参考/[S0_00]读前必看` 模板 + `参考/[S1_03]某魔法的禁书目录`，
汉化组惯例）审视本项目的标准输出模板，确认两项调整：

1. **注释**：正文注码用 `[N]` 样式（非裸数字），指向章末集中注释区，保留双向回链；
   按章独立编号（章末集中的自然搭配），CSS 维持极简不变。
2. **导航**：真实书籍标题可达六级。目录不应照抄全部层级——印刷书目录惯例只列 2–3 级。
   采用「结构保真 + 导航投影」：nav/NCX 最多渲染 K 层（默认 3，可配 1–6），
   超出 K 的节点保留在 spine 阅读顺序与锚点中，但不进目录。

单元切分默认维持现状（每个标题一个单元）。`structure.split_level`（只按前 S 级切单元、
更深标题留在单元内）作为后续扩展点，本轮不实现。

## 技术设计

### 1. 注释样式（`src/auto_epublizer/build/html.py`）

- `_substitute_noterefs`：注码 `N` → **`[N]`**，补 `role="doc-noteref"`：
  `<sup class="noteref"><a epub:type="noteref" role="doc-noteref" id="ref-N" href="#fn-N">[N]</a></sup>`
- `_render_footnote_section`：章末条目补 `[N]` 前缀：
  `<p>[N] {正文} <a epub:type="backlink" href="#ref-N">↩</a></p>`
- **按章独立编号**：`FootnoteState` 由「全书共享」改为「每单元新建」（`orchestrator`
  `_render_and_pack` 循环内实例化）；每章从 1 起。id（`ref-1`/`fn-1`）在各自 XHTML
  文档内作用域唯一，跨文档重复合法。
- 回链、`epub:type`/`role` 语义不变；`E_FN_BACKLINK` 校验逻辑无需改。

### 2. 导航深度投影（`src/auto_epublizer/build/__init__.py` + `auto_common/config.py`）

- `OutputConfig` 新增 `nav_depth: int = Field(3, ge=1, le=6)`（config 快照自动带入
  `publication.json`）。
- 新纯函数 `nav_toc_entries(entries, nav_depth)`：先排除封面单元（`kind == "cover"`），
  再按 `_toc_depths` 归一化深度投影（`depth > nav_depth` 的节点剔除）；
  nav/NCX 共用。
- `_render_nav` / `_render_ncx` / `build_epub` 增加 `nav_depth` 参数；
  `dtb:depth` = 投影后实际最大深度。
- **投影深度写进产物**：`nav.xhtml` head 输出 `<meta name="nav-depth" content="K"/>`。
  审计以产物声明为准，避免「`build --nav-depth N` 后 `qa` 用默认配置」造成的
  投影/豁免错位（配置/参数只兜底无声明的旧产物）。
- 投影语义：被剔除的单元仍在 spine 阅读顺序正常翻页；锚点与内部链接照常解析。

### 3. 配置与命令

- `docs/configuration.md`：`output.nav_depth`。
- CLI `build` / `convert` 增加 `--nav-depth`（缺省取配置）；`orchestrator.build/convert/
  _render_and_pack` 逐层透传。

### 4. 审计适配（`qa/audit.py` + `qa/provenance.py`）

- `audit_epub(path, *, nav_exempt: set[str] | None = None)`：投影掉的 spine 文档
  （basename 集合）豁免 `E_TOC_COVERAGE` 的「未进目录」检查；nav 幽灵条目检查不变；
  豁免集出现非 spine 文档名报错（防豁免集写错）。
- `audit_provenance(..., nav_depth=3)`：
  - 读产物内 `nav-depth` 声明（缺失时用参数兜底），用 `nav_toc_entries` 计算
    「投影后的期望目录序列」，`E_TOC_FLAT`/`W_TOC_DEPTH` 与投影后的 nav 对账
    （投影即预期，不再误报）；
  - `ProvenanceResult` 新增 `nav_exempt: list[str]`（被投影剔除的文档名），
    供 `orchestrator.qa` 传给 `audit_epub`。
- `orchestrator.qa`：先跑 provenance（拿到 `nav_exempt`），再跑 audit；`nav_depth`
  参数取 `Config().output.nav_depth` 仅作旧产物兜底。

## 测试设计

- `test_build.py`：
  - 脚注：`[N]` 注码/条目前缀、`role="doc-noteref"`、跨单元**按章重置**（两单元都从 1 起）；
  - 导航：6 级单元清单 + `nav_depth=2` → nav/NCX 只含前两级；深层文档不在 nav；
    `dtb:depth == 2`；封面单元不进目录。
- `test_qa.py`：投影豁免——超深 spine 文档不报 `E_TOC_COVERAGE`，同书非投影缺失仍报错。
- `test_config.py`：`nav_depth` 边界（1–6，越界报错）。
- 全量 `uv run pytest -q` + `ruff check .` + `ruff format --check .`。

## 文档同步

- `docs/epub-template-spec.md`：§3 结构层（目录深度投影 + 封面不进目录）、
  §6 注释标准化（`[N]` + 按章编号 + role）、§7 配置（`output.nav_depth`）、§8 清单。
- `docs/postprocessing-spec.md`：目录层级验收与投影后的 `E_TOC_FLAT`/`W_TOC_DEPTH` 语义。
- `docs/configuration.md`：`output.nav_depth` 字段。
- `skills/auto-epublizer/references/build.md`、`qa.md`、`invariants.md` 对应条目。

## 验证记录

- `uv run pytest -q`：**287 passed**（新增 4 例：脚注章内编号 + `[N]`、目录投影与封面排除、
  `E_TOC_COVERAGE` 投影豁免、`nav_depth` 配置边界；更新既有脚注/溯源测试）。
- `uv run ruff check .` / `ruff format --check .`：通过。
- CLI 冒烟（六级标题 + 脚注的 md）：
  `convert --nav-depth 2` → nav 只列前 2 级、`dtb:depth=2`、nav.xhtml 含
  `<meta name="nav-depth" content="2"/>`；脚注渲染为 `[1]` 注码 + 章末
  `<aside epub:type="footnote">` + `↩` 回链；`qa`（默认配置）`released=True`、
  无 `E_TOC_COVERAGE` 误报。
- **偏差记录（计划外新增）**：设计审查时发现「`build --nav-depth N` 后 `qa` 用默认配置
  会导致投影/豁免错位、误报 E_TOC_COVERAGE」——补了「投影深度写进 nav.xhtml 声明、
  审计以产物为准」机制（配置/参数仅兜底旧产物）。

## 后续扩展点

- `structure.split_level`：只按前 S 级标题切单元，更深标题留在单元内并局部重基
  （h2…h6，连续不跳级），用于超深书籍控制单元数量；默认不启用。
