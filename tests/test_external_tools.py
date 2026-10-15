"""F 组：外部工具分层与真实 CLI 登记覆盖（skip 与工具缺口单独列出，不冒充通过）。

- 真实 epubcheck：``java`` + ``epubcheck.jar`` 可用时**实际执行外部工具**，断言零 error
  且干净成品放行；不可用 → 明确 skip 原因（其余测试把 jar 指向不存在路径属密闭策略，
  不能替代真实执行覆盖）；
- 真实 CLI 登记：``import --reviewed`` 经 CLI 推进 reviewed（不只在领域层测）；
- 工具缺口（本机无 tesseract/ocrmypdf/rapidocr/MinerU 时扫描件仅伪后端覆盖）与全部
  skip 原因在计划 §7「F 报告」单独列出。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from auto_common.config import Config
from auto_common.workspace import RunStore
from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app

runner = CliRunner()

_SRC_MD = "# Chapter I\n\nFirst sentence here.\n"
_TGT_MD = "# 第一章\n\n第一句话在这里。\n"


def _write_translation_and_align(store: RunStore) -> None:
    pub = store.load_publication()
    for unit in pub.units:
        rel = unit.meta["rel_path"]
        tp = store.translation_dir / rel
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_text(_TGT_MD, encoding="utf-8")
        rows = [
            {"seq": 1, "src": "Chapter I", "tgt": "第一章", "note": None},
            {"seq": 2, "src": "First sentence here.", "tgt": "第一句话在这里。", "note": None},
        ]
        store.unit_align_path(unit.id).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )


def _epubcheck_env() -> tuple[Path, str] | None:
    """真实 epubcheck 环境：返回 (jar, java) 或 None（无则 skip）。"""
    jar = Path(Config().qc.epubcheck.jar).expanduser()
    java = shutil.which("java")
    if jar.is_file() and java:
        return jar, java
    return None


@pytest.mark.skipif(
    _epubcheck_env() is None, reason="需要 java + epubcheck.jar（真实外部工具未安装）"
)
def test_real_epubcheck_executes_and_clean_product_releases(tmp_path: Path) -> None:
    """工具执行覆盖：真实调用 epubcheck（非 stub），干净成品零 error 且放行。"""
    src = tmp_path / "book.md"
    src.write_text(_SRC_MD, encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    _write_translation_and_align(store)
    # 契约（references/workflow 等文档）：import 推 translated→aligned；
    # import --reviewed 再把 **已 aligned** 的单元推 reviewed（两步登记，幂等）
    orch.import_translations(store)
    result = orch.import_translations(store, mark_reviewed=True)
    assert result["reviewed"] == ["ch01"]

    epub = orch.build(store)
    report = orch.qa(store, epub_path=str(epub), config=Config())  # 默认 jar = 真实路径

    assert report["epubcheck"]["ran"] is True, report["epubcheck"]
    assert report["g4_epubcheck_errors"] == 0, report["epubcheck"]
    assert report["g4_audit"] == "pass", report["audit"]
    assert report["released"] is True, report["released_reason"]
    assert report["released_reason"] == "ok"


def test_real_cli_import_reviewed_registers_reviewed_state(tmp_path: Path) -> None:
    """真实 CLI 登记：`import --reviewed` 经 CLI 推进 reviewed 且 status --json 可见。"""
    src = tmp_path / "book.md"
    src.write_text(_SRC_MD, encoding="utf-8")
    ws = tmp_path / "ws"
    assert runner.invoke(app, ["init", str(src), "--workspace", str(ws)]).exit_code == 0
    store = RunStore(ws / "book")
    _write_translation_and_align(store)

    first = runner.invoke(app, ["import", "--workspace", str(store.dir)])
    assert first.exit_code == 0, first.output
    r = runner.invoke(app, ["import", "--workspace", str(store.dir), "--reviewed"])
    assert r.exit_code == 0, r.output
    assert "审校通过已登记" in r.output

    sj = runner.invoke(app, ["status", "--workspace", str(store.dir), "--json"])
    assert sj.exit_code == 0, sj.output
    data = json.loads(sj.output)
    assert [u["status"] for u in data["units"]] == ["reviewed"]
