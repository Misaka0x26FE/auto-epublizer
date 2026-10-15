"""许可与来源标识回归（issue #40 §5.1/§5.2）：SPDX 头覆盖、producer 标识、构建日志署名。

不测「条文解释」只测可执行的合规契约：源码副本携带 AGPL 声明；工作区与事件账本带
机器可判定的工具身份；构建日志固定带工具 + 许可证 + 源码地址（均不出网、无遥测）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from auto_common.workspace import RunStore
from auto_epublizer import __version__
from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()

_SPDX_LINE = "# SPDX-License-Identifier: AGPL-3.0-only"
_COPYRIGHT_RE = re.compile(r"^# Copyright \(C\) \d{4} \S")


def test_all_source_files_carry_spdx_and_copyright_header() -> None:
    """AGPL §5(a) 的「适当法律声明」：`src/` 下每个 .py 都带 SPDX + 版权行。"""
    missing_spdx: list[str] = []
    missing_copyright: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        head = path.read_text(encoding="utf-8").splitlines()[:5]
        if not any(line.strip() == _SPDX_LINE for line in head):
            missing_spdx.append(str(path.relative_to(ROOT)))
        if not any(_COPYRIGHT_RE.match(line.strip()) for line in head):
            missing_copyright.append(str(path.relative_to(ROOT)))
    assert missing_spdx == [], f"缺 SPDX 头：{missing_spdx}"
    assert missing_copyright == [], f"缺版权行：{missing_copyright}"


def test_pyproject_declares_spdx_license_expression() -> None:
    """分发元数据用规范 SPDX 表达式（AGPL-3.0-only），不是弃用的 AGPL-3.0。"""
    import tomllib

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["license"] == "AGPL-3.0-only"
    assert data["project"]["license"] != "AGPL-3.0"


def test_workspace_records_machine_readable_producer(tmp_path: Path) -> None:
    """工作区来源可机器判定：metadata.producer + run_initialized 事件字段。"""
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\n第一句话。\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    pub = store.load_publication()
    assert pub.meta.producer == f"auto-epublizer@{__version__}"
    events = [json.loads(ln) for ln in store.event_log_path.read_text().splitlines()]
    init_events = [e for e in events if e["event"] == "run_initialized"]
    assert init_events and init_events[0]["producer"] == pub.meta.producer


def test_old_publication_without_producer_still_parses(tmp_path: Path) -> None:
    """向后兼容：旧工作区（无 producer 字段）照常解析（空串）。"""
    from auto_common.workspace.models import Publication

    pub = Publication.model_validate(
        {"schema_version": "0.1.0", "slug": "old", "meta": {"title": "旧书"}, "units": []}
    )
    assert pub.meta.producer == ""


def test_build_log_carries_tool_license_and_source_url(tmp_path: Path) -> None:
    """构建日志固定带工具/许可证/源码地址（#40 §5.2：让来源可识别，不出网）。"""
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.\n", encoding="utf-8")
    ws = tmp_path / "ws"
    assert runner.invoke(app, ["init", str(src), "--workspace", str(ws)]).exit_code == 0
    store = RunStore(ws / "book")
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n第一句话。\n", encoding="utf-8"
    )
    (store.translation_dir / "align").mkdir(parents=True, exist_ok=True)
    (store.unit_align_path("ch01")).write_text(
        json.dumps(
            {"seq": 1, "src": "First sentence.", "tgt": "第一句话。", "note": None},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["build", "--workspace", str(store.dir)])
    assert result.exit_code == 0, result.output
    # 状态行是人类可读输出，允许 Rich 按终端宽度折行：归一化空白后核对关键字段
    normalized = re.sub(r"\s+", " ", result.output)
    assert f"auto-epublizer {__version__}" in normalized
    assert "AGPL-3.0-only" in normalized
    assert "github.com/Misaka0x26FE/auto-epublizer" in normalized
