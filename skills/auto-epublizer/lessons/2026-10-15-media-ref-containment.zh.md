> **中文** | [English](2026-10-15-media-ref-containment.md)

# 媒体引用越出媒体目录：`../` / 绝对路径 / 外指符号链接会被读进成品

> 日期：2026-10-15　来源：全项目审查（`docs/plans/2026-10-14-review-and-repair.md` D 组）
> 最小坏文件复现 + 根因修复。状态：**已修复**（`build/__init__.py::collect_media._resolve`
> 包含性校验；`qa/provenance.py::_audit_inserts` 同口径；回归 `tests/test_ingest_boundary.py`）。

## 触发场景

源件（Markdown/HTML/DOCX/EPUB 等）里的图片引用不是普通相对路径，而是：

- `../…` 链（含足以走到工作区之外的层数，甚至 `../../../../etc/…` 这类绝对位置）；
- 绝对路径（`/etc/hostname`、`/home/...`）；
- 工作区内指向**外部**目标的符号链接。

命中后构建会把**工作区之外的文件内容**作为媒体收进 EPUB，并把 `media/../../…` 这类
非法成员名写进成品——既是越界读取（成品外泄），也破坏 EPUB 成员命名。

## 判据（怎么判断可能命中该情况）

1. `structured/` 的 md 里出现绝对路径或含 `..` 的图片引用（`grep -n '!\[.*\](.*\.\.'`）；
2. `events.jsonl` 有 `media_dropped` 事件（列出被丢弃的引用）；
3. qa `report.json` 出现 `epub_media_missing > 0` 与 provenance `E_MEDIA_EPUB_LOST`；
4. 成品解包 `OEBPS/media/` 里出现带 `..` 的成员名（修复前才会发生）。

`media_dropped` / `E_MEDIA_EPUB_LOST` 是**硬门**：越界引用不会静默丢图，会阻断放行。

## 处置（怎么修）

1. **不要手工把这些引用改成工作区内的路径**——先判断来源：若是源件本身携带越界引用
   （脏源），正确做法是让 ingest/构建两侧的边界生效：
   - 构建侧已固定：候选路径 `resolve()`（跟随符号链接）后必须落在 `structured/raw/media/`
     之内，越界一律拒绝读取并只记入 `dropped` 列表；
   - ingest 侧：pandoc 路径的媒体引用会被改写为工作区相对的 `raw/media/<name>`；
     EPUB 源同口径（见另一篇 lessons）。
2. **把图片放进 `structured/raw/media/`**（正确文件名/子目录）后重跑 `build`，
   再 `qa` 确认 `E_MEDIA_EPUB_LOST` 归零；
3. 若该引用本就是源件错误（例如指向源站外链），在 `preprocessing/catalog.csv` 记
   `unresolved`/`absent` 并在 `analysis`/`repairs` 留痕，按放行规则处理。

## 复现/验证（最小 fixture）

```python
# 1) 纯函数：越界目标真实存在 → 必须被丢弃、不得读取
media_root = tmp_path / "structured/raw/media"
media_root.mkdir(parents=True)
secret = tmp_path / "outside.txt"
secret.write_text("SECRET")
ref = os.path.relpath(secret, media_root)  # "../../outside.txt"
rewritten, files, dropped = collect_media(f"![x]({ref})", media_root)
assert files == [] and dropped == [ref]  # 修复前：files 含 SECRET 字节

# 2) 端到端：成品不得含 ".." 成员，且 qa 以 E_MEDIA_EPUB_LOST 阻断放行
```

对应回归：`tests/test_ingest_boundary.py`（相对 `..`、绝对路径、外指符号链接、合法嵌套对照、
成品成员名、provenance 阻断）。

## 代码位置

- `src/auto_epublizer/build/__init__.py::collect_media._resolve`（包含性校验；`已修复`）
- `src/auto_epublizer/qa/provenance.py::_audit_inserts`（inserts 文件同口径；`已修复`）
- 经验来源计划：`docs/plans/2026-10-14-review-and-repair.md` §7 批次 D
