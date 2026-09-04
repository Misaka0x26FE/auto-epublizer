# 质量控制流程设计（auto-epublizer）

本文档把 README 里的"六道关"落成可实现的规格：每道关的**触发时机、输入、输出、失败动作、
成本、数据契约、验收阈值与收敛条件**。范围边界沿用：只负责**交付质量**（准确 / 完整 /
一致 / 规范 / 结构正确 / 可复现），不做价值观 / 政治 / 思想性判断。

## 0. 设计原则

1. **成本分层**：先零 token，再 cheap 档，再 strong 档，按需升级——绝不让 cheap 能挡的错烧 strong 的钱。
2. **角色分离**：翻译 / 审校 / 取证 / 修订 / 仲裁各自独立，审校不直接改译文，修订走影子 overlay。
3. **证据驱动，非投票**：候选问题先取证再裁决；术语库、参考、影子修订都是"待核验材料"。
4. **确定性 + 可续跑 + 可审计**：结果按稳定原文序合并；每道关有检查点；全部产物落盘可回看。

## 1. 六道关总览

```text
translator(强档)                 G0 零 token 静态校验 ── 不过则退回重译/标记
      │                                     │
      ▼                                     ▼
  align/ 句级对照表                G1 逐批双语审校(cheap) ── 报 issue，不直接改
                                            │
                                            ▼
                                G2 证据取证复核(strong) ── 确认/驳回候选
                                            │
                                            ▼
                                G3 冲突仲裁 + 影子修订 + 盲复审(收敛状态机)
                                            │
                                            ▼
                                      build → EPUB
                                            │
                                            ▼
                                G4 EPUB 结构 QA(epubcheck + 解包审计)
                                            │
                                            ▼
                                G5 交付验收(质量报告 + 发布清单)
```

| 关 | 名称 | 时机 | 成本 | 可跳过 | 产出 |
|---|---|---|---|---|---|
| G0 | 零 token 静态校验 | 每个单元翻译后立即 | 0 | 否 | 静态告警列表 |
| G1 | 逐批双语审校 | 全书翻译完成后 | cheap | 否（默认） | `issues`（候选） |
| G2 | 证据取证复核 | G1 报 issue 后 | strong，按需 | 是 | `issues`（确认/驳回） |
| G3 | 冲突仲裁 + 影子修订 + 盲复审 | G2 后循环 | strong | 是 | `patches` + 收敛判定 |
| G4 | EPUB 结构 QA | `build` 后 | 0（epubcheck 本地） | 否 | 结构审计报告 |
| G5 | 交付验收 | 发布前 | 0 | 否 | `report.json` + 发布清单 |

## 2. 关卡详细规格

### G0 零 token 静态校验（纯函数，翻译后立即）

输入：`translation/align/<id>.jsonl` + `structured/<id>.md` + `analysis/glossary.csv`。

| 检查项 | 规则 | 失败动作 |
|---|---|---|
| 对照表完整性 | 每句原文有 `src↔tgt` 映射，`seq` 连续 1..N 无缺号、无重复 | 标记单元 `aligned_failed`，退回重译该段 |
| 句数一致 | 原文句数 == 译句句数（允许 `note` 声明的拆/并句） | 同上 |
| 长度比 | `len(tgt)/len(src)` 落在 `[0.30, 3.0]`；译文非空 | 告警，交 G1 复核 |
| 术语命中 | 正文出现 glossary `source` 时，译文包含对应 `target`（NFKC 归一化 + 词边界） | 告警，交 G1 定责 |
| 勘误留痕 | 句 src 命中已知排印讹误先例（IDG→IDF 等）→ align `note` 前缀 `corr:` | 留痕，不告警 |

> 实现状态：以上五项已接线（`g0_unit_flags` / `annotate_correction_notes`）。
> 规格中的「标点规范化」（`normalize_punctuation`）与「残留产物」（HTML 注释/占位符/
> 页眉页码）属确定性纯函数，分别在构建期样式清理与 G4 解包审计（`E_RESIDUE`/`W_RESIDUE`）
> 承担；源语言字符残留属语义判断，归 G1（agent 任务）。

G0 不烧 token、不出"裁决"，只出**确定性告警**，作为 G1 的输入线索。

### G1 逐批双语审校（cheap 档 Reviewer）

输入：源句 + 译句（来自 `align/` 对照表）、相关术语子集、G0 告警。

- 问题类型：`missing`（漏译）/ `added`（增译）/ `mistranslation`（误译）/ `terminology`（术语违例）/ `pronoun`（人称/性别错误）。
- **宁缺毋滥**：合理语序调整、自然意译、风格润色不算问题，拿不准不报。
- **严格 JSON 协议**：对象末尾必须依次 `reviewed_segments`（= 本批句数）与 `complete:true`；违例整批重试（缩小输入再试），防止坏字段被静默当作"无问题"。
- 输出：`issues` 候选列表（`verdict` 未定），交 G2。

### G2 证据取证复核（strong 档 Agent Loop）

输入：G1 候选问题。

- 只读工具：`glossary_term`（按术语查库）、`term_occurrences`（术语全书命中位置）、`segment_context`（段落附近上下文）、`book_context`（风格/概览/章梗概）。
- 单轮最多 4 个请求、最多 `max_evidence_rounds` 轮取证；**禁止假设未取得的上下文**。
- 每个候选判 `confirmed` / `dismissed`，附 `evidence_refs`。
- 术语库、references、影子修订是**待核验材料**，互相矛盾时驳回候选或保留基线。

### G3 冲突仲裁 + 影子修订 + 盲复审（收敛状态机）

对 G2 确认的问题，分三步循环：

1. **冲突仲裁**：跨块对同一术语/人称/固定表达给出矛盾建议时，Arbiter 终局裁决 `suggested`（取其一）或 `unresolved`（证据不足）。
2. **影子修订**：Fixer 在内存 overlay 上生成"最小修改的完整单句替换"（回显 `segment_ref`、`before_hash`、全部 `issue_ids`，末尾 `complete:true`）。正式 `translation/`、`glossary`、`publication.json` 全程只读。
3. **盲复审**：下一轮审校**不传旧问题说明**，只读修订后的影子译文，防止"按说明书打勾"。

收敛判定（见 §5）：

- 连续 `clean_confirmations` 轮无 issue → `clean_confirmed`；
- 超过轮数上限 → `max_rounds`；
- 影子译文整体摘要（SHA-256）出现 A↔B 循环 → `no_progress`；
- Fixer 失败积压且复审不再报 → `unresolved_fixes`。

Autofix（可选）：先写可恢复索引 `reviews/<ts>/autofix/index.json`，再更新正式 `align/` 的 `tgt`；其余历史保留在 Review 目录。

### G4 EPUB 结构 QA（build 后，本地）

- `epubcheck` 零 error（jar 缓存于 `~/.cache`）。
- 解包逐项审计（`qa/audit.py`，已实现）：
  - `mimetype` 首位、未压缩、内容恰为 `application/epub+zip`；
  - `META-INF/container.xml` 良构、指向 OPF；
  - manifest 每个 href 可解析、spine 每个 idref 存在；
  - nav / NCX / landmarks / 内容文档 img src 引用全部可解析（悬空检测）；
  - 危险 URL（javascript:/data:）注入拦截；
  - 主题层边界：style.css 无具体字体名/字号（`E_THEME_FONT`）、无颜色（`E_THEME_COLOR`）；
  - 封面 meta 互证：`properties="cover-image"` ↔ `<meta name="cover">`（`E_COVER_META`）；
  - 每个内容文档 `xml:lang` 正确、恰好一个 `h1`、无跳级（`E_HEADING_SKIP`）；
  - 残留：HTML 注释（`E_RESIDUE`）、markdown/pandoc 标记（`W_RESIDUE`）；
  - 内部锚点可解析（`E_ANCHOR`，含脚注 noteref→footnote）+ 脚注回链（`E_FN_BACKLINK`）；
  - 双语 src/tgt 段落数成对（`E_BI_PAIRS`）；
  - 媒体：alt 空值（`W_IMG_NO_ALT`）、格式兼容（`W_IMG_FORMAT`）、超大/超宽超高/未压缩
    （`W_IMG_LARGE`/`W_IMG_RATIO`/`W_IMG_UNCOMPRESSED`）、EPUB 总体积（`W_EPUB_SIZE`）；
  - DC 元数据缺失提示（`W_META_INCOMPLETE`）。
- 溯源审计（`qa/provenance.py`，postprocessing-spec §2）：三边对账、媒体溯源、逐段覆盖率、
  目录层级——见 G5。

### G5 交付验收（发布前）

- 汇总 G0–G4 + 溯源审计生成 `report.json`：
  ```json
  {
    "slug": "…", "epub_path": "…",
    "g0_flags": [], "g1_candidates": 0, "g2_confirmed": 0,
    "g3_patched": 0, "g3_termination": "clean_confirmed", "g3_rounds": 2,
    "g4_epubcheck_errors": 0, "g4_audit": "pass",
    "error_rate": 0.0,
    "provenance_coverage": 1.0, "units_missing": 0, "units_order_ok": true,
    "media_lost": 0, "toc_missing": [], "toc_flat": false,
    "provenance_findings": [],
    "released": true, "released_reason": "ok"
  }
  ```
- 发布清单核对：成品命名（`<slug>.epub` / `<slug>-bi.epub`，`W_NAMING`）、元数据（DC 项齐全）、
  封面、版权署名、许可。
- **放行条件**（对齐 docs/postprocessing-spec.md §5）：`g2_confirmed == 0` 或全部已修订；
  `g4_epubcheck_errors == 0`；`g4_audit == "pass"`；溯源完整（`provenance_coverage ≈ 1.0`
  （无翻译产物为 null）、三边对账/媒体溯源零缺失、`toc_flat == false`）。
  G0 告警为 advisory，不阻断（英→中长度比天然偏低，实测大量误报）。

## 3. 数据契约（落 `reviews/`）

### Issue（G1 产出、G2 定谳）

```json
{
  "issue_id": "r1-ch01-0003",
  "chapter": "ch01",
  "index": 3,
  "seq": [12, 13],
  "type": "terminology",
  "detail": "old sport 未用已确认译法「老兄」",
  "suggestion": "改为「老兄」",
  "evidence_refs": ["glossary:old sport"],
  "consistency": null,
  "verdict": "confirmed",
  "status": "open"
}
```

`seq` 定位到 `align/<id>.jsonl` 的具体句，是双语定位、修回、统计差错率的锚点。

### Patch（G3 影子修订）

```json
{
  "patch_id": "p-ch01-0003-1",
  "chapter": "ch01",
  "index": 3,
  "before_hash": "sha256 当前译文",
  "after": "修订后的完整译句",
  "issue_ids": ["r1-ch01-0003"],
  "review_round": 1,
  "status": "provisional"
}
```

### Review 运行目录

```text
reviews/review-<ts>/
├── metadata.json         # 内容摘要 + 审校配置指纹 + 术语表指纹（复用判定）
├── checkpoint.json       # 轮级检查点（续跑）
├── rounds/<n>/{issues,patches,summary}.json
├── conflicts.json        # 冲突仲裁记录
├── shadow_overlay.json   # 影子译文覆盖
├── autofix/index.json    # 可选：正式写回索引
├── usage.json            # 本轮 token 增量
└── result.json           # 终局：issue_count / termination / usage
```

## 4. 验收阈值（默认，可配置）

| 指标 | 阈值 | 含义 |
|---|---|---|
| 长度比 | `0.30 ≤ ratio ≤ 3.0` | 过小疑漏译、过大疑失控 |
| 空译文 | 禁止 | 直接退回 |
| 句数一致 | 严格相等（含 `note` 声明例外） | 对齐完整性 |
| 差错率 | `confirmed_issues / 总句数 ≤ 1e-4`（万分之一） | 对齐出版差错率惯例 |
| epubcheck | 0 error | 结构合法性 |
| 术语命中 | 术语违例数 → 0（仲裁后） | 全书一致性 |

## 5. 收敛状态机（G3）

```text
start ──▶ R1 审校 ──▶ 无 issue ──▶ clean_streak++ ──▶ 达 clean_confirmations ──▶ clean_confirmed
   │                        │
   │                        └─▶ 有 issue ──▶ 仲裁+影子修订 ──▶ R2 盲审（重复，且 clean_streak=0）
   │
   └─▶ 轮数超限 ──▶ max_rounds
   └─▶ 摘要 SHA-256 循环 ──▶ no_progress
   └─▶ Fixer 失败积压且复审不再报 ──▶ unresolved_fixes
```

轮数上限 = `(fix_max_rounds + 1) × clean_confirmations`（默认 `3 × 2 = 6`）。

## 6. 配置项（`config` 的 `qc` 段）

```yaml
qc:
  gates: [g0, g1, g2, g3, g4, g5]
  length_ratio: { too_short: 0.30, too_long: 3.0 }
  error_rate_threshold: 0.0001
  align_retry_limit: 2            # 翻译对齐失败重试次数
  review: { enabled: true, concurrency: 4, output_retries: 2 }
  evidence: { enabled: true, tier: strong, max_rounds: 2 }
  arbitration: { enabled: true }
  fix_loop: { enabled: true, max_rounds: 2, clean_confirmations: 2 }
  autofix: false
  epubcheck: { jar: "~/.cache/epubcheck.jar", strict: true }
```

## 7. 与工作区目录的对应

| QC 产物 | 落点 |
|---|---|
| 句级对照表 | `translation/align/<id>.jsonl` |
| 静态告警 | `reviews/review-<ts>/g0_flags.json` |
| 审校问题/补丁/仲裁 | `reviews/review-<ts>/` |
| 质量报告 | `report.json`（工作区根） |
| 行为/用量账本 | `events.jsonl`、`usage.json` |

## 8. 与传统三审三校的对应

| 传统 | 本项目关卡 |
|---|---|
| 校异同 | G0（确定性对照 + 对照表完整性） |
| 校是非 | G1 + G2（报 issue、取证裁决，不直接改） |
| 初审 | G1（基础错误） |
| 复审 | G2 + G3 仲裁（一致 + 存疑） |
| 编辑加工 | G3 影子修订（只读、留痕、疑难上报） |
| 核红 | G3 盲复审 + 振荡检测 |
| 三校一读 | G3 连续 clean 确认 + G4 结构审计 |
| 付印清样 | G4 + G5（零 error 放行） |
