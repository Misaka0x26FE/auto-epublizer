# Workflow（阶段路由 + 命令总览）

## 状态路由

工作区是 `<workspaces_dir>/<book-slug>/`，权威索引是 `publication.json`。

**开工前**：`auto-epublizer doctor --json` 自检环境（pandoc/pymupdf/OCR/epubcheck/
MinerU/网络），并自报 multimodal / search（能否看图、有无搜索工具）——按
`references/ingest.md` 的能力-路由决策表选 ingest 路由。

```text
无 publication.json               -> 全新流程：先 preprocess <input>（= init + 事实收集）
有 publication.json              -> 续跑：status --json 看状态机与对账（stale / preprocessing）
  preprocessing_complete=false   -> 按 facts.md 待办完成 agent 理解产物（capabilities/plan/global/...）
  单元 status 全 built           -> 已完成，跳过对应阶段
  有 structured/ 无 analysis/ 且无 preprocessing/global.md -> agent 写 global.md（理解层）
  有 translation/ 但 status 未推进（stale） -> 运行 import 登记
  有 translation/ 无 reviews/    -> agent 写审校产物 reviews/review-<ts>/
  有 output/*.epub               -> 已封装，qa 或重新 build
```

## 标准阶段

```text
doctor（能力自检：工具链 + 自报 multimodal/search）
  -> preprocess （CLI：嗅探/元数据/TOC/体检/规模 -> preprocessing/facts.*，零 token）
  -> agent 理解 （读 facts.md 撰写 capabilities/plan/global/units/terms/risks/report；
                 analysis/*.md 也由 agent 撰写）
  -> 翻译      （agent 手写 translation/ + align/，然后 import 登记）
  -> g0        （静态校验，advisory）
  -> review    （QC G1–G3，agent 语义审校后写 reviews/review-<ts>/result.json）
  -> build     （EPUB 封装 -> output/）
  -> qa        （epubcheck + 解包审计 + G5 放行 -> report.json）
```

仅转换不翻译：

```text
convert <input>   -> 归一化 + 结构 + EPUB + QA
```

## 命令总览

```bash
# 能力自检（开工前必做；multimodal/search 由 agent 自报补填）
auto-epublizer doctor [--json] [--ping]

# 预处理（新书：init + 零 token 事实收集 → preprocessing/facts.*；已有工作区：幂等刷新）
auto-epublizer preprocess <input> [--reference <path...>] [--target zh-CN] [--workspace <dir>]
# （agent 读 facts.md 撰写 capabilities/plan/global/units/terms/risks/report，见 references/preprocessing.md）
# init <input> 等价于 preprocess 的建工作区子集（不产 facts；仍可用于仅需拆解的场景）

# agent 手写翻译后的登记入口（G0 结构校验 + 状态推进 + 术语冲突外置）
auto-epublizer import [--unit <id>] [--terms <csv>] [--workspace <dir>]

# G0 零 token 静态校验（翻译/导入后立即跑，advisory 不阻断）
auto-epublizer g0 [--unit <id>] [--workspace <dir>]

# 封装（译文缺省回退源文；--bilingual 产出 -bi.epub；--theme 选排版主题）
auto-epublizer build [--bilingual] [--theme standard|compact|spacious] [-o <out.epub>] [--workspace <dir>]

# 质检（epubcheck 零 error + 解包审计 + 溯源审计 + G5 放行判定）
auto-epublizer qa [--epub <path>] [--workspace <dir>]

# 仅转换不翻译
auto-epublizer convert <input> [--theme standard|compact|spacious] [-o <out.epub>] [--workspace <dir>]

# 进度 / 状态机 / 产物-状态对账
auto-epublizer status [--workspace <dir>] [--json]
```

## 状态机与 `status --json`

单元状态机：`pending → split → analyzed → translated → aligned → reviewed → built`。

```bash
auto-epublizer status --workspace <dir> --json
# {"slug":"book","title":"...","target_language":"zh-CN","units_total":N,
#  "units":[{"id":"ch01","kind":"chapter","title":"...","status":"built",
#            "has_translation":true,"has_align":true}, ...],
#  "has_preprocessing":true,"preprocessing_complete":false,
#  "stale":[{"id":"preprocessing","status":"facts_written","reason":"preprocessing_plan_missing"}]}
```

- `stale`：agent 手写了 translation/align 但尚未 `import` 登记，或预处理 facts 已产但
  理解产物（capabilities/global）未完成——状态机与产物脱节的信号。
- agent 手写产物必须跑 `import` 状态才会推进；`import` 会校验
  seq 连续性/空译文（阻断）与长度比/术语命中（告警）。

## 故障排查

| 现象 | 处理 |
|---|---|
| `工作区尚未初始化` | 先 `init`；或 `--workspace` 指向错误的目录 |
| `输入文件内容与工作区不一致` | 源文件被替换；用原始源文件或重新 `init` |
| `成品不存在：...请先 build/convert` | `qa` 前先 `build` |
| `epubcheck errors: -1` | 未装 epubcheck jar（`~/.cache/epubcheck.jar`）；G4 审计仍可跑，`released_reason=epubcheck_not_run` |
| `导入失败`（import 阻断） | 按 `--unit` 输出的错误清单修 align（断号/空译文/缺文件）后重试 |
| `pandoc` 缺失 | `doctor` 已提示；装 pandoc 或先把文件转为 PDF/TXT/MD |
| 扫描 PDF 处理不了 | 按 OCR 路由（`doctor` + multimodal 自报）：tesseract/ocrmypdf → rapidocr（`[ocr]` extra）→ MinerU API → 询问用户；可看图则自行视觉兜底难页 |
| 单元状态停在中间态 / stale | `status --json` 定位，从对应阶段续跑（手写产物跑 `import`） |
