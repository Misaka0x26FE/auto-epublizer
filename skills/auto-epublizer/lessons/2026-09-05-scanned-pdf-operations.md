# 扫描件 PDF 实操：传统 OCR 灾难 vs MinerU（1018 页实测）

> 日期：2026-09-05　来源：豆包云端 agent 实测——《JavaScript 权威指南（第 6 版）》
> 1018 页纯扫描件（中文版，RapidOCR → 后处理 vs MinerU vlm 全量重做）。
> 状态：经验留存。MinerU 后端已入主仓库（`d16badb`，见
> `2026-09-05-scanned-pdf-mineru-first.md`）；本文是**操作经验**（分批/合并/拆分/构建粒度）。

## 触发场景

拿到扫描件 PDF（无文字层）要做 EPUB。传统 OCR 一条路走通但产物灾难，
MinerU 方案重做后质量碾压。以下判据与处置是「先想到 MinerU」的实证依据。

## 判据（传统 OCR 的灾难特征，命中即换 MinerU）

| 维度 | RapidOCR（传统） | MinerU（vlm 模型） |
|---|---|---|
| 换行/段落 | ❌ 每行独立成段、句子被拆 | ✅ 段落完整，空行分隔正确 |
| 标题层级 | ❌ 无，需手动提目录+定位 | ✅ 自动分级（216 个标题） |
| 图片提取 | ❌ 整页扫描图无法分离 | ✅ 自动提取（125 张，30 张正文引用） |
| 代码块 | ❌ 需手动识别修复 | ✅ 自动（389 个 ``` 块） |
| 表格/公式 | ❌ 无法处理 | ✅ enable_table/formula 自动识别 |
| 耗时（1018 页） | 75.5 分钟 | ~2 分钟（6 批并行） |
| 后处理 | merge_paragraphs_v3 + 目录坐标匹配 + 代码修正 + 方括号转义 | 几乎为零 |

**核心结论**：扫描件（尤其代码/技术书）直接走 MinerU，别浪费时间在传统 OCR +
后处理脚本链上——「每行独立成段 → 合并段落」的脚本反复调阈值（40→20、允许冒号）
仍是烂尾工程。

## 处置

### 1. >200 页 PDF 分批

MinerU 单任务 ≤200 页 / ≤200MB。1018 页切 6 批（1-200, 201-400, … 1001-1018）：
- 用 pymupdf 切片生成子 PDF（`doc.subset([range])` / 逐页 insert_pdf）；
- **本地上传走 `/api/v4/file-urls/batch`**（申请预签名 URL → PUT 原始字节）→ 轮询
  `GET /api/v4/extract-results/batch/{batch_id}`；
- ⚠️ 不是 `/api/v4/extract/task`（那是 URL 方式，需公网可访问地址）；
- 6 批并行提交，全部 done 后下载各 zip。

### 2. 合并 6 批结果

每批 zip 含 `full.md` + `images/`。合并 = 按页序拼接 markdown + 合并 images 目录
（重名哈希冲突按批前缀去重）+ 重写图片引用路径。

### 3. 拆分单元：别脚本化，agent 手动拆（关键教训）

MinerU 输出标题层级**可能混乱**（代码内容被误标为标题、层级不一致）。此时**不要写
「智能拆分脚本」**——脚本阈值/正则永远差一点（本次就反复翻车）。正确做法（豆包
最后一条总结）：

> **「别脚本了，你自己手动拆分不行吗」**——结构拆分是语义判断，归 agent：
> 直接读 `full.md`，按真实章节标题手动切出 `structured/<unit>.md`，逐章核对。

脚本只做确定性搬运（落盘/改 publication.json units/rel_path），「哪个是标题」
这种判断交给 agent 用理解力完成。

### 4. 构建粒度 = 单元粒度，否则丢目录导航

⚠️ 把整本 markdown 作为**单单元**构建 → EPUB 无 nav 目录（只有一页正文）。
必须按章节拆成多单元（publication.json.units 各带 `rel_path`）再 build，
nav.xhtml 才完整。做完检查 `OEBPS/nav.xhtml` 项数 = 单元数。

## 已核实：主仓库与豆包本地修复的差异

| 能力 | 主仓库（本 repo） | 豆包容器本地 |
|---|---|---|
| 围栏代码块 ` ```language ` → `<pre><code>` | ❌ 无（`html.py` 仅行内 `` ` ``） | ✅ 加过（含 `\x00` 占位符） |
| `\[` 方括号转义（防误判链接） | ❌ 无 | ✅ 加过 |
| 封面手动注入（add_cover.py） | ❌ 无 | ✅ 临时脚本 |

> 代码密集型扫描件（技术书）若要正式支持，需评估把这些能力合入主仓库——
> 尤其围栏代码块，目前缺。

## 复现 / 验证

```python
# 主仓库 MinerU 后端离线回归（真机流程已由 tests + /tmp 探测脚本覆盖）
uv run pytest -q tests/test_mineru.py
```

- 分批：切片 PDF + 并行提交 → 轮询全 done → 合并，脚本流程见豆包执行日志
  （飞书云盘「JavaScript 权威指南（第 6 版）- MinerU 版」）。
- 单单元丢 nav 回归：构造单单元 publication.json → build → 断言 nav 只有 1 项。

## 关联

- MinerU 后端契约/路由：`lessons/2026-09-05-scanned-pdf-mineru-first.md`、
  `src/auto_epublizer/ingest/mineru.py`；
- 扫描件路由表：`references/ingest.md`（MinerU 最优先，无 key 先询问用户）；
- agent 翻译工作流教训：`lessons/2026-09-05-agent-translation-workflow.md`。
