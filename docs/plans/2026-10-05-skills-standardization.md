# 2026-10-05 仓库 skills 标准化（skills.sh / Agent Skills 规范）

状态：实施中（2026-10-05 完成 P0 合规修复 + P1 发布准备；P2–P4 待做；
P3 依赖的原子化 S1 已完成）

## 背景与目标

**目标（用户）**：让整个仓库现有的内容都能转化为**标准 skill 包**——可被
[skills.sh](https://www.skills.sh)（`npx skills`）发现、安装、上榜，且安装后的使用体验
符合 Agent Skills 规范（渐进式披露 + 原子任务 + 机器可判的完成判据）。

**规范来源（唯一权威）**：

- Agent Skills 规范：<https://agentskills.io>
- skills.sh 的判定逻辑开源在 `vercel-labs/skills`（其 README 即发现规则说明）：
  <https://github.com/vercel-labs/skills>
- 判定可本机复现：`npx skills add . --list`（不安装，只列出发现的 skill）。

**硬性要求（合规判定的全部内容）**：

1. `SKILL.md` 必须**以 YAML frontmatter 开头**，含必填 `name` + `description`；
2. 目录布局命中发现路径（容器目录内最多 3 层）：
   `skills/<name>/SKILL.md`、`skills/<category>/<name>/SKILL.md`、
   `skills/<category>/<category>/<name>/SKILL.md`，以及 `skills/.curated/`、
   `skills/.experimental/`、`skills/.system/` 等；
3. `name` 小写连字符、与所在目录同名；`description` 1–1024 字符；
4. 只识别 `name` / `description` / `license` / `compatibility` / `metadata`，
   未知字段忽略；`metadata.internal: true` 为隐藏 skill（需 `INSTALL_INTERNAL_SKILLS=1` 才可见）。

> 注意：官方规范**不读** `manifest.json`、不校验 `references/` 内容、不认 `.zh.md`
> 侧车文件——它们只是随 skill 一起被复制的 bundled resources。合规只由「目录 + frontmatter」
> 决定。

## P0 合规修复（2026-10-05 已完成）

**根因**：`SKILL.md` 顶部被 i18n 戳 + 语言横幅占据，frontmatter 落在第 4 行，违反
「以 frontmatter 开头」。实测官方 CLI 直接报：

```text
⚠ Skipped .../skills/auto-epublizer/SKILL.md — missing required frontmatter field(s): name, description
◇  No skills found
```

**改动**：

| 文件 | 内容 |
|---|---|
| `skills/auto-epublizer/SKILL.md` / `.zh.md` | YAML frontmatter 移到文件**第一行**；i18n 戳与语言横幅移到 `---` 之后；补标准可选字段 `license: AGPL-3.0` |
| `scripts/i18n.py` | 新增 `split_frontmatter()`；`parse_stamp` / `_has_banner` / `_strip_i18n_header` / `finalize` 全部改为先跳过 frontmatter 再处理戳/横幅（普通文档排版不变） |
| `tests/test_i18n.py` | 回归：`finalize` 保持 frontmatter 在首；仓库每个 `skills/*/SKILL.md` 首行必须是 `---` 且含 name/description |
| `docs/i18n.md` | 补记契约例外：标准 skill 的横幅/戳位于 frontmatter 之后 |

**验收（机器可判）**：

```bash
DISABLE_TELEMETRY=1 npx -y skills@latest add . --list   # 期望：Found 1 skill → auto-epublizer
uv run python scripts/i18n.py --check                    # OK
uv run python scripts/i18n.py --links                    # OK
uv run pytest -q                                         # 395 passed
uv run ruff check . && uv run ruff format --check .      # 全绿
```

## 待办

### P1 发布准备（2026-10-05 已完成）

- [x] 确认 GitHub 仓库 `Misaka0x26FE/auto-epublizer` 为 **public**（`gh repo view`：
      `visibility=PUBLIC`）；
- [x] `README.md`（+zh）加徽章：
      `[![skills.sh](https://skills.sh/b/Misaka0x26FE/auto-epublizer)](https://skills.sh/Misaka0x26FE/auto-epublizer)`；
- [x] `scripts/install-skills.sh` 增加 `--check`：复制前校验 `SKILL.md` frontmatter
      （首行 `---`、name 与目录一致、description 非空、长度 ≤1024），不合规则拒绝安装；
      配套回归 `tests/test_install_skills.py`；
- [ ] 在 `skills/auto-epublizer/manifest.json` 旁（或 SKILL.md 内）注明：该 manifest 是
      **仓库自定义契约**（version 门禁 + references 清单），标准加载器不读取，`minimum_cli_version`
      门禁只有按 SKILL.md 指引读取它的 agent 才会执行。（仍待做）

### P2 渐进式披露：`SKILL.md` 减重

- [ ] 把 `SKILL.md` 里的「Standard workflow」大段与 `references/workflow.md` 去重：入口只保留
      `description` / 红线 / 路由表 / 指针，细节全部下沉 `references/`；
- [ ] `description` 收敛为 1–3 句「做什么 + 何时用」，命令清单归还 workflow.md
      （description 越长越稀释选题信号）。

### P3 原子任务卡 + 机器指针

> **依赖**：`2026-09-30-workflow-microtasks.md` 的 **S1**（`status --json` 的
> `next_tasks` 机器指针 + `done_when`）——**已于 2026-10-05 完成**，任务卡现在有了可挂靠的索引。
> 没有 S1，任务卡只是又一批要模型自己判断该读哪篇的散文。

- [ ] 新增 `skills/auto-epublizer/references/taskcards/`，每张卡「一屏以内、自包含」：
      `重述现场（读哪些文件）→ 动作（写到哪）→ 完成判据（跑哪条命令）→ 失败处置`；
- [ ] 弱模型主路径 = `SKILL.md` → `status --json.next_tasks` → 对应任务卡；
      阶段级 references 降级为编排说明（保留给强模型与人类维护者，不删除）；
- [ ] `manifest.json` 的 `references` 清单与新增目录严格一致。

### P4 多 skill 拆分（评估项，先不做）

当前仓库只暴露 **1 个** skill（`auto-epublizer`）。skills.sh 支持一个仓库暴露多个：
`skills/<category>/<name>/SKILL.md`（分类最多 2 层）。将来可把「大而全」的单一 skill 拆为：

```text
skills/
├── auto-epublizer/            # 编排入口（保留路由 + 红线）
├── auto-epublizer-translate/  # 翻译 + 对齐 + 术语回路
├── auto-epublizer-convert/    # 纯转换（PDF/EPUB/DOCX → EPUB）
├── auto-epublizer-repair/     # 语义整备
├── auto-epublizer-review/     # G0–G3 审校
└── auto-epublizer-deliver/    # build + qa + 交付审计
```

**拆分判据（先实测再拆）**：用 P3 的任务卡跑一本真书，若单 skill 的
「SKILL.md + 15 篇 references」在弱模型会话里明显超载、或路由误判频发，再拆。
不要为拆而拆（拆分会带来 manifest/references 双份维护成本）。

## 「全部事项」总表（跨文档索引，避免多处失同步）

| 事项 | 权威文档 | 状态 |
|---|---|---|
| skills.sh 合规（frontmatter 置顶 + i18n 适配） | **本文件 P0** | ✅ 2026-10-05 |
| 发布准备（public / 徽章 / install --check） | 本文件 P1 | ✅ 2026-10-05 |
| SKILL.md 减重（渐进式披露） | 本文件 P2 | ⬜ |
| 原子任务卡 + `done_when` | 本文件 P3 + `2026-09-30-workflow-microtasks.md` | ⬜（依赖 S1） |
| 多 skill 拆分 | 本文件 P4 | ⬜（评估） |
| 工作原子化 S1（`next_tasks` 指针） | `2026-09-30-workflow-microtasks.md` | ✅ 2026-10-05 |
| 工作原子化 S2–S5 | 同上 | ⬜（S1 实测后决定范围） |
| #16 导航扁平 S-A（meta 如实声明） | `2026-10-04-backlog-three-items.md` §1.4 | ⬜（低风险，可先做） |
| #16 导航扁平 S-B（源书签→锚点映射） | 同上 §1.4 | ⬜（需案例工作区） |
| 项目 skills 化（内容层） | 本文件 P2–P4 | ⬜ |

## 边界与不变量

- **`skills/` 是纯文档，无业务逻辑**：可执行面是本仓库安装的 `auto-epublizer` CLI，
  不向 skill 内塞脚本（P1 的 `--check` 属于仓库工具链，不在 skill 目录内）；
- **单一状态源不变**：P3 的 `done_when` 全部由现有 CLI 判定，不新增状态文件、不改
  `publication.json` 契约；
- **强模型路径无损**：阶段级 references 保留，skill 化是增量而非替换；
- **i18n 契约照旧**：新增/修改 `skills/**` 文档须中英双语并走
  `scripts/i18n.py --finalize`；`docs/plans/**` 保持中文单语。

## 实施顺序

```text
P0 合规（✅ 已做，解除“装不上”故障）
  → P1 发布准备（小，解除“上不了榜”）
  → 原子化 S1 + P2 SKILL.md 减重（内容层使能，独立可交付）
  → P3 任务卡（依赖 S1；先拿真书 + 偏弱 agent 实测再铺卡）
  → P4 多 skill 拆分（仅当实测证明单 skill 超载时）
（#16 S-A/S-B 与本主题技术独立，按价值优先级穿插）
```

## 验收

- 合规/发布：`npx skills add . --list` 稳定发现；仓库 public；README 有徽章；
- 内容层：偏弱 agent 能沿 `SKILL.md → status --json.next_tasks → 任务卡` 完成至少一个完整阶段
  （如逐单元 `translate-unit → import-unit → fix-g0-unit`）而不跳步、不重做、不依赖会话记忆；
- 回归：`uv run pytest -q` + `ruff check` + `ruff format --check` +
  `i18n.py --check/--links` 全绿。
