# 计划：skills 缺口——inserts 补全与判读指引

> 状态：**规划中**（2026-09-04 立项）。前置：preprocessing-plan-v2 计划 C 已落地
> （S2–S4），`docs/pdf-content-spec.md` 已实现。

## 1. 背景与问题

PDF 内容提取管线已产出 `structured/raw/inserts/<id>.json`（插图/表格/公式描述文件），
provenance 审计也会检查 `content_desc` / `latex` 缺失（W_INSERT_NO_DESC /
W_INSERT_NO_LATEX）。但 **skills references 没有告诉下游 agent 这些事**：

1. agent 不知道要补全 inserts 语义字段（content_desc 必填、formula 手写 latex）；
2. agent 不知道**何时**补（翻译后、qa 前）、**怎么核对**（source.page/bbox 回源页）；
3. `translation.md` 没讲三类新段怎么翻译：图片引用段、`$$…$$` 公式段、markdown 表格段；
4. `qa.md` 不认识 `E_INSERT_MISSING_FILE` / `E_INSERT_BAD_SOURCE` /
   `W_INSERT_NO_DESC` / `W_INSERT_NO_LATEX` 四个新发现码。

## 2. 已定决策

- **内容描述与 LaTeX 是 agent 任务**（CLI 不调 LLM）；CLI 只做确定性检测与审计。
- **审计源切换（本计划唯一的代码改动）**：`_audit_inserts` 与 `read_inserts` 改为
  扫 `raw/inserts/*.json`（排除 `index.jsonl`，按 id 排序）——agent 只需编辑单个
  `<id>.json`；`index.jsonl` 降级为 ingest 时的汇总快照（ingest 写、审计不读）。
  理由：若审计仍以 index.jsonl 为准，agent 编辑单文件后索引失真，必然产生
  「改了描述却仍报 warning」的困惑。
- 不新增 CLI 命令；补全动作纯 agent 写文件。

## 3. 任务清单

| # | 文件 | 改动 |
|---|---|---|
| 1 | `src/auto_epublizer/ingest/inserts.py` | `read_inserts` 改扫 `*.json`（排除 `index.jsonl`）；`write_inserts` 行为不变（仍写单文件 + 索引快照） |
| 2 | `src/auto_epublizer/qa/provenance.py` | `_audit_inserts` 注释与数据源同步（经 `read_inserts` 自动切换，确认无直接读 index 处） |
| 3 | `skills/auto-epublizer/references/translation.md` | 新增小节「特殊段处理」：图片引用段原样保留（不译 alt）；`$$…$$` 公式段保留包裹、内部公式不机翻（agent 在 inserts 补 latex）；markdown 表格段翻译单元格内容、保留表格结构 |
| 4 | `skills/auto-epublizer/references/translation.md` | 新增小节「inserts 补全」：时机（翻译完成后、qa 前）；每条记录必做——读 `source.page` 回源页核对、写 `content_desc`（这个插入内容讲什么/为什么出现在此）、formula 补 `latex`；同步更新 `index.jsonl` 可选（审计不读） |
| 5 | `skills/auto-epublizer/references/qa.md` | 新增四码判读：E_INSERT_MISSING_FILE（媒体文件缺失→重跑 ingest 或从源 PDF 重提）/ E_INSERT_BAD_SOURCE（描述文件 source 非法→人工修）/ W_INSERT_NO_DESC、W_INSERT_NO_LATEX（agent 补写后复跑 qa） |
| 6 | `skills/auto-epublizer/references/ingest.md` | 「中间产物」一节补一句：index.jsonl 为汇总快照，审计以 `<id>.json` 为准 |
| 7 | 测试 | `tests/test_inserts.py`：`read_inserts` 扫描目录且排除 index.jsonl；手工只改 `<id>.json` 后 audit 不再报 W_INSERT_NO_DESC（集成进 test_provenance 或 test_inserts） |

## 4. 验收标准

- agent 按 translation.md 新小节操作后，`auto-epublizer qa` 不再出现
  W_INSERT_NO_DESC / W_INSERT_NO_LATEX（前提：书里确有 inserts 且已补全）。
- 只编辑 `<id>.json`（不动 index.jsonl）→ 审计结果即时反映。
- 全量回归通过（基线 245）+ ruff 双检。

## 5. 本轮不做

- inserts 补全的 CLI 命令化（如 `inserts lint`）
- 公式 LLM 自动转 LaTeX（pdf-content-spec §12 持续排除）
