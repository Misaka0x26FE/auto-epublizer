> **中文** | [English](work-root.md)

# 长期工作区（多书工作根）

每次首次使用 Skill 都先建立**用户选定的工作根**，即使只处理一本书。Skill 只是文档，
安装 Skill **不会安装 Python 引擎**。源码固定放在 `<工作根>/auto-epublizer/`；
书籍放在同级 `inbox/`、`sources/`、`workspaces/`，绝不放进源码仓库。

## 首次使用与安全续用（先于 version / doctor）

需要 Git、`uv` 及可用的 Python 3.12（`uv` 可按项目声明准备解释器）。先与用户确定工作根，
将下面唯一占位路径替换为其选定的**绝对路径**，在 Bash 中整体执行。不从 Skill 安装目录、
当前碰巧所在的 Git 仓库或 Gitee 镜像推断源码位置。停止时保留现场，请用户处理；
不得 reset、stash、clean、切换分支、改 origin 或覆盖文件来绕过护栏。

```bash
set -eu
export AEP_ROOT='/absolute/user-selected-root'
unset AEP_CLI
(
  set -eu
  fail() { printf '%s\n' "$1" >&2; exit 1; }
  case "$AEP_ROOT" in /*) ;; *) fail 'Work root must be absolute.' ;; esac
  command -v git >/dev/null
  command -v uv >/dev/null
  mkdir -p -- "$AEP_ROOT"
  root=$(cd -- "$AEP_ROOT" && pwd -P)
  checkout="$root/auto-epublizer"
  official='https://github.com/Misaka0x26FE/auto-epublizer.git'
  if [ ! -e "$checkout" ] && [ ! -L "$checkout" ]; then
    git clone --origin origin --branch main --single-branch "$official" "$checkout"
  fi
  [ -d "$checkout" ] && [ ! -L "$checkout" ] || fail 'Checkout is not a regular directory.'
  [ "$(git -C "$checkout" rev-parse --show-toplevel)" = "$checkout" ] ||
    fail 'Wrong repository root.'
  [ "$(git -C "$checkout" remote get-url --all origin)" = "$official" ] &&
    [ "$(git -C "$checkout" remote get-url --push --all origin)" = "$official" ] ||
    fail 'Origin must be exactly the official GitHub repository.'
  [ "$(git -C "$checkout" symbolic-ref -q HEAD)" = refs/heads/main ] ||
    fail 'Checkout must already be on main.'
  [ "$(git -C "$checkout" rev-parse --symbolic-full-name '@{upstream}')" = refs/remotes/origin/main ] ||
    fail 'Main must track origin/main.'
  [ -f "$checkout/pyproject.toml" ] && [ -f "$checkout/skills/auto-epublizer/manifest.json" ] ||
    fail 'Project files are missing.'
  dirty=$(git -C "$checkout" status --porcelain=v1 --untracked-files=all)
  [ -z "$dirty" ] ||
    fail 'Tracked or untracked changes found; nothing fetched or overwritten.'
  git -C "$checkout" merge-base --is-ancestor HEAD refs/remotes/origin/main ||
    fail 'Local main is ahead or divergent; stop without changing HEAD.'
  git -C "$checkout" fetch --no-tags origin refs/heads/main:refs/remotes/origin/main
  git -C "$checkout" merge-base --is-ancestor HEAD refs/remotes/origin/main ||
    fail 'Local main is ahead or divergent after fetch; stop.'
  git -C "$checkout" merge --ff-only refs/remotes/origin/main
  UV_PROJECT_ENVIRONMENT="$checkout/.venv" uv sync --project "$checkout" --locked
  "$checkout/.venv/bin/auto-epublizer" work-root "$root"
)
export AEP_CLI="$AEP_ROOT/auto-epublizer/.venv/bin/auto-epublizer"
```

源码校验在 fetch 前完成，dirty 检查包含 tracked 与 untracked 文件；本地 ahead/divergent、
错误分支、错误 origin 或错误仓库根均停止。fetch 后再次检查祖先关系，只允许 fast-forward；
网络、依赖或其他命令失败也停止。`work-root` 仍是现有 CLI 命令，复制唯一权威模板
`template/work-root/`，**不加 `--force`**，已有文件只保留/补缺，不覆盖。
不要与其他进程并发修改该 checkout；成功后再执行下面命令：

```bash
"$AEP_CLI" version
# 对照本 Skill manifest.json 的 minimum_cli_version；不兼容则停止，不运行后续阶段。
"$AEP_CLI" doctor --json
cd -- "$AEP_ROOT"
```

后续所有 reference 中的 `auto-epublizer …` 都指**同一个准备好的 CLI**：运行时写作
`"$AEP_CLI" …`，不要调用未知 PATH 中的同名程序。新 shell 先重新执行上述安全续用步骤，
再导出该变量；不要依赖当前目录、全局安装或 Skill 自带 Python。
下面命令的相对书籍路径均以工作根为当前目录。

## 各组件的作用

| 组件 | 作用 |
|---|---|
| `auto-epublizer/` | 官方 main 源码 + `.venv`；只用于 CLI，绝不存书或提交书籍产物 |
| `AGENTS.md` | 本目录怎么工作（红线：根目录只保留一个 `.md`、源身份以 sha256 为准、禁手编、数字必须重算） |
| `config.example.yaml` | 复制为 `config.yaml`；关键项 `paths.workspaces_dir: ./workspaces` |
| `inbox/` | 尚未开工的源书（原名原字节） |
| `sources/` | 送审暂存副本，命名 `<slug>.<ext>`（交给 `preprocess`） |
| `workspaces/<slug>/` | 每本书一个**标准工作区**（由 CLI 生成） |
| `docs/` | 过程文档：计划 / 规范 / 审计 + 跨书台账 |
| `references/` | 跨书共享资料（只读） |
| `README.md` | 上面这些的**用户说明** |

## 怎么用

1. **新书**：`cp inbox/<原名> sources/<slug>.<ext>` →
   `"$AEP_CLI" preprocess sources/<slug>.<ext> --workspace ./workspaces` → 之后按单书常规流程
   推进（`status --json` → 任务卡 → `import` / `g0` / `build` / `qa` / 交付审计）。
2. **跨书总览**：`"$AEP_CLI" status --all --workspace . --json`（三档进度：
   `released` / `built_not_released` / `preprocessing`）；
   `python3 docs/build_ledger.py --cli "$AEP_CLI"` 重算台账并按唯一 slug 保留人工列。
3. **身份以 `publication.json.meta.source_sha256` 为准**，不认文件名。入库前对源做过加工
   （注入书签、格式转换）时，用 `preprocess --original <原始件>` 归档未改动的交付原件。
4. **数字一律由命令重算**，绝不手维护。

## 告诉用户的话（可直接转述）

> 这是你的**长期工作区**：`inbox/` 放还没开工的原书；开工时复制到 `sources/<slug>.<ext>` 交给
> agent 处理；每本书成为 `workspaces/<slug>/` 下一个标准工作区；`docs/` 放过程文档与跨书台账；
> `references/` 放跨书共享资料；`auto-epublizer/` 只放软件源码和环境，不放书。随时用
> `"$AEP_CLI" status --all` 看全部书的进度（已交付 / 已建未放行 / 仅预处理），
> `"$AEP_CLI" ledger` 生成台账。源身份以 sha256 为准。

## 可直接运行的操作护栏（issue #47）

生成器同时复制 `docs/{pack_outbox,build_ledger,check_doc_links,check_tracked}.py`。
四者均为 Python 3.11+ 标准库脚本，不依赖原仓库、不联网、无 LLM，不自动 stage/push。
前两项调用已安装的真实 CLI，可通过 `--cli /绝对路径/auto-epublizer` 指定未激活环境中的
可执行文件；不会另算 QA 摘要或机器进度。默认工作根由脚本位置确定，显式相对路径参数按
shell 当前目录解释。复制或生成工作根后即可运行；无书籍时仍可运行空台账与文档检查。

```bash
python3 docs/build_ledger.py --cli "$AEP_CLI" --workspace workspaces --output docs/工作台账.md
python3 docs/pack_outbox.py --cli "$AEP_CLI" workspaces/book-a workspaces/book-b --batch 2026-10-17
python3 docs/check_doc_links.py --root .
python3 docs/check_tracked.py --repo workspaces/book-a
```

### 保守交付

打包位置参数显式列出**整批实际工作区**；嵌套布局应传包含 `publication.json` 的 `book/`。
整批先逐项调用真实 `status --json`，必须当前 `released=true`、`stale=false`、`reason=ok`，
再读对应 `report.artifacts_epub` 精确路径（相对路径按工作区解释）。不猜 output 文件，
不以有无译文判断合法源语言转换。任何预检失败时整批不复制；忽略大小写的文件名冲突也失败。

默认新批次位于 `outbox/<batch>/epub/`（`--outbox` 可改根）。已存在的完整批次和无
`MANIFEST.md` 的中断批次均拒绝覆盖，退出非零并明确未复制。复制后逐件重算源文件与
副本 SHA256，再检查真实状态及报告快照，全部一致才通过临时文件原子发布批次 `MANIFEST.md`。
清单写失败不得留下完成标记；中途失败保留无清单现场。人工核证后用新批次名重试，
不把残件当交付，不并发修改工作区。

### 机器台账与人工列

`build_ledger.py` 实际调用 `ledger --workspace … --output <临时文件>`，按表头与列数解析。
所有机器单元格保持真实 CLI 原值，只按唯一稳定 `slug` 保留四个人工列：
`批次/领域/摘要/最后修改`，缺列补上，转义 `\|` 原样保留。不会把词数当领域、因无译文而
降低放行状态、按书名或行号搬数据，也不额外手算放行计数。扫描范围内 slug 必须唯一且
保持稳定；重复/空 slug、列数错误、旧机器表头不兼容、CLI 失败均不覆盖旧台账。
成功时原子替换；生成期间旧台账被改也拒绝覆盖。改了 slug 时应人工核证迁移对应人工列。
CLI 会转义书名/slug 中的反斜线与竖线、把换行转为空格；工具保留该机器值，不自行猜拆列。

### 本地文档引用

`check_doc_links.py` 只检查已知根 `AGENTS.md` 与 `docs/*.md`，覆盖普通 inline、
full/collapsed/shortcut reference links 及独立行内代码中的相对文档/脚本/目录路径。
断链和未定义显式引用给出文件与行号并退出非零。跳过外链、纯 fragment、围栏/缩进代码示例、
`<slug>`/花括号/通配等显式占位与 EPUB 内部成员；不请求网络、不验证锚点。
Markdown 脚注正文中的真实链接与普通 HTML 文档链接也会核对；脚注文本本身不是文件路径。
初次生成后先跑台账，否则 `AGENTS.md` 指向尚不存在的台账会如实失败。

### Git/磁盘/忽略对账

`check_tracked.py --repo <实际仓库根>` 读取 Git 跟踪、ignored、untracked 与磁盘文件，
列出 missing/无法归类并按顶层汇总 ignored。每本书有独立 Git 时逐本检查，不要求工作根
也必须入库；嵌套仓库内容需对其根单独检查。未跟踪、缺失、无法归类及意外忽略均失败。

独立的默认允许忽略规则**仅** `docs/__pycache__/**` 和 `outbox/*/epub/**`，
不把 `.gitignore` 自身当允许清单。故 `outbox/batch/secret.txt` 和 `.tr/draft.txt` 即使被
Git 忽略也会失败。核证后用可重复 `--allow '精确/模式'` 或 `--allow-file <独立规则文件>`
添加规则（一行一条、`#` 注释；`*` 不跨路径段、`**` 可跨层、尾 `/` 允许子树）。
不接受 `.gitignore` 作为独立规则文件。失败不等于应把文件入库：先检查内容与保密边界，
应忽略者添加精确允许规则，**绝不要为消警把 secret 加 Git**。工具不执行 `git add`。

这些脚本不替代逐书 QA 或内容核证；四项操作失败均退出非零，不自动修文件或制造放行证据。
