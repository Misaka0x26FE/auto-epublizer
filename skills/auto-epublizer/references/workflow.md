# Workflow（阶段路由 + 命令总览）

## 状态路由

工作区是 `<workspaces_dir>/<book-slug>/`，权威索引是 `publication.json`。

```text
无 publication.json               -> 全新流程：先 init
有 publication.json              -> 续跑：status --json 看单元状态机
  单元 status 全 built           -> 已完成，跳过对应阶段
  有 structured/ 无 analysis/    -> 从 analyze 续跑
  有 analysis/ 无 translation/   -> 从 translate 续跑
  有 translation/ 无 reviews/    -> 从 review 续跑
  有 output/*.epub               -> 已封装，qa 或重新 build
```

## 标准阶段

```text
init  （建工作区 + 归一化 + 四层结构拆分）
  -> analyze   （分层理解 + 术语播种 + 语言/体裁检测）
  -> translate （切片翻译 + 句级对齐 align/）
  -> review    （QC G0–G3，影子修订收敛）
  -> build     （EPUB 封装 -> output/）
  -> qa        （epubcheck + 解包审计 -> report.json）
```

仅转换不翻译（跳过 analyze/translate/review）：

```text
convert <input>   -> 归一化 + 结构 + EPUB + QA
```

## 命令总览

```bash
# 建工作区并解析（source/ -> structured/ 四层结构；--reference 导入参考材料）
auto-epublizer init <input> [--reference <path...>] [--target zh-CN] [--workspace <dir>]

# 分层理解（analysis/overview|global|units|keypoints + 术语播种 + 语言/体裁检测）
auto-epublizer analyze [--workspace <dir>]

# 翻译（读 analysis/，写 translation/ + align/ 句级对照表）
auto-epublizer translate [--target zh-CN] [--bilingual] [--workspace <dir>]

# 审校（G0–G3，只读影子修订，写 reviews/review-<ts>/ + report.json）
auto-epublizer review [--workspace <dir>]

# 封装（译文缺省回退源文；--bilingual 产出 -bi.epub）
auto-epublizer build [--bilingual] [-o <out.epub>] [--workspace <dir>]

# 质检（epubcheck 零 error + 解包审计）
auto-epublizer qa [--epub <path>] [--workspace <dir>]

# 仅转换不翻译
auto-epublizer convert <input> [-o <out.epub>] [--workspace <dir>]

# 进度 / 状态机
auto-epublizer status [--workspace <dir>] [--json]
```

## 状态机与 `status --json`

单元状态机：`pending → split → analyzed → translated → aligned → reviewed → built`。

```bash
auto-epublizer status --workspace <dir> --json
# {"slug":"book","title":"...","target_language":"zh-CN","units_total":N,
#  "units":[{"id":"ch01","kind":"chapter","title":"...","status":"built"}, ...]}
```

- 已完成单元（`built`/`reviewed`）可安全跳过；改术语/理解/解析后须覆盖受影响单元重跑后续阶段。
- 每个 `translate` 批次、`review` 轮次都是断点；中断后同命令续跑。

## 故障排查

| 现象 | 处理 |
|---|---|
| `工作区尚未初始化` | 先 `init`；或 `--workspace` 指向错误的目录 |
| `输入文件内容与工作区不一致` | 源文件被替换；用原始源文件或重新 `init` |
| `成品不存在：...请先 build/convert` | `qa` 前先 `build` |
| `epubcheck errors: -1` | 未装 epubcheck jar（`~/.cache/epubcheck.jar`）；G4 审计仍可跑 |
| `缺少 API Key` | 设置环境变量（见 `config.example.yaml` 的 `llm.api_key_env`） |
| 单元状态停在中间态 | `status --json` 定位，从对应阶段续跑 |
