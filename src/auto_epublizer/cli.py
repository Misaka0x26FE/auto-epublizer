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
    else:
        console.print(f"工作区：{store.dir}")
        console.print(f"  书名：{data['title']}（{data['slug']}）")
        console.print(f"  目标语言：{data['target_language']}")
        console.print(f"  单元数：{data['units_total']}")
        for u in data["units"]:
            console.print(f"    {u['id']:24s} {u['kind']:10s} {u['status']}")


@app.command()
def analyze(
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """分层理解 + 术语播种 + 语言/体裁检测（写 analysis/）。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    client = orch.make_client(cfg)
    try:
        result = orch.analyze(store, client)
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"分析失败：{e}") from None
    console.print(
        f"[green]分析完成：[/green]语言={result['language']} 体裁={result['genre']} "
        f"单元={result['units']} 术语播种={result['terms_seeded']}"
    )


@app.command()
def translate(
    workspace: str | None = typer.Option(None, "--workspace", help="工作区目录"),
    target: str | None = typer.Option(None, "--target", help="目标语言"),
    bilingual: bool = typer.Option(False, "--bilingual", help="产出双语对照"),
    config: str | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """翻译（读 analysis/，写 translation/ + align/ 对照表）。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    client = orch.make_client(cfg)
    try:
        result = orch.translate(store, client, target_language=target, bilingual=bilingual)
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"翻译失败：{e}") from None
    console.print(
        f"[green]翻译完成：[/green]单元={result['units']} 目标语言={result['target_lang']}"
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
    """结构审计 + epubcheck（写 report.json）。"""
    cfg = load_config(config or _CONFIG_PATH)
    store = _store_from(workspace, cfg)
    try:
        report = orch.qa(store, epub_path=epub)
    except (ValueError, OSError, orch.OrchestrationError) as e:
        raise typer.Exit(f"质检失败：{e}") from None
    console.print(
        f"  G4 审计：{report['g4_audit']}；epubcheck errors：{report['g4_epubcheck_errors']}；"
        f"passed：{report['passed']}"
    )


@app.command()
def version() -> None:
    """显示版本。"""
    console.print(f"auto-epublizer {__version__}")


def main() -> None:
    app()
