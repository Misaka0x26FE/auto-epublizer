# 2026-10-15 审查回流修复报告（待审查）

状态：**待审查**。本报告覆盖两件事：① 计划 §8.1「审查回流（未修复）」8 项的修复情况；
② 历史成品 `sample-archive-a` 的 V 返修与 H 版本回收。审查通过前不视为结项。

来源：

真实作品的交付或摘录记录已移除；通用修复契约保留。

## 1. 主仓库修复：4 项 P1 + 2 项 P2（附失败回归）

| 项 | 位置 | 修复 | 回归 |
|---|---|---|---|
| P1-1 候选↔注文图对账 | `orchestrator.register_notes` + 新增 `notes.validate_candidates_vs_graph` | 已核证 `note` 候选与 `inventory=none` **矛盾即拒绝登记**；`present` 时每条 note 候选必须在注文/引用图留下证据（同单元/全局 label 命中，或候选文本落于某条 `source_markdown`），否则按**部分遗漏**拒绝 | `test_register_rejects_note_candidates_with_none_inventory`、`test_register_rejects_note_candidate_missing_from_graph` |
| P1-2 译注源版本绑定 | `orchestrator._load_notes_context`（import/build/qa **共享入口**） | 校验译注 `source_notes_sha256` == 当前源注文摘要；按实际源/译模式 `require_target`（build `prefer_translation`、qa 有译文参与时强制译注齐备）；`inventory=none` 零对零不受影响 | 更新 `test_import_gate_blocks_stale_translation_notes_digest`（改由共享入口报错）+ 新增 `test_build_blocks_when_translation_notes_binding_stale` |
| P1-3 注文媒体核对 | `qa/notes_audit.audit_notes_epub` | 期待引用（`target_markdown`/`source_markdown` 的图片）⊆ aside 实渲染 `<img>`；实渲染资源必须在包内。`E_NOTES_MEDIA_MISSING` / `E_NOTES_MEDIA_ABSENT`；不再被去图文本规范化掩盖 | `test_notes_product_gate_flags_note_media_missing` |
| P1-4 摘要覆盖全部放行输入 | `qa/artifacts.artifacts_digest` | 单元描述改为**发布顺序**（不再按 id 排序）+ region/kind/level/rel_path/title；新增 `catalog.csv`/`repairs.jsonl`/`facts.json`；新增**实际源件字节**哈希 | `test_report_goes_stale_when_catalog_unresolved_added_after_release` |
| P2-a 伪 stale 项不当单元 | `orchestrator._derive_next_tasks` | `report_stale → build→qa`；`notes_changed_since_register → notes register`；`catalog_binding_broken → 修 catalog.csv`；未知伪项跳过。杜绝 `import --unit report` 死循环 | `test_next_tasks_report_stale_not_routed_as_unit` |
| P2-b 成品路径 cwd 敏感 | `qa/artifacts`（`_resolve_epub_path`）+ `qa()` 保存 | 工作区内成品按 `store.dir` 相对保存/解析；外部成品用规范化绝对路径 | 上述 P1-4 回归 + 既有 B2 失效链用例 |

**前后证据**：在 HEAD 工作树（`/tmp` 临时 worktree + `PYTHONPATH` 指向其 `src/`）运行本次新增/更新的回归
——**P1 五项全部失败、P2-a 一项失败**；修复后同一批全部通过。全量 **578 passed, 1 skipped**、
`ruff check`/`format --check` 全绿（离线可跑）。

**提交**：`6cb79f0`（本次修复；`orchestrator.py` 同时带入在途「处理工具记录」两行，同文件无法分离）、
`22c8c55`（在途指纹实现随审提交）。两提交已推送 GitHub 与 Gitee（远端 `HEAD = 22c8c55`，双远端核验一致）。
隐私核对：改动仅含公开项目链接与「禁止记录机器路径/密钥」类条款文字；`fingerprint.py` 的
`_revision()` 只对本包源码仓库执行 git 查询，写入内容为 commit 与 dirty 布尔，不含路径。

## 2. 未修两项 P2 的设计（待审）

- **P2-c（旧门移交）**：判别口径由「单元素材（`[^ref-…]` 标记）」提升为**书级登记状态**——
  `orchestrator.qa` 已加载 `notes_ctx`，将其作为 `notes_registered` 传给 `audit_provenance`
  （登记后跳过旧「md 定义数 ↔ 成品 aside 数」计数）与 `audit_epub`
  （新增 `unreferenced_notes`，回链门只对**被引用的** aside 生效；`orphan_ok` 注文由 notes 门
  的 `kept_notes` 负责）。红线：不伪造引用、不删除合法注文、未登记的多余 aside 与内容/媒体缺失
  仍按 `E_NOTES_*` 阻断；legacy（无登记图）行为不变。回归：① 带 `orphan_ok` 注文的工作区
  build→qa 不再报 `E_FN_EPUB_LOST`/`E_FN_BACKLINK`；② 删孤儿注内容/媒体后 notes 门仍阻断；③ legacy 对照。
- **P2-d（入口顺序）**：`AGENTS.{zh,md}` 工作流段把「注释结构化与绑定」整块前移到翻译之前并重编号
  （注释核证/登记 → 语义整备 → 翻译（含 `translation/notes.json`）→ import/g0 → 审校）；
  `SKILL.{zh,md}` 管线摘要补注释步骤；建议加轻量文档闸：在 AGENTS/SKILL 的流程代码块中断言
  「注释登记命令首次出现位置 < 翻译登记命令首次出现位置」（命令名锚定，避免自然语言脆弱匹配）。
  `references/workflow.{zh,md}` 与 `status --json` 机器指针已为注释在前（无需改）。

## 3. 真实作品记录（已脱敏）

真实作品识别信息、摘录及交付记录不随公开代码保留。

## 4. 真实作品记录（已脱敏）

真实作品识别信息、摘录及交付记录不随公开代码保留。

## 5. 未完成/未验证（审查关注点）

- P2-c / P2-d（设计见 §2，未实现）；
- 书籍 **N 迁移**（前置：恢复注文真实边界/跨页续文/编号作用域/引用位置 → `notes.json` +
  原位标记 + 三道硬门；legacy 弹窗/回链语义目前为 0）；
- 245 条术语命中的**逐项证据映射**（不照抄旧豁免 CSV；旧清单绑定旧单元、style.md §40–49
  不支持「著录一律不译」）；
- 阅读器**交互**验收（跳转/弹窗/落点；审查侧已取目录截图）；
- 主仓库侧 `terminology_exempt` 机制是否移植的产品决策。

## 6. 复现命令

```bash
# 主仓库回归（离线）
uv run --offline pytest -q && uv run --offline ruff check . && uv run --offline ruff format --check .

# 修复前证据（HEAD 工作树）
git worktree add /tmp/x HEAD && cp tests/test_notes.py /tmp/x/tests/ \
  && (cd /tmp/x && PYTHONPATH=/tmp/x/src uv run --offline --project <repo> pytest -q tests/test_notes.py -k "none_inventory or missing_from_graph or binding_stale or media_missing or catalog_unresolved_added")

# 书籍侧（包内）
tar -xzf <scratch>/sample-archive-a-v-fixed.tar.gz
cd sample-archive-a && uv run --offline --project <repo> auto-epublizer status --workspace . --json
# 核对：report.json.artifacts_epub 指向包内相对路径；nav/NCX 97 条一致见 reviews/v-20261015-structure.md 第 5 节
```
