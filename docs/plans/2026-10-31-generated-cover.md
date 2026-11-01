# 生成式封面（Magadan 版式）内置

状态：实施中（代码/测试/文档已落地，待提交号回填）。

## 背景

译作经常没有可用封面：纯文本 / Markdown / DOCX / HTML 源本来就没有封面图；扫描件首页图
未必是封面，`preprocessing/cover.json` 未确认就不能用（issue #63 已把「不猜」写死）。
结果是成品 EPUB 在书架/锁屏上空白，`provenance` 也会给出 `W_NO_COVER`。

已有的封面能力只有「识别源封面」：`preprocess/cover.py` 负责候选发现与确认登记，
build 把它写成 `properties="cover-image"`。缺的是「确实没有源封面时，给一本统一的封面」。

## 目标与边界

目标：把已在 `~/work/cover-template/` 验证过的 Magadan 版式做成 CLI 内置能力——
`auto-epublizer cover` 一条命令出图并登记，`build` 自动写 `cover-image`；再配一份
skill 参考文档让 agent 知道「什么时候生成、写什么设计稿、缺字体怎么降级」。

边界（不做的）：

- **不做图像生成/模型调用**：版式是纯排版参数，零 token（单 LLM 原则）。
- **不替代源封面**：`cover.json` 已确认时生成封面不会被使用。
- **不在 build 里凭空造封面**：没有登记就什么都不做（source 缺失 ≠ 必须生成）。
- **不做语义推断**：不从 `description` 切副书名、不凭印象补国籍/角色。

## 方案

1. **渲染后端选 PyMuPDF，不用 Chromium**。`pdf` 命令已经用浏览器渲染 HTML，但封面是
   一页纯排版：PyMuPDF 是硬依赖（`pymupdf>=1.24`）、可离线、可确定性输出，也不需要
   外部进程。代价是排版能力弱于 CSS（无 `text-wrap: balance`、无字距），因此自己实现
   断行 + 摊平（balance）与逐字宽度量测（`Font.text_length`）。
2. **版式比例沿用实测值**：参考样张 1363×1920 逐像素测出的 11 组比例（色带、
   竖色条、版心右边界、五级字号、四处墨迹间距、署名位置）直接写进
   `cover.py` 的 `GEOM/TYPE/GAPS/INK`，单位统一为页宽 W / 页高 H 的比例。
3. **墨迹锚定而不是行框锚定**：每块按「墨迹顶/底」推进，与样张的观感一致；
   实测结果与参考样张差 < 0.002H（`tests/test_cover_render.py` 断言守住）。
4. **字体发现 + 显式降级**：中文宋体必需（缺失直接报错）；拉丁衬线、行书署名缺失时
   降级并在命令输出/`doctor`/登记里明说，不假装是同一套封面。
   `fc-match` 会为不存在的家族返回「最相近」字体，故必须核对返回的家族名（否则中文会
   变豆腐块还装作正常）。
5. **登记 + 摘要**：`preprocessing/cover-generated.json` 记 `design_digest`（文字/色板/
   开本/色值的摘要）与 `sha256`。build 只「用」和「同步」：摘要一致直接复用，
   不一致按 `cover.auto_sync` 重绘，事件留痕（`cover_regenerated` 等）。
6. **状态可见**：`status --json` 的 `cover` 增加 `generated` 与 `effective`
   （source / generated / null），弱模型不必自己推断这本书有没有封面。

## 落地清单

| 层 | 文件 | 内容 |
|---|---|---|
| 领域 | `src/auto_epublizer/cover.py` | 设计解析 / 断行 / 渲染 PNG+PDF / 登记与同步 |
| 配置 | `src/auto_common/config.py` | `CoverConfig`（palette/size/dpi/imprint/字体/auto_sync） |
| 编排 | `src/auto_epublizer/orchestrator.py` | `generate_cover`/`delete_cover`；`_render_and_pack` 接入；`status` 增加封面全景 |
| CLI | `src/auto_epublizer/cli.py` | `cover`（--palette/--size/--dpi/--pdf/--out/--remove/--json） |
| 自检 | `src/auto_epublizer/doctor.py` | `cover-fonts` 一行（选中文件 + 缺失项） |
| 测试 | `tests/test_cover_render.py` | 设计解析/契约/对版/确定性/build 接线/优先级/撤销 |
| 文档 | `docs/configuration*.md`、`docs/epub-template-spec*.md`、`AGENTS*.md` | 配置段、结构层条目、工作流步骤与目录契约 |
| Skill | `skills/auto-epublizer/references/cover.*.md`、`SKILL*.md`、`manifest.json`、`taskcards/build-qa-delivery.*.md` | 何时生成 / 设计稿 / 色板开本 / 字体 / 红线 / 排错 |

## 第二轮：quarto（界栏）成为默认版式

Magadan 版式是「参考样张风格」，但作为**默认**它有两个问题：白底 + 色带/色条的版式
放在一批书里辨识度低（换的只是颜色），而且它天然属于「那一批参考书」的语汇。
因此新增第二套版式 `quarto`（中文名「界栏」）并设为默认：

- **整幅深色底面 + 反白左对齐大字书名**，一本一个色板（8 套），同批书成套但互不雷同；
- **左侧双线界栏**（书口意象）+ 书名下短横 + 斜体原文名 + 左下责任者 + 右下行书署名；
- **字号随内容自适应**：短书名放到版心 88%（≤1.45×基准），长书名收到 0.75×后折行；
  书名群撞到责任者时整块 0.9 一档缩小（≤3 档），不叠字；
- **`paper` 浅色板**给同一批里的「轻书」，骨架不变。

工程上不改生成器骨架：`CoverSpec.colors` 改为颜色角色字典（quarto: field/type/accent；
magadan: band/bar/ink/paper），色板按版式分表，`_draw` 按 `style` 分派。这样两套版式
共享设计稿、字体发现、登记/同步、CLI 与状态；切换只改一个 `--style`。
magadan 保留（不删除），用户仍可对某本书指定。

## 第三轮：可辨认下限 + 停用旧版式

真机反馈：缩到 600px 宽（EPUB 缩略图/书架）时小字糊成一团。量化后确认问题成立——
quarto 原来最小字号是 1.35% 页宽，600px 宽度下只有 8.1px，中文衬线在这个尺寸上不可读。

- **定一条硬底线**：`LEGIBILITY_EM_PX = 14`、`LEGIBILITY_REF_WIDTH_PX = 600` →
  `MIN_TYPE_FRAC = 2.333%` 页宽。字号表整体重定：丛书 2.45、小字 2.60、书名 9.6（基准）、
  副书名 3.05、原文名 2.75、原文副名 2.50、责任者 2.40、署名 2.60（%W）。
  600px 宽下最小 14.4px、最大 57.6px。
- **夹紧而不是靠自觉**：`_quarto_layout` 的 `text()` 统一 `max(size, MIN_TYPE_FRAC * W)`，
  碰撞缩放只在书名群内生效（丛书/责任者/署名不参与缩放），任何路径都压不到线下。
- **测试拦住**：`test_legibility_floor_at_600px` 断言字号表 ≥ 底线、缩放兜底也不破线。

同时**停用旧版式**：`magadan` 的渲染路径、色板表、常数、`_draw` 分派全部删除；
`cover.style`/`--style` 只接受 `quarto`，写 `magadan` 给出「旧版式已停用」的中文错误。
已用旧版式生成过的工作区保留 PNG 与记录，重跑 `cover` 会按新版式重绘。

## 关键决策

- **只保留一套版式**：色板承担「区分」职责，版式承担「统一」职责。旧版 magadan 已停用
  （两套并存会让「以后默认用哪套」永远含糊，也让字号下限难统一）。
- **默认只在显式调用时生成**：`build` 不自动给每本书加封面。理由是「没有源封面」可能是
  有意的（书本身不需要，或还在找源封面），自动生成会让「封面」变成不可见的副作用；
  需要时跑一次 `cover` 即可，之后 build 负责保持一致。
- **`--out` 只额外导出**：登记位置固定为 `structured/raw/media/`，避免「登记指向工作区
  之外」导致构建期取不到图（事件 `cover_generated_external` 就是这种情形的留痕）。
- **行书字体不分发**：OFL 允许分发，但 4MB 级别的字库进仓库不划算；改为发现 + 显式降级
  + 文档给出获取方式。想要原样署名就装一份。
- **不改 `preprocess/cover.py`**：源封面与生成封面是两条互不覆盖的路径，混在一起会让
  「未确认不当封面」这条红线变模糊。

## 验收

- `uv run pytest -q`：1043 passed / 3 skipped（含新增 19 条封面断言）。
- `uv run ruff check .`、`uv run ruff format --check .`、`python scripts/i18n.py --check`、
  `--links` 全绿。
- 端到端：`init → meta → cover-spec.json → cover → build`，EPUB 内出现
  `properties="cover-image"` + `<meta name="cover">`，媒体字节为 PNG，事件链完整。
- 优先级验证：`cover.json` 存在时 build 用源封面、生成封面不进 EPUB。
- 同步验证：改 `meta --title` 后 build 自动重绘，`design_digest` 变化、事件 `cover_regenerated`。
- 对版验证：渲染结果与参考样张的色带/书名群起点/署名位置差 < 0.002H。
