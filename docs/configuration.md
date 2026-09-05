# 配置参考（config.yaml 目标 schema）

本文档汇总各环节的配置项，作为 `config.yaml` 与 `publication.json.meta.config`（配置快照）的统一形状。
实现以 `src/auto_common/config.py` 为契约，新增配置项须同步更新此处、根目录示例与测试。

**唯一 LLM 原则**：CLI 不调用任何 LLM，配置中没有 provider/密钥/档位段；
一切语义工作（理解/翻译/审校）由操作 CLI 的 agent 用自身能力完成。

```yaml
# ── 语言与文体 ───────────────────────────────────────────────
language:
  source: auto          # auto=确定性脚本启发式检测；或写死 ISO 639-1（en/ja/ru/ko/fr/de/es…）
  target: zh-CN         # 目标语言，任意可配
  genre: auto           # auto=启发式判定；或显式 novel/academic/paper/poetry/newspaper

# ── 管线开关 ────────────────────────────────────────────────
pipeline:
  bilingual: false

# ── 质量控制 ─────────────────────────────────────────────────
qc:
  length_ratio: { too_short: 0.30, too_long: 3.0 }   # G0 长度比告警阈值
  epubcheck:
    jar: "~/.cache/epubcheck.jar"
    strict: true

# ── PDF 解析 ────────────────────────────────────────────────
pdf:
  backend: auto           # auto | pymupdf | mineru
  ocr: auto               # auto | off | 强制 rapidocr
  page_dpi: 300           # 页渲染分辨率（OCR 兜底）
  mineru_effort: medium   # medium | high（MinerU 解析强度）

# ── 术语表 ──────────────────────────────────────────────────
glossary:
  storage: csv            # csv（默认）| sqlite（可选内部索引）
  scope: chapter          # chapter=只注入本章出现的词条；full=全量表

# ── 路径 ─────────────────────────────────────────────────────
paths:
  workspaces_dir: .       # 工作区根目录（每本书一个 <book-slug>/）

# ── 输出 ─────────────────────────────────────────────────────
output:
  mono: true
  bilingual: false
  about_page: true        # 书末附加"关于此翻译"说明页
  theme: standard         # 排版主题：standard | compact | spacious（docs/epub-template-spec.md §5）
                          # 仅排版微调（泛化字族/行距/缩进/对齐），无具体字体名/颜色/字号
```

## 配置快照与续跑

`init` 成功后，把本次运行的关键配置（`language.target`、`pipeline.bilingual` 等）
快照进 `publication.json.config`；续跑时优先用快照，避免配置漂移导致结果不一致。

## 密钥

本项目配置无任何密钥段（唯一 LLM = agent 本身，agent 自身的凭证与 CLI 无关）。
仅有的外部凭据是可选的 `MINERU_API_KEY` 环境变量（MinerU 外部解析 API），只从环境变量读取，
禁止写入配置文件、源码、测试或提交。
