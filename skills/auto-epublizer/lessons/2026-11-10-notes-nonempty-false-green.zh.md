> **中文** | [English](2026-11-10-notes-nonempty-false-green.md)

# 注文层「非空即已译」的假绿

## 判据（何时适用）

- 一本书有集中注文（`structured/notes.json` + `translation/notes.json`），`qa` 报
  `released=true/ok`、`notes_findings` 为空、`notes_missing` 为空。
- 但成品（或 `translation/notes.json`）里的注文**仍是源语言**：纯外文、或与
  `source_markdown` 逐字相同。
- 用眼睛抽读发现「注文没翻」，而所有门禁都是绿灯——此时**不是漏跑 qa，是判据本身不看语言**。

命中特征（可机器预筛，秒级）：

```python
# target_markdown 非空但零汉字（目标语言为 zh*）
b = (note.target_markdown or "").strip()
CJK = re.search(r"[\u4e00-\u9fff]", b)
suspect = bool(b) and not CJK
```

## 处置

1. **先定位判据，不要先改译文。** 现行成品注文门只做**登记文本 ↔ 成品渲染**的对账：
   `translation/notes.json` 的 `target_markdown` 非空即视为「已译」，于是「登记外文、
   渲染外文」两边一致 → 通过。检查顺序：

   ```text
   translation/notes.json 的 target_markdown
     → 若非空 → 期望值 = 该串 → 与成品 aside 比对 → 一致 → 通过   ← 缺口在此
     → 若为空 → 退回收源 source_markdown（源文回退，语义上是「未译」）
   ```

2. **把「语言核对」做成独立硬门**，与内容对账并列（不要塞进内容对账里）：

   - `target_markdown` 归一化后 == `source_markdown` → 判未译；
   - 目标语言 `zh*` 且 `target_markdown` 归一化后零汉字 → 判未译；
   - 合法例外（纯著录条目、拉丁书名、URL/DOI、外文引文整段）走**逐条带证据的豁免行**，
     照样报出（`blocking=false`），不得整单元豁免。

3. **配套做一次全库普查**（只统计，不动译文）：按「无汉字注文 / 总注文」逐本列表。
   实测口径可作参考——一本书若该比例 >0，几乎一定存在整层未译或整段未译的章节，
   按单元抽取前 20 条即可定性。

4. **验收**：合成 fixture 三条注（真译文 / 源文照搬 / 纯著录），断言
   ① 只有真译文与著录豁免通过；② 源文照搬被判 `E_NOTES_UNTRANSLATED`；
   ③ 著录条目在豁免后仍出现在报告里（不得消失）。

## 为什么这条比「多跑一次审校」更值钱

- **假绿的传播面最大**：注文是学术译著的主要成本（实测单本 96–2,215 条），
  且注文常被当成「著录、翻译价值低」而最后处理；一旦门禁不看语言，
  它会以「结构完整、epubcheck 0 错、溯源 1.0」的完美形式放行。
- **它与正文语言门不对称**：正文有「源译归一化后逐字相同 → 硬缺陷」的判据
  （`auto_translator/review/g0.py` 的 `language_identical`），注文层没有对应项。
  这类「同一语义判断只在一条路径上有门」的缺口，要在加门时**同时问一句
  『另一条路径呢』**。

## 复现 / 验证

```bash
# 1) 只读普查（不写任何文件）：逐本统计无汉字注文
python3 - <<'PY'
import json, glob, re
CJK = re.compile(r"[\u4e00-\u9fff]")
for p in sorted(glob.glob("workspaces/*/translation/notes.json")):
    slug = p.split("/")[0]
    notes = json.load(open(p)).get("notes") or []
    if not notes:
        continue
    bad = sum(1 for n in notes
              if (n.get("target_markdown") or "").strip()
              and not CJK.search(n["target_markdown"]))
    print(f"{slug}: {bad}/{len(notes)}")
PY

# 2) 单条最小复现（判据层）：同一段源语言文本写进 target_markdown
#    期望：新增硬门报 E_NOTES_UNTRANSLATED；现状实现报 notes_findings 为空。

# 3) 负向测试：真译文 / 纯著录豁免 不得被误报（合成 fixture，见 tests/test_notes.py 风格）
```

- 判据位置：`src/auto_epublizer/qa/notes_audit.py`（成品注文门）；
  正文侧对照判据：`src/auto_translator/review/g0.py::language_identical`。
- 现状与影响规模的分析见 `docs/plans/2026-11-10-field-archive-gap-analysis.md` §2 P0-1。
