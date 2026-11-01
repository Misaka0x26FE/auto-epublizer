> **中文** | [English](cover.md)

# 生成式封面（Magadan 版式）

面向**没有可用封面**的书：纯文本 / Markdown / DOCX / HTML 源本来就没有封面图；扫描件
首页图未必是封面（`preprocessing/cover.json` 未确认就不算）。这类书在书架上、锁屏上
是空白。本流程给它们一套统一排版封面：白底 + 顶部通栏色带 + 右侧竖色条 + 右对齐宋体
书名群 + 底部行书署名。

> **源封面优先**：`preprocessing/cover.json` 确认过的源封面永远不被生成封面顶替。
> 生成封面只补「确实没有封面」这一种情况。

## 什么时候做

先查三件事，再决定要不要生成（顺序不能倒）：

1. `preprocessing/cover.json` 是否存在 —— 存在=agent 已核证的源封面，**不做生成**；
2. cover 单元的 Markdown 里是否已有 `![…]` 图片引用（在 `structured/` 与 `translation/`
   两侧看），且图片文件真实存在 —— 有就不用生成；
3. 两者都没有 → 这本书缺封面，可以生成。

```bash
# 只读盘点（封面候选/确认状态都在里面）
"$AEP_CLI" evidence source --workspace <ws> --json

# 状态全景（推荐：一条就能判定这本书该不该生成封面）
"$AEP_CLI" status --workspace <ws> --json
# cover.confirmed / cover.has_image → 有源封面
# cover.generated            → 生成封面登记（file/exists/palette/stale/fonts_missing）
# cover.effective            → source | generated | null，最终会用哪一份
# cover.missing              → 只表示「没有源封面」，不要与 effective 混读
```

`cover_candidates` 是**候选**而不是结论：第一页整页图可能是书名页、插图、版权页。
只有在核对过（页号、版式、文字）之后才写 `preprocessing/cover.json` 把候选转成源封面；
核不上就走本章的生成封面，不要拿「看起来像」的图当封面。

## 生成 / 撤销

```bash
"$AEP_CLI" cover --workspace <ws>                       # 默认：indigo 色板、a5、300dpi
"$AEP_CLI" cover --workspace <ws> --palette maroon --pdf # 换色板 + 附带印刷 PDF
"$AEP_CLI" cover --workspace <ws> --json                 # 机器可读（design_digest/字体/文字）
"$AEP_CLI" cover --workspace <ws> --remove               # 撤销（源封面不受影响）
```

产物：

| 文件 | 作用 |
|---|---|
| `structured/raw/media/cover-generated.png` | 成品图；build 时按 `media/cover-generated.png` 进 EPUB |
| `preprocessing/cover-generated.json` | 登记：`design_digest`、`sha256`、字体、实际排进去的文字 |
| `structured/raw/media/cover-generated.pdf` | 仅 `--pdf` 时生成，用于印刷核对（不进 EPUB） |

生成后正常 `build`：`properties="cover-image"` 与 `<meta name="cover">` 自动写入，
事件里出现 `cover_generated_used`。**没有登记就不会凭空多出封面**——build 只会「用」
和「同步」已有登记，不会替你决定这本书该有封面。

## 设计稿 `preprocessing/cover-spec.json`（可选，agent 手写）

元数据装不下的内容（副书名、原文副书名、丛书名、书名上方小字、署名行）从这里给。
字段名固定，出现未知字段直接报错（不静默忽略）。

```json
{
  "series": "拜占庭历史文献集成",
  "lead": "前皇帝约翰尼斯 · 坎塔库泽努斯",
  "title": "史书",
  "subtitle": "伊斯兰共和国的权力焦虑",
  "original_title": "Ioannis Cantacuzeni Eximperatoris Historiarum",
  "original_subtitle": "Anxieties of Power in the Islamic Republic",
  "credits": ["[东罗马] 约翰尼斯 · 坎塔库泽努斯 著", "[德] 卢多维库斯 · 叔彭努斯 校订"],
  "imprint": "马加丹汉化组",
  "palette": "crimson",
  "size": "a5"
}
```

缺省取值的规则（不传就按这个来）：

| 字段 | 缺省来源 |
|---|---|
| `title` | `meta.title_translated` → `meta.title`；两者都空 → 报错「没有书名」 |
| `original_title` | `meta.title`（与展示书名相同则**不印**，避免同一行重复两遍） |
| `subtitle` / `original_subtitle` | 空（**不从 `description` 切句子**——那是语义猜测） |
| `credits` | `creator 著` + `translator 译`，一行一个 |
| `imprint` | 配置 `cover.imprint`（默认「马加丹汉化组」；空串=不画署名） |
| `palette` / `size` | 配置 `cover.palette` / `cover.size` |

写设计稿的三条纪律：

1. **只摆事实**：国籍、职务、校订/编译角色不确定就写「某某 著」，不要凭印象补
   「[乌克兰]」。封面是署名，不是推断。
2. **不裁句子**：副书名要么来自书名页/版权页的原文，要么空着；从简介里截半句当副书名
   会让封面替作者说话。
3. **换行用 `\n` 或数组**：换行是排版决定（哪一行断在哪里），由你决定，不要指望自动折行
   断在好看的位置。

## 配色与开本

| 色板 | 主色（通栏色带） | 侧条 |
|---|---|---|
| `indigo`（默认，最常用） | `#0D1168` | 同色 |
| `blue` 蓝 + 金边 | `#2C5F9E` | `#FECB00` |
| `maroon` 绛红 | `#612326` | 同色 |
| `purple` 墨紫 | `#4B2C65` | 同色 |
| `crimson` 朱红 | `#962311` | 同色 |
| `brown` 赭褐 | `#5A2B1B` | 同色 |
| `green` 松绿 | `#236243` | 同色 |
| `ink` 墨黑 | `#1A1A1A` | 同色 |

开本与 `pdf --size` 同一组：`a5`（148×210，默认）/ `32k` / `b5` / `16k`。
`--dpi` 默认 300（A5 → 1749×2481，EPUB 封面足够）。

## 字体

| 用途 | 缺省发现顺序 | 缺失后果 |
|---|---|---|
| 中文宋体（必需） | 思源宋体 Noto Serif CJK / Source Han Serif / 宋体 | **直接报错**（没有中文就无法排版） |
| 拉丁衬线（可选） | Nimbus Roman → Times New Roman → Liberation Serif | 原文书名改用中文字体排，输出里明说 |
| 行书署名（可选） | 志莽行书 → 马善政 → 龙藏 → 华文行楷 | 署名降级为宋体（版式位置不变），输出里明说 |

显式指定：配置 `cover.font_serif` / `cover.font_latin` / `cover.imprint_font`（文件路径）。
`"$AEP_CLI" doctor` 的 `cover-fonts` 一行给出实际选中的文件与缺失项。

> 行书字体是 OFL 授权的思源之外的第三方字库，**不随本仓库分发**。想要毛笔署名，
> 装一款（如 [Zhi Mang Xing](https://fonts.google.com/specimen/Zhi+Mang+Xing)）到系统字体目录，
> 或用 `cover.imprint_font` 指到 `.ttf`。

## 版式（不要手改比例）

比例写在 `src/auto_epublizer/cover.py` 的 `GEOM`/`TYPE`/`GAPS`/`INK`，全部实测自参考样张：

| 元素 | 比例 |
|---|---|
| 通栏色带 | 距顶 `1.35%H`，高 `5.28%H`，通栏到页右 |
| 右侧竖色条 | 左边缘 `89.7%W`，宽 `2.1%W`（右边留 `8.2%W` 白） |
| 版心 | 右边界 `88.2%W` |
| 书名群起点 | `30.99%H`（书名墨迹顶） |
| 书名 / 副书名 / 原文名 / 原文副 / 责任者 | `7.67 / 3.75 / 3.83 / 2.95 / 2.94 %W` |
| 署名 | 垂直居中于 `47%W`，墨迹顶 `91.91%H` |

改这些常数等于改版式：改完必须重跑 `tests/test_cover_render.py`（含墨迹位置对版断言）。

## 红线

1. **不得顶替源封面**：`cover.json` 已确认时生成封面不会被使用（源封面优先，命令会当场
   提示），也不要在没确认时就把候选图当封面。
2. **不猜语义**：副书名/国籍/角色没证据就空着或写中性表述。
3. **不进译文校验**：生成封面是排版产物，不参与 G0、不改变单元状态、不进 `align/`。
4. **构建期只同步不新建**：登记缺失时 build 不会自己造封面；`auto_sync` 只负责
   「元数据/设计稿改了 → 把已有封面重绘成一致的」。

## 故障排查

| 现象 / 事件 | 含义 | 处理 |
|---|---|---|
| `没有书名，无法生成封面` | `meta.title` 与 `meta.title_translated` 都空 | 先 `meta --title`，或写 `cover-spec.json` 的 `title` |
| `未知色板 / 未知开本` | 名字拼错 | 按上表取值 |
| `找不到中文字体` | 系统无 CJK 字体 | 装 `fonts-noto-cjk` 或配 `cover.font_serif` |
| `⚠ 未找到行书字库` | 行书缺失，已降级宋体 | 装行书字体或配 `cover.imprint_font`；接受降级也可以 |
| 事件 `cover_regenerated` | 元数据/设计稿变了，构建期已重绘 | 正常；确认封面文字确实跟着变了 |
| 事件 `cover_generated_stale` | 设计变了但 `cover.auto_sync=false` | 手动重跑 `cover`，或打开 `auto_sync` |
| 事件 `cover_generated_external` | 登记指向工作区标准位置之外 | 重跑 `cover`（标准位置是 `structured/raw/media/`） |
| 事件 `cover_generated_failed` | 构建期同步失败（字体/设计稿问题） | 读 `reason`，修好后重跑 `cover`；构建本身不会被阻断 |
