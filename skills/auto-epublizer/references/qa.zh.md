> **中文** | [English](qa.md)

# QA（epubcheck + 解包审计）

> 排障与放行判读速查（错误码全集/条件全集）见 `references/invariants.md`。

`qa` 命令对成品 EPUB 做结构 QA（G4），写 `report.json`。

## 命令

```bash
auto-epublizer qa [--epub <path>] [--workspace <dir>]
# 输出：G4 审计：pass/fail；epubcheck errors：N；passed：true/false
```

## epubcheck

- 用配置中的完整发行包 JAR（默认 `~/.cache/epubcheck.jar`）校验；必须保留相邻 `lib/` 依赖目录，不能只复制 JAR。Java headless 运行时足够，无需桌面。
  进程必须成功退出且无 ERROR/FATAL 才可放行；固定英文诊断便于稳定计数，启动异常与未识别的非零退出仍阻断，并保留退出码与诊断。
- jar 缺失时 `available=False`、`ran=False`、`errors=-1`，`passed=False`（未验证 ≠ 合格）。
- 报告 `epubcheck.returncode` 保存实际退出值，未执行为 null，未知不得补成 0。缺此证据的旧 released 报告会标记 stale、进度降为未放行，须重新 QA，不手改历史 released。

## 解包逐项审计（离线，零 token）

标准 EPUB 注释必须离线独立验收：核证有效登记绑定、完整内容、注释/引用语义、目标、回链及资源身份，`inventory=none` 也须零对零。仅有效、未过期的登记图且本次已执行独立成品注释门时，才移交旧计数/必须有回链判据；新门任一缺陷仍阻断。登记字段非空或出现 `[^ref]` 文本本身不构成证据，未登记/过期仍保留旧门。无需桌面；阅读器 GUI 只作有条件兼容抽查，不可用时记「阅读器未实测」，不推断所有阅读器均弹窗（见 `references/delivery.md`）。

| 检查 | 失败码 |
|---|---|
| 非 zip | `E_NOT_EPUB` |
| mimetype 非首位 / 被压缩 / 内容错 | `E_MIMETYPE_FIRST` / `E_MIMETYPE_STORED` / `E_MIMETYPE_CONTENT` |
| 缺 container.xml / 未声明 OPF | `E_NO_CONTAINER` / `E_CONTAINER_OPF` |
| OPF 缺失 | `E_OPF_MISSING` |
| spine idref 未在 manifest | `E_SPINE_REF` |
| manifest href 无法解析 | `E_MANIFEST_HREF` |
| nav 链接无法解析 | `E_NAV_HREF` |
| NCX content src 无法解析（悬空引用） | `E_NCX_HREF` |
| landmarks 链接无法解析（悬空引用） | `E_LANDMARKS_HREF` |
| 内容文档 img src 无法解析（媒体悬空） | `E_IMG_SRC` |
| javascript:/data: URL 注入 | `E_UNSAFE_URL` |
| 内容文档缺 lang / h1 数量不为 1 | `W_NO_LANG` / `W_H1_COUNT`（告警） |
| 标题跳级（h1→h3 等） | `E_HEADING_SKIP` |
| HTML 注释残留 / markdown 标记残留（`![` `**` `:::` `{.` `[^`） | `E_RESIDUE` / `W_RESIDUE`（error/告警） |
| DC 元数据缺失（creator/date/publisher/rights） | `W_META_INCOMPLETE`（告警） |
| 内部锚点无法解析（含脚注 noteref→footnote） | `E_ANCHOR` |
| 脚注 aside 缺回链或回链不可解析 | `E_FN_BACKLINK` |
| 主题含具体字体名/字号 / 颜色 | `E_THEME_FONT` / `E_THEME_COLOR` |
| 封面 properties 与 meta 互证失败 | `E_COVER_META` |
| img alt 空值或缺失 / 格式兼容性差（.webp/.avif） | `W_IMG_NO_ALT` / `W_IMG_FORMAT`（告警） |
| 图片超大（>4000px）/ 超宽超高（>5:1）/ 未压缩（>2MB） | `W_IMG_LARGE` / `W_IMG_RATIO` / `W_IMG_UNCOMPRESSED`（告警） |
| EPUB 总体积超阈值（50MB） | `W_EPUB_SIZE`（告警） |
| 已确认注释区疑似未分段 | `W_COLLECTED_NOTES_UNSEGMENTED`（warning 候选，不阻断） |

### Collected-notes 未分段候选（#46）

生产 `qa` 向 `audit_epub(notes_context=...)` 传精确 EPUB 成员路径对应的实际构建输入：
权威 `kind=notes`、unit、Markdown 与 `input_path`。source convert 只看源文；translation build
按每单元实际译文/源文 fallback 选择，不统计尚未渲染的译文。默认 API 调用仍兼容；
没有 context 时只扫描显式 `epub:type=endnotes|footnotes|rearnotes` 或
`role=doc-endnotes|doc-footnotes` 集合区，不凭文件名、全书数字或标题猜身份。

固定保守判据（无新开关）：注号形态是非单词/点字符之后的 1–3 位 ASCII 数字加 `. `，
MD 中 `\.` 同样计数。整单元 MD 候选 ≥8，且 ≥4×（非空 p + 独立 li 数），并有文本块
含 ≥2 个候选时提示失衡；或已确认区单文本块 ≥1000 字符且 ≥2 个候选时提示长块。
含 p 或嵌套 li 的 li 只作容器，不重复计数；独立 li 本身也检查，避免单项 ol 藏住摊平注释。
从不要求一注一个 p。
围栏/行内代码和真实 code/pre 字面量不计；显式单注 footnote/endnote/rearnote
（及 doc-footnote/doc-endnote）的合法内部多段/列表交给独立 N 门，不作 legacy 分段猜测。

发现进入原有 `report.json.audit.findings`，非空 `data` 提供 `file`、`unit`、`input_path`、
`scope`、`region_id`、`paragraph_count`、`list_item_count`、`input_candidate_count`、
`rendered_candidate_count`、`longest_paragraph_chars`、`longest_list_item_chars`、
`longest_block_chars`、`paragraph_indices`、`list_item_indices`、逐段 `paragraphs` 与逐列表项
`list_items`（均为 `{index,chars,candidate_count}`）、`reasons` 与 `raw_evidence=structured/raw/`。
两类索引分别是文件内全部 p / li 的 1-based 序号；集合区无整单元 MD 可比口径时 input 数为 null。
计数均排除代码及上述单注节点，不是已核证注条数。

长书目/引文可能假阳性；短摊平段、非数字/四位数字标号、无权威区语义的旧书可能漏报。
agent 按文件/段索引回 `structured/raw/` 与原页逐注核证边界、续页、内容和引用位置，
再按 `notes.zh.md` 完成规范 N 阶段；不得自动切注、以字号/大小写/引号或 DP 代替语义判断。
此 warning 不直接影响 released；独立 N 身份、内容、媒体、href/backlinks hard gate 不变。

## 质量报告 `report.json`

```json
{"slug":"...","g4_audit":"pass","g4_epubcheck_errors":0,"passed":true,
 "audit":{"ok":true,"errors":0,"findings":[]},
 "epubcheck":{"available":true,"ran":true,"errors":0,"warnings":0}}
```

## 放行条件（G5）

- `g4_epubcheck_errors == 0`（epubcheck 已实际运行）
- `g4_audit == "pass"`（解包审计零 error）
- G0 blocking 术语命中清零（`g0_terminology_open == 0`；经取证登记的 `terminology_exempt` 不计入，见 `translation.md`）
- G0 结构违例清零（`g0_structure_open == 0`：**blocking** 的 align/marker/footnote/
  heading/table/fidelity/language；fidelity 前向缺块与长度比是 advisory，不计入）
- 成品注释门清零（有注书：`notes_findings == 0`；`inventory=none` 时零对零）
  ——源件有注文（`structured/notes.json` 已核证，或正文有 `[^ref-…]` 标记）却没
  `notes register` 时**硬失败**（注文门不得静默跳过）
- 未决术语冲突清零（`glossary_conflicts_open == 0`；未清零 → `glossary_conflict_open`——
  回 analysis/glossary_conflicts.jsonl 裁决写回 glossary.csv 后重跑 qa）
- 审校 `g2_confirmed == 0` 或全部已修订
- 溯源完整（postprocessing-spec §5）：`provenance_coverage ≈ 1.0`（无翻译产物时为
  null，不适用）、`units_missing == 0`、`units_order_ok`、`media_lost == 0`、
  `toc_flat == false`、`inserts_missing_files == 0`（插图/表格/公式可回溯原始地址且文件在，
  pdf-content-spec §9）
- 成品呈现对账清零（交付审计 S1）：`epub_media_missing == 0`、
  `epub_footnotes_missing == 0`、`align_md_drift == 0`、`epub_coverage ≈ 1.0`
  （成品实际包含 ↔ 译文正文/对照表）

> **报告时效**：`report.json` 记录生成时的 `artifacts_digest`（源哈希 + 各单元
> structured/translation/align + 注释文件 + 最新审校 result + 成品字节）。之后改过
> 译文/对照表/审校/注释或成品，`status`/`status_all`/`ledger` 即把报告标为过期
> （`report_stale`，进度降为 `built_not_released`）；须重跑 `build`/`qa` 才恢复。
> 重跑 qa 时旧成品与当前产物不一致也会被 coverage/drift/注释内容核对拒绝。
>
> `preprocessing/terminology_exemptions.csv` 的创建、修改、删除同样使摘要失效；
> 历史 released 不重写，但 status 标为 stale / `built_not_released`，须重新 QA。

正文与注文独立核对：源 `label`/`ref_id` 不等于显示注号；语义 noteref 与完整脚注/尾注内容
不计入正文覆盖率，由独立注释门核对引用、内容、href 和回链。注文不能补偿邻接正文丢失。
字面代码、普通数学上标仍属正文；标题后紧接的正文不能随标题块一起跳过。
合法字面代码和表格中的 `# 1`、行内代码 `# comment` 必须保留，不能当残留剥掉。

> `qa released=True` 只代表已知契约全绿；**交付前还须执行 `references/delivery.md`
> 的交付审计清单**（独立对账 + 人工抽查 + 写交付记录），两者都完成才算交付。

`released` 为 False 时看 `released_reason` 判定原因：
`unresolved_confirmed`（G2 确认未修订）/ `structure_open`（含 align 缺失/空对照表）/
`notes_open`（有注书成品注释门未清零）/ `audit_failed` / `provenance_incomplete`
（溯源不完整：看 `provenance_findings` 里的 E_UNIT_MISSING/E_UNIT_ORDER/E_MEDIA_LOST/
E_MEDIA_ORDER/E_MEDIA_EPUB_LOST/E_FN_EPUB_LOST/E_EPUB_PARA_LOST/E_ALIGN_MD_DRIFT/
E_TOC_FLAT/E_INSERT_MISSING_FILE/E_INSERT_BAD_SOURCE 定位）/
`epubcheck_not_run`（jar 缺失，装 jar 重跑）/ `epubcheck_errors`。
G0 **长度比**类告警是 advisory 线索，不阻断放行；**术语命中**（`g0_terminology_open`）
是放行硬门，未清零 → `released_reason=terminology_open`。
**译文为空**与**语言一致性**（`language`：源译文逐字相同）同为 blocking 硬门；
经 `preprocessing/style_exemptions.csv` 登记体例豁免的命中输出 `language_exempt`
（advisory），未豁免的仍阻断。
`toc_missing`（facts 源 TOC 对账）与 `W_TOC_DEPTH` 是 warning 线索，不阻断。

## 图注与重复图（成品呈现）

- `E_CAPTION_FILENAME` / `E_CAPTION_PLACEHOLDER`（**error**）：成品的 `<img alt>`
  或 `<figcaption>` 是**文件名**（`p001-img01`、`image_1.png`）或**占位词**
  （`image`、`插图`、`TODO`）→ 不是说明文字，须改写。
- `W_IMAGE_DUPLICATE`（**warning**）：同一图片被引用多次 → 交流程裁决
  （流程门禁可对已解释的条目放行，CLI 只报事实）。

## 插入内容（inserts）审计判读

`raw/inserts/<id>.json`（插图/表格/公式描述文件，pdf-content-spec §2）存在时，
provenance 追加四码检查（E 级进放行门；W 级不阻断，但按 translation.md「inserts 补全」补齐后再复跑）：

| 码 | 级别 | 含义与处置 |
|---|---|---|
| `E_INSERT_MISSING_FILE` | error | `source.file` 指向的媒体文件不在盘——重跑该单元 ingest（`preprocess`/`init`）或从源 PDF 重新提取；确认不是被误删 |
| `E_INSERT_BAD_SOURCE` | error | `source.page` 非正整数或 `bbox` 非法——描述文件损坏，手工修正该 `<id>.json` 的 source 字段（回源 PDF 核对页号/坐标） |
| `W_INSERT_NO_DESC` | warning | `content_desc` 为空——agent 按 translation.md「inserts 补全」回源页写内容描述 |
| `W_INSERT_NO_LATEX` | warning | formula 记录 `latex` 为空——agent 手写 LaTeX 填入（依据 bbox 定位公式，图为准） |

report.json 落盘的计数字段只有 `inserts_missing_files`（进放行门）；
`inserts_total` / `inserts_no_desc` / `inserts_no_latex` 只在溯源结果对象内存在，
不落盘——需要计数时自行统计 `provenance_findings` 里的 `W_INSERT_NO_DESC` /
`W_INSERT_NO_LATEX` 条目。

## 排查

- `epubcheck errors: -1` → 校验未执行；根据 messages 检查 JAR、Java 或超时。解压完整发行包、保留 `lib/`，让 `qc.epubcheck.jar` 指向包内 JAR 后重跑。
- `epubcheck 进程退出码` / `NoClassDefFoundError` → 启动或校验失败，不是零错误；检查分发包依赖和报告里的原始诊断，不能靠重装 JRE 或只看 JAR 存在来认定可用。
- `成品不存在` → 先 `build` 或 `convert`。
- 审计发现 `W_H1_COUNT` → 内容文档标题层级问题（每章应恰一个 h1）。
- `E_ZIP_DUPLICATE` → zip 条目名重复（手改包/损坏）；从译文重新 build，不修成品。
- `E_IMG_REMOTE` → 图片外链；把图下载进 raw/media/、译文改本地引用后重 build。
- `E_TOC_COVERAGE` → spine↔nav 双向覆盖缺口（章节缺 nav 条目 / nav 幽灵条目）；
  注意**目录深度投影**（`output.nav_depth`）剔除的超深单元是预期豁免，不算缺口；
  其他情况查该单元 translation md 的标题层级，重 build。
- `E_MEDIA_EPUB_LOST` → 译文引用的图片未进成品（构建静默丢弃/渲染缺失）：
  查 `structured/raw/media/` 是否有该文件、`events.jsonl` 的 `media_dropped` 事件；
  补文件后重 build。
- `E_FN_EPUB_LOST` → 成品脚注数与译文不一致：查译文 md 的 `[^label]:` 定义是否完整、
  重 build；`W_RESIDUE` 提示字面 `[^` 残留时即定义缺失。
- `E_EPUB_PARA_LOST` → 成品缺失译文段落（正文探针 `epub_coverage` < 1.0）：
  从报告中定位 `unit:段`，核对 translation md 与 structured 后重 build。
- `E_ALIGN_MD_DRIFT` → 译文正文与对照表不一致（一侧缺内容）：以 align 为准核对并
  重写 md，重跑 `import`。
- `W_DELIVERY_AUDIT_MISSING` → 全部单元已构建但无交付记录：按
  `references/delivery.md` 执行交付审计并写 `reviews/delivery-<ts>.md`。
- `W_REPAIR_UNRESOLVED` → 语义整备有未决修复（`preprocessing/repairs.jsonl`
  中 status=unresolved）：能修则修后复跑 qa；确属存疑的在交付记录中说明。
- `W_REPAIR_STALE_UNIT` → `repairs.jsonl` 有行引用的单元已被结构重建删除：历史 `done` 行可
  忽略；`unresolved` 行请重挂现存单元。仅为 warning，不会中断 qa（issue #23）。
- `W_NAMING` → 成品文件名与 slug 前缀不符；`-o` 重命名或按 `<slug>.epub` 输出。
- `W_STRUCT_MISSING` → structured/ 源文文件缺失（被误删）；从源文件重跑该单元 ingest。
- `provenance_incomplete` →
  - `E_UNIT_MISSING`：spine 缺单元——检查该单元译文/源文是否存在、是否为空壳被跳过；
  - `E_MEDIA_LOST`/`E_MEDIA_ORDER`：译文丢图或图片顺序变了——对照 `structured/` 原文补齐；
  - 覆盖率 < 1.0：`report.json` 无逐段清单，跑 `g0` 看告警定位漏译段落；
  - `E_TOC_FLAT`：源文有层级（单元 level 链或正文子标题）但目录扁平——确认源单元 `level`
    已登记（重跑 init/preprocess）；单元内子标题锚点自 2026-09-29 起参与期望序列对账。
