# QA（epubcheck + 解包审计）

`qa` 命令对成品 EPUB 做结构 QA（G4），写 `report.json`。

## 命令

```bash
auto-epublizer qa [--epub <path>] [--workspace <dir>]
# 输出：G4 审计：pass/fail；epubcheck errors：N；passed：true/false
```

## epubcheck

- 用 `~/.cache/epubcheck.jar`（`java -jar`）校验，零 error 放行。
- jar 缺失时 `available=False`、`ran=False`、`errors=-1`，`passed=False`（未验证 ≠ 合格）。

## 解包逐项审计（离线，零 token）

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
| 双语 src/tgt 段落数不一致 | `E_BI_PAIRS` |
| 主题含具体字体名/字号 / 颜色 | `E_THEME_FONT` / `E_THEME_COLOR` |
| 封面 properties 与 meta 互证失败 | `E_COVER_META` |
| img alt 空值或缺失 / 格式兼容性差（.webp/.avif） | `W_IMG_NO_ALT` / `W_IMG_FORMAT`（告警） |
| 图片超大（>4000px）/ 超宽超高（>5:1）/ 未压缩（>2MB） | `W_IMG_LARGE` / `W_IMG_RATIO` / `W_IMG_UNCOMPRESSED`（告警） |
| EPUB 总体积超阈值（50MB） | `W_EPUB_SIZE`（告警） |

## 质量报告 `report.json`

```json
{"slug":"...","g4_audit":"pass","g4_epubcheck_errors":0,"passed":true,
 "audit":{"ok":true,"errors":0,"findings":[]},
 "epubcheck":{"available":true,"ran":true,"errors":0,"warnings":0}}
```

## 放行条件（G5）

- `g4_epubcheck_errors == 0`（epubcheck 已实际运行）
- `g4_audit == "pass"`（解包审计零 error）
- 审校 `g2_confirmed == 0` 或全部已修订
- 溯源完整（postprocessing-spec §5）：`provenance_coverage ≈ 1.0`（无翻译产物时为
  null，不适用）、`units_missing == 0`、`units_order_ok`、`media_lost == 0`、
  `toc_flat == false`、`inserts_missing_files == 0`（插图/表格/公式可回溯原始地址且文件在，
  pdf-content-spec §9）

`released` 为 False 时看 `released_reason` 判定原因：
`unresolved_confirmed`（G2 确认未修订）/ `audit_failed` / `provenance_incomplete`
（溯源不完整：看 `provenance_findings` 里的 E_UNIT_MISSING/E_UNIT_ORDER/E_MEDIA_LOST/
E_MEDIA_ORDER/E_TOC_FLAT/E_INSERT_MISSING_FILE/E_INSERT_BAD_SOURCE 定位）/
`epubcheck_not_run`（jar 缺失，装 jar 重跑）/ `epubcheck_errors`。
G0 告警（`g0_flags`）是 advisory 线索，不阻断放行；
`toc_missing`（facts 源 TOC 对账）与 `W_TOC_DEPTH` 是 warning 线索，不阻断。

## 插入内容（inserts）审计判读

`raw/inserts/<id>.json`（插图/表格/公式描述文件，pdf-content-spec §2）存在时，
provenance 追加四码检查（W 级不阻断，但按 translation.md「inserts 补全」补齐后再复跑）：

| 码 | 级别 | 含义与处置 |
|---|---|---|
| `E_INSERT_MISSING_FILE` | error | `source.file` 指向的媒体文件不在盘——重跑该单元 ingest（`preprocess`/`init`）或从源 PDF 重新提取；确认不是被误删 |
| `E_INSERT_BAD_SOURCE` | error | `source.page` 非正整数或 `bbox` 非法——描述文件损坏，手工修正该 `<id>.json` 的 source 字段（回源 PDF 核对页号/坐标） |
| `W_INSERT_NO_DESC` | warning | `content_desc` 为空——agent 按 translation.md「inserts 补全」回源页写内容描述 |
| `W_INSERT_NO_LATEX` | warning | formula 记录 `latex` 为空——agent 手写 LaTeX 填入（依据 bbox 定位公式，图为准） |

计数在 `report.json` 的溯源字段：`inserts_total` / `inserts_missing_files`（进放行门）/
`inserts_no_desc` / `inserts_no_latex`；逐条信息看 `provenance_findings`。

## 排查

- `epubcheck errors: -1` → 未装 jar；按 `doctor` 提示下载放到 `~/.cache/epubcheck.jar` 后重跑。
- `成品不存在` → 先 `build` 或 `convert`。
- 审计发现 `W_H1_COUNT` → 内容文档标题层级问题（每章应恰一个 h1）。
- `provenance_incomplete` →
  - `E_UNIT_MISSING`：spine 缺单元——检查该单元译文/源文是否存在、是否为空壳被跳过；
  - `E_MEDIA_LOST`/`E_MEDIA_ORDER`：译文丢图或图片顺序变了——对照 `structured/` 原文补齐；
  - 覆盖率 < 1.0：`report.json` 无逐段清单，跑 `g0` 看告警定位漏译段落；
  - `E_TOC_FLAT`：源文有层级但目录扁平——确认源单元 `level` 已登记（重跑 init/preprocess）。
