# 计划：移除内部 LLM 路径（唯一 LLM = agent 本身）

> 状态：**实施中**（2026-09-04 立项并当日实施）。原则已写入 `AGENTS.md`「唯一 LLM 原则」：
> CLI 只做确定性、零 token 计算；禁止新增任何 LLM API 调用；存量内部 LLM 路径全部移除。

## 已定决策

- `usage.json` token 账本**移除**（`events.jsonl` 行为账本保留）。
- review G1–G3 契约**保留**：`review/g0.py`、`review/models.py`、`review/convergence.py`
  是 agent 手写 `reviews/review-<ts>/result.json` 的 schema/常量契约；qa 继续读
  result.json 计 g1/g2/g3。删 `review/service.py`（LLM 收敛循环）。
- **保留** `analysis/detect.py`（语言/文体启发式，convert 路径用）+ `genre/` 档案 +
  `render_style_md`（确定性）；删 analyze 的 LLM 分支。
- OCR 视觉兜底 = **agent 自身**（`multimodal` 自报槽位；agent 无多模态即标记无此能力）；
  删 `llm_vision_model` 配置与探测。MinerU 保留（外部解析 API，非 LLM）。
- `SegmentConfig`（仅 LLM 切片用）删；`PipelineConfig` 仅留 `bilingual`。

## 阶段 1：删除核心 LLM 层

删 `auto_common/llm/` 全包、`auto_translator/agents/` 全包、`_parallel.py`、
`translation/service.py`、`translation/slice.py`、`review/service.py`；
`analysis/service.py` 只留 `render_style_md`；config 删 LLMConfig/TierConfig/
SegmentConfig、PipelineConfig 只留 bilingual；workspace 删 engine_profile/usage 账本；
pyproject 删 `json-repair`。

## 阶段 2：编排/CLI/doctor/facts 去 LLM 化

删 `make_client`/`analyze`/`translate`/`review`（orchestrator + cli 三命令）；
doctor 删 `probe_llm`/`_ping_endpoint`，`--ping` 只探测网络；
`_ocr_routing` 改为 传统OCR→rapidocr→MinerU→询问用户，视觉兜底移入 skills。

## 阶段 3：测试重构

删 `test_llm.py`；test_review_convergence 只留纯函数；test_translation 只留 align；
test_analysis 只留 detect/genre/style；test_cli 删三命令；test_e2e 改 agent 路径；
test_workspace 删 usage；架构边界删 agents 规则。

## 阶段 4：文档与 skills 同步

skills：translation/analysis/review/workflow/SKILL/manifest/ingest/preprocessing 改
agent 单路径；docs：configuration/translation-flow/quality-control/testing-doubao/
development-plan/agent-vs-code/pdf-parsing/README 等全面去 LLM 化；AGENTS.md 收尾。

## 阶段 5：验收

全量 pytest + ruff 双检；架构边界无 llm 模块；全库 grep 无 LLM API 调用残留。
