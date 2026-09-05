# 参考项目：wenyi

> **定位**：设计借鉴来源。wenyi（`trans_novel`）实现了多项 auto-epublizer 想要的能力，
> 本文记录**借鉴**（直接采用其模式）与**差异**（我们做不同/更强）。
> 面向维护本仓库的 agent 的设计契约见 `AGENTS.md`；此处是溯源参考。

参考 [wenyi](https://github.com/BigDawnGhost/wenyi)（包名 `trans-novel`）——面向长篇文本的多阶段翻译工具。

## 借鉴（直接采用其模式）

1. **数据模型**：`Document → Chapter → Segment`。Segment 是最小可翻译/可对齐单元（通常一段），带 `anchor`（EPUB 回填占位符）、`resource_href`、`cont`（超长段拆分后的续段标记，回填时并回原段）。
2. **状态与续跑（RunStore）**：
   - 同目录临时文件 + `os.replace` 原子写；
   - `source_sha256` 绑定源内容，拒绝"同名不同内容"静默复用状态；
   - 多级文件锁（run/state/event/assemble）隔离长流程与短状态读写；
   - `manifest.json` 最后原子提交，作为初始化完成标志（"派生状态先落盘，manifest 最后"）；
   - `events.jsonl` 追加式行为账本，用于审计与批次检查点恢复；
   - 导出前冻结一致快照（ExportSnapshotStore），避免读到 manifest 与章节文件的混合时刻。
3. **段级对齐策略**：一批 N 段整体发给模型，要求返回**等长 JSON 数组**；数量不符重试（align_retry_limit），仍不符则逐段兜底翻译——从结构上杜绝整段漏译。我们在此之上再加**句级对照表**（见 AGENTS.md「句级对照表」）。
4. **术语库**：SQLite 存储 + `term_conflicts` 冲突表；同 source 出现不同 target 时保留当前译法、记录候选待人工裁决；逐批按正文实际出现过滤注入 prompt；按 rowid 排序稳定前缀缓存。
5. **标点规范**：中文标点统一（PUNCT_RULE 思路）；翻译时保持源文标点/段落结构。
6. **架构边界**：`CLI → Orchestrator（薄 façade）→ 领域服务`，下层不得反向导入上层，并发只属于领域服务、结果按稳定顺序合并；用 `test_architecture_boundaries.py` 固定契约。
7. **配置与续跑**：YAML 配置（language/pipeline/qc/pdf/glossary/paths/output），同一命令幂等续跑。

## 差异（我们做不同 / 更强）

| 维度 | wenyi | auto-epublizer |
|---|---|---|
| 目标语言 | 仅简体中文 | 任意语言可配 |
| 对齐粒度 | 段级等长数组 | 段级对齐 + **句级 JSONL 对照表** |
| 结构模型 | 全部按章处理 | 显式出版物**四层结构**（frontmatter/body/backmatter + 外观） |
| 核心功能 | 翻译为主 | **转换（convert）为一等功能**，翻译可选 |
| PDF | 依赖 MinerU 外部 API | 本地 OCR（RapidOCR）+ 文字层/插图/表格/公式提取 + agent 视觉（MinerU 外部 API 最优先） |
| 工作区 | `state/<slug>/` | `publication.json` + 工作区目录 |
