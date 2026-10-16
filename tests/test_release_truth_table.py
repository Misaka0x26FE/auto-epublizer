"""B2：放行真值表回归——每个门的级别（blocking/advisory）、拥有层与拒绝放行定位。

真值表（条件 → 拥有层 → 级别 → 用例）：

| 条件 | 拥有层 | 级别 | 用例 |
|---|---|---|---|
| 术语命中 terminology | auto_translator/review（G0） | 硬 | test_terminology_blocks_release（test_qa 已有）+ 本文件冒烟 |
| marker/footnote/heading/table 守恒 | G0 | 硬 | test_qa 已有 |
| fidelity 反向失配（src 不在源文） | G0/fidelity | 硬 | test_reverse_fidelity_blocks_release |
| fidelity 前向缺块（合法剔除可能） | G0/fidelity | **advisory** | test_forward_fidelity_is_advisory |
| align 完整性（seq/空行） | G0/check_alignment | 硬 | test_align_integrity_blocks_release |
| length 长度比 | G0 | advisory | test_advisories_do_not_block_release |
| footnote_suspect 注号差集 | G0 | advisory | 同上 |
| 未裁决术语冲突 | glossary | 硬 | test_qa 已有 |
| catalog unresolved | 源盘点 | 硬 | test_catalog_unresolved_blocks_release |
| 审校未修（g2 > g3） | reviews/result.json | 硬 | test_unresolved_review_blocks_release |
| epubcheck 未运行/有错 | qa/epubcheck | 硬 | test_epubcheck_not_run_never_releases |
| 解包审计 error | qa/audit | 硬 | test_qa 已有 |
| 溯源/成品覆盖率 | qa/provenance | 硬 | test_qa 已有 |
| 成品注释门（N 阶段） | qa/notes_audit | 硬 | test_notes 已有 |
| repairs unresolved / 交付审计缺记录 | repairs / delivery | warning | test_qa 已有（不阻断） |

产物核对：test_clean_workspace_releases_and_zip_verified 独立解析 ZIP（不看 report 声称）。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from auto_common.config import Config
from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app
from auto_epublizer.qa import (
    AuditResult,
    EpubcheckResult,
    generate_report,
)

runner = CliRunner()


def _clean_audit() -> AuditResult:
    return AuditResult(ok=True)


def _epubcheck_ok() -> EpubcheckResult:
    return EpubcheckResult(available=True, ran=True, errors=0, warnings=0, returncode=0)


def _report(g0_flags=None, **kw):
    return generate_report(
        "book",
        _clean_audit(),
        _epubcheck_ok(),
        g0_flags=g0_flags or [],
        **kw,
    )


# ── fidelity：前向 advisory / 反向硬门 ────────────────────────────────────


def test_forward_fidelity_is_advisory() -> None:
    """前向缺块（可能是合法剔除）：不进 g0_structure_open，不阻断放行。"""
    flags = [
        {
            "unit": "ch01",
            "check": "fidelity",
            "message": "源文块未进对照表",
            "blocking": False,
            "data": {"block": 2},
        }
    ]
    r = _report(g0_flags=flags)
    assert r.g0_structure_open == 0
    assert r.released is True and r.released_reason == "ok"


def test_reverse_fidelity_blocks_release() -> None:
    """反向失配（src 被改写/杜撰）：硬门，拒绝放行且原因指向结构违例。"""
    flags = [
        {
            "unit": "ch01",
            "check": "fidelity",
            "message": "对照表 src 不在源文中（疑抄错/改写）",
            "blocking": True,
            "data": {"seq": 3},
        }
    ]
    r = _report(g0_flags=flags)
    assert r.g0_structure_open == 1
    assert r.released is False and r.released_reason == "structure_open"
    assert any(f["message"].startswith("对照表 src 不在源文中") for f in r.g0_flags)


# ── 其余硬门/advisory ────────────────────────────────────────────────────


def test_align_integrity_blocks_release() -> None:
    """align 完整性（seq 断号/空行）是校验基准的结构不变量：硬门。"""
    flags = [{"unit": "ch01", "check": "align", "message": "seq 不连续", "blocking": True}]
    r = _report(g0_flags=flags)
    assert r.g0_structure_open == 1
    assert r.released is False and r.released_reason == "structure_open"


def test_advisories_do_not_block_release() -> None:
    """length 与 footnote_suspect 是 advisory：不出现在放行硬门计数里。"""
    flags = [
        {"unit": "ch01", "check": "length", "message": "长度比过低（疑漏译）", "blocking": False},
        {
            "unit": "ch01",
            "check": "footnote_suspect",
            "message": "译文疑似缺少源侧注号 1 个",
            "blocking": False,
        },
    ]
    r = _report(g0_flags=flags)
    assert r.g0_structure_open == 0 and r.g0_terminology_open == 0
    assert r.released is True


def test_catalog_unresolved_blocks_release() -> None:
    r = _report(catalog_unresolved_open=2)
    assert r.released is False and r.released_reason == "catalog_open"


def test_unresolved_review_blocks_release() -> None:
    r = _report(review={"g1_candidates": 5, "g2_confirmed": 2, "g3_patched": 0})
    assert r.released is False and r.released_reason == "unresolved_confirmed"
    assert r.g2_confirmed == 2 and r.g3_patched == 0


def test_epubcheck_not_run_never_releases() -> None:
    """epubcheck 无法运行 = 未验证，不得声称放行。"""
    r = generate_report(
        "book",
        _clean_audit(),
        EpubcheckResult(available=False, ran=False, errors=-1, warnings=0, returncode=None),
    )
    assert r.passed is False and r.released is False
    assert r.released_reason == "epubcheck_not_run"


def test_g0_check_serializes_blocking_field(tmp_path: Path) -> None:
    """g0_check 输出的告警带 blocking 字段（CLI/报告共用同一判据）。"""
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.1\n\nSecond sentence.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n第一句话。[^ref-x]\n", encoding="utf-8"
    )
    (store.translation_dir / "align").mkdir(parents=True, exist_ok=True)
    with open(store.unit_align_path("ch01"), "w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"seq": 1, "src": "First sentence.1", "tgt": "第一句话。", "note": None},
                ensure_ascii=False,
            )
            + "\n"
        )
    flags = orch.g0_check(store, config=Config())["flags"]
    assert flags and all("blocking" in f for f in flags)
    # 该 fixture：第二段未进对照表（前向）→ advisory；长度比过低 → advisory
    assert all(f["blocking"] is False for f in flags if f["check"] in ("fidelity", "length"))


# ── 干净工作区：真实 CLI 走通 + 产物 ZIP 独立核对 ────────────────────────


def _clean_ws(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.\n", encoding="utf-8")
    ws = tmp_path / "ws"
    result = runner.invoke(app, ["init", str(src), "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    # init 的工作区在 <ws>/book；直接用 RunStore 定位，避免依赖内部约定
    from auto_common.workspace import RunStore

    store = RunStore(ws / "book")
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n第一句话。\n", encoding="utf-8"
    )
    (store.translation_dir / "align").mkdir(parents=True, exist_ok=True)
    with open(store.unit_align_path("ch01"), "w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"seq": 1, "src": "First sentence.", "tgt": "第一句话。", "note": None},
                ensure_ascii=False,
            )
            + "\n"
        )
    return store


def test_clean_workspace_releases_and_zip_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """干净合成工作区：import→build→qa 放行；再**独立解析 ZIP**核对产物不变量。"""
    store = _clean_ws(tmp_path)
    monkeypatch.setattr(orch, "run_epubcheck", lambda *a, **k: _epubcheck_ok())
    result = runner.invoke(app, ["import", "--workspace", str(store.dir)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["build", "--workspace", str(store.dir)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["qa", "--workspace", str(store.dir)])
    assert result.exit_code == 0, result.output
    assert "G5 放行：是" in result.output
    assert json.loads(store.report_path.read_text(encoding="utf-8"))["released"] is True

    # 独立核对：不看 report 声称，直接解析 ZIP
    with zipfile.ZipFile(store.output_dir / f"{store.load_publication().slug}.epub") as zf:
        names = zf.namelist()
        first = zf.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
        assert zf.read("mimetype") == b"application/epub+zip"
        for required in ("META-INF/container.xml", "OEBPS/content.opf", "OEBPS/nav.xhtml"):
            assert required in names
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        for href in ("ch01.xhtml",):
            assert href in opf
        assert zf.read("OEBPS/ch01.xhtml").decode("utf-8").count("<h1") == 1
        nav = zf.read("OEBPS/nav.xhtml").decode("utf-8")
        assert 'epub:type="toc"' in nav


# ── B2 失效链：产物变更后旧报告不得当当前证据 ────────────────────────────


def _released_ws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = _clean_ws(tmp_path)
    monkeypatch.setattr(orch, "run_epubcheck", lambda *a, **k: _epubcheck_ok())
    assert orch.import_translations(store)["imported"] == ["ch01"]
    orch.build(store)
    rep = orch.qa(store, config=Config())
    assert rep["released"] is True and rep["artifacts_digest"]
    assert orch.status(store)["report"]["stale"] is False
    return store


def test_report_goes_stale_after_translation_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _released_ws(tmp_path, monkeypatch)
    md = store.translation_dir / "body" / "ch01.md"
    md.write_text("# 第一章\n\n改写后的一句话。\n", encoding="utf-8")

    st = orch.status(store)
    assert st["report"]["stale"] is True
    assert any(s["id"] == "report" and s["reason"] == "report_stale" for s in st["stale"])
    # 重跑 qa：旧成品与译文不一致 → 拒绝放行（不许把旧报告当新证据）
    rep2 = orch.qa(store, config=Config())
    assert rep2["released"] is False
    assert rep2["released_reason"] == "provenance_incomplete"


def test_report_goes_stale_after_align_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _released_ws(tmp_path, monkeypatch)
    store.unit_align_path("ch01").write_text("", encoding="utf-8")
    assert orch.status(store)["report"]["stale"] is True
    rep2 = orch.qa(store, config=Config())
    assert rep2["released"] is False
    # 已登记译文的单元对照表为空 → G0 align（硬门）定位到具体单元
    assert rep2["released_reason"] == "structure_open"
    assert any(
        f["unit"] == "ch01" and f["check"] == "align" and "对照表为空" in f["message"]
        for f in rep2["g0_flags"]
    )


def test_report_goes_stale_after_review_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _released_ws(tmp_path, monkeypatch)
    rd = store.reviews_dir / "review-2026-01-01T00-00-00"
    rd.mkdir(parents=True)
    (rd / "result.json").write_text(
        json.dumps({"g1_candidates": 1, "g2_confirmed": 1, "g3_patched": 0}),
        encoding="utf-8",
    )
    assert orch.status(store)["report"]["stale"] is True
    rep2 = orch.qa(store, config=Config())
    assert rep2["released"] is False
    assert rep2["released_reason"] == "unresolved_confirmed"


def test_status_all_downgrades_stale_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """多书台账：报告过期的书不得继续记为 released（降到 built_not_released）。"""
    store = _released_ws(tmp_path, monkeypatch)
    base = store.dir.parent
    rows = orch.status_all(base)
    assert rows and rows[0]["progress"] == "released" and rows[0]["report_stale"] is False

    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n改了。\n", encoding="utf-8"
    )
    rows2 = orch.status_all(base)
    assert rows2[0]["progress"] == "built_not_released"
    assert rows2[0]["report_stale"] is True


# ── 破坏场景：篡改成品 → 经真实 qa 拒绝且定位正确 ────────────────────────


def _tamper(src: Path, dst: Path, name: str, old: str, new: str) -> Path:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == f"OEBPS/{name}":
                data = data.decode("utf-8").replace(old, new).encode("utf-8")
            zout.writestr(item, data)
    return dst


def test_tampered_nav_blocks_release_at_audit_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _released_ws(tmp_path, monkeypatch)
    epub = store.output_dir / f"{store.load_publication().slug}.epub"
    bad = _tamper(epub, tmp_path / "bad-nav.epub", "nav.xhtml", "ch01.xhtml", "missing.xhtml")
    rep = orch.qa(store, epub_path=str(bad), config=Config())
    assert rep["released"] is False and rep["released_reason"] == "audit_failed"
    assert any(f["code"] == "E_NAV_HREF" for f in rep["audit"]["findings"])


def test_missing_spine_doc_blocks_release_at_provenance_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _released_ws(tmp_path, monkeypatch)
    epub = store.output_dir / f"{store.load_publication().slug}.epub"
    # 删除一个 spine 文档（成品与产物不再对应）
    bad = tmp_path / "missing-doc.epub"
    with zipfile.ZipFile(epub) as zin, zipfile.ZipFile(bad, "w") as zout:
        for item in zin.infolist():
            if item.filename == "OEBPS/ch01.xhtml":
                continue
            zout.writestr(item, zin.read(item.filename))
    rep = orch.qa(store, epub_path=str(bad), config=Config())
    assert rep["released"] is False and rep["released_reason"] == "audit_failed"
    codes = {f["code"] for f in rep["audit"]["findings"] if f["level"] == "error"}
    assert codes & {"E_MANIFEST_HREF", "E_NAV_HREF", "E_NCX_HREF"}
