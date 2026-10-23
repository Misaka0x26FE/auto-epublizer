> **中文** | [English](delivery.md)

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
| `epubcheck.ran` / `epubcheck.returncode` / `epubcheck.errors` | true / 实际进程值 0 / 0 |
| `epub_coverage` | ≈ 1.0（成品段落探针；无探针为 null） |
| `epub_media_missing` / `epub_footnotes_missing` | 0 |
| `align_md_drift` | 0（译文正文与对照表一致） |
| `g0_terminology_open` / `g0_structure_open` | 0 / 0 |
| `glossary_conflicts_open` / `catalog_unresolved_open` | 0 / 0 |
| `W_INSERT_NO_DESC` / `W_REPAIR_UNRESOLVED` / `W_REPAIR_STALE_UNIT` / `W_DELIVERY_AUDIT_MISSING` | 逐条过目处置（见 §4） |

error 级溯源发现（`provenance_findings`）必须清零；warning 逐条判读。

仅 jar 存在、Java 进程启动或旧 `ran` 字段不能证明 EPUBCheck 通过。保留完整发行包中 jar 相邻的 `lib`；headless Java 足够，无需 GUI。`report.epubcheck.returncode` 必须记录实际进程退出值，未执行为 `null`，未知不得猜 0；进程失败或 FATAL 不能按零错误放行。旧 released 报告缺字段或无可靠成功证据不代表当前合规：`status` 标为 stale，重新运行 `qa`，不得手改旧 `released`。已有 `digest_missing` 原因优先保留，否则此类旧报告过期原因为 `epubcheck_unverified`。

标准 EPUB 注释验收独立于桌面且为强制项：通过独立注释门和离线 ZIP/XML 对账，核证有效登记绑定、`noteref`/`footnote`/`endnote` 语义、完整注文、每个引用目标与回链、包内资源身份。不能用旧记号计数或阅读器截图替代；登记图为空也须零对零核证。

## 2. 解包抽查（首/中/尾 + 高风险章：图表/脚注/多语密集）

先解包成品：

```bash
mkdir -p /tmp/epub-check && cd /tmp/epub-check && unzip -o <slug>.epub
```

- **正文探针**：从译文挑 3–5 句代表句，在 `OEBPS/*.xhtml` 里逐个 grep 命中
  （工具已全量对账，这一步是防工具自身错位的**第二道保险**）；
- **图片**：逐项核包内资源身份及引用位置，复用图不要求文件数等于引用数；再**看 2–3 张图**
  （multimodal）确认图的内容与上下文位置吻合——防「图在但放错位置/张冠李戴」；
- **注释**：独立全量核对登记内容与包内完整注文；人工抽样需覆盖首/中/尾及跨页高风险注，
  列出样本 ID、分母、取样理由，不以最多前三条替代全量对账。不接受空串或截短子串通过；
- **目录**：逐条核标签/目标/层级与真实篇目（对照源 TOC）；区分子标题、封面排除、nav=no
  与 landmarks，不能只要求 nav 条目数等于单元数。

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
- `W_REPAIR_STALE_UNIT`（`repairs.jsonl` 引用了被结构重建删除的单元）：历史 `done` 行无害；
  `unresolved` 行请重挂现存单元。

## 5. 阅读器兼容抽查（有条件，不阻塞）

有桌面和目标阅读器时，用 Foliate / Apple Books / 手机阅读器翻首/中/尾：目录落点、注释跳转与返回位置、图片渲染及实际弹窗行为。记录阅读器/版本和真实观察。是否弹窗由阅读器实现和用户设置决定，标准 EPUB 语义不保证所有阅读器均弹窗。

无桌面/阅读器时，明确记「阅读器未实测」及原因，不阻塞标准交付、不声称 GUI 兼容已验；内容、链接/回链、资源、登记绑定、独立注释门、epubcheck 和独立对账仍必须通过。

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
- [ ] 注文内容全量对账；人工抽样 ID/范围/分母/理由与结果（或已核证零对零）
- [ ] 目录/封面/元数据核对（结论）
- [ ] inserts desc 空值处置：补全 X / 显式接受 Y（理由）
- 强制离线注释门：登记/语义/内容/链接/回链/资源（结果）
- 阅读器兼容：<阅读器/版本及实际观察，或「阅读器未实测：无桌面/阅读器」>
- 发现与处置：（缺陷 → 根因 → 修复 → 复验；或「无」）
- 修复循环轮次：0（或 N）
- 产物清单与同步：本地/备份/云盘/仓库（字节核对结果）
- 检查性质：逐项标明重做/沿用；沿用须证实输入摘要及检查规则未变
- 源件身份：实际 source/ 哈希与登记对比；外部 sources/ 缺失记未知，不写三方一致
- 机械门禁全绿 ≠ 内容已验收：已检查范围、未知项与尚待人工核证事项
```

所有自写审计/索引修复工具须遵守 [证据与安全修复契约](quality-evidence.zh.md)。
未执行项记 unknown/manual，不预勾选；不得用 H1 命中、词元袋覆盖或目录数量冒充内容验收。

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
