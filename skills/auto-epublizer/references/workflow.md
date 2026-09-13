# Workflow（阶段路由 + 命令总览）

## 状态路由

工作区是 `<workspaces_dir>/<book-slug>/`，权威索引是 `publication.json`。

**开工前**：`auto-epublizer doctor --json` 自检环境（pandoc/pymupdf/OCR/epubcheck/
MinerU/网络），并自报 multimodal / search（能否看图、有无搜索工具）——按
`references/ingest.md` 的能力-路由决策表选 ingest 路由。

```text
无 publication.json               -> 全新流程：先 preprocess <input>（= init + 事实收集）
有 publication.json              -> 续跑：status --json 看状态机与对账（stale / preprocessing）
  preprocessing_complete=false   -> 按 facts.md 待办完成 agent 理解产物（todo.md 逐细节清单 + capabilities/plan/global/...）
  单元 status 全 built           -> 已完成，跳过对应阶段
  有 structured/ 无 analysis/ 且无 preprocessing/global.md -> agent 写 global.md（理解层）
  有 translation/ 但 status 未推进（stale） -> 运行 import 登记
  有 translation/ 无 reviews/    -> agent 写审校产物 reviews/review-<ts>/
  有 output/*.epub               -> 已封装，qa 或重新 build
```

遇到**源站/脏源/边界情况**（如 Baka-Tsuki 插图段不渲染、epubcheck 离线装 jar、
MediaWiki 卷导航垃圾混入 structured），先查 `lessons/` 目录——里面是真实工作沉淀的
「判据 + 处置 + 验证」，命中即按它处理；未命中再自行排查。

## 标准阶段

```text
doctor（能力自检：工具链 + 自报 multimodal/search）
  -> preprocess （CLI：嗅探/元数据/TOC/体检/规模 -> preprocessing/facts.*，零 token）
  -> agent 理解 （读 facts.md 撰写 capabilities/plan/global/units/terms/risks/report；
                 analysis/*.md 也由 agent 撰写）
  -> 语义整备 （可选/条件：facts 可疑信号触发；OCR/扫描件路径必做——按
                 references/repair.md 对照 raw 证据修复 structured/ 并写
                 preprocessing/repairs.jsonl 留痕）
  -> 翻译      （agent 手写 translation/ + align/，然后 import 登记）
  -> g0        （静态校验：术语命中=真实缺陷须清零；长度比=advisory）
  -> review    （QC G1–G3，agent 语义审校后写 reviews/review-<ts>/result.json）
  -> build     （EPUB 封装 -> output/）
  -> qa        （epubcheck + 解包审计 + G5 放行 -> report.json）
  -> delivery  （交付审计：按 references/delivery.md 全量校验 + 写
                 reviews/delivery-<ts>.md；强制，全部单元 built 后 qa 会以
                 W_DELIVERY_AUDIT_MISSING 提示）
```

仅转换不翻译：

```text
convert <input>   -> 归一化 + 结构 + EPUB + QA
```

## 交付收尾：反馈贡献（可选）

交付完成后，询问用户：**是否将本次工作中遇到的技术问题与建议解决方案作为 PR
提交到项目 GitHub 仓库（`Misaka0x26FE/auto-epublizer`）？** 用户同意时：

1. **检查 GitHub 登录状态**：`gh auth status`。已登录 → 以该账户（即用户账户）
   名义继续；未登录 → 请用户先登录自己的 GitHub 账户（`gh auth login`，走浏览器/
   设备码流程），不要向用户索要密码或 token，登录成功后再继续。
2. **整理内容**（只含技术问题与解决方案，参照 `lessons/` 的判据/处置/验证三段式）：
   - 纯经验沉淀 → 写 `skills/auto-epublizer/lessons/<日期>-<主题>.md` 并同步
     `lessons/README.md` 索引；
   - 若工作过程中修复了代码缺陷 → 带上对应回归测试与文档同步，遵循仓库规范
     （`uv run pytest -q` + `ruff check .` + `ruff format --check .`，单主题一提交）。
3. **以用户账户名义提交 PR**：
   - fork（`gh repo fork Misaka0x26FE/auto-epublizer --clone=false`）或用户有权限时
     直接建分支；从最新 `main` 开主题分支（如 `feedback/<主题>`）；
   - Conventional Commits 提交 → push → `gh pr create --repo Misaka0x26FE/auto-epublizer`
     指向主仓库 `main`。
4. **隐私提醒（必须说）**：提交内容不得包含用户书籍的源文件、译文、元数据或任何
   个人信息；PR 标题/正文/改动先给用户过目确认后再提交。

## 命令总览

```bash
# 能力自检（开工前必做；multimodal/search 由 agent 自报补填）
auto-epublizer doctor [--json] [--ping]

# 预处理（新书：init + 零 token 事实收集 → preprocessing/facts.*；已有工作区：幂等刷新）
auto-epublizer preprocess <input> [--reference <path...>] [--target zh-CN] [--workspace <dir>]
# （agent 读 facts.md 撰写 capabilities/plan/global/units/terms/risks/report，见 references/preprocessing.md）
# init <input> 等价于 preprocess 的建工作区子集（不产 facts；仍可用于仅需拆解的场景）

# agent 手写翻译后的登记入口（G0 结构校验 + 状态推进 + 术语冲突外置）
auto-epublizer meta [--translator X] [--publisher P] [--date D] [--rights R] [--workspace <dir>]
auto-epublizer import [--unit <id>] [--terms <csv>] [--reviewed] [--workspace <dir>]

# G0 零 token 静态校验（翻译/导入后立即跑；术语命中是放行硬门，长度比 advisory）
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
| 扫描 PDF 处理不了 | 按 OCR 路由（`doctor` + multimodal 自报）：**MinerU 外部 API 最优先**（无 key 先询问用户）→ 传统 OCR（tesseract/ocrmypdf）/rapidocr + agent 逐页阅读兜底 |
| 单元状态停在中间态 / stale | `status --json` 定位，从对应阶段续跑（手写产物跑 `import`） |
