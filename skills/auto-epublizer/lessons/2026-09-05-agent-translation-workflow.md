# Agent 主进程翻译工作流：GT1/GT2/On Lisp 三轮实测教训

> 日期：2026-09-05　来源：豆包云端 agent 主进程翻译实录（魔法禁书目录 GT1/GT2、
> On Lisp 25 章）——全程未调用外部 LLM API，翻译由 agent 逐段完成。
> 状态：经验留存。

## 触发场景

用「agent 主进程手写 translation/ + align/，再 import 登记」的路径 B 翻译整本书。
本轮是这条工作流的三轮真实踩坑总结，直接指导后续 GT3 / 其他书目。

## 教训与处置

### 1. 每译 3–5 单元就 build 一次（验证格式契约）

- **坑**：GT2 连续译 47 单元才首次 build，手写译文时漏掉 `<img src>` 行，一次污染
  8 个插图单元，最后集中返工。
- **处置**：翻译中每 3–5 个单元 build 一次 + 抽查渲染，格式契约（图片段、空行、
  转义）当轮暴露。

### 2. 标题开工前一次性定稿

- **坑**：GT2 ch06 标题中途改过、ch46 手误混入 `」」`——边写边补。
- **处置**：翻译前把全部单元标题定稿进 `preprocessing/plan.md` 或术语文件；
  import 后统一核对 `publication.json.units[].title`。

### 3. 译文数据用 Write 工具写文件，别用 heredoc 内嵌 Python

- **坑**：多次踩 heredoc 内嵌 Python 的语法坑（Lisp 括号、引号、`'\'`），
  改 JSON 转义反复翻车。
- **处置**：译文列表一律用 Write 工具写 `.json`/`.py` 数据文件，再跑确定性写入器
  生成 `translation/` + `align/`。

### 4. 长句别用省略号收尾「偷懒」

- **坑**：对超长句用「她正在……」省略号收尾。部分是 Baka-Tsuki 源文本就截断，
  部分是压缩长句时偷懒——两者混在成品里无法区分。
- **处置**：压缩长句必须保住语义完整，宁可拆句；所有省略号收尾段落
  在 align 对照里标注，供审校抽查。

### 5. G0 告警不能全当噪声

- **坑**：GT2 G0 1970 条 advisory 全部忽略，但里面混着真问题（如
  `Academy City 译文缺失 学园都市` 术语未命中）；长度比告警把「漏译」和
  「正常压缩」混在一起。
- **处置**：术语告警逐条过（`g0 --unit <id>` 定位）；长度比异常抽 align 双语
  核对是否漏译；产一版 `--bilingual` 用于人工抽查。

### 6. 结构/语义判断归 agent，脚本只做确定性搬运

- **坑**：为拆分 MinerU 输出、剔除目录页垃圾反复写「智能脚本」，阈值永远差一点。
- **处置**：标题判定、章节边界、垃圾剔除这类**语义判断**直接由 agent 读源文
  手动完成；脚本只做落盘/对齐/改 status 这类确定动作（详见
  `2026-09-05-scanned-pdf-operations.md` §3）。

### 7. 术语闭环要真跑

- GT1 → GT2 用 `import --terms preprocessing/terms.csv` 继承译名表 + 新词
  seed，import 时报 csv_io 空单元格 bug（主仓库已修，`1766e7a`）。
- 冲突外置 `glossary_conflicts.jsonl` 后要人工裁决写回，不能丢着不管。

## 关联

- 翻译流程：`references/translation.md`、`references/review.md`；
- G0 判读：`references/review.md`；build 验证：`references/build.md`；
- 豆包 GT2 上游 bug 修复：`docs/plans/2026-09-05-scanned-pdf-mineru.md` 与
  `1766e7a`。
