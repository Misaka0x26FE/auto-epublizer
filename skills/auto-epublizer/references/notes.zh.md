> **中文** | [English](notes.md)

# 注释结构化与绑定（N 阶段）

面向**有注释**（脚注/尾注/边注、集中注文）的书：让每条注文有稳定身份、在正文原位保留
引用标记、全书级渲染为标准语义注释，并由**独立硬门**阻断"有注却零语义节点/部分遗漏/
错配"的成品。

> 无注书不进入本流程（不写 `notes.json`，构建/审计走原路径）——"无注"是**经核证**的
> 结论（`inventory=none`），不是"检测数为零"。

## 流程（零 token CLI + agent 语义核证）

1. **盘点候选**（CLI）：

   ```bash
   auto-epublizer notes candidates --workspace <ws>
   # → preprocessing/note_candidates.jsonl（marker/pandoc_ref/definition/numbered_paragraph）
   ```

   候选带 `unit/line/text` 证据；身份是内容哈希（不含行号），重跑保留已有处置。

2. **agent 核证**（语义工作，CLI 不做）：

   - 回看源件/`structured/raw/` 证据，逐条给候选写 `disposition=note|not_note`；
   - 判定**真实注文边界**（页底残片、跨页续文、编号错位）、**注号作用域**（原书章/节）
     与**每次引用**的位置；
   - `unverified` 是过程态：登记前必须落到 `present`（有注且建好绑定）或 `none`。

3. **写源注文权威** `structured/notes.json`（见下 schema），注文全文进
   `source_markdown`（多段/列表/强调/图片/公式照原样保留 Markdown）。

4. **正文原位标记**：在**原引用位置**写 `[^ref-000123]`（标记文本即 `ref_id`，
   不编码可见序号，不按源文字数偏移插入，不强制搬到句末）。同一段源文里的一条注文
   被引用多次时，每次引用注册一条独立 `references`（独立 `ref_id`）。

5. **登记**（分离登记门）：

   ```bash
   auto-epublizer notes register --workspace <ws>
   ```

   校验 schema/源哈希绑定/身份唯一/作用域/双位置证据/未决状态/**正文标记 ↔ 引用双向
   对账**/候选处置完整性；通过后把**摘要**写入 `publication.json.notes`（agent 不手改
   官方状态）。

6. **翻译**：译文正文在**对应语义位置**保留同一 `ref_id`；注文本身在
   `translation/notes.json` 用同一 `note_id` 保存完整译注。译注同样参加术语检查、
   内容完整性与 G1–G3 审校。

7. **`import`**（翻译导入门）：译文标记守恒（每条引用恰好一次、无未登记标记）、所需
   译注齐全、译注摘要与源注文绑定有效；失败即阻断该单元登记。

8. **`build`**：全书级渲染——正文标记 → `epub:type="noteref"` 链接；注文渲染为
   `epub:type="footnote"` aside（`id="fn-<note_id>"`，完整块级 Markdown + 每条引用独立
   回链）；跨文件引用 href 指向注文宿主文件（spine 序第一个引用它的单元）；显示号按
   作用域确定性生成（章内重号合法，一注多引同号）。构建发现未登记标记或未进成品的
   引用时报错，**不静默丢弃**。

9. **`qa`**（成品门）：独立解析最终 XHTML，逐条对账引用锚点/href/aside/回链/内容；
   `released_reason=notes_open` 阻断放行；篡改/遗漏/错配都会定位到具体 `ref_id`/`note_id`。

## JSON 契约（N2）

`structured/notes.json`（源注文权威）：

```json
{
  "schema_version": "1",
  "source_sha256": "<publication.json.meta.source_sha256>",
  "inventory": "present | none | unverified",
  "notes": [
    {
      "note_id": "n-000001", "scope_id": "ch01", "source_label": "23",
      "note_type": "footnote | endnote | sidenote",
      "source_markdown": "完整源注文（Markdown）",
      "source_locations": [{"kind": "page", "page": 12, "text_block": "…"}],
      "status": "verified | unresolved",
      "orphan_ok": false, "orphan_reason": ""
    }
  ],
  "references": [
    {
      "ref_id": "ref-000001", "note_id": "n-000001", "unit": "ch01", "scope_id": "ch01",
      "label_text": "23", "context": "…注码前后文…", "status": "verified"
    }
  ]
}
```

`translation/notes.json`（译注；不复制源引用/位置）：

```json
{
  "schema_version": "1",
  "source_notes_sha256": "<structured/notes.json 的 sha256>",
  "notes": [{"note_id": "n-000001", "target_markdown": "完整译注（Markdown）"}]
}
```

约定：

- 身份稳定：`note_id`/`ref_id` 一经登记不得重排或复用；显示号与身份分离。
- `scope_id` 取经来源确认的章/节；跨作用域同号合法，同作用域同号报错。
- 未引用注文（原书确实存在）必须 `orphan_ok=true` + `orphan_reason`，构建仍渲染保留。
- 源文回退构建用 `source_markdown`；译文构建要求相应译注齐全（缺则阻断）。

## 门与失效

| 门 | 检查 | 触发点 |
|---|---|---|
| 分离登记门 | schema/源哈希/身份/作用域/双位置/未决/标记双向对账/候选处置 | `notes register` |
| 翻译导入门 | 译文标记守恒 + 译注齐全 + 摘要绑定 | `import` |
| 成品门 | noteref/href/aside/回链/内容逐条对账；none 零对零 | `qa`（`notes_open`） |

**失效**：源哈希、正文标记、`structured/notes.json` 或译注变更后，登记摘要失效——
`notes status` 报 `stale`，`import`/`build`/`qa` 明确报错或阻断（`E_NOTES_STALE`），
须重跑 `notes register` 并按需重译受影响注文。

## 状态与排障

```bash
auto-epublizer notes status --workspace <ws>        # 摘要 / stale / 候选处置进度
auto-epublizer status --workspace <ws> --json       # notes 段 + next_tasks
```

`next_tasks` 会给出前置注释任务（`notes_verify` → `notes_register`），完成前不进入翻译/交付。

常见阻断与处置：

- `inventory=unverified`：先核证，再登记；
- `未决注文`/`候选未全部处置`：逐条给核证结论（`note`/`not_note`）；
- `正文缺原位标记`/`标记出现 N 次`/`未登记标记`：正文与 `references` 双向对齐；
- `译文缺 [^ref-…]`/`出现未登记标记`：译文标记与登记不一致；
- `译注摘要不符`/`E_NOTES_STALE`：源注文已变更，重登记并重译受影响注文；
- 若干注文无引用：补 `orphan_ok=true` + `orphan_reason`（原书未引用注文不得删除）。
