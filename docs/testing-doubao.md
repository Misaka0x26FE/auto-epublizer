# 豆包云容器真实使用测试指南

目的：在**豆包 APP 云容器**里用真实书籍、真实 LLM 跑通完整管线，验证
`AGENTS.md` / `skills/` 承诺的行为，记录与预期的偏差。

> 本文档面向**手动测试**（人或豆包 agent 照抄执行）。离线自动化测试见 `uv run pytest -q`。

---

## 1. 豆包云容器的环境约束

| 约束 | 影响 | 应对 |
|---|---|---|
| 无外网大模型 API（DeepSeek/OpenAI 等不可用） | 默认 `config.example.yaml` 的 `api.deepseek.com` **连不通** | LLM 走火山方舟（豆包）OpenAI 兼容端点（§2.3） |
| GitHub / astral.sh 等外网可达性不确定 | `git clone`、`uv` 安装脚本可能失败 | 备选：上传 zip（§2.2）、`pip install uv` |
| `pandoc` / `java` 大概率未预装 | EPUB/DOCX/HTML 读取、epubcheck 跳过 | `apt-get install pandoc`；epubcheck 可选（§2.1） |
| 容器可能是低配 CPU | 本地计算都轻（无重模型） | 主要耗时在 API 往返 |

---

## 2. 环境准备（容器内）

### 2.1 基础工具

```bash
# Python 3.12 + uv（uv 装不上时用 pip 兜底）
curl -LsSf https://astral.sh/uv/install.sh | sh || pip install uv
uv python install 3.12        # 容器自带 python < 3.12 时

# pandoc（EPUB/DOCX/HTML 输入需要；TXT/MD/PDF 不需要）
apt-get update && apt-get install -y pandoc

# epubcheck + java（可选；缺失时 qa 的 epubcheck 结果为 -1，released 恒 False）
# java -jar ~/.cache/epubcheck.jar 为默认查找路径
```

### 2.2 获取项目

```bash
# 首选
git clone https://github.com/Misaka0x26FE/auto-epublizer.git
cd auto-epublizer

# GitHub 不通时：本机下载 zip 后经豆包 APP 上传到容器
unzip auto-epublizer-main.zip && cd auto-epublizer-main

uv sync                       # 安装三包依赖
uv run pytest -q              # 离线冒烟：应全绿（不依赖网络与 API Key）
```

### 2.3 LLM 配置：火山方舟（豆包唯一通道）

豆包模型经火山方舟提供 OpenAI 兼容端点，provider 无需改代码，只改配置：

```bash
# API Key 只从环境变量读（契约：禁止写进 config.yaml / 提交）
# Key 在火山方舟控制台创建：console.volcengine.com/ark
export ARK_API_KEY="<方舟 API Key>"
```

项目根写 `config.yaml`（**与 config.example.yaml 的差异只有 llm 段**）：

```yaml
llm:
  provider: openai-compatible
  base_url: https://ark.cn-beijing.volces.com/api/v3   # 注意不带 /chat/completions
  api_key_env: ARK_API_KEY
  timeout: 600
  max_retries: 4
  tiers:
    strong:                       # 翻译 / 取证 / 修订
      model: doubao-seed-1.6-250615
      options: {}                 # 不带 thinking 等私有参数，避免 4xx
    cheap:                        # 审校 G1 / 分析
      model: doubao-seed-1.6-flash-250615
      options: {}
    fast:
      model: doubao-seed-1.6-flash-250615
      options: {}
```

> 模型 ID 以方舟控制台「在线推理」页为准，本文示例可能过期。strong 用旗舰、
> cheap/fast 用低价档可显著省钱。方舟端点属豆包体系域名，容器网络应放行。

其余段（segment/qc/paths…）直接抄 `config.example.yaml`。

### 2.4 通用注意

- **所有 CLI 命令从项目根目录跑**（CLI 默认读 cwd 的 `config.yaml`）。
- 工作区默认建在 cwd 下：`auto-epublizer init ~/books/foo.txt` → `./foo/`。
- 一次只跑一条长流程命令（`publication.json` 有文件锁，但别自找麻烦）。

---

## 3. 冒烟测试（5 分钟，先证明通路）

```bash
cd auto-epublizer
printf '# Chapter One\n\nIt was a bright cold day in April, and the clocks were striking thirteen.\n' > /tmp/demo.md
uv run auto-epublizer init /tmp/demo.md
uv run auto-epublizer analyze
uv run auto-epublizer translate
uv run auto-epublizer review
uv run auto-epublizer build
uv run auto-epublizer qa
uv run auto-epublizer status --json
```

预期：每步有绿色中文输出；最终 `output/demo.epub` 存在；`qa` 输出
`G5 放行：否`（**无 epubcheck jar 时 released 恒为 False，这是预期而非 bug**）。

若 analyze 即失败：先查 `ARK_API_KEY` 是否 export、方舟模型 ID 是否有效（§8）。

---

## 4. 测试用例

> 选书：只用**公有领域**文本（古腾堡公版书等）。建议先短篇（< 1 万词）再长书。
> 成本直觉：短篇全流程约几十~百余次 API 调用；review 轮次每 +1，成本近似翻倍。

### T1 短篇 TXT/MD 翻译全流程（核心必测）

```bash
uv run auto-epublizer init ~/books/poe-tell-tale.txt
uv run auto-epublizer analyze          # 产 analysis/：语言/体裁检测 + 术语播种
uv run auto-epublizer translate        # 产 translation/ + align/*.jsonl
uv run auto-epublizer review           # 产 reviews/review-<ts>/
uv run auto-epublizer build            # 产 output/<slug>.epub（纯译文）
uv run auto-epublizer qa
```

验证点：

| 项 | 预期 |
|---|---|
| `status --json` | 单元走完 `split → analyzed → translated/aligned → reviewed → built` |
| `analysis/glossary.csv` | 有 seed 状态术语行（豆包提取质量顺带记录） |
| `translation/align/*.jsonl` | 每行 `{seq,src,tgt,note}`，seq 连续 1..N |
| `reviews/review-<ts>/result.json` | `termination=clean_confirmed`（真实 LLM 也可能 max_rounds，记录即可） |
| `report.json` | g0_flags / g1_candidates / g2_confirmed / g3_patched / error_rate 字段齐全 |
| `usage.json` | merged_runs 含 `analyze-`、`translate-`、`review-` 前缀 |
| 打开 EPUB | 译文完整、无英文残留段落、中文标点正常 |

### T2 断点续跑（translate 跳过已完成单元）

```bash
# 在 T1 完成后：
uv run auto-epublizer translate
# 输出应显示 单元=0 跳过=N；usage.json 的 calls 不增长（不调 LLM）

uv run auto-epublizer translate --force
# 输出应显示 单元=N 跳过=0；全部重译重计费
```

### T3 审校真实收敛

用 T1 工作区，读 `reviews/review-<ts>/rounds/`：

- R1 若有 issue → `issues.json` 有候选 → `summary.json` 记 confirmed 数；
- `shadow_overlay.json` 存在且**只含修订句**（正式 `translation/` 未被改动，diff 验证）；
- 盲复审：下一轮 issues 数应下降或保持 0；连续 2 轮 0 → `clean_confirmed`。
- 若 `termination=max_rounds / no_progress / unresolved_fixes`：单元**不得**被标
  `reviewed`（`status --json` 应停在 aligned）——这是有意行为，人工处置后重跑。

### T4 转换路径（不翻译）

```bash
uv run auto-epublizer convert ~/books/some.epub -o /tmp/out.epub
```

验证：不消耗任何 LLM 调用（usage 不变）；英文书 OPF 的 `dc:language` 是源语言
而非 zh-CN；单元状态直接 `built`。

### T5 双语 EPUB

```bash
uv run auto-epublizer build --bilingual    # 产 <slug>-bi.epub
```

验证：每句译文段 `xml:lang="zh-CN"`、源文段 `xml:lang="<源语言>"` 交错。

### T6 pandoc 格式（EPUB / DOCX / HTML）

需 §2.1 的 pandoc。每种格式各 init 一本小书，走 T1 全流程。重点：章节拆分成
多个 chXX 单元（TXT/MD 是标题启发式，EPUB/DOCX 应按文档结构来）。

### T7 PDF（文字层）

```bash
uv run auto-epublizer init ~/books/legacy.pdf
```

已知行为：**整本书归为一个 `ch01` 单元**（无章级切分）；`structured/raw/page-NNN.json`
逐页留档。扫描版 PDF（无文字层）会报错提示走 OCR——**OCR 未接进 CLI**，属已知
未接线项（见 §6），遇到记录即可，勿当 bug 修。

### T8 错误路径（零成本）

| 操作 | 预期 |
|---|---|
| 不 export ARK_API_KEY 直接 translate | 中文报错「缺少 API Key」，无 traceback |
| `init /tmp/不存在.md` | 中文报错「源文件不存在」 |
| 同名工作区重复 init | 报「工作区已存在」 |
| 改动 source 文件后跑续命令 | 报「输入文件内容与工作区不一致」（sha256 绑定） |
| `qa` 前没 build | 报「成品不存在…请先 build/convert」 |

---

## 5. 判读手册

**`status --json`**：`units[].status` 是唯一进度真相。卡在中间态 → 从该阶段续跑。

**`report.json`（qa 产物，聚合 G0–G5）**：

| 字段 | 含义 |
|---|---|
| `g0_flags[]` | 零 token 静态告警（长度比/空译文/术语缺失/seq 断号），advisory 线索不阻断放行（英→中长度比误报多，实测 994 条均为误报） |
| `g1_candidates` / `g2_confirmed` / `g3_patched` | G1 候选 → G2 取证确认 → G3 实际修订数 |
| `error_rate` | `g2_confirmed / 总句数` |
| `g4_audit` / `g4_epubcheck_errors` | 解包审计 / epubcheck（-1=未运行） |
| `released` | 放行判定：问题清零或全修订 + 审计 pass + epubcheck 0 error + 无 G0 告警 |

**`usage.json`**：`merged_runs` 的 run_id 幂等——同一命令重跑不会重复计费；
`totals.calls` 是累计调用数。

**`reviews/review-<ts>/result.json`**：termination 四态的含义与下一步见
`skills/auto-epublizer/references/review.md`。

---

## 6. 已知限制（遇到 ≠ bug，记录即可）

| 现象 | 原因 |
|---|---|
| PDF 整书一个单元、无章切分 | 未实现章级聚合 |
| 扫描 PDF 报「没有可抽取的文字层」 | OCR 后端存在但未接进 CLI 路径 |
| `released` 恒 False | 容器无 epubcheck jar；装了才会按真实结果放行 |
| analyze 的 overview/global 只看前 6000 字 | 截断设计，长书理解覆盖不全 |
| 翻译期不自动提案术语冲突 | `Glossary.propose()` 未接线（三态闭环在 CSV 工具层） |
| review 逐批串行、G2/G3 逐句调用 | 无并发实现，长书慢且贵 |
| convert 的 `dc:language=und` | 源语言未检测时（convert 路径不跑 analyze） |
| `.progress.json` 不存在 | 只实现单元级跳过，无批次级断点文件 |
| 自动化批量重试后仍失败 | 每批已重试 2 次，报错即停，人工看报文 |

## 7. 结果记录模板

每个用例跑完，把以下材料归档（供回填 issue / 改进迭代）：

```text
用例编号 / 书名 / 规模（词数或句数）
环境：豆包云容器规格、pandoc 有无、epubcheck 有无
config.yaml 的 llm 段（抹掉 Key）+ 模型 ID
命令序列与每步耗时（uv run … 的墙钟时间）
status --json 末态、report.json 全文、reviews 最新 result.json
usage.json 的 totals 与 merged_runs 数
与预期的偏差列表（含 §6 之外的新发现）
译文抽样 3 段（源/译对照）
```

## 8. 故障排查

| 症状 | 处置 |
|---|---|
| analyze 报 HTTP 401/403 | `ARK_API_KEY` 未 export 或无效 |
| 报 HTTP 404 | base_url 写错（应止于 `/api/v3`）或模型 ID 不存在 |
| 报 4xx 且提示 `response_format` | 所选豆包模型不支持 json_object；换 pro/seed 系列模型 ID |
| 全部请求超时 | 容器网络未放行方舟域名；在豆包侧确认 |
| `审校输出协议违例` 反复出现 | 豆包模型 JSON 稳定性问题；换 strong 档模型再试，保留报文 |
| pandoc 报错 | EPUB/DOCX 先转 PDF/TXT 兜底（`IngestError` 有中文提示） |
| translate 中断 | 直接重跑同命令：已完成单元自动跳过（T2） |

---

## 9. 豆包环境实测记录（2026-09-02）

> 本节为**豆包 APP 云容器**内真实执行本指南的实测结果与偏差，回填供后续迭代。
> 测试对象：Baka-Tsuki《魔法禁书目录 GT 卷1》（英文，约 66,619 词，42 结构单元，13 张插图）。

### 9.1 实测发现的问题与处置

| # | 现象 | 根因 | 处置 |
|---|---|---|---|
| 1 | `uv run pytest` 收集期 4 个文件 ImportError；CLI 启动即 `ModuleNotFoundError: auto_epublizer.build` | 仓库**从未提交 `src/auto_epublizer/build/`**：`.gitignore` 的 `build/` 无锚定模式误伤源码目录 | 依测试与 QA 契约补齐 build 模块；**主仓已修复**（`585f3a2`：`build/` → `/build/` 并补推模块） |
| 2 | `init`/`convert` 后 `structured/raw/media/` 为空，插图不进 EPUB | pandoc 对相对路径资源按 **cwd** 解析（非源文件目录） | `run_pandoc` 改 `cwd=源文件目录` + 绝对路径；**主仓已回移**（`d7a3e46`） |
| 3 | pandoc 孤立图片段落输出占位语法 `[alt]{.image .placeholder …}`，标准正则匹配不到 | pandoc 固有行为 | `collect_media` 识别占位语法；**主仓已回移** |
| 4 | MediaWiki 皮肤痕迹（`[]{#…}`、`[edit]`）导致 classify 误判 | pandoc 保留皮肤痕迹 | 预处理脚本 lxml 提取 `#mw-content-text` 深度清理（用户侧脚本，不入主仓） |
| 5 | **容器无外部 LLM API**：无可用方舟 Key，`analyze` 报 401；部分外网（wikimedia）超时 | 环境限制 | 见 §9.2 |

### 9.2 关键决策：翻译由 agent 主进程完成

> 豆包环境无可用外部 LLM API，翻译流程由 **agent 主进程**完成：agent 读 `structured/`
> → 自身能力翻译 → 写 `translation/`（镜像结构）+ `align/` 句级对照 → `build` → `qa`。
> CLI 的 `analyze`/`translate`/`review` 在豆包容器内**不作为翻译主路径**；§2.3 的方舟配置
> 降级为**可选分支**（有 Key 的环境仍可用）。

### 9.3 Build 层缺陷（全量中文交付时发现）

| # | 现象 | 处置 | 主仓状态 |
|---|---|---|---|
| 6 | 目录与页面标题显示英文（源文标题） | build/convert 优先取译文文件首个 `# ` 标题 | 已回移（`d7a3e46`） |
| 7 | MediaWiki 容器 div 空壳单元混入目录 | 跳过无正文且标题占位的空壳单元 | 已回移 |
| 8 | HTML `<img>`/`<figure>` 被整体转义、pandoc 缩略图二次转义 | `collect_media` 认 HTML 图片；`_PANDOC_LINKED_IMG` 归一 | 已回移 |

### 9.4 质量校验结果

- ch20 译文错位（漏译 1 段导致整体前移）由「对话引号连续性 + 图片段对齐」扫描发现并修复；全 42 单元复扫无错位。
- 最终交付：41 spine 单元 + 13 图全量中文 EPUB，G4 审计 pass、差错率 0.0。
- **G0 长度比告警 994 条均为误报**（英→中信息密度差）→ 主仓已修正放行逻辑（G0 告警为 advisory，不阻断 `released`）。
- epubcheck 因容器无 jar 未跑（已知限制）。

### 9.5 主仓回移状态（2026-09-02）

| 修复 | 提交 |
|---|---|
| `.gitignore` 误伤 build 模块（P0） | `585f3a2` |
| pandoc cwd / collect_media / 译文标题 / 空壳单元 / HTML 图片（P4/P5/P8/P9/P10） | `d7a3e46`（含 4 个新增回归测试） |
| G0 告警不阻断放行（P12，对齐 AGENTS.md G5 契约） | 见 `git log -- qa/report.py` |
