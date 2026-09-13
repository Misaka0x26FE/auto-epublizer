# Delivery（交付审计：qa 之后、交付之前的强制全量校验）

> **定位**：`qa` 通过只代表**已知契约**全绿。本清单要求你在交付前独立做一次
> 「源引用 ↔ 成品包含」的全量对账与人工抽查，防止「工具没查到的缺口」直达成品。
> 真实案例：《俄国铁路史》翻译任务工具 QA 全过，成品 72 张引用图只收了 34 张——
> 根因是译文正文丢图片段而工具守恒只查对照表（align）。

## 何时执行

`qa` 返回 `released=True` 之后、把成品交给用户/分发之前。**强制**，不可跳过
（小书可压缩第 2–4 步的抽查量，但不能省略）。

## 0. 前置：刷新事实

```bash
auto-epublizer preprocess          # 幂等刷新 facts（对账以当前产物为准，不用旧快照）
auto-epublizer qa                  # 确认 released=True；released_reason=ok
```

## 1. 工具对账复核（读 report.json）

| 字段 | 要求 |
|---|---|
| `released` / `released_reason` | True / ok |
| `epub_coverage` | ≈ 1.0（成品段落探针；无探针为 null） |
| `epub_media_missing` / `epub_footnotes_missing` | 0 |
| `align_md_drift` | 0（译文正文与对照表一致） |
| `g0_terminology_open` / `g0_structure_open` | 0 / 0 |
| `glossary_conflicts_open` / `catalog_unresolved_open` | 0 / 0 |
| `W_INSERT_NO_DESC` / `W_REPAIR_UNRESOLVED` / `W_DELIVERY_AUDIT_MISSING` | 逐条过目处置（见 §4） |

error 级溯源发现（`provenance_findings`）必须清零；warning 逐条判读。

## 2. 解包抽查（首/中/尾 + 高风险章：图表/脚注/多语密集）

先解包成品：

```bash
mkdir -p /tmp/epub-check && cd /tmp/epub-check && unzip -o <slug>.epub
```

- **正文探针**：从译文挑 3–5 句代表句，在 `OEBPS/*.xhtml` 里逐个 grep 命中
  （工具已全量对账，这一步是防工具自身错位的**第二道保险**）；
- **图片**：确认 `OEBPS/media/` 文件数 = 引用数（工具已查）；再**看 2–3 张图**
  （multimodal）确认图的内容与上下文位置吻合——防「图在但放错位置/张冠李戴」；
- **脚注**：抽 3 条注码，确认注文**内容**正确（不是只回链存在）；支持弹窗的阅读器
  应弹窗显示，不支持者跳章末列表；
- **目录**：nav 条目数 = 单元数、层级与原书目录一致（对照 facts 的源 TOC）。

## 3. 人肉核对

- 封面：`cover-image` 指向正确图、无裁切异常；
- 元数据：`dc:title/creator/translator/language` vs 版权页（预处理期已用 `meta` 写回，
  此处复核）；
- landmarks：frontmatter/bodymatter/backmatter 指向存在的文档。

## 4. inserts 描述与未决项

- `raw/inserts/<id>.json` 中 `content_desc` 为空（`W_INSERT_NO_DESC`）会影响 EPUB
  图片 alt：逐项补全，或在交付记录中写明「显式接受」及理由（装饰图可接受）；
- `W_REPAIR_UNRESOLVED`（语义整备未决修复）逐条判读：能修则修；确属存疑的记入
  交付记录。

## 5. 阅读器实测（可选，推荐）

用 Foliate / Apple Books / 手机阅读器翻首/中/尾：目录跳转、脚注弹窗、图片渲染、
双语版抽查（如产出 `-bi.epub`）。

## 6. 修复循环（发现缺陷时）

```text
发现缺陷 → 定位（源文 structured / 译文 translation / 构建）
  → 修复（文本缺陷走语义整备 repairs.jsonl 留痕；边界/结构走 restructure）
  → import（校验 + 状态推进）→ g0 → build → qa → 回到本清单第 0 步重跑
```

- 修复译文正文后必须重新 `import`（md↔align 不一致会阻断）；
- 修复后必须**重跑全部对账 + 抽查**，不能只验修的那一处。

## 7. 交付记录（强制）

写 `reviews/delivery-<YYYYMMDD-HHMMSS>.md`（存在该文件后 qa 不再提示
`W_DELIVERY_AUDIT_MISSING`）：

```markdown
# 交付审计 <YYYYMMDD-HHMMSS>

- 审计对象：<slug>.epub（qa released，reason=ok）；facts 刷新时间 …
- 工具对账：epub_coverage=…；epub_media_missing=0；epub_footnotes_missing=0；align_md_drift=0
- 抽查章节：<首/中/尾/高风险章清单>
- [ ] 正文探针 N/N 命中
- [ ] 图片语义抽查 M 张正确（列出）
- [ ] 脚注内容抽查 3 条正确
- [ ] 目录/封面/元数据核对（结论）
- [ ] inserts desc 空值处置：补全 X / 显式接受 Y（理由）
- 发现与处置：（缺陷 → 根因 → 修复 → 复验；或「无」）
- 修复循环轮次：0（或 N）
- 产物清单与同步：本地/备份/云盘/仓库（字节核对结果）
```

## 8. 产物同步与分发

按 `references/publishing.md`：成品清单 + 分发副本字节核对（本地 `output/`、
备份、云盘/仓库等全部副本更新）；更新分发说明与版本记录。

## 9. 经验沉淀

交付中发现的**可复用判据**（不只是本书特例）写 `lessons/`（判据/处置/验证三段式）
并在交付记录中互引；计划级验证上下文回写对应 `docs/plans/` 文档。

## 常见误区

- **只信工具 QA**：工具校验它知道的契约（align 守恒/结构审计），build 实际消费的
  译文正文与成品包含必须独立对账（本轮已自动化，抽查是第二道保险）；
- **facts 当实时**：facts 是快照，重建/重切/修复后先 `preprocess` 刷新再对账；
- **只验修复点**：修复会引入新的不一致（状态/产物/分发），必须全量重验。
