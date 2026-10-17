> **中文** | [English](2026-10-17-collected-notes-resegmentation.md)

# 书末注释被按页摊平：成品里每条注挤成一个巨型段落

> 日期：2026-10-17　来源：交付后校对反馈（工作根 `sample-notes-a`）
> 状态：工作根侧已修（该工作区的 `preprocessing/tools/rebuild_notes.py`）；**本仓库无代码改动**

## 触发场景

书末统一注释区（collected endnotes）的书，尤其「每章一组 `1. 2. 3. …` 编号注」的体例。
成品里出现**极长的注释段落**：一条 `<p>` 里串着好几条注，最长能到数千字符，
读者无法分辨注与注的分界。

## 判据（怎么判断可能命中该情况）

1. **成品侧**：数 notes 单元 XHTML 的 `<p>` 数量。若**远少于注条数**，且单个 `<p>` 内
   含 ≥2 个注号形态（`(?<![0-9])\d{1,2}\.\s`），即命中。
   ⚠ 该指标**有假阳性**——注文里引用「第 3 章」「vol. 2.」都会命中，只能当**候选**。
2. **源侧（决定「可不可重建」）**：`structured/raw/page-*.json` 里**同一页存在多个
   `font_size`**，且注文块字号与正文块不同。实测某书同一页：区标题 `27.5`、
   分章标题 `15.0`、注文 `11.25`。
   → 这说明**分段信息在 raw 层是完好的**，只是抽取/整备时被摊平了。
   此时修复是**按 raw 块重建**，不靠猜、不需要模型判断。
3. **反例（不可用字号法）**：MinerU 路径的书 raw 是 `structured/raw/mineru/content_list.json`，
   没有 `font_size` 语义，改看 `type`（`text`/`page_footnote`/`page_number`/`header`/`footer`/`list`/`image`）。

## 处置（怎么修）

1. **按字号分类 raw 块**：`fs >= 20` 区标题（跳过）；`14 < fs < 20` 分章标题；
   `10 < fs <= 14` 注文。阈值按每本书实测标定，别硬套。
2. **只在行首认注号**：`^\d{1,2}\.\s`。**这是核心判据**——注释正文里会出现
   **引文内部的数字**，实测有 `‘Nation: 4. Le nationalisme’`、`‘Nation: 3. Nation et idéologie’`
   两种。按「句中任意 `N. `」切会把一条注**切碎**、并让下一条**重号**。
   字号/缩进都救不了这一刀，只有「行首」能救。
3. **自检（必做）**：每章注号必须严格连续 `1..N`、**0 处跳号**。实测某书 148 条 / 12 章组，
   行首判据 0 跳号；同一份数据用句中判据则立刻出现重号与碎块。
4. **续块分类**：不以注号开头的块——首字符小写或引号 → **跨页续句**，接回上一条；
   首字符大写 → 同一条注内的**引文另起段**（是否真另起段按书体例定；本次并入同段）。
5. **译文侧（摊平文本没有行首信息）**：以**源为模板**做单调 DP——把译文按句中 `N. `
   切成碎片，为每个源块选一段连续碎片。代价：首碎片号不符 `100000`、
   号对但前面不是句末标点 `200`、多吞一个碎片 `800`。
   ⚠ 判据必须看**跨度首**碎片；曾误用**末**碎片 → 2 处错配（末碎片号常常也"对得上"，
   错得不显眼）。
6. **md 与 align 必须同步**：CLI 有两把门——「文档一致性」（translation md ↔ align `tgt`）与
   「源保真」（align `src` ↔ structured md）。只改一边必挂，且**改源 md 忘了 align 的 `src`
   也一样挂**（实测一次挂 148 条）。

## 复现/验证（最小 fixture）

```bash
# 1) 成品侧：数「段内含 ≥2 个注号形态」的段（候选，不是结论）
python3 - <<'PY'
import zipfile, re, html
z = zipfile.ZipFile('output/<slug>.epub')
x = z.read('OEBPS/back-notes.xhtml').decode()
b = x[x.index('<body>'):]
ps = [html.unescape(re.sub(r'<[^>]+>', '', p)) for p in re.findall(r'<p[^>]*>(.*?)</p>', b, re.S)]
print(len(ps), sum(1 for t in ps if len(re.findall(r'(?<![0-9])[0-9]{1,2}\.\s', t)) >= 2))
PY

# 2) 源侧：同一页是否有多个字号（决定可不可重建）
python3 -c "
import json;d=json.load(open('structured/raw/page-244.json'));
print(sorted({round(b['font_size'],2) for b in d['blocks'] if b.get('font_size')}))"
```

自检清单（重建之后逐条过）：

- 每章注号 `1..N` 连续、0 跳号；
- `g0` 硬缺陷 0，其中 **`heading`（标题层级守恒）与 `terminology`** 都要清零；
- 成品 notes 页 `<p>` 数 == 注条数；
- 残留反斜杠 0（若用了注号转义，见下）。

**幂等是硬要求**：重建工具必须可重复运行且输出字节相同。首版不幂等，重跑时读了上一次的
产物，产出 `## ## 序言` 与一串空 `##`，**直接打破标题守恒门**。

## 顺带命中过的两个坑

1. **行末连字符被当断词删掉**：注释区实测 4 处行末连字符
   （`self-`/`World-`/`Christian-`/`anti-`）**全是真复合词**且恰好断在连字符上，
   正确结果是 `self-contradiction`、`World-Economy`、`Christian-non-Christian`、
   `anti-capitalism`。旧管线一律删连字符，产出 `selfcontradiction` 等 4 处错误。
   判据：先看这批行末连字符是不是真复合词，再决定「保留」还是「拼接」。
2. **孤立的 `1. …` 成块会被渲染成单项有序列表**：`build/html.py` 的 `_OL_MARK` 分支
   在「编号自 1 起连续递增」时输出 `<ol>`（并自动编号）。于是一条注只占一个段落块时，
   **每章第一条**渲染成 `<ol><li>`、其余是 `<p class="fnlist">`，同一章里两种样式。
   处置：注号**转义**为 `1\. `（项目已有先例：`europe-an-empire-of-400-million` 的列表即写作
   `1\. ` `2\. `）。⚠ **源 md、align 的 `src`、译文 md 三处必须由同一个函数生成**——
   漏了 align 的 `src` 那次，保真门一次报了 148 条。

## 代码位置

- 列表判定：`src/auto_epublizer/build/html.py` 的 `_OL_MARK` / `_OL_LINE` 分支
  （`<ol>` 自动编号的适用条件）；
- 标题层级守恒：`src/auto_translator/review/g0.py` 的 `count_heading_levels`；
- 源保真双向绑定：`src/auto_translator/review/fidelity.py`；
- 重建工具：工作根侧 `workspaces/<slug>/preprocessing/tools/rebuild_notes.py`（**不在本仓库**）。

## 仍然缺的检测口

`qa/audit.py` 目前**没有**「collected-notes 未分段」这一类检查——即成品注释页 `<p>` 数
与注条数严重不符、或单段含多个注号形态时不会报警。这正是本类缺陷能一路走到交付的原因
（与「审计覆盖什么决定缺陷能否被发现」同族，参见 issue #38）。现场同一形态在另外 9 本
出现过（某本 75 段、某本 29 段），说明值得做成检测口而不是靠人肉普查。
