"""typer CLI 命令入口：init/convert/status/build/qa/preprocess/doctor/import/g0/version。"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from auto_common.config import load_config
from auto_common.workspace import RunStore

from . import __version__
from . import orchestrator as orch

app = typer.Typer(help="auto-epublizer：翻译 + 转 EPUB 的 Python CLI")
console = Console()

_CONFIG_PATH = "config.yaml"


def _find_workspace(base: Path) -> Path:
    if (base / "publication.json").is_file():
        return base
    candidates = sorted(base.glob("*/publication.json"))
    if not candidates:
        raise typer.BadParameter(f"未找到工作区（缺少 publication.json）：{base}")
    if len(candidates) > 1:
        names = ", ".join(c.parent.name for c in candidates)
        raise typer.BadParameter(f"存在多个工作区（{names}）；请用 --workspace 指定")
    return candidates[0].parent


def _store_from(workspace: str | None, cfg) -> RunStore:
    base = Path(workspace) if workspace else Path(cfg.paths.workspaces_dir)
    ws = _find_workspace(base)
    store = RunStore(ws)
    if not store.exists():
        raise typer.BadParameter(f"工作区未初始化：{ws}")
    return store


@app.command()
def init(
    input: str = typer.Argument(..., help="源文件路径"),
    reference: list[str] | None = typer.Option(None, "--reference", help="参考材料（可多次）"),
    target: str | None = typer.Option(None, "--target", help="目标语言（ISO 639-1）"),
    workspace: str | None = typer.Option(None, "--workspace", help="工作区根目录"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """初始化工作区：source/ + publication.json + 四层结构拆分。"""
    cfg = load_config(config or _CONFIG_PATH)
    try:
        store = orch.init(
            input,
            config=cfg,
            target_language=target,
            references=reference,
            workspace_dir=workspace or cfg.paths.workspaces_dir,
        )
    except (ValueError, OSError) as e:
        raise typer.Exit(f"初始化失败：{e}") from None
    pub = store.load_publication()
    console.print(f"[green]工作区已初始化：[/green]{store.dir}")
    console.print(f"  书名：{pub.meta.title}")
    console.print(f"  目标语言：{pub.meta.target_language}")


@app.command()
def convert(
    input: str | None = typer.Argument(None, help="源文件路径（省略则在工作区内转换）"),
    output: str | None = typer.Option(None, "-o", "--output", help="输出 EPUB 路径"),
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    theme: str | None = typer.Option(None, "--theme", help="排版主题（standard/compact/spacious）"),
    nav_depth: int | None = typer.Option(
        None, "--nav-depth", help="目录最大嵌套深度（1–6，默认取配置 output.nav_depth）"
    ),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """仅转换（不翻译）：归一化 + 结构 + EPUB + QA。"""
    cfg = load_config(config or _CONFIG_PATH)
    try:
        if input:
            store = orch.init(
                input, config=cfg, workspace_dir=workspace or cfg.paths.workspaces_dir
            )
        else:
            store = _store_from(workspace, cfg)
        out = orch.convert(
            store, output=output, theme=theme or cfg.output.theme, nav_depth=nav_depth
        )
        console.print(f"[green]EPUB 已生成：[/green]{out}")
        report = orch.qa(store, epub_path=str(out))
        console.print(
            f"  G4 审计：{report['g4_audit']}；epubcheck errors：{report['g4_epubcheck_errors']}"
        )
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"转换失败：{e}") from None


@app.command()
def status(
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    json_output: bool = typer.Option(False, "--json", help="输出 JSON"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """查看工作区进度 / 状态机。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    data = orch.status(store)
    if json_output:
        console.print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    console.print(f"工作区：{store.dir}")
    console.print(f"  书名：{data['title']}（{data['slug']}）")
    console.print(f"  目标语言：{data['target_language']}")
    console.print(f"  单元数：{data['units_total']}")
    for u in data["units"]:
        console.print(f"    {u['id']:24s} {u['kind']:10s} {u['status']}")
    if data.get("stale"):
        console.print("  [yellow]⚠ 有产物未登记（translation/align 存在但状态未推进）：[/yellow]")
        for s in data["stale"]:
            console.print(f"    {s['id']}（当前 {s['status']}）→ 运行 auto-epublizer import 登记")


@app.command()
def build(
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    output: str | None = typer.Option(None, "-o", "--output", help="输出 EPUB 路径"),
    bilingual: bool = typer.Option(False, "--bilingual", help="产出双语 EPUB"),
    theme: str | None = typer.Option(None, "--theme", help="排版主题（standard/compact/spacious）"),
    nav_depth: int | None = typer.Option(
        None, "--nav-depth", help="目录最大嵌套深度（1–6，默认取配置 output.nav_depth）"
    ),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """从译文（缺省回退源文）封装 EPUB。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    try:
        out = orch.build(
            store,
            bilingual=bilingual,
            output=output,
            theme=theme or cfg.output.theme,
            nav_depth=nav_depth,
        )
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"封装失败：{e}") from None
    console.print(f"[green]EPUB 已生成：[/green]{out}")


@app.command()
def qa(
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    epub: str | None = typer.Option(None, "--epub", help="待检 EPUB 路径"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """结构审计 + epubcheck（写 report.json，聚合 G0–G5 放行判定）。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    try:
        report = orch.qa(store, epub_path=epub, config=cfg)
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"质检失败：{e}") from None
    console.print(
        f"  G4 审计：{report['g4_audit']}；epubcheck errors：{report['g4_epubcheck_errors']}；"
        f"passed：{report['passed']}"
    )
    console.print(
        f"  G0 告警：{len(report['g0_flags'])}；G1 候选：{report['g1_candidates']}；"
        f"G2 确认：{report['g2_confirmed']}（已修订 {report['g3_patched']}）；"
        f"差错率：{report['error_rate']}"
    )
    console.print(
        f"  硬门：术语命中 {report['g0_terminology_open']}；"
        f"结构违例 {report.get('g0_structure_open', 0)}；"
        f"术语冲突未裁决 {report.get('glossary_conflicts_open', 0)}"
    )
    console.print(f"  G5 放行：{'是' if report['released'] else '否'}")


@app.command()
def preprocess(
    input: str | None = typer.Argument(
        None, help="源文件路径（新书：init + facts；省略则刷新已有工作区的 facts）"
    ),
    reference: list[str] | None = typer.Option(None, "--reference", help="参考材料（可多次）"),
    target: str | None = typer.Option(None, "--target", help="目标语言（ISO 639-1）"),
    workspace: str | None = typer.Option(None, "--workspace", help="工作区根目录"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """预处理事实收集（零 token）：嗅探/元数据/TOC/体检/规模 → preprocessing/facts.*。

    产出 facts.md 内含 agent 待办清单：方案决策（plan.md）、全局理解（global.md）、
    章节理解（units/）、术语预提取（terms.csv）、风险标注（risks.md）、汇总（report.md）。
    """
    cfg = load_config(config or _CONFIG_PATH)
    try:
        if input:
            store = orch.init(
                input,
                config=cfg,
                target_language=target,
                references=reference,
                workspace_dir=workspace or cfg.paths.workspaces_dir,
            )
        else:
            store = _store_from(workspace, cfg)
        result = orch.preprocess(store, config=cfg)
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"预处理失败：{e}") from None
    facts = result["facts"]
    src = facts["source"]
    console.print(f"[green]预处理事实已生成：[/green]{result['facts_md']}")
    console.print(
        f"  类型={src.get('kind')} 单元={facts['structure']['totals']['units']} "
        f"词={facts['structure']['totals']['words']} 句={facts['structure']['totals']['sentences']}"
    )
    for s in facts["suggestions"]:
        console.print(f"  [yellow]提示：{s}[/yellow]")
    console.print(
        "  [dim]下一步：按 facts.md 的 agent 待办依次撰写 plan/global/units/terms/risks/report[/dim]"
    )


@app.command()
def meta(
    title: str | None = typer.Option(
        None, "--title", help="书名（译名用 --title，源名不动则不传）"
    ),
    creator: str | None = typer.Option(None, "--creator", help="原作者"),
    translator: str | None = typer.Option(
        None,
        "--translator",
        help="译者（agent 自报框架名，如 OpenCode/DouBao；用户指定名优先；空串清空）",
    ),
    publisher: str | None = typer.Option(None, "--publisher", help="出版社"),
    date: str | None = typer.Option(None, "--date", help="出版日期"),
    rights: str | None = typer.Option(None, "--rights", help="版权/许可声明"),
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """更新 DC 元数据（元数据核对与译者署名的写入口）。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    try:
        result = orch.set_meta(
            store,
            title=title,
            creator=creator,
            translator=translator,
            publisher=publisher,
            date=date,
            rights=rights,
        )
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"元数据更新失败：{e}") from None
    console.print(f"[green]元数据已更新：[/green]{', '.join(result['updated'])}")


@app.command()
def doctor(
    json_output: bool = typer.Option(False, "--json", help="输出 JSON 能力报告"),
    ping: bool = typer.Option(False, "--ping", help="实际请求外部站点验证网络连通性（有超时风险）"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """环境与能力自检：工具链 / Python 依赖 / 外部解析 API 与网络（纯只读）。"""
    from .doctor import capabilities_summary, collect_capabilities

    cfg = load_config(config or _CONFIG_PATH)
    caps = collect_capabilities(cfg, ping=ping)
    if json_output:
        console.print_json(json.dumps(capabilities_summary(caps), ensure_ascii=False))
        return
    ok_mark = "[green]✓[/green]"
    miss_mark = "[red]✗[/red]"
    for c in caps:
        mark = ok_mark if c.available else miss_mark
        console.print(f"  {mark} {c.name:18s} {c.detail or ('可用' if c.available else '缺失')}")
        if not c.available:
            if c.impact:
                console.print(f"      影响：{c.impact}")
            if c.hint:
                console.print(f"      应对：{c.hint}")
    console.print(
        "  [dim]multimodal（能否看图）与 search（有无搜索工具）CLI 无法探测，"
        "由 agent 自行判定并落盘 preprocessing/capabilities.md[/dim]"
    )


@app.command("import")
def import_cmd(
    unit: str | None = typer.Option(None, "--unit", help="只导入指定单元（缺省全部）"),
    terms: str | None = typer.Option(
        None, "--terms", help="导入 agent 提取的新术语提案（CSV，含 source/target/type 列）"
    ),
    reviewed: bool = typer.Option(
        False, "--reviewed", help="把已对齐（aligned）单元推进为 reviewed（审校通过后的登记）"
    ),
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """登记 agent 手写的 translation/ + align/（校验 + 推进状态 + 术语冲突外置）。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    try:
        result = orch.import_translations(
            store, unit_id=unit, terms_path=terms, mark_reviewed=reviewed
        )
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"导入失败：{e}") from None
    if result["reviewed"]:
        console.print(
            f"[green]审校通过已登记：[/green]{len(result['reviewed'])} 个单元推进为 reviewed"
        )
    for item in result["failed"]:
        console.print(f"[red]✗ {item['unit']}[/red]")
        for err in item["errors"]:
            console.print(f"    {err}")
    # 硬缺陷类（术语命中/标记/脚注守恒等）：红色 ✗；advisory（长度比等）：黄色 ⚠
    _HARD_CHECKS = {"terminology", "marker", "footnote", "table", "fidelity"}
    for w in result["warnings"][:20]:
        hard = w["check"] in _HARD_CHECKS
        color = "[red]" if hard else "[yellow]"
        mark = "✗" if hard else "⚠"
        console.print(
            f"{color}{mark} {w['unit']} {w['check']}：{w['message']}[/{color.strip('[]')}]"
        )
    if len(result["warnings"]) > 20:
        console.print(f"  … 共 {len(result['warnings'])} 条告警")
    n_term = sum(1 for w in result["warnings"] if w["check"] in _HARD_CHECKS)
    if n_term:
        console.print(
            f"[red]其中硬缺陷 {n_term} 条（术语命中/标记/脚注守恒等，真实缺陷），"
            f"须逐条核验清零后才能放行[/red]"
        )
    for sid in result["skipped"]:
        console.print(f"[dim]- {sid}：跳过（无 rel_path 或已 reviewed/built）[/dim]")
    if result["conflicts_open"]:
        console.print(
            f"[yellow]术语冲突 {result['conflicts_open']} 条已外置到 "
            f"analysis/glossary_conflicts.jsonl，请裁决后写回 glossary.csv[/yellow]"
        )
    console.print(
        f"[green]导入完成：[/green]单元={len(result['imported'])} "
        f"失败={len(result['failed'])} 告警={len(result['warnings'])}"
    )


@app.command()
def restructure(
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """登记 agent 重建的单元结构（preprocessing/structure.csv → publication.json）。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    try:
        result = orch.restructure(store)
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"结构登记失败：{e}") from None
    console.print(
        f"[green]结构已登记：[/green]{result['units']} 个单元"
        f"（新增 {len(result['added'])}、回退重译 {len(result['reset'])}、消失 {len(result['removed'])}）"
    )
    if result["reset"]:
        console.print(f"  需重译：{'、'.join(result['reset'])}")
    if result["added"]:
        console.print(f"  新增：{'、'.join(result['added'])}")
    if result["removed"]:
        console.print(f"  消失（旧 translation/align 产物可清理）：{'、'.join(result['removed'])}")


@app.command()
def g0(
    unit: str | None = typer.Option(None, "--unit", help="只校验指定单元（缺省全部）"),
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """G0 零 token 静态校验（翻译/导入后立即跑，不必等到 qa）。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    try:
        result = orch.g0_check(store, unit_id=unit)
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"G0 校验失败：{e}") from None
    # 硬缺陷类（术语命中/标记/脚注守恒等）红色 ✗，须逐条核验；其余 advisory 黄色 ⚠
    _HARD_CHECKS = {"terminology", "marker", "footnote", "table", "fidelity"}
    n_hard = 0
    for f in result["flags"]:
        if f["check"] in _HARD_CHECKS:
            n_hard += 1
            console.print(f"[red]✗ {f['unit']} {f['check']}：{f['message']}[/red]")
        else:
            console.print(f"[yellow]⚠ {f['unit']} {f['check']}：{f['message']}[/yellow]")
    console.print(
        f"G0 完成：校验 {len(result['checked_units'])} 单元，告警 {len(result['flags'])} 条"
        f"（其中硬缺陷 {n_hard} 条——术语命中/标记/脚注守恒等真实缺陷，须逐条核验清零；"
        f"其余为 advisory）"
    )


@app.command()
def version() -> None:
    """显示版本。"""
    console.print(f"auto-epublizer {__version__}")


def main() -> None:
    app()
