# 文体优化（总览与索引）

不同文体对分析、翻译、术语、审校的要求差异很大。本目录为每种文体提供一篇专门文档；本文档是
总览与索引。

## 核心框架：两个正交维度

```text
文体档案（genre profile，随体裁变）  ×  语言特定指引（langprofile，随源语言变）
```

- **文体档案**决定：分析维度（analyze 提取什么）、术语类型白名单（抽什么词）、翻译指引（怎么译）、
  审校侧重（reviewer 什么算问题）、辅文侧重（哪些辅文重要）。
- **语言指引**决定：翻译时的语言陷阱（敬称、代词性别、时态、拟声、汉字词…），与文体无关。

两者叠加，组成注入 prompt 的文体指引。文体档案是**声明式数据**，按 `genre` 键加载，新增体裁不改代码。

## 文体文档索引

| 文体 | 文档 | 核心特殊优化 |
|---|---|---|
| 小说叙事 | [novel.md](genres/novel.md) | 角色圣经 + source-only 术语 + 敬称策略 + 对话辨识度 + 前文滚动衔接 |
| 学术专著 | [academic.md](genres/academic.md) | 学科术语统一 + 索引边码 + 缩略语加注 + 参考文献不译 + 数字单位规范 |
| 论文（IMRaD） | [paper.md](genres/paper.md) | IMRaD 结构 + 结果/讨论分离 + 缩略语加注 + 可复现 |
| 诗歌/散文 | [poetry.md](genres/poetry.md) | 行结构保留 + 意象优先 + 韵脚策略声明 |
| 报刊/期刊 | [newspaper.md](genres/newspaper.md) | 按版面组织 + 标题导语化 + 事实/引语准确 + 客观转达 |

## 语言特定指引（langprofile，独立于文体）

| 源语言 | 要点 |
|---|---|
| `ja` | 敬称策略；第一人称（私/僕/俺/あたし）定语域与代词；拟声拟态词按中文习惯；汉字词≠中文词勿照搬；振假名〘〙仅供判读严禁写入 |
| `en` | 无敬称，Mr./Ms./Sir 全书统一；据姓名性别与上下文定"他/她/它"；时态/关系从句/长句按中文重组，被动酌情转主动；专名音译 |
| `ru/ko/fr/de/es…` | 忠实传意，符合中文目标语言表达习惯 |

## 文体档案统一 schema

`publication.json.meta.genre` 声明/判定体裁，`analysis/style.md` 存文体档案：

```yaml
genre: novel                # novel | academic | paper | poetry | newspaper | ...
detect: auto                # auto | 显式声明
style: { … }                # 文体分析维度
characters: […]             # 小说：角色圣经
term_types: […]             # 该文体术语类型白名单
review_focus: […]           # 审校 issue 类型加权
translation_rules: […]      # 文体翻译指引
```

## 注入顺序（沿用"静态→动态"）

system 放文体指引 + 语言指引 + 标点规则；user 放风格/角色圣经 → 全书概览 → 章梗概 → 重点 →
术语子集 → 前文译文 → 待译正文。
