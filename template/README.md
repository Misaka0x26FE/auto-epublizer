# The Great Gatsby · 翻译与电子书工作区

> 本目录由 `auto-epublizer init` 生成，是一个可被 `git` 管理、可上传 GitHub 长期维护与协作的
> 文献处理仓库模板。复制本目录并替换为你的书名/作者即可开箱。

- **书名**：The Great Gatsby（了不起的盖茨比）
- **作者**：F. Scott Fitzgerald
- **源语言 / 目标语言**：en → zh-CN
- **源文件**：`source/the-great-gatsby.epub`（SHA-256 见 `publication.json`）
- **成品**：`output/the-great-gatsby-fitzgerald.epub`

## 目录说明

| 目录 | 职责 |
|---|---|
| `source/` | 待处理文件（原样，绝不改动） |
| `structured/` | 四层结构拆分的源文 + `raw/` 处理中间产物（持久化供审查） |
| `analysis/` | agent 理解：概要 / 全局 / 每单元 / 重点 / 术语表 / 人物表 |
| `translation/` | 译文（镜像 structured）+ `align/` 句级对照表 |
| `references/` | 参考：`user/` 用户上传 + `web/` 网络检索 + `index.jsonl` |
| `reviews/` | 审校运行记录 `review-<ts>/` |
| `output/` | 成品 EPUB（二进制，走 Release） |
| `preprocessing/` | CLI facts + agent 预处理产物；可选 `terminology_exemptions.csv` 按单元记录有据术语豁免 |

## 如何复现

```bash
auto-epublizer preprocess source/the-great-gatsby.epub --target zh-CN  # init + 零 token 事实
# agent 依 preprocessing/facts.md 写理解产物与 analysis/，先完成必要语义整备
# 有注书在翻译前：notes candidates → 逐条核证并写源注 JSON/原位标记 → notes register
# 随后逐单元翻译并写 align；无注书不要捏造注释
auto-epublizer import                 # 登记 agent 手写的 translation/ + align/（G0 结构校验）
auto-epublizer g0                     # 静态校验（术语命中/守恒类）
auto-epublizer import --reviewed      # 审校通过后登记
auto-epublizer build                  # 封装标准 EPUB
auto-epublizer qa                     # epubcheck + 解包审计 + 放行报告
```

> 翻译与审校由**操作本 CLI 的 agent** 完成（本项目遵循单 LLM 原则，CLI 自身不做 LLM 调用）；
> **没有** `analyze` / `translate` / `review` 子命令。

术语豁免模板只含表头 `unit,source,reason`，没有示例豁免。仅在核对原题/引文等保留依据后，
填写精确单元 id、规范术语源词与非空理由；误译须修复，不得批量豁免。该表新增、修改或删除
均使旧 QA 摘要失效，须重新 QA；import、g0 和 QA 均保留带理由的非阻断记录。

## 许可与版权

- **版权风险由用户负责**：本项目**不审查处理对象（源文件、插图等）是否包含版权风险**，
  也不代用户做权属判断；请自行确认对处理对象的使用、翻译与再分发许可。
- **工作区全量入库且默认私有**：处理过程产生的工作目录（含 `source/` 源文件与全部
  处理产物）整体纳入 git 仓库，默认作为**私有仓库**上传到指定的 git 托管平台
  （默认 GitHub）。
- **转公开需显式声明**：如需将仓库转为公开，须由用户自行处理或显式声明授权，
  本项目不代为判断。
- 发布（分发成品）前仍按 `skills/auto-epublizer/references/publishing.md` 的 gate
  做隐私扫描（凭据/本地路径/个人数据）与署名记录。
