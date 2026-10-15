> **中文** | [English](2026-10-15-epub-source-media-normalization.md)

# EPUB 源件的绝对媒体路径：机器路径进了工作区、嵌套插图在成品里丢失

> 日期：2026-10-15　来源：全项目审查（`docs/plans/2026-10-14-review-and-repair.md` D 组）
> 合成 EPUB 复现 + 根因修复。状态：**已修复**（`ingest/epub_reader.py::read_epub` 补
> `normalize_media_refs`；回归 `tests/test_ingest_boundary.py::test_epub_source_conserves_*`）。

## 触发场景

源件是 **EPUB**（或经 calibre 转出的 Kindle 容器），且书内图片放在**子目录**里
（如 `OEBPS/img/pic.png`）。read_epub 走 pandoc 抽媒体后：

- `structured/` 的 md 里图片引用是**绝对路径**（`/tmp/.../raw/media/img/pic.png`）——
  机器路径进入 git 追踪的持久化产物；
- 构建时该绝对路径规范化后命中不到（`media_root/tmp/...` 不存在），basename 兜底也命中
  不到子目录里的文件 → **插图在成品里丢失**（只留下 `media_dropped` 与 provenance 阻断）。

## 判据（怎么判断可能命中该情况）

1. `structured/` 的 md 里有**绝对路径**图片引用（`grep -n '!\[.*\](/[^)]*'`）；
2. `events.jsonl` 有 `media_dropped`，或 qa 报 `epub_media_missing` / `E_MEDIA_EPUB_LOST`；
3. 解包成品：`OEBPS/media/` 下缺少源书里有子目录层级的图片（例如应以
   `media/img/pic.png` 存在）。

注意与 docx 路径的区别：docx 走 `read_pandoc` 一直有归一化；**EPUB/Kindle 链路此前漏了
这一步**，所以镜像修复应落在 `read_epub`。

## 处置（怎么修）

1. 源码已修复（2026-10-14 起）：`read_epub` 与 docx 同口径调用
   `normalize_media_refs(run_pandoc(...), media_dir)`——绝对路径改写为工作区相对的
   `raw/media/<name>`，多出的 `media/` 层被拍平，图片属性块剔除；
2. 若工作区里已经留下绝对路径（旧产物）：**重跑 ingest/结构准备**（或手工把引用改为
   `raw/media/<正确相对路径>`，注意保留子目录）→ `build` → `qa` 确认
   `epub_media_missing == 0`；
3. 不要用「把图片复制到 media 根目录」来绕过子目录问题——那会丢层级、与源书不符，且
   多图同名时会互相覆盖。

## 复现/验证（最小 fixture）

合成 EPUB：`OEBPS/c1.xhtml` 含 `<h1>/<h2>` + 脚注 + `<img src="img/pic.png">`，
`OEBPS/img/pic.png` 为真 PNG；走 `orch.init(epub) → orch.build`：

```python
md = (store.structured_dir / "body/ch01.md").read_text()
assert "raw/media/img/pic.png" in md  # 引用已相对化
assert str(store.dir) not in md  # 机器绝对路径不得入产物
# 成品：OEBPS/media/img/pic.png 存在、正文含 <img src="media/img/pic.png">、脚注内容在
```

对应回归：`tests/test_ingest_boundary.py::test_epub_source_conserves_headings_footnote_and_nested_media`
（pandoc 门控 `skipif`，跳过时给出原因）。

## 代码位置

- `src/auto_epublizer/ingest/epub_reader.py::read_epub`（归一化调用；`已修复`）
- `src/auto_epublizer/ingest/pandoc_reader.py::normalize_media_refs`（归一化实现；docx 路径原有）
- 经验来源计划：`docs/plans/2026-10-14-review-and-repair.md` §7 批次 D
