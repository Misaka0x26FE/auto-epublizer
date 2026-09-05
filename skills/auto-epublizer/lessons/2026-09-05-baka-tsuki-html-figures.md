# Baka-Tsuki 源站 HTML 的插图段保真

> 日期：2026-09-05　来源：豆包 GT2（创约魔法禁书目录 GT2）实测。
> 状态：build 端缺陷已修复（1766e7a），本文留存「遇同型情况怎么判、怎么修」。

## 触发场景

输入是 **Baka-Tsuki / MediaWiki 系源站导出的 HTML**（`init` 走 pandoc 抽取），正文中
插图以三行结构出现：

```html
<figure class="mw-default-size" typeof="mw:File/Thumb">
<a href="/project/index.php?title=File:GT_Index_v02_055.jpg" class="mw-file-description"><img src="/path/to/media/<hash>.jpg" class="mw-file-element" decoding="async" srcset="…" data-file-width="…" data-file-height="…" width="300" height="426" /></a>
</figure>
```

- 三行分别是 `<figure>`、`<a>…<img …/></a>`、`</figure>`；pandoc 抽取后 `<img src>`
  常被改写为**工作区 media 的本地绝对路径**（`…/structured/raw/media/<hash>.jpg`）。

## 判据（怎么命中该情况）

1. structured 单元 md 里出现 `<figure` 与 `<img src="…">`；
2. build 后成品 EPUB 里对应插图**缺失**；
3. 源站原图 URL 可下载，但 build 找不到本地文件。

**根因（实测校正）**：build 端 `collect_media`（`src/auto_epublizer/build/__init__.py:426`）
用 `_HTML_FIG_IMG`/`_HTML_IMG` 提取 `<img src>` 并按 `raw/media/` 解析文件；**找不到文件
→ 该引用被丢弃**。`\s*` 允许换行，所以「三行连续 / 中间有空行 / 夹带少量文本」都能识别
（已实测）；真正丢图的场景是：

- 译文段里 `<img …>` **整行被删/改写**（豆包 GT2：8 个单元译文图片段缺 `<img src>` 行）；
- 或 `<img src>` 指向的文件不在 `structured/raw/media/`（pandoc 抽取失败 / 未下载）。

## 处置

1. **译文段保 `<img>` 行**：图片段在 `translation/<unit>.md` 与 `align/<unit>.jsonl` 中
   必须**保留含 `<img src="…">` 的完整一行**（可连同 `<figure>/<a>` 一起保留），tgt=src
   （不翻译 alt/srcset/路径）；不要拆成多段、不要删除 `<img>`。
2. **校验文件存在**：确认 `<img src>` 相对路径能在 `structured/raw/media/` 解析到文件；
   不存在则从源站下载原图放该目录、文件名对齐。
3. **build 验证**：`auto-epublizer build` 后解包 `OEBPS/*.xhtml` 应含 `<img src="media/…">`；
   `qa` 看 `media_lost == 0`。
4. **多图单元**：一章内多处插图全部按此处理（本次 ch07/10/12/18/23/32/36/45）。

## 已修复的主仓库问题（同型缺陷，勿再踩）

| 问题 | 根因 | 修复 |
|---|---|---|
| manifest media id 含 `/` → epubcheck RSC-005 | `item_id = epub_path`（含 `/` 非法 XML name） | `1766e7a`：`epub_path.replace("/", "_")` |
| spine 缺 `toc="ncx"` → RSC-005 | NCX 恒生成但 spine 未引用 | `1766e7a`：`<spine toc="ncx">` |
| `import --terms` 首次调用崩溃 | `row_to_entry` 对 None 值 `.strip()` | `1766e7a`：`(row.get(x) or "")` |

## 复现 / 验证

```python
# collect_media 能识别三种形态（三行连续 / 中间空行 / 夹带文本），关键在文件存在
from auto_epublizer.build import collect_media
import pathlib
media = pathlib.Path("/tmp/opencode/med"); media.mkdir(exist_ok=True)
(media / "x.png").write_bytes(b"PNG")
for md in [
    '<figure>\n<a><img src="media/x.png"/></a>\n</figure>\n',          # 三行连续
    '<figure>\n\n<a><img src="media/x.png"/></a>\n\n</figure>\n',       # 中间空行
    '<figure>\n<a><img src="media/x.png"/></a>\n夹带文本\n</figure>\n',  # 夹带文本
]:
    out, files = collect_media(md, media)
    assert "![](media/x.png)" in out and len(files) == 1, md[:20]

# 反例：`<img>` 存在但文件缺失 → 引用被替换为空（图被丢弃）
out, files = collect_media('<figure>\n<a><img src="media/gone.png"/></a>\n</figure>\n', media)
assert "![](media/gone.png)" not in out and not files
```

完整端到端：`tests/test_build.py::test_build_epub_embeds_media_files`（含 media id/spine 回归断言）。

## 关联

- 源站 HTML 抽取：`references/ingest.md`（pandoc 路由）；
- md 图片引用形态与 provenance 对账：`docs/pdf-content-spec.md` §2.3、`references/qa.md`（`media_lost`）。
