"""typer CLI：init/convert/status 命令入口（convert 路径先行）。"""

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
        out = orch.convert(store, output=output)
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
def analyze(
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """分层理解 + 术语播种 + 语言/体裁检测（写 analysis/）。无 LLM Key 时走确定性降级。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    client = orch.make_client(cfg)
    try:
        result = orch.analyze(store, client)
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"分析失败：{e}") from None
    mode = "LLM 增强" if result.get("llm_enhanced") else "确定性降级（无 LLM Key）"
    console.print(
        f"[green]分析完成：[/green]语言={result['language']} 体裁={result['genre']} "
        f"单元={result['units']} 术语播种={result['terms_seeded']}（{mode}）"
    )
    if not result.get("llm_enhanced"):
        console.print(
            "[dim]analysis/ 概要与术语表可由 agent 自身能力撰写，"
            "翻译产物经 auto-epublizer import 登记[/dim]"
        )


@app.command()
def translate(
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    target: str | None = typer.Option(None, "--target", help="目标语言"),
    force: bool = typer.Option(False, "--force", help="强制重译（默认跳过已完成单元，断点续跑）"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """翻译（读 analysis/，写 translation/ + align/ 对照表）。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    client = orch.make_client(cfg)
    try:
        result = orch.translate(store, client, target_language=target, force=force)
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"翻译失败：{e}") from None
    skipped = f" 跳过={result['skipped']}" if result.get("skipped") else ""
    console.print(
        f"[green]翻译完成：[/green]单元={result['units']}{skipped} 目标语言={result['target_lang']}"
    )


@app.command()
def review(
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """审校（G0–G3，只读影子修订，产出质量报告）。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    client = orch.make_client(cfg)
    try:
        result = orch.review(store, client)
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"审校失败：{e}") from None
    console.print(
        f"[green]审校完成：[/green]issue={result['issue_count']} "
        f"收敛={result['termination']} 轮次={result['rounds']}"
    )


@app.command()
def build(
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    output: str | None = typer.Option(None, "-o", "--output", help="输出 EPUB 路径"),
    bilingual: bool = typer.Option(False, "--bilingual", help="产出双语 EPUB"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """从译文（缺省回退源文）封装 EPUB。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    try:
        out = orch.build(store, bilingual=bilingual, output=output)
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
def doctor(
    json_output: bool = typer.Option(False, "--json", help="输出 JSON 能力报告"),
    ping: bool = typer.Option(False, "--ping", help="实际请求 LLM 端点验证连通性（有超时风险）"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """环境与能力自检：工具链 / Python 依赖 / LLM 可用性（纯只读）。"""
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
        "  [dim]multimodal（能否看图）需 agent 自行判定：能看图 → 扫描 PDF 可用视觉 LLM 兜底[/dim]"
    )


@app.command("import")
def import_cmd(
    unit: str | None = typer.Option(None, "--unit", help="只导入指定单元（缺省全部）"),
    terms: str | None = typer.Option(
        None, "--terms", help="导入 agent 提取的新术语提案（CSV，含 source/target/type 列）"
    ),
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """登记 agent 手写的 translation/ + align/（校验 + 推进状态 + 术语冲突外置）。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    try:
        result = orch.import_translations(store, unit_id=unit, terms_path=terms)
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"导入失败：{e}") from None
    for item in result["failed"]:
        console.print(f"[red]✗ {item['unit']}[/red]")
        for err in item["errors"]:
            console.print(f"    {err}")
    for w in result["warnings"][:20]:
        console.print(f"[yellow]⚠ {w['unit']} {w['check']}：{w['message']}[/yellow]")
    if len(result["warnings"]) > 20:
        console.print(f"  … 共 {len(result['warnings'])} 条告警")
    for sid in result["skipped"]:
        console.print(f"[dim]- {sid}：无 rel_path，跳过[/dim]")
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
    for f in result["flags"]:
        console.print(f"[yellow]⚠ {f['unit']} {f['check']}：{f['message']}[/yellow]")
    console.print(
        f"G0 完成：校验 {len(result['checked_units'])} 单元，告警 {len(result['flags'])} 条"
    )


@app.command()
def version() -> None:
    """显示版本。"""
    console.print(f"auto-epublizer {__version__}")


def main() -> None:
    app()
