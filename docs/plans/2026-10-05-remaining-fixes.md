# 2026-10-05 现场核对与剩余修复计划（#30 / #31 / #14 / #10-B3）

状态：规划中

## 0. 目的

上一轮把 4 个开放 PR 全部整合、并修复了 12 个 issue，`main` 现剩 4 个开放 issue
（#30 布局提案 / #31 PDF 结构 / #14 页边界证据 / #10 现场报告收尾），0 个开放 PR。

本文件在动手前先核对「世界情况」——**代码现状 + 真实工作区现场**——再据此为剩余项制定
可执行计划。**不预设一次性做完**：每项独立评估风险与验收。

## 1. 现场核对

### 1.1 代码/测试现状

- `main` = 4 个 PR（#17/#27/#11/#15）已 cherry-pick 整合 + 12 个 issue 修复；
- `uv run pytest -q` → **445 passed**；ruff / i18n 全绿；
- 开放 issue 4（#30/#31/#14/#10），开放 PR 0。

### 1.2 真实工作区现场（本机 `~/work/translate/`）

| 目录 | `publication.json` schema | 判定 |
|---|---|---|
| `slave-labor-nazi-camps/book/` | `0.1.0`（本工具） | ✅ 真 auto-epublizer 工作区：33 单元全 `built`，`released=ok`，1 条 `W_TOC_MISSING` |
| `fleming-china/` | 顶层旧 translation-skill 布局（`split/`、`GLOSSARY.csv`、`_progress`）+ 其下 `book/` 为 `epub-builder/v1alpha1` | ⚠️ 遗留/他项目 |
| `history-of-jaipur/book/` | `epub-builder/v1alpha1` | ⚠️ 他项目（非本工具） |
| 其余 8 个目录 | 无 `publication.json` | ⚠️ 未开工/他项目 |

**关键结论**：

1. 本机只有 **1 个** 真 auto-epublizer 工作区；#30/#32 里「26 个工作区」的数据来自**另一台
   机器**（`/home/agent/work/translate/`），本机不可直接复核；
2. 真实布局是 **`<base>/<slug>/book/publication.json`**（多一层 `book/`，且目录名多为书名
   而非 slug）——与 #30 §2 的「`workspaces/<slug>/`」不完全一致；
3. 工作区之间**异构共存**（旧 translation-skill、`epub-builder`、本工具三种 schema 同目录）。

### 1.3 现场暴露的新缺陷（本计划新增 R0）

**R0**：`auto-epublizer status --all --workspace ~/work/translate` 返回 **`[]`**——因为
`status_all` 只扫 `<base>/*/publication.json`，而真实工作区在 `<base>/<slug>/book/` 下。
即 #32 的实现对公司真实布局不成立。

## 2. 修复计划（R0–R4）

| 项 | 目标 | 改动点 | 验收 | 风险 |
|---|---|---|---|---|
| **R0** | `status --all` 支持嵌套布局 + schema 过滤 | `orchestrator.status_all`：递归（限深 2–3 层）查找 `publication.json`；跳过 `schema_version` 非本工具的目录 | 对 `~/work/translate` 能列出 `slave-labor-nazi-camps`，跳过 `epub-builder/*`；回归造临时嵌套树 | 低 |
| **R1** | #14 页边界证据导出 | 新增 `auto-epublizer evidence breaks [--workspace]`：读 `structured/raw/page-NNN.json`，逐页找被删页眉/分隔线，输出 `breaks.jsonl`（unit, page, kind, prev_line, next_line, prev_block, next_block, candidate）；只**定位证据**，不做语义合并（`repair.zh.md` 禁自动并段） | 在 `matla`/真实 PDF 上产出候选清单；纯函数、零 token、可离线单测 | 中（契约设计） |
| **R2** | #31 PDF 标题识别加固 | `ingest/pdf_reader._is_chapter_heading` / `_aggregate_by_toc`：① 纯数字/章节号行与相邻标题合并；② 标题截断到首个合理边界；③ 前置页（标题/版权/页码密集）归 `frontmatter` | 以 On Lisp（公开文字层 PDF，1 MB）为 fixture：无 4 字符纯数字伪单元、标题完整、前置页归属正确；全套无回归 | **高**（启发式易误伤，须真实样本回归） |
| **R3** | #30 §4.1/.mobi、§4.4 `--progress` | §4.1：`.azw3/.mobi` 经 `ebook-convert`（本机已装）转 EPUB 再入库；§4.4：长任务每 N 页输出 stderr 进度 | §4.1 仅在有 calibre 时启用并给出清晰降级；§4.4 进度可观测 | 中（§4.1 离线测试难覆盖，用 mock/skip） |
| **R4** | #30 §1–§3 布局模板固化（可选） | 落 `template/work-root/` 骨架 + `references/workflow`（已在 c6742a4 落文档） | 维护者确认后 | 低（但属产品决策） |

## 3. 顺序与依赖

```text
R0（先做：修复现场暴露的真实缺陷，小且独立）
  → R1（#14 证据导出；确定性、可单测，价值最高）
  → R2（#31 结构识别；需 R1/粒度信号辅助定位，风险最高放后面）
  → R3（#30 §4.1/§4.4；低优先）
  → R4（模板固化；待维护者确认）
```

- R0/R1 相互独立，可并行；R2 依赖真实样本（On Lisp 已在本机，可直接用）；
- #10 的收尾依赖 R1（B3=#14），R1 完成即可关闭 #10。

## 4. 验收总纲

- 每项：新增最小失败回归 → 实现 → `uv run pytest -q` + ruff + i18n 全绿；
- R1：`breaks.jsonl` 契约写入 `references/repair.md`（+zh）并 `--finalize`；
- R2：On Lisp fixture 断言（单元数/无纯数字伪单元/标题非截断/前置页 region）；
- R0：对真实 `~/work/translate` 目录的集成断言（可跳过缺失环境）。

## 5. 风险与边界

- **R2 最高风险**：PDF 标题启发式改动会影响所有 PDF 书；必须先建 fixture 再改，逐条对比；
- **R1 契约**：`breaks.jsonl` 字段一旦发布即对外，需先定契约（与 `repairs.jsonl` 并列）；
- **不引入 LLM**：全部 R0–R4 为确定性代码（单 LLM 原则）；
- **本机现场有限**：只有 1 个真工作区，R1/R2 的验证以公开书（On Lisp）与 `matla` 沙箱为主。
