> **中文** | [English](configuration.md)

# 配置参考（config.yaml 目标 schema）

本文档汇总各环节的配置项，作为 `config.yaml` 的统一形状。
实现以 `src/auto_common/config.py` 为契约，新增配置项须同步更新此处、根目录示例与测试。
`init` 时仅把关键项快照进 `publication.json.config`（顶层字段，只含
`target_language`，见 `workspace/models.py::ConfigSnapshot`），
并非本表全量的镜像。

**唯一 LLM 原则**：CLI 不调用任何 LLM，配置中没有 provider/密钥/档位段；
一切语义工作（理解/翻译/审校）由操作 CLI 的 agent 用自身能力完成。

```yaml
# ── 语言与文体 ───────────────────────────────────────────────
language:
  source: auto          # auto=确定性脚本启发式检测；或写死 ISO 639-1（en/ja/ru/ko/fr/de/es…）
  target: zh-CN         # 目标语言，任意可配
  genre: auto           # auto=启发式判定；或显式 novel/academic/paper/poetry/newspaper

# ── 质量控制 ─────────────────────────────────────────────────
qc:
  length_ratio: { too_short: 0.30, too_long: 3.0 }   # G0 长度比告警阈值
  epubcheck:
    jar: "~/.cache/epubcheck.jar"
    strict: true

# ── PDF 解析 ────────────────────────────────────────────────
pdf:
  backend: auto           # auto | pymupdf | mineru（auto=扫描件且 MINERU_API_KEY 存在时优先 MinerU）
  ocr: auto               # auto | off | 强制 rapidocr（新版 rapidocr 3.x，缺失时回落 1.x）
  page_dpi: 300           # 页渲染分辨率（OCR 兜底）
  mineru_effort: medium   # 未接线（MinerU v4 API 无此参数）；保留兼容旧配置
  mineru_model: pipeline  # pipeline（默认，确定性、零幻觉）| vlm（高精度，内部为 VLM）
  mineru_language: ch     # MinerU OCR 语言（PaddleOCR 语言码：ch/en/ja/…）
  mineru_batch_pages: 200 # >此页数自动分批（MinerU 单文件 ≤200 页限制；≤0 关闭）

# ── Pandoc 导入（DOCX/HTML/EPUB）────────────────────────────
pandoc:
  ast_check: false        # 试点：额外跑 `pandoc -t json` 做文本覆盖对账（按源序消费词
                          # 序列，只查丢失块，不校验标题层级/段落边界）；结果写入
                          # meta["ast_check"] 与 structured/raw/pandoc-ast-check.json；
                          # 工作区仍是可编辑的 Markdown

# ── 术语表 ──────────────────────────────────────────────────
glossary:
  storage: csv            # csv（默认，权威存储）；sqlite 未实现（预留）
  scope: chapter          # 未接线（预留；当前术语注入由 agent 按本章出现过滤）

# ── 路径 ─────────────────────────────────────────────────────
paths:
  workspaces_dir: .       # 工作区根目录（每本书一个 <book-slug>/）
  knowledge_dir: ""       # 统一术语库/知识库目录；空=默认 ~/Documents/auto-epublizer
                          # 覆盖：--dir > 环境变量 AUTO_EPUBLIZER_HOME > 本项 > 默认
  knowledge_remote: ""    # 统一库 git 远端（跨设备同步 + 公共知识库）；空=用已固化默认值
                          #   https://github.com/Misaka0x26FE/auto-epublizer-knowledge.git
                          # 覆盖：--remote > 环境变量 AUTO_EPUBLIZER_REMOTE > 本项 > 默认

# ── 生成式封面（没有源封面的书）──────────────────────────────
cover:
  enabled: true           # cover 命令可用；false=连显式生成也拒绝
  style: quarto           # quarto（界栏）/ hanze-academic（汉译学术本）；旧版 magadan 已停用
  palette: ""             # 空=按版式默认；quarto: ink|oxblood|forest|indigo|aubergine|slate|rust|paper
                          #                     hanze: ochre|forest|moss|ink|navy|plum
  format: ""              # 空=按版式默认（quarto: png / hanze: jpeg q92）；也可写 png|jpeg
  size: a5                # 与 pdf --size 同一组：a5|32k|b5|16k
  dpi: 300                # 位图分辨率（72–1200）
  imprint: "马加丹汉化组"  # 底部署名；空串=不画署名行
  imprint_font: ""        # 行书字体文件；空=自动发现（志莽行书/马善政/…）
  font_serif: ""          # 中文宋体文件；空=自动发现（思源宋体/宋体）
  font_latin: ""          # 拉丁衬线文件；空=自动发现（Nimbus Roman/Times）
  auto_sync: true         # 构建期发现封面设计摘要过期时自动重绘

# ── 输出 ─────────────────────────────────────────────────────
output:
  about_page: true        # 未接线（预留；"关于此翻译"页未实现）
  theme: standard         # 排版主题：standard | compact | spacious（docs/epub-template-spec.md §5）
                          # 仅排版微调（泛化字族/行距/缩进/对齐），无具体字体名/颜色/字号
  nav_depth: 3            # 目录最大嵌套深度（1–6，docs/epub-template-spec.md §3 投影）
                          # 超深单元不进 nav/NCX，但保留在 spine 阅读顺序与锚点中
```

## 生成式封面

`cover` 给**没有可用源封面**的书（纯文本/Markdown 源，或扫描件首页图从未被确认）出排版
封面。纯确定性排版（PyMuPDF，无 LLM、无浏览器）：文字来自 `publication.json` 元数据与
可选的、由 agent 手写的 `preprocessing/cover-spec.json`，成品登记在
`preprocessing/cover-generated.json`。

只有一套版式（`quarto`，界栏）：整幅底面 + 反白左对齐大字书名 + 左侧双线界栏 + 短横 +
斜体原文名 + 左下责任者 + 右下署名。旧版 `magadan` **已停用**：点名它会得到明确报错，
不会静默换成别的版式。

**可辨认底线**：封面按 600px 宽看（更小的分辨率不考虑），所以每个字号在该宽度下都
≥14px —— `MIN_TYPE_FRAC` = 14/600 ≈ 2.34% 页宽，由代码夹紧并由
`tests/test_cover_render.py` 拦住。改比例可以，把任何字号压到这条线下就是缺陷。

两套版式（同一批书用同一套）：

- `quarto`（默认，界栏）：整幅深底 + 反白左对齐书名 + 左侧双线界栏，一套书靠色板分家；
- `hanze-academic`（汉译学术本）：纸纹 + 双线框 + 居中四段式 + 可选意象区（`globe`/`arch`），
  主色取书。默认输出 JPEG q92，`format` 可改。

```bash
auto-epublizer cover --workspace <ws> [--palette oxblood] [--size a5] [--dpi 300] \
    [--pdf] [--json] [--format png|jpeg]
auto-epublizer cover --workspace <ws> --template hanze-academic \
    [--accent "#7A2222"] [--motif none|globe|arch] [--series "STUDIES · 229"] \
    [--subtitle "…"] [--publisher-line "BRILL · 2023"] [--note-line "内部研究译本"]
auto-epublizer cover --workspace <ws> --remove
```

必须知道的三条：

- **源封面永远优先**：`preprocessing/cover.json` 已确认时不会使用生成封面；未确认的
  首页图也不会被当成封面。
- **构建期只同步，不新建**：没有登记时 build 不会添加任何封面；有登记时才写
  `properties="cover-image"` + `<meta name="cover">`，且只在设计摘要变化时重绘
  （`auto_sync`）。
- **不做语义猜测**：缺副书名/国籍/角色就空着或写中性表述，CLI 绝不从 `description`
  里切句子。
- **字体是发现的，降级是明说的**：中文字体必需；缺拉丁衬线或行书署名时降级并写明
  （`doctor` 的 `cover-fonts` 一行）。

完整版式比例、色板、设计稿 schema 与故障排查：`skills/auto-epublizer/references/cover.zh.md`。

## 统一术语库 / 知识库

跨工作区的持久化术语表与知识库（由 agent 自行维护，避免重复考据与重复裁决），目录默认为
`~/Documents/auto-epublizer/`，本身是一个 **git 仓库**。远端地址**已固化在软件里**：

- 默认远端：`https://github.com/Misaka0x26FE/auto-epublizer-knowledge`（**公共**仓库）
  —— 常量 `auto_common.config.DEFAULT_KNOWLEDGE_REMOTE`；
- 该仓库内容采用 **[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)**：
  他人可只读订阅、按位署名、改编后再发布（须以相同许可证共享）；
- 覆盖顺序：`--remote` > 环境变量 `AUTO_EPUBLIZER_REMOTE` > `paths.knowledge_remote` >
  上述默认值（自建库 / fork 走这条）。

因为地址已固化，`knowledge init` **无需手填 `--remote`** 即可配好远端，避免出现「远端找不到 /
各设备各配一份」的访问不到问题。相关命令见 `auto-epublizer knowledge --help`：

- `knowledge path` 解析目录；`knowledge init [--remote URL] [--push]` 建骨架 + git 初始化；
- `knowledge export --workspace <ws>` 把同语对已确认术语播种到 `preprocessing/terms.csv`；
- `knowledge import --workspace <ws>` 把工作区 `analysis/glossary.csv` 合并进统一库并自动提交；
- `knowledge status` / `knowledge push` 查看统计与推送。

只读订阅（不维护只复用）：

```bash
git clone https://github.com/Misaka0x26FE/auto-epublizer-knowledge.git
```

源语言为 `auto`（`publication.json.meta.language` 未回写）时，`import`/`export` 需用
`--src-lang` 显式声明源语言，以保证统一库按语言对隔离。

## 配置快照与续跑

`init` 成功后，把本次运行的目标语言配置（`language.target`）
快照进 `publication.json.config`；续跑时优先用快照，避免配置漂移导致结果不一致。

## 密钥

本项目配置无任何密钥段（唯一 LLM = agent 本身，agent 自身的凭证与 CLI 无关）。
仅有的外部凭据是可选的 `MINERU_API_KEY` 环境变量（MinerU 外部解析 API），只从环境变量读取，
禁止写入配置文件、源码、测试或提交。
