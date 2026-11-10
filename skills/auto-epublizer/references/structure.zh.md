> **中文** | [English](structure.md)

# Structure（四层结构重建 + 溯源）

把归一化单元归类为出版物四层结构，清洗后落 `structured/`，作为翻译与封装的源文权威。

## 四层结构

```text
structured/
├── cover.md                        # 封面
├── frontmatter/{titlepage,copyright,dedication,foreword,preface,toc}.md
├── body/ch01.md ...                # 正文单元（翻译主战场）
├── backmatter/{afterword,appendix,notes,bibliography,index,glossary}.md
└── media/                          # 媒体资产
```

## 归类规则

标题关键词 → (region, kind)，例：

| 标题含 | region | kind |
|---|---|---|
| 封面 / cover | cover | cover |
| 书名页 / titlepage | frontmatter | titlepage |
| 版权 / copyright | frontmatter | copyright |
| 献词 / dedication | frontmatter | dedication |
| 他序 / foreword | frontmatter | foreword |
| 前言 / 自序 / preface | frontmatter | preface |
| 目录 / toc / contents | frontmatter | toc |
| 后记 / 跋 / afterword | backmatter | afterword |
| 附录 / appendix | backmatter | appendix |
| 参考文献 / bibliography | backmatter | bibliography |
| 索引 / index | backmatter | index |

未命中关键词 → `body` + `chNN`（顺序编号）。单元 ID 稳定（`ch01`、`front-preface`、`back-index`）。

## 清洗

- **页码剔除（需版式证据）**：显式标签（`第3页`、`p12`）、带装饰的页码（`- 8 -`），
  以及有 `source_page` 定位、跨 ≥5 页递增、且与页序偏移 0–3 的裸数字才删除。证据不足的裸数字（年份、
  诗歌编号、表格数字）**保留**并在 `structured/raw/structure-clean.json` 记为候选；
  不得按「长得像页码」静默删除。
- **页眉页脚剔除**：按 `source_page` 分组，同一短文本在 ≥50% 页首/页末出现即剔除（`min_pages` 保护）；
  删除项连同页码一起写入 `structure-clean.json`（`removed` / `candidates`）。
- **清洗与归类一致**：书名页/封面豁免用归类结果（`kind`），不再按标题二次判定；
  聚合单元按内容判为书名页时同样不剔家具。
- **落盘即清洗**：`write_structured` 写入的是清洗后的段，页眉/页码不会进入 `structured/`；
  重建预演用 `preprocess --force --dry-run`（只报告 new/changed/unchanged 与台账，不写盘）。
- **EPUB 锚点/属性残留**：`read_epub` 在入库时已清除 `[]{#id}` 锚点、`{#id}` 属性、
  `[text]{.class}` 类属性与 `<br>`；若 `structured/` 仍见此类残留在标题里，说明走了
  pandoc 通用回退路径，按 `references/ingest.md`「EPUB 按 spine 切分」排查。
- **溯源**：每个 `Segment` 带 `meta.source_page`，PDF 每页有 `page-NNN.json` 对应。

## 媒体身份与迁移映射

- 交付对账（QA/注文门）只接受**精确路径**（原相对路径、重复根前缀）或**显式映射**；
  同名不同目录不再用 basename 静默替代，目录错误的引用直接报缺失。
- 构建期仍兼容旧路径（basename 兜底），这只是过渡；错配由交付门暴露。
- 旧绝对路径需要逐条登记 `preprocessing/media-map.json`：

  ```json
  {"schema": 1, "entries": [
    {"ref": "/home/agent/book/media/fig1.png", "member": "fig1.png",
     "reason": "旧工作区绝对路径迁移", "sha256": "可选，64 位小写十六进制"}
  ]}
  ```

  `member` 相对 `structured/raw/media/`；必须给 `reason`；`sha256` 可选，用于锁定目标字节。
  越界成员、重复 ref、目标缺失、摘要不符都会成为审计 finding，不会被静默忽略。

## 契约

- 单元 = 翻译最小可管理单位；`Unit.meta` 存 `rel_path` 与 `region`（`set_units` 时写入
  `publication.json`），analysis/translation/build 都靠它定位文件。
- 标题层级（h1/h2）数量、段落块数量应与源文一致——**审校核对锚点**（g0.py 提供计数
  纯函数但未接入自动校验，属后续扩展点）。
- 插入元素（`{fig:NNN}` 等）标记数量守恒（G0 单元级总量守恒已接线，丢失即硬缺陷）；
  **md 表格形状守恒已接线**（表数/行列数，import 硬校验）；
  脚注/尾注引用↔定义配对与回链由 G4 审计（`E_FN_BACKLINK`/`E_ANCHOR`）覆盖。

## 单元边界重建（restructure 登记）

修复/重切导致**单元集合变化**（拆分、合并、新增、删除），或修改已完成单元的源正文时，应重新登记结构与内容摘要，否则
`publication.json.units` 与磁盘脱节：

1. 按真实章节手动重写 `structured/`（每个单元一个 md，首行 `# 标题`）；
2. 写 `preprocessing/structure.csv`（列 `id,region,kind,title,level,rel_path`；
   每行一个单元，`title` 必须等于该文件首行标题、`rel_path` 与 region 前缀一致）；
   可选第 7 列 `nav`（`yes`/`no`，缺省 `yes`）：`no` 的单元**进 spine 但不进目录**
   ——献词页等前置噪声页用它从正文目录里排除（仍在阅读顺序中）；
3. 运行 `auto-epublizer restructure`：校验（文件在、无孤儿 md、无重复 id）后更新
   `publication.json.units`；
4. 状态语义：同 id 且结构字段与已登记的正文 SHA-256 均未变 → 保留状态；有变 → 回退 `split`（需重译重 import）；
   旧工作区缺正文摘要时不推断历史完成态，首次 `restructure` 回退到 `split` 并登记当前基线；重复登记未变内容不会再次回退。
   消失的 id → 输出孤儿产物提示（旧 translation/align 可清理）。

> 何时用：MinerU/OCR 层级混乱需重切、碎片单元合并、单单元丢 nav 需拆分。
> 详见 `references/repair.md` 与 `docs/semantic-repair.md` §3.3。

## 说明

### 源清点 catalog.csv

列为 `item,kind,status,locator,unit_id,note`。kind 可取 toc/figure/table/footnote/section/physical/blank；figure 包含地图和整页图，输入 image 会规范化为 figure。blank 是内容类型，不是处置状态；OCR 没有文字不足以确认空白，仍需回看源页图。

| status（适用于各 kind） | 必填约束 | 放行语义 |
|---|---|---|
| included | unit_id 绑定真实单元 | 内容已纳入 |
| physical | 保留定位，物理载体记录 | 不自动作为未决 |
| excluded | note 说明排除理由 | 不自动作为未决 |
| absent | note 说明源件本身缺失依据 | 不自动作为未决 |
| unresolved | 待核证，不以猜测补齐 | 阻断放行 |

blank 的 locator 始终必填；除 unresolved 外还须 note 记录核证依据。`repairs.jsonl.evidence` 必须为存在的工作区相对文件路径（如 `structured/body/ch01.md`），路径或符号链接越出工作区均报错。

分栏阅读顺序、复杂表格保形、脚注/尾注专项提取是复杂 PDF 场景，当前为后续扩展点；
基础四层归类 + 页眉页脚/页码剔除已实现。
