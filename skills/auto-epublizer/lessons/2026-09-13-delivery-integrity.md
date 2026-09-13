# 成品完整性对账：工具 QA 全过仍缺 38/72 张图（交付审计教训）

> 日期：2026-09-13　来源：《俄国铁路史》中译任务交付前手动全量检验（外部工具链，
> 本项目复盘）。状态：**已落地**——对账自动化见 `qa/provenance.py`（E_MEDIA_EPUB_LOST/
> E_FN_EPUB_LOST/E_EPUB_PARA_LOST/E_ALIGN_MD_DRIFT）与
> `docs/plans/2026-09-13-delivery-audit.md`；强制清单见 `references/delivery.md`。

## 触发场景

翻译任务流程已结束、工具 QA 全绿（epubcheck 0 error、结构审计 pass），准备交付/分发。
此时**必须再做一次交付审计**：对成品做独立于工具契约的「源引用 ↔ 成品包含」对账。

## 判据（怎么判断可能命中该情况）

工具校验它「知道」的契约，build 消费的却是另一些文件——两者可能脱节：

| 实际案例 | 根因 | 工具为何没抓到 |
|---|---|---|
| EPUB 只含 34/72 张正文引用图 | 译文正文文件（translation/body）在翻译时丢了 38 处图片引用段 | 守恒校验查的是对照表（align，脚本回填过、完整），build 消费的是 md |
| 脚注内容部分缺失 | 同一批 md 也丢了部分脚注标记 | 脚注守恒同样只看 align |
| inserts 描述 80 条为空 | 语义层未补 | 工具只出 W 级提示，易被忽视 |

命中信号：
- 用 `grep` 统计 structured 的图片引用数/脚注标记数，与 translation/成品实际数量对不上；
- 译文 md 与 align 的文本量不一致（align 更长/更短）；
- 成品解包后 `OEBPS/media/` 文件数 ≠ 正文 `<img>` 引用数；
- 交付前从未做过「解包抽查」。

## 处置（怎么修）

1. **独立对账（先量化）**：分别统计 structured/、translation/、成品解包三方的
   图片引用、脚注标记、段落数——本案由此定位到 38 张缺图集中在 ch02/ch04/ch05/
   ch06/ch07，与 EPUB 缺失清单完全吻合；
2. **以 align 为准重建正文**（align 是经 import 校验的权威对照）：按序用 align 的
   tgt 重建 md（同时修复图片段与脚注）；重建前**备份原文件**（`*_backup_pre_rebuild/`）；
3. **验证重建无内容丢失**：译文探针与重建前做重叠率比对（本案 95–98%，未匹配项
   均为标题/引号跨段边界的探针假阴性）；
4. **重 build + 重 QA**：确认图片从 34 → 72、无断链无多余、epubcheck 0 error；
5. **全量重验后同步所有分发副本**：本地成品、云盘、仓库三处字节核对一致；
   修复记录写 ISSUES 报告/交付记录。

## 复现/验证

```bash
# 自动化对账（主仓库已接线）：错误案例 → qa 应按 E_MEDIA_EPUB_LOST 阻断
uv run pytest -q tests/test_provenance.py -k "epub_media_lost or silent_media_drop"
uv run pytest -q tests/test_provenance.py -k "epub_footnote_lost or epub_para_lost"
uv run pytest -q tests/test_import.py -k drift
```

端到端最小复现：工作区译文 md 引用 `raw/media/ghost.png` 但文件不存在 → build 静默
丢弃（`events.jsonl` 记 `media_dropped`）→ `qa` 报 `E_MEDIA_EPUB_LOST` 且
`released=False`（见 `tests/test_provenance.py::test_silent_media_drop_blocks_via_epub_reconciliation`）。

## 可复用判据（跨任务）

- **成品校验必须独立做「源引用 ↔ 成品包含」对账**，不能只依赖工具 QA——工具全绿
  不代表 build 输入与成品一致；
- md 是 build 输入、align 是校验基准：二者必须一致（`E_ALIGN_MD_DRIFT` 已自动对账）；
- 修复后必须**全量重验 + 全部分发副本同步**，不能只验修复点。

## 关联

- 计划/设计：`docs/plans/2026-09-13-delivery-audit.md`（S1 对账自动化 + delivery.md）；
- 强制清单：`references/delivery.md`（qa released 后的交付审计步骤与记录模板）；
- 现行代码：`qa/provenance.py`（成品呈现对账）、`review/g0.py::md_align_drift`、
  `build/__init__.py::collect_media`（丢弃清单 + `media_dropped` 事件）。
