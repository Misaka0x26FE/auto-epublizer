# The Great Gatsby · 翻译与电子书工作区

> 本目录由 `auto-epublizer init` 生成，是一个可被 `git` 管理、可上传 GitHub 长期维护与协作的
> 文献处理仓库模板。复制本目录并替换为你的书名/作者即可开箱。

- **书名**：The Great Gatsby（了不起的盖茨比）
- **作者**：F. Scott Fitzgerald
- **源语言 / 目标语言**：en → zh-CN
- **源文件**：`source/the-great-gatsby.epub`（SHA-256 见 `publication.json`）
- **成品**：`output/the-great-gatsby-fitzgerald.epub`（纯译文）/ `-bi.epub`（双语）

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

## 如何复现

```bash
auto-epublizer init source/the-great-gatsby.epub --reference <可选>
auto-epublizer analyze
auto-epublizer translate --target zh-CN
auto-epublizer review
auto-epublizer build
auto-epublizer qa
```

## 许可与版权

仅处理**公有领域**或**已获授权**的文本；不得上传受版权保护的正文、私密书籍或含敏感信息的
`state/` 目录。发布前确认版权与署名。
