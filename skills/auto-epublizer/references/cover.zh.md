> **中文** | [English](cover.md)

# 生成式封面（quarto「界栏」）

面向**没有可用封面**的书：纯文本 / Markdown / DOCX / HTML 源本来就没有封面图；扫描件
首页图未必是封面（`preprocessing/cover.json` 未确认就不算）。这类书在书架上、锁屏上
是空白。本流程给它们一套统一排版封面：`quarto`（中文名「界栏」）——整幅深色底面 +
反白左对齐大字书名 + 左侧双线界栏 + 短横 + 斜体原文名 + 左下责任者 + 右下署名。

> **旧版式已停用**：早先的 `magadan`（白底 + 色带/色条）不再提供。配置或设计稿里写
> `style: magadan` 会明确报错「已停用」，不会静默换版式。

## 可辨认底线（硬约束）

封面最窄按 **600px 宽** 看，更小的分辨率不考虑。中文衬线字身低于约 14px 就成糊字，
所以**每个字号都必须 ≥ 2.34% 页宽**（`MIN_TYPE_FRAC` = 14/600；A5 上 ≈9.8pt）。
这条线由代码夹紧（`_quarto_layout` 里的 `max(size, MIN_TYPE_FRAC * W)`）并由
`tests/test_cover_render.py` 拦住。

改版式比例、改字重、改间距都可以；**把任何字号压到这条线以下就是缺陷**。

> **源封面优先**：`preprocessing/cover.json` 确认过的源封面永远不被生成封面顶替。
> 生成封面只补「确实没有封面」这一种情况。

## 什么时候做

先查三件事，再决定要不要生成（顺序不能倒）：

1. `preprocessing/cover.json` 是否存在 —— 存在=agent 已核证的源封面，**不做生成**；
2. cover 单元的 Markdown 里是否已有 `![…]` 图片引用（`structured/` 与 `translation/`
   两侧都要看），且图片文件真实存在 —— 有就不用生成；
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
"$AEP_CLI" cover --workspace <ws>                        # 默认：quarto、ink 色板、a5、300dpi
"$AEP_CLI" cover --workspace <ws> --palette oxblood --pdf
"$AEP_CLI" cover --workspace <ws> --json                 # 机器可读（style/design_digest/字体/文字）
"$AEP_CLI" cover --workspace <ws> --remove               # 撤销（源封面不受影响）
```

产物：

| 文件 | 作用 |
|---|---|
| `structured/raw/media/cover-generated.png` | 成品图；build 时按 `media/cover-generated.png` 进 EPUB |
| `preprocessing/cover-generated.json` | 登记：`style`、`design_digest`、`sha256`、字体、实际排进去的文字 |
| `structured/raw/media/cover-generated.pdf` | 仅 `--pdf` 时生成，用于印刷核对（不进 EPUB） |

生成后正常 `build`：`properties="cover-image"` 与 `<meta name="cover">` 自动写入，
事件里出现 `cover_generated_used`。**没有登记就不会凭空多出封面**——build 只会「用」
和「同步」已有登记。

## 版式（quarto「界栏」）

设计逻辑，按重要性：

1. **整幅底面**，只有一种底色，靠**色板**分家（见下表）。同一批书摆在一起是一套，
   但每本颜色不同，不会像复制粘贴。
2. **左对齐、大字**。中文字少就更要撑住版面，所以字号按内容自适应：
   短书名放到版心的 88%（最多 1.45 倍基准），长书名收到 0.75 倍基准后折行——
   「字少就大、字多就稳」。
3. **左侧双线界栏**（一粗一细，通高）是这套版式的记号：像版框/书口，但不抢戏。
4. **标题下短横**（30% 版心宽）分隔书名与副书名；**原文名用斜体**、压到 60% 浓度，
   中文与原文一眼分层。
5. **责任者在左下、署名在右下**，页脚细线收底：署名（行书）是这套封面的落款。

### 色板（quarto）

| 色板 | 底面 | 文字 | 强调 |
|---|---|---|---|
| `ink`（默认） | `#171A20` 墨黑 | `#F5F0E6` | `#C9A227` 金 |
| `oxblood` | `#5B1B22` 绛 | `#F2EADD` | `#D8B26E` |
| `forest` | `#1D3A2F` 松绿 | `#F1EDDF` | `#CBB27A` |
| `indigo` | `#1B2A55` 靛 | `#F3EFE4` | `#C9B37E` |
| `aubergine` | `#3A2340` 紫 | `#F3ECEE` | `#D9A7A0` |
| `slate` | `#22333B` 石板 | `#F0EEE7` | `#A8C3B5` |
| `rust` | `#6B2E17` 赭 | `#F5EDDF` | `#E3C08A` |
| `paper` | `#F4EFE3` 纸（浅色版） | `#1A1A1A` | `#8A2B2B` |

浅色 `paper` 是给「同一批里的轻书」用的：纸底墨字，印得省、看着轻，骨架完全一样。

### 比例（quarto，`src/auto_epublizer/cover.py` 的 `QUARTO_GEOM`/`QUARTO_TYPE`）

| 元素 | 比例 |
|---|---|
| 版心 | 左右各留 `9.0%W`（版心宽 `82%W`） |
| 左侧界栏 | 主线 `6.2%W`，细线在其左 3.4pt；自 `6.5%H` 到 `94.5%H` |
| 丛书名基线 | `8.5%H`（前缀一个小色点） |
| 书名墨迹顶 | `25.5%H` |
| 字号（书名基准 / 副书名 / 原文名 / 原文副名 / 责任者 / 丛书名 / 署名） | `9.6 / 3.05 / 2.75 / 2.50 / 2.40 / 2.45 / 2.60 %W` |
| 600px 宽下的实际字号 | 书名 57.6px；副书名 18.3；原文名 16.5；原文副名 15.0；责任者 14.4；署名 15.6 |
| 书名下短横 | 书名底 + `3.0%H`，长 `30%W` |
| 责任者末行墨迹底 | `87.8%H` |
| 页脚细线 / 署名基线 | `90.6%H` / `94.0%H` |

书名群长到快碰上责任者时，整块按 0.90 一档自动缩排（最多三档），**绝不叠字**。

## 旧版式（已停用）

`magadan` 版式（白底 + 顶部色带 + 右侧色条 + 右对齐书名群）**已停用**：代码里不再有这条
渲染路径，配置或设计稿写 `style: magadan` 会报「未知版式 …（旧版式 magadan 已停用）」。
已在用旧版式生成过封面的工作区里，`cover-generated.json` 与 PNG 都还在，但下次重跑
`cover` 会按新版式重绘（记录里的 `style` 随之变成 `quarto`）。

## 设计稿 `preprocessing/cover-spec.json`（可选，agent 手写）

元数据装不下的内容（副书名、原文副书名、丛书名、书名上方小字、署名行）从这里给。
字段名固定，出现未知字段直接报错（不静默忽略）。

```json
{
  "style": "quarto",
  "series": "拜占庭历史文献集成",
  "lead": "前皇帝约翰尼斯 · 坎塔库泽努斯",
  "title": "史书",
  "subtitle": "伊斯兰共和国的权力焦虑",
  "original_title": "Ioannis Cantacuzeni Eximperatoris Historiarum",
  "original_subtitle": "Anxieties of Power in the Islamic Republic",
  "credits": ["[东罗马] 约翰尼斯 · 坎塔库泽努斯 著", "[德] 卢多维库斯 · 叔彭努斯 校订"],
  "imprint": "马加丹汉化组",
  "palette": "oxblood",
  "size": "a5"
}
```

缺省取值的规则（不传就按这个来）：

| 字段 | 缺省来源 |
|---|---|
| `style` | 配置 `cover.style`（默认 `quarto`）；命令行 `--style` 优先 |
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

## 开本与 dpi

`a5`（148×210，默认）/ `32k` / `b5` / `16k`，与 `pdf --size` 同一组。
`--dpi` 默认 300（A5 → 1749×2481，EPUB 封面足够）。

## 字体

| 用途 | 缺省发现顺序 | 缺失后果 |
|---|---|---|
| 中文宋体（必需） | 思源宋体 Noto Serif CJK / Source Han Serif / 宋体 | **直接报错**（没有中文就无法排版） |
| 拉丁衬线（可选） | Nimbus Roman → Times New Roman → Liberation Serif | 原文书名改用中文字体排，输出里明说 |
| 拉丁斜体（可选） | 拉丁衬线的同族斜体（`-Italic`/`-Oblique`） | quarto 的原文名退回正体（仍是拉丁衬线） |
| 行书署名（可选） | 志莽行书 → 马善政 → 龙藏 → 华文行楷 | 署名降级为宋体（位置不变），输出里明说 |

显式指定：配置 `cover.font_serif` / `cover.font_latin` / `cover.imprint_font`（文件路径）。
`"$AEP_CLI" doctor` 的 `cover-fonts` 一行给出实际选中的文件与缺失项。

> 行书字体是第三方 OFL 字库，**不随本仓库分发**。想要毛笔署名，装一款
> （如 [Zhi Mang Xing](https://fonts.google.com/specimen/Zhi+Mang+Xing)）到系统字体目录，
> 或用 `cover.imprint_font` 指到 `.ttf`。

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
| `未知版式 … 已停用` | 写了 `style: magadan`（或别的名字） | 删掉该字段；现在只有 `quarto` |
| `未知色板 / 未知开本` | 名字拼错，或用了已停用版式的色板名 | 按上表取（`crimson` 是旧版式的） |
| `找不到中文字体` | 系统无 CJK 字体 | 装 `fonts-noto-cjk` 或配 `cover.font_serif` |
| `⚠ 未找到行书字库` | 行书缺失，已降级宋体 | 装行书字体或配 `cover.imprint_font`；接受降级也可以 |
| 事件 `cover_regenerated` | 元数据/设计稿变了，构建期已重绘 | 正常；确认封面文字确实跟着变了 |
| 事件 `cover_generated_stale` | 设计变了但 `cover.auto_sync=false` | 手动重跑 `cover`，或打开 `auto_sync` |
| 事件 `cover_generated_external` | 登记指向工作区标准位置之外 | 重跑 `cover`（标准位置是 `structured/raw/media/`） |
| 事件 `cover_generated_failed` | 构建期同步失败（字体/设计稿问题） | 读 `reason`，修好后重跑 `cover`；构建本身不会被阻断 |
