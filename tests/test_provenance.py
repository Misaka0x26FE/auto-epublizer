"""溯源审计回归测试（postprocessing-spec §2/§3）：三边对账 / 媒体溯源 / 覆盖率 / 目录层级。"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from auto_common.workspace import Publication, PublicationMeta, RunStore
from auto_epublizer.build import build_epub
from auto_epublizer.build.html import render_document
from auto_epublizer.qa.provenance import audit_provenance
from auto_epublizer.qa.report import EpubcheckResult, generate_report
from auto_translator.translation.align import write_align


def _pub() -> Publication:
    return Publication(
        slug="book",
        meta=PublicationMeta(title="书", language="en", target_language="zh-CN"),
    )


def _align_rows(src_md: str) -> list[dict[str, Any]]:
    """把 structured md 的每个正文段落作为一行 src（tgt 为占位译文）。"""
    rows: list[dict[str, Any]] = []
    seq = 0
    for block in src_md.strip().split("\n\n"):
        block = block.strip()
        if not block or block.startswith("#"):
            continue
        seq += 1
        rows.append({"seq": seq, "src": block, "tgt": f"译{seq}", "note": None})
    return rows


def _make_workspace(
    tmp_path: Path,
    units: list[dict[str, Any]],
    *,
    translate: bool = True,
) -> tuple[RunStore, list[dict[str, Any]]]:
    """搭最小工作区：structured md + （可选）translation md + align。

    ``units`` 条目：{id, rel, md, level, tgt_md?, align_rows?}。
    """
    store = RunStore(tmp_path / "ws")
    store.ensure_skeleton()
    entries: list[dict[str, Any]] = []
    for u in units:
        rel: str = u["rel"]
        sp = store.structured_dir / rel
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(u["md"], encoding="utf-8")
        if translate:
            tp = store.translation_dir / rel
            tp.parent.mkdir(parents=True, exist_ok=True)
            tp.write_text(u.get("tgt_md", u["md"]), encoding="utf-8")
            rows = u.get("align_rows")
            if rows is None:
                rows = _align_rows(u["md"])
            if rows:
                write_align(store.unit_align_path(u["id"]), rows)
        entries.append(
            {
                "id": u["id"],
                "kind": "chapter",
                "region": "body",
                "title": u.get("title", u["id"]),
                "level": u.get("level", 1),
                "rel_path": rel,
            }
        )
    return store, entries


def _build(store: RunStore, entries: list[dict[str, Any]], *, drop: set[str] | None = None) -> Path:
    content = []
    for e in entries:
        if drop and e["id"] in drop:
            continue
        tp = store.translation_dir / e["rel_path"]
        md_path = tp if tp.is_file() else store.structured_dir / e["rel_path"]
        content.append(
            (
                f"{e['id']}.xhtml",
                render_document(
                    e["title"], md_path.read_text(encoding="utf-8"), lang="zh-CN", unit_id=e["id"]
                ),
            )
        )
    out = store.output_dir / "book.epub"
    build_epub(
        _pub(),
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=out,
    )
    return out


def test_provenance_happy_path(tmp_path: Path) -> None:
    """齐备工作区：零 error、覆盖率 1.0、目录不扁平。"""
    store, entries = _make_workspace(
        tmp_path,
        [
            {"id": "ch01", "rel": "body/ch01.md", "md": "# 一\n\n第一段。\n\n第二段。\n"},
            {"id": "ch02", "rel": "body/ch02.md", "md": "# 二\n\n第三章内容。\n"},
        ],
    )
    result = audit_provenance(store, entries, _build(store, entries))
    assert result.ok
    assert result.coverage == 1.0
    assert result.units_missing == [] and result.units_order_ok
    assert result.media_lost == [] and not result.toc_flat


def test_provenance_missing_unit(tmp_path: Path) -> None:
    """spine 缺单元 → E_UNIT_MISSING；放行被 provenance_incomplete 阻断。"""
    store, entries = _make_workspace(
        tmp_path,
        [
            {"id": "ch01", "rel": "body/ch01.md", "md": "# 一\n\n甲。\n"},
            {"id": "ch02", "rel": "body/ch02.md", "md": "# 二\n\n乙。\n"},
        ],
    )
    epub = _build(store, entries, drop={"ch02"})
    result = audit_provenance(store, entries, epub)
    assert result.units_missing == ["ch02"]
    assert any(f["code"] == "E_UNIT_MISSING" for f in result.findings)
    report = generate_report(
        "book",
        _audit_ok(),
        EpubcheckResult(available=False, ran=False, errors=-1, warnings=0),
        provenance=result.to_dict(),
    )
    assert not report.released and report.released_reason == "provenance_incomplete"


def test_provenance_media_lost(tmp_path: Path) -> None:
    """译文丢源文图片 → E_MEDIA_LOST。"""
    store, entries = _make_workspace(
        tmp_path,
        [
            {
                "id": "ch01",
                "rel": "body/ch01.md",
                "md": "# 一\n\n看图 ![图](media/p1.png)。\n",
                "tgt_md": "# 一\n\n看图。\n",
            }
        ],
    )
    result = audit_provenance(store, entries, _build(store, entries))
    assert any(f["code"] == "E_MEDIA_LOST" for f in result.findings)
    assert result.media_lost == ["ch01:p1.png"]


def test_provenance_coverage_gap(tmp_path: Path) -> None:
    """align 漏段 → 覆盖率 < 1.0，定位到缺段。"""
    store, entries = _make_workspace(
        tmp_path,
        [
            {
                "id": "ch01",
                "rel": "body/ch01.md",
                "md": "# 一\n\n第一段。\n\n第二段。\n",
                "align_rows": [{"seq": 1, "src": "第一段。", "tgt": "译", "note": None}],
            }
        ],
    )
    result = audit_provenance(store, entries, _build(store, entries))
    assert result.coverage == 0.5
    assert result.coverage_missing == ["ch01:2"]
    report = generate_report(
        "book",
        _audit_ok(),
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0),
        provenance=result.to_dict(),
    )
    assert not report.released and report.released_reason == "provenance_incomplete"


def test_provenance_toc_flat(tmp_path: Path) -> None:
    """源文有层级但 nav 扁平 → E_TOC_FLAT（手工替换扁平 nav 模拟）。"""
    store, entries = _make_workspace(
        tmp_path,
        [
            {"id": "ch01", "rel": "body/ch01.md", "md": "# 一\n\n甲。\n", "level": 1},
            {"id": "ch02", "rel": "body/ch02.md", "md": "# 二\n\n乙。\n", "level": 2},
        ],
    )
    epub = _build(store, entries)
    # 重写 zip：nav.xhtml 换成扁平版（模拟旧渲染/外部工具）
    flat_nav = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">\n'
        '<body>\n<nav epub:type="toc" id="toc">\n  <ol>\n'
        '      <li><a href="ch01.xhtml">一</a></li>\n'
        '      <li><a href="ch02.xhtml">二</a></li>\n'
        "  </ol>\n</nav>\n</body>\n</html>\n"
    )
    out2 = epub.with_name("flat.epub")
    with zipfile.ZipFile(epub) as zin, zipfile.ZipFile(out2, "w") as zout:
        for item in zin.infolist():
            data = (
                flat_nav.encode("utf-8")
                if item.filename.endswith("nav.xhtml")
                else zin.read(item.filename)
            )
            zout.writestr(item, data)
    result = audit_provenance(store, entries, out2)
    assert result.toc_flat
    assert any(f["code"] == "E_TOC_FLAT" for f in result.findings)
    assert result.toc_depths_expected == [1, 2] and result.toc_depths_nav == [1, 1]


def _audit_ok() -> Any:
    from auto_epublizer.qa.audit import AuditResult

    return AuditResult(ok=True)


# ── 插入内容溯源审计（pdf-content-spec §9） ────────────────────────────────


def _write_inserts(store: RunStore, records: list[Any]) -> None:
    from auto_epublizer.ingest.inserts import write_inserts

    write_inserts(store.structured_dir / "raw", records)


def test_provenance_inserts_happy_path(tmp_path: Path) -> None:
    """inserts 齐备（文件在、source 合法、描述/latex 已补）→ 零 INSERT 发现。"""
    from auto_epublizer.ingest.inserts import InsertRecord, InsertSource

    store, entries = _make_workspace(
        tmp_path, [{"id": "ch01", "rel": "body/ch01.md", "md": "# 一\n\n甲。\n"}]
    )
    media = store.structured_dir / "raw" / "media"
    media.mkdir(parents=True)
    (media / "p001-img01.png").write_bytes(b"png")
    _write_inserts(
        store,
        [
            InsertRecord(
                id="p001-img01",
                type="image",
                source=InsertSource(page=1, bbox=[0, 0, 10, 10], xref=1, method="embedded"),
                file="media/p001-img01.png",
                content_desc="示意图",
            ),
            InsertRecord(
                id="p002-fml01",
                type="formula",
                source=InsertSource(page=2, bbox=[0, 0, 10, 10], method="formula"),
                content_desc="质能方程",
                latex="E = mc^2",
            ),
        ],
    )
    result = audit_provenance(store, entries, _build(store, entries))
    assert result.ok
    assert result.inserts_total == 2
    assert result.inserts_missing_files == 0
    assert result.inserts_no_desc == 0 and result.inserts_no_latex == 0
    assert not any("INSERT" in f["code"] for f in result.findings)


def test_provenance_inserts_errors_and_warnings(tmp_path: Path) -> None:
    """缺文件/坏 source 为 error；缺描述/公式缺 latex 为 warning。"""
    from auto_epublizer.ingest.inserts import InsertRecord, InsertSource

    store, entries = _make_workspace(
        tmp_path, [{"id": "ch01", "rel": "body/ch01.md", "md": "# 一\n\n甲。\n"}]
    )
    media = store.structured_dir / "raw" / "media"
    media.mkdir(parents=True)
    (media / "p001-img01.png").write_bytes(b"png")
    _write_inserts(
        store,
        [
            InsertRecord(
                id="p001-img01",
                type="image",
                source=InsertSource(page=1, bbox=[0, 0, 10, 10], xref=1, method="embedded"),
                file="media/p001-img01.png",
                content_desc="在文件",
            ),
            InsertRecord(
                id="p002-img01",
                type="image",
                source=InsertSource(page=2, bbox=[0, 0, 10, 10], method="embedded"),
                file="media/gone.png",
                content_desc="文件缺失",
            ),
            InsertRecord(
                id="p003-img01",
                type="image",
                source=InsertSource(page=0, method="embedded"),
                content_desc="坏页号",
            ),
            InsertRecord(
                id="p004-img01",
                type="image",
                source=InsertSource(page=4, bbox=[0, 0, 10], method="embedded"),
                content_desc="坏 bbox",
            ),
            InsertRecord(
                id="p005-fml01",
                type="formula",
                source=InsertSource(page=5, method="formula"),
                content_desc="公式",
            ),
            InsertRecord(
                id="p006-img01",
                type="image",
                source=InsertSource(page=6, method="embedded"),
            ),
        ],
    )
    result = audit_provenance(store, entries, _build(store, entries))
    codes = [f["code"] for f in result.findings]
    assert "E_INSERT_MISSING_FILE" in codes
    assert "E_INSERT_BAD_SOURCE" in codes
    assert "W_INSERT_NO_LATEX" in codes
    assert "W_INSERT_NO_DESC" in codes
    assert not result.ok
    assert result.inserts_total == 6
    assert result.inserts_missing_files == 1
    assert result.inserts_no_desc == 1
    assert result.inserts_no_latex == 1


def test_report_blocks_release_on_missing_insert_files() -> None:
    """inserts 文件缺失 → prov 不完整，阻断放行（provenance_incomplete）。"""
    report = generate_report(
        "book",
        _audit_ok(),
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0),
        provenance={
            "coverage": None,
            "units_missing": [],
            "units_order_ok": True,
            "media_lost": [],
            "toc_flat": False,
            "inserts_missing_files": 2,
            "findings": [],
        },
    )
    assert report.released is False
    assert report.released_reason == "provenance_incomplete"
    assert report.inserts_missing_files == 2
