# 2026-09-13 Issue 清理：协作者实测缺陷修复与 MinerU 分批

状态：规划中

## 背景与来源

协作者 Misaka0x272F 在《俄国铁路史》（352 页扫描件）等真实书目上用本 CLI 完成翻译
交付，复盘后向仓库提交 4 个 issue（#3–#6，2026-09-13）。本计划统一核查并修复：

- 2 个 g0 假阳性缺陷（术语命中 / 脚注守恒）——直接干扰硬门与 G5 放行判定；
- 1 个 MinerU 大文件功能缺口（>200 页被 API 拒绝）；
- 1 个经核查**已被交付审计计划覆盖**（验证后回帖关闭）。

### 核查结论（以当前 main 实测为准）

| Issue | 现象 | 当前 main 核查 | 定性 |
|---|---|---|---|
| #6 | QA 媒体/脚注守恒对象为 align，成品缺 38/72 图无法发现 | **主体已修**：`md_align_drift`（import 阻断 + provenance error finding）覆盖「body↔align 一致性」；`E_MEDIA_EPUB_LOST`/`E_FN_EPUB_LOST`/`E_EPUB_PARA_LOST` + `epub_coverage` 覆盖「structured/translation 引用 ↔ EPUB 实际包含」对账；content_desc 子项 = `W_INSERT_NO_DESC`（W 级）+ delivery.md 强制逐项处置 | 已修，验证后关闭 |
| #4 | 术语命中 target 未 NFKC 归一化，含全角括号术语全部误报 | **确认存在**：`terms.py` 对 src/tgt 归一化，但 target/candidates 未归一化即参与匹配；源侧同病（全角形式术语假阴性） | 真实缺陷 |
| #3 | g0 脚注守恒正则误报年份/句首数字（每章 10~30 条） | **部分成立**：4 位年份被 `(?!\d)` 回溯排除（issue 列出的 1881/1888/1900 等样例不复现）；实测 `。82个`/`。95年`/`。46%` 等 **1–3 位数字紧跟中文/百分号**仍误报 | 真实缺陷（范围修正） |
| #5 | MinerU 单文件 ≤200 页限制，>200 页扫描件被拒 | **未实现**：`mineru.py` 单文件单批；pymupdf 已是依赖（可切页）；`PDFConfig` 已有 `mineru_*` 配置位 | 待实现 |

> Issue #3 回帖口径（必须写清）：4 位年份样例在当前 main 已不复现（`(?!\d)` 排除）；
> 本次修复的是 1–3 位数字紧跟中文/百分号的误报类。协作者本地若仍见年份误报，
> 请先核对克隆版本（本仓库该正则自 e28eecd 未变更，但其本地 clone 时间早于
> 交付审计系列提交，`/g0` 行为可能不同）。

## 已定决策（用户确认）

| # | 决策 | 理由 |
|---|---|---|
| D1 | #3 排除集 = 中文 + `%` + `％` | 真注码是句子最后 token，后不可能紧跟百分号；零误伤风险 |
| D2 | #5 顺序逐批解析（非单 batch 多文件） | 复用 100% 已验证的单文件 API 契约，风险最低；代价 = 轮询时间 ×批数（可接受） |
| D3 | #6 验证后回帖关闭；content_desc 维持 W 级 + 交付审计强制项 | 与 delivery-audit D6 一致；语义补全属 agent 工作（唯一 LLM 原则） |

## S1 #4：术语命中 NFKC 归一化（小）

**根因**（`src/auto_translator/glossary/terms.py`）：

- `terminology_hits`：`:49-50` 对 src/tgt 归一化，但 `:58` `target = entry.target`、
  `:61-62` candidates（source/aliases）**未归一化**即参与 `_boundary_pattern` 匹配；
- `terms_in_text`：`:42` candidates 同样未归一化 vs `normalize(text)`（源侧假阴性）。

**修复**：上述三处统一 `normalize()`；归一化后为空的 target/candidate 跳过。
`_boundary_pattern` 的 CJK 判定不受 NFKC 影响（归一化不改变 CJK 字符）。

**测试**（`tests/test_glossary.py`，先写失败用例）：

1. 反例：术语 target 含全角括号（如 `交通（道路）部`），译文用 NFKC 形式
   `交通(道路)部` → `terminology_hits` 为空；
2. 正例：同上术语，译文真正缺失 → 恰好 1 条 hit；
3. `terms_in_text`：正文含全角形式（源侧）→ 经归一化后命中；
4. aliases 含全角形式同理。

## S2 #3：句末注码正则排除中文/百分号（小）

**根因**（`src/auto_translator/review/g0.py:38`）：

```python
_FOOTNOTE_REF_RE = re.compile(r"(?<!\d)[.!?…。！？](\d{1,3})(?!\d)")
```

`。82个`→命中 `82`、`。95年`→`95`、`。46%`→`46`（实测）。

**修复**：追加负向前瞻（D1）：

```python
_FOOTNOTE_REF_RE = re.compile(r"(?<!\d)[.!?…。！？](\d{1,3})(?!\d)(?![\u4e00-\u9fff%％])")
```

同步更新正则上方注释（说明排除类与理由）。

**测试**（`tests/test_review.py`，先写失败用例）：

- FP（计 0）：`……。82个车站`、`……。95年起义`、`……。46%的燃料`、`……。50％占比`；
- TP（计 1 不变）：`句子。1`（行尾）、`句子。12 下一段`（空格）、`style.5 next`、
  `style.1The`（英文粘连——`T` 不在排除集，保持命中）；
- 守恒接线：含 FP 数字的 src/tgt 对，`g0_unit_flags` 不产 `footnote` flag；
  真缺注码仍报。

**残余风险（接受，写入测试注释）**：真注码紧跟 CJK 的粘连形态（如 `句。1下一句`
无空格）双侧同时漏计；概率低，且相比每章 10~30 条假阳性收益远大于风险。

## S3 #5：MinerU >200 页自动分批（中，新功能）

**现状**：`mineru.py` 只有 `MineruClient.parse_file`（单文件单批）；
`read_mineru` 单次解析。MinerU API 单文件 ≤200 页。

**接口设计**（`src/auto_epublizer/ingest/mineru.py`）：

1. `MineruClient.parse_bytes(name: str, data: bytes, *, model_version, language, is_ocr=True)`
   ——从 `parse_file` 拆出的核心；`parse_file` 读字节后委托（现有测试全绿）。
2. `_pdf_page_count(path) -> int`：pymupdf（`import pymupdf as fitz`，与 pdf_reader 一致）。
3. `_split_pdf(path, pages_per_part) -> list[tuple[str, bytes]]`：返回
   `[(f"{stem}-part{i:02d}.pdf", bytes)]`；pymupdf `insert_pdf` 按页范围切。
4. `_merge_results(results, page_counts) -> MineruParseResult`（纯函数）：
   - `page_idx += 本批起始偏移`（全局页序连续）；
   - `img_path` 与 `images` 字典 key 同步加 `b{part}/` 前缀（防跨批 `images/0.jpg` 撞名），
     `_segments_from_content_list` 按重映射后的 key 查图；
   - `markdown` 以 `\n\n` 拼接；header/footer 已在单批内跳过。
5. `read_mineru(..., batch_pages: int = 200)`：`_pdf_page_count > batch_pages > 0` 时
   切批 → 顺序 `parse_bytes` → `_merge_results`；否则走原路径；任一批失败 →
   `MineruError` 带批次号（中文提示）。
6. 落盘：`raw/mineru/content_list.json` + `full.md` 写**合并后**结果（与不分批同名同语义，
   审查对账的 ground truth）；insert id 经 `next_insert_id(records, 全局页, type)` 天然全局唯一。

**配置与接线**：

- `src/auto_common/config.py` `PDFConfig`：新增 `mineru_batch_pages: int = 200`
  （≤0 = 不分批，仍受 API 200 页限制）；
- `ingest/load.py::load_document` 与 `orchestrator.prepare_structure` 透传
  `cfg.pdf.mineru_batch_pages`。

**测试**（`tests/test_mineru.py`）：

1. `_merge_results` 纯函数：页偏移、图片前缀重映射、markdown 拼接；
2. `_split_pdf`：pymupdf 生成 5 页 PDF，batch=2 → 3 份、页数 `[2,2,1]`；
3. e2e（MockTransport）：模拟 3 批各自 `file-urls/batch` + PUT + poll + zip，
   断言全局页序连续、图片零丢失、insert id 全局唯一、`raw/mineru/` 落合并结果；
4. 不分批回归：页数 ≤ batch_pages 仍单批（现有测试即覆盖）。

**文档同步**：`docs/configuration.md` 新增键；`skills/auto-epublizer/references/ingest.md`
MinerU 节注明「>200 页自动分批（`pdf.mineru_batch_pages`），页序/图片/块完整拼接」。

## S4 #6：验证后回帖关闭（零代码）

1. 跑相关测试确认主体已修：`tests/test_import.py`（drift 正反例）、
   `tests/test_provenance.py`（含 `test_silent_media_drop_blocks_via_epub_reconciliation`）；
   确认 `references/delivery.md` 存在且含 inserts 描述处置项。
2. `gh issue comment 6`：指向 4 个修复提交（`7041126` md↔align drift / `ece1790`
   EPUB 呈现对账 / `c9ae1ba` delivery.md + `W_DELIVERY_AUDIT_MISSING` / `fb71fb3`
   收尾与 lesson `2026-09-13-delivery-integrity.md`），说明 content_desc 按 D6：
   `W_INSERT_NO_DESC` 保持 W 级 + 交付清单强制「逐项补全或显式接受并记理由」；
   自动补全属 agent 语义工作（唯一 LLM 原则）。
3. `gh issue close 6`。

## 文档同步清单（实施时一并提交）

- `docs/configuration.md`：`pdf.mineru_batch_pages`；
- `skills/auto-epublizer/references/ingest.md`：自动分批说明；
- `skills/auto-epublizer/references/invariants.md`：如 #3/#4 涉及校验描述则微调
  （术语命中/脚注守恒定义不变，仅假阳性修复——预计无需改）；
- 本计划 + `docs/plans/README.md` 索引 + 状态回写；
- 验证记录含可复用经验时沉淀 `skills/auto-epublizer/lessons/`（评估项：
  「g0 启发式正则的两类假阳性与排除集设计」）。

## 提交、验证与 issue 工作流

| 批次 | 提交信息（Conventional Commits） | 内容 |
|---|---|---|
| C1 | `docs: 立项 issue 清理计划（#3–#6）` | 本文件 + README 索引 |
| C2 | `fix(glossary): 术语命中对 target/candidates 做 NFKC 归一化 (#4)` | S1 |
| C3 | `fix(g0): 句末注码排除紧跟中文/百分号的数字误报 (#3)` | S2 |
| C4 | `feat(mineru): >200 页扫描件自动分批解析 (#5)` | S3 |
| C5 | `docs: issue 清理收尾（验证记录 + 状态回写）` | 回写本文件 |

- 每批提交前：`uv run pytest -q` + `uv run ruff check .` + `uv run ruff format --check .` 全绿；
- 每批推送（GitHub + Gitee 双推）；
- C2/C3/C4 推送后逐 issue 回帖（修复提交号 + 使用注意）并 close；#6 按 S4 回帖 close；
- 全程零 LLM 调用、测试离线确定（MockTransport + pymupdf 生成的临时 PDF）。

## 验证记录

（实施完成后回写：测试数、ruff 结果、各提交号、issue 回帖/关闭结果。）

## 实施偏差

（实施中出现与计划的偏差时回写本节；无偏差则记「无」。）
