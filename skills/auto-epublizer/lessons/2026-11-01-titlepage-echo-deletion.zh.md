> **中文** | [English](2026-11-01-titlepage-echo-deletion.md)

# 书名页标题被当「页眉回声」删除

## 判据（何时适用）

- 成品或 `structured/` 的书名页只剩 `# Title Page` 加编者、出版地，书名/副题消失。
- `structured/raw/page-*.json` 里书名与副题仍在，且 `font_size` 明显大于正文（书名页常是整页最大字）。
- 删除发生在 agent 按「与单元 title 同文的页眉回声块」规则清理 md 时，不是 CLI 拆分自动完成。
- 页首/页尾跨页重复的短行才是版式家具；同一文本位于**页中**，或所在单元是
  `titlepage` / 半书名页 / `cover`，都不是可删除的回声。

## 处置

1. 先冻结源证据：`auto-epublizer evidence source --json` 取出该页 blocks 的
   `page`、`block`、`bbox`、`font_size`、`column`，确认书名页原文与字号层级。
2. 回声剔除只适用于正文单元（chapter/section），且必须同时满足：该块是该页第一个或
   最后一个正文块、跨页重复、字号不大于正文。只有「与 title 同文」不构成删除理由。
3. 书名页、半书名页、封面：与书名/副题同文的行一律保留；标题段（heading）不得按页眉删除。
4. 每次删除都要写入 `preprocessing/repairs.jsonl`：unit、源页、块号、字号、删除理由和保留证据。
   没有源位置与理由的删除视为未批准，不能只留结果。
5. 清理后重建书名页：`structured/` 的书名、副题、编者、出版地必须与 raw 对应块逐字一致；
   同步 `translation/` 与 `align/`，再复跑 `g0`、`qa` 和字数/漂移检查。

## 当前代码边界

- `src/auto_epublizer/structure/rebuild.py` 的 `_render_markdown` 只在 heading 段与将要写入的
  `# title` 同文时省略该段，文本仍以 h1 出现；它不做跨页重复判断，也不删除书名页行。
- `src/auto_epublizer/structure/classify.py` 的 `clean_header_footer` 只删除**页首/页末那一次**
  出现，并保留 `kind == "heading"` 的段。
- 同文件的 `clean_unit` 对 `cover` / `titlepage` 单元原样返回；这两类单元整页都是内容，
  出版年、页码同形行也不能按家具剔除。
- `init`/`preprocess` 写出 `structured/` 时不套用这些清洗函数；结构修复属于 agent 的语义任务，
  必须自带位置与理由留痕。不要把「CLI 没删」当作「清理无需记录」。

## 复现/验证

```bash
uv run --offline pytest -q tests/test_structure.py \
  -k 'title_page or header_footer or clean_unit'
```

- 合成书名页夹具（书名 + 副题 + 编者 + 出版地）经 `rebuild_structure` → `write_structured`
  后逐字保留。
- 页中与页眉同文的短行保留 3 次，标题段保留 3 次；只有页首/页末那次被删除。
- 现场核验：渲染源 PDF 书名页读图，对照 `structured/raw/page-*.json` 与
  `structured/frontmatter/front-titlepage.md`；再检查成品 XHTML 的同一页，而不是只看 md。
- 若历史书已手工恢复，保留恢复记录并在交付记录中说明原始删除来源；不要用当前测试通过
  反推当时没有删除。
