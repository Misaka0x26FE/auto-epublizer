# 配置参考（config.yaml 目标 schema）

本文档汇总各环节的配置项，作为 `config.yaml` 与 `publication.json.meta.config`（配置快照）的统一形状。
实现时以本文件为契约，新增配置项须同步更新此处、`_DEFAULT_CONFIG`、根目录示例与测试。

```yaml
# ── 语言与文体 ───────────────────────────────────────────────
language:
  source: auto          # auto=模型检测；或写死 ISO 639-1（en/ja/ru/ko/fr/de/es…）
  target: zh-CN         # 目标语言，任意可配
  genre: auto           # auto=分析判定；或显式 novel/academic/paper/poetry/newspaper

# ── LLM ─────────────────────────────────────────────────────
llm:
  provider: deepseek    # deepseek | openai | openai-compatible | ollama | …（多 profile）
  base_url: https://api.deepseek.com
  api_key_env: DEEPSEEK_API_KEY
  timeout: 600
  max_retries: 4        # 统一重试（关闭 SDK 内置重试避免嵌套）
  tiers:                # 档位：strong/cheap/fast
    strong:
      model: deepseek-v4-pro
      options: { thinking: true }
    cheap:
      model: deepseek-v4-flash
      options: { thinking: true }
    fast:
      model: deepseek-v4-flash

# ── 切片 ─────────────────────────────────────────────────────
segment:
  max_chars_per_segment: 1200     # 单段超长按句拆的阈值（续段 cont 回并）
  max_chars_per_batch: 1800       # 一个翻译批次目标大小（≈token 估算）
  rolling_context_segments: 6     # 注入前文译文尾段数

# ── 管线开关 ────────────────────────────────────────────────
pipeline:
  translate: true
  polish: false                   # 润色（强档，最烧钱）
  review: true
  book_understanding: true        # 翻译前预扫（分析 + 逐章梗概 + 概览）
  prescan_concurrency: 4
  bilingual: false
  bilingual_order: target_first   # target_first | source_first
  bilingual_preserve_source_style: false
  annotation_alignment: true      # 脚注/尾注链接对齐

# ── 质量控制（六道关）────────────────────────────────────────
qc:
  gates: [g0, g1, g2, g3, g4, g5]
  length_ratio: { too_short: 0.30, too_long: 3.0 }
  error_rate_threshold: 0.0001    # 差错率阈值（万分之一）
  align_retry_limit: 2
  review:
    enabled: true
    concurrency: 4
    output_retries: 2
  evidence:
    enabled: true
    tier: strong
    max_rounds: 2                 # 取证最多轮数
  arbitration: { enabled: true }
  fix_loop:
    enabled: true
    max_rounds: 2                 # 影子修订最多轮数
    clean_confirmations: 2        # 连续干净确认轮数
  autofix: false                  # 是否把影子修订写回正式译文
  epubcheck:
    jar: "~/.cache/epubcheck.jar"
    strict: true

# ── PDF 解析 ────────────────────────────────────────────────
pdf:
  backend: auto           # auto | pymupdf | mineru
  ocr: auto               # auto | rapidocr | vision-llm
  page_dpi: 300           # 页渲染分辨率
  vision_llm_fallback: true   # 难页降级到多模态 LLM（页面转图片）
  mineru_effort: medium   # medium | high（hybrid 解析强度）

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

`init` 成功后，把本次运行的关键配置（`language.target`、`llm.provider`、`pipeline.bilingual`、
`qc.*` 等）快照进 `publication.json.meta.config`；续跑时优先用快照，避免配置漂移导致结果不一致。

## 密钥

API Key 只从环境变量读取（`api_key_env` 指向的变量），禁止写入配置文件、源码、测试或提交。
