# 进度快照（自动生成，供续跑参考）

> ⚠️ **历史存档（2026-09-01）**：本文件是早期开发阶段的进度快照，内容已过时——
> 提及的 `agents/` 包、`analyze`/`translate`/`review` 命令已在「移除内部 LLM 路径」
> （`docs/plans/2026-09-04-remove-internal-llm.md`）中删除；现以 `AGENTS.md` +
> `docs/` 权威文档为准。保留仅作历史追溯。

> 更新于 2026-09-01。当前所有源码/测试尚未 git 提交（均为 `??` 未跟踪）。

## 已完成

- **convert 路径（A 阶段）完整可用**：`init`/`convert`/`status`/`version` + `qa`/`build` 命令。
  - ingest（TXT/MD/HTML/DOCX/EPUB/文字型 PDF）、structure（四层归类/页眉页脚/页码剔除）、
    build（确定性 EPUB 3 直写）、qa（解包审计 + epubcheck 跳过）。
- **翻译路径（B 阶段）主体已实现并测试通过**：
  - `glossary/`：术语三态（seed→candidate→conflict→confirmed）、CSV 权威、冲突外置、
    旧案例 `category,source,target,note` 格式读取、注入过滤（terms_in_text）、术语命中。
  - `review/g0.py`：零 token 校验（对照表完整性/长度比/句数一致/标记守恒/脚注注码/
    h1-h6 层级/段落 1:1/断字符修复/排印讹误修正/版权残句剔除/标点规范化）。
  - `analysis/`：语言/体裁检测（启发式）、文体档案 style.md、分层理解（overview/global/
    units/keypoints）、术语播种、characters.csv、回填 meta.language/genre。
  - `translation/`：切片（split_paragraph/batch）、句级对齐 align/、翻译服务。
  - `review/`（G1–G3）：审校 Agent（严格 JSON 协议）+ 取证 + 仲裁/影子修订 + 收敛状态机。
  - `genre/`：声明式文体档案（novel/academic/paper/poetry/newspaper）+ 语言指引。
  - `agents/`：analyzer/translator/reviewer/evidence/arbiter/fixer 提示词封装。
  - CLI 已暴露 `analyze`/`translate`/`review`/`build`/`qa` 命令。
- **P0/P1 缺陷已修复**：update_meta 死锁、convert 语言取源语言、NCX/OPF uid 对齐、
  report passed 语义（epubcheck 未跑不算 pass）、档位 options 透传。
- **旧真实案例测试**：`tests/fixtures/real_cases/glossary_{fleming,morris}.csv` +
  `tests/test_real_cases.py`（术语冲突、韩复榘、标记守恒、断字符、排印讹误等黄金向量）。

## 测试与质量现状

- `uv run pytest -q` → **125 passed**。
- `uv run ruff check .` → **All checks passed**；`ruff format --check .` 通过。

## 尚未完成

1. **CLI 端到端真实联调**：`analyze`/`translate`/`review`/`build`/`qa` 命令尚未跑真实
   FakeClient 之外的冒烟（当前只用 `convert` 跑过端到端）。建议补一个 `test_cli.py` 或
   手动冒烟验证命令链路。
2. **双语 EPUB**：`--bilingual` 参数已接线到 `build`（产出 `-bi.epub`），但正文只渲染单语，
   双语排版（源/译对照）未实现。
3. **review G2/G3 的证据工具**：取证 Agent 目前 `context=""`，只读工具（glossary_term/
   term_occurrences/segment_context/book_context）未接入。
4. **usage.json 合并幂等**：`merge_usage` 尚无防重（重试/续跑不得重复计费未强制）。
5. **PDF 复杂场景**：OCR（RapidOCR 可选 extra）、扫描件视觉 LLM 兜底、多栏/表格/脚注专项
   仍为占位（`ingest/ocr.py`、`pdf_reader.py` 只做文字层）。
6. **skills/ 文档（S1–S10）** 与 `THIRD_PARTY_LICENSES.md` 未写。
7. **打包发布**：`uv build` 尚未验证；EPUB 成品走 Release 未接线。

## 续跑注意事项

- **LSP 报 `pytest`/`httpx`/`fitz`/`pydantic` 无法解析是解释器未指向 venv**，忽略，以
  `uv run` 为准。
- **`import fitz` 是 pymupdf 废弃 API**，运行有 deprecation warning，暂不阻断，后续改 `import pymupdf`。
- **FakeClient 脚本是严格 FIFO**：agent 每次 `complete`/`complete_json` 消耗一条；
  测试里 `enqueue`/`enqueue_json` 顺序必须与实际调用顺序一致（analyze 会额外调
  characters、review 会额外调 evidence/fixer）。
- **ruff 规则**：select `E W F I UP B SIM`，ignore `E501 B008`；zip() 需 `strict=` 显式。
- **架构边界测试** `test_architecture_boundaries.py` 会校验依赖方向，新增模块别反向 import
  orchestrator；agents 不得 import workspace。
- **新增单元字段**：`PublicationMeta.genre`；`Unit.meta` 存 `rel_path` 与 `region`
  （`set_units` 时写入），translation/analysis/build 都依赖它定位 structured 文件。
- **epubcheck jar 缺失**：本机 `~/.cache/epubcheck.jar` 不存在，QA 相关测试按预期跳过；
  `report.passed` 现在在未跑 epubcheck 时为 False。
