"""T12 硬门与豁免通道的**坏样本负向回归**测试。

覆盖审查结论 §4 点名的五条：

- T12-1 译文语言一致性：``src == tgt`` 必须是**硬缺陷**；体例豁免命中时降为
  advisory（照样报出）；页面家具（标题/图注/链接/注码定位行）不在门内。
- T12-2 非空译文字数下限：**译文为空**是硬缺陷；长度比阈值不得被升格
  （0.30 仍是 advisory 的下界）。
- T12-3 注释语义登记非空：源件有注文却没登记时，注文门**不得静默跳过**。
- T12-4 图注不得是文件名/占位词。
- T12-6 重复图检测：同一图片多处引用 → warning（供流程裁决）。

外加「单元不进目录」的结构开关（structure.csv 的 nav 列）。
"""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from auto_epublizer import orchestrator as orch
from auto_epublizer.build import nav_toc_entries
from auto_epublizer.cli import app
from auto_epublizer.qa import audit as qa_audit
from auto_translator.glossary import Glossary
from auto_translator.review.g0 import g0_unit_flags, language_identical

runner = CliRunner()


def _rows(src: str, tgt: str, seq: int = 1) -> list[dict]:
    return [{"seq": seq, "src": src, "tgt": tgt, "note": None}]


# ── T12-1 语言一致性 ────────────────────────────────────────────────────


def test_language_identical_flags_untranslated_prose() -> None:
    flags = g0_unit_flags(
        _rows(
            "This is a long English sentence that was never translated at all.",
            "This is a long English sentence that was never translated at all.",
        ),
        Glossary(),
    )
    lang = [f for f in flags if f.check == "language"]
    assert lang, [f.check for f in flags]
    assert lang[0].blocking is True


def test_language_identical_ignores_page_furniture() -> None:
    # 标题行 / 图片行 / 注码定位行 / 属性锚点行：按体例保留原文，不判漏译
    for src in (
        "# A Chapter Heading",
        "[]{#page_297}[]{#indexGroup-1}",
        "[]{#p1}![Image 1](raw/media/index-1_1.jpg)",
        "[12](ch05.xhtml#fn-n-000012)",
    ):
        assert language_identical(src, src) is False, src


def test_language_identical_ignores_chinese_target() -> None:
    assert (
        language_identical(
            "Dies ist ein langer deutscher Satz ohne Uebersetzung.",
            "这是一个完全没有翻译过来的长德语句子。",
        )
        is False
    )


def test_language_exemption_downgrades_to_advisory() -> None:
    import re

    src = "This is a long English sentence that was never translated at all."
    flags = g0_unit_flags(
        _rows(src, src),
        Glossary(),
        language_exempt=[(re.compile("^This is"), "文献著录体例：按体例保留原文")],
    )
    exempt = [f for f in flags if f.check == "language_exempt"]
    assert exempt and exempt[0].blocking is False
    assert not [f for f in flags if f.check == "language"]


def test_style_exemptions_contract(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# One\n\nAlpha text.\n\n# Two\n\nBeta text.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    p = store.preprocessing_dir / "style_exemptions.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("unit,pattern,style_ref,reason\n", encoding="utf-8")

    p.write_text(
        "unit,pattern,style_ref,reason\nch01,^Alpha,§5,文献著录体例\n",
        encoding="utf-8",
    )
    from auto_epublizer.preprocess.artifacts import read_style_exemptions

    data = read_style_exemptions(store)
    assert "ch01" in data and data["ch01"][0][1] == "文献著录体例"

    p.write_text("unit,pattern,style_ref,reason\nnope,^A,§5,x\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_style_exemptions(store)

    p.write_text("unit,pattern,style_ref,reason\nch01,^A,§5,\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_style_exemptions(store)

    p.write_text("unit,pattern,style_ref,reason\nch01,^A,§5,x\n", encoding="utf-8")
    p.write_text("unit,pattern,style_ref\nch01,^A,§5\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_style_exemptions(store)


# ── T12-2 长度下限 ──────────────────────────────────────────────────────


def test_empty_translation_is_blocking() -> None:
    flags = g0_unit_flags(
        _rows("A reasonably long English sentence that must be translated.", ""),
        Glossary(),
    )
    empty = [f for f in flags if f.check == "length" and "为空" in f.message]
    assert empty and empty[0].blocking is True


def test_length_ratio_stays_advisory() -> None:
    flags = g0_unit_flags(
        _rows(
            "A reasonably long English sentence that must be translated.",
            "村庄。",
        ),
        Glossary(),
    )
    low = [f for f in flags if f.check == "length" and "过低" in f.message]
    assert low and low[0].blocking is False


# ── T12-3 注文门不得静默跳过 ────────────────────────────────────────────


def test_unregistered_notes_block_qa(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# One\n\nAlpha text.\n\n# Two\n\nBeta text.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    # 源层有已核证注文，但 publication.json.notes 为空（没跑 notes register）
    notes_path = store.structured_dir / "notes.json"
    notes_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "source_sha256": "x",
                "inventory": "present",
                "notes": [
                    {
                        "note_id": "n-000001",
                        "scope_id": "ch01",
                        "source_label": "1",
                        "note_type": "endnote",
                        "source_locations": [],
                        "source_markdown": "note text",
                        "status": "verified",
                    }
                ],
                "references": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(orch.OrchestrationError) as e:
        orch._assert_no_unregistered_notes(store, store.load_publication())
    assert "notes register" in str(e.value)


def test_unregistered_note_markers_block(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# One\n\nAlpha text.\n\n# Two\n\nBeta text.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    rel = (store.load_publication().unit("ch01").meta or {}).get("rel_path")
    (store.structured_dir / rel).write_text("# One\n\nAlpha[^ref-000001] text.\n", encoding="utf-8")
    with pytest.raises(orch.OrchestrationError) as e:
        orch._assert_no_unregistered_notes(store, store.load_publication())
    assert "notes register" in str(e.value)


# ── T12-4 / T12-6 图注与重复图 ──────────────────────────────────────────


def _epub(tmp_path: Path, xhtml: str) -> Path:
    path = tmp_path / "book.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            "</rootfiles></container>",
        )
        zf.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>t</dc:title>'
            '<dc:language>zh-CN</dc:language><dc:identifier id="i">x</dc:identifier>'
            '<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta></metadata>'
            '<manifest><item id="c" href="content.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="img" href="media/p001.png" media-type="image/png"/></manifest>'
            '<spine><itemref idref="c"/></spine></package>',
        )
        zf.writestr("OEBPS/content.xhtml", xhtml)
        zf.writestr("OEBPS/media/p001.png", b"\x89PNG\r\n\x1a\n")
    return path


def _page(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN" lang="zh-CN">'
        '<head><meta charset="utf-8"/><title>t</title></head>'
        f"<body>{body}</body></html>"
    )


def test_caption_filename_is_error(tmp_path: Path) -> None:
    path = _epub(tmp_path, _page('<h1>t</h1><p><img src="media/p001.png" alt="p001-img01"/></p>'))
    result = qa_audit.audit_epub(path)
    assert not result.ok
    assert any(f.code == "E_CAPTION_FILENAME" for f in result.findings)


def test_caption_chinese_description_is_not_filename(tmp_path: Path) -> None:
    """中文说明文字（带数字）不是文件名，不得误报 E_CAPTION_FILENAME。

    回归背景（2026-10-21，批次 11 复查）：判据用 ``\\w`` 匹配 slug，而 ``\\w``
    在 Unicode 下**包含 CJK**，于是「1955年两名年轻女子在花丛中微笑的合影」这种
    正常中文图注被判成「文件名」，把两本书的合格成品挡在放行门外。文件名是
    ASCII 串，判据只该认 ASCII。
    """
    path = _epub(
        tmp_path,
        _page(
            '<h1>t</h1><p><img src="media/p233-img01.png" alt="1955年两名年轻女子在花丛中微笑的合影"/></p>'
        ),
    )
    result = qa_audit.audit_epub(path)
    assert not any(f.code == "E_CAPTION_FILENAME" for f in result.findings)


def test_caption_ascii_slug_with_underscore_is_error(tmp_path: Path) -> None:
    """ASCII 串（含下划线/连字符 + 数字）仍是文件名，必须照报。"""
    path = _epub(tmp_path, _page('<h1>t</h1><p><img src="media/101_1.png" alt="101_1"/></p>'))
    result = qa_audit.audit_epub(path)
    assert any(f.code == "E_CAPTION_FILENAME" for f in result.findings)


def test_caption_placeholder_is_error(tmp_path: Path) -> None:
    path = _epub(tmp_path, _page('<h1>t</h1><p><img src="media/p001.png" alt="插图"/></p>'))
    result = qa_audit.audit_epub(path)
    assert any(f.code == "E_CAPTION_PLACEHOLDER" for f in result.findings)


def test_duplicate_image_is_warning(tmp_path: Path) -> None:
    path = _epub(
        tmp_path,
        _page(
            '<h1>t</h1><p><img src="media/p001.png" alt="说明文字"/></p>'
            '<p><img src="media/p001.png" alt="另一处说明"/></p>'
        ),
    )
    result = qa_audit.audit_epub(path)
    assert any(f.code == "W_IMAGE_DUPLICATE" for f in result.findings)


# ── 单元不进目录（structure.csv 的 nav 列） ───────────────────────────────


def test_nav_false_excludes_unit_from_nav(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# One\n\nAlpha text.\n\n# Two\n\nBeta text.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    p = store.preprocessing_dir / "structure.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "id": u.id,
            "region": (u.meta or {}).get("region", "body"),
            "kind": u.kind,
            "title": u.title,
            "level": 1,
            "rel_path": (u.meta or {}).get("rel_path", ""),
            "nav": "no" if u.id == "ch02" else "yes",
        }
        for u in store.load_publication().units
    ]
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["id", "region", "kind", "title", "level", "rel_path", "nav"]
        )
        w.writeheader()
        w.writerows(rows)
    orch.restructure(store)
    entries = orch.structure_entries(store)
    assert [e["id"] for e in entries if e["nav"] is False] == ["ch02"]
    nav = nav_toc_entries(entries, 3)
    assert [e["id"] for e in nav] == ["ch01"]


def test_nav_column_contract_rejects_bad_value(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# One\n\nAlpha text.\n\n# Two\n\nBeta text.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    p = store.preprocessing_dir / "structure.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "id": u.id,
            "region": (u.meta or {}).get("region", "body"),
            "kind": u.kind,
            "title": u.title,
            "level": 1,
            "rel_path": (u.meta or {}).get("rel_path", ""),
            "nav": "maybe",
        }
        for u in store.load_publication().units
    ]
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["id", "region", "kind", "title", "level", "rel_path", "nav"]
        )
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(orch.OrchestrationError) as e:
        orch.restructure(store)
    assert "nav 非法" in str(e.value)


def test_cli_restructure_accepts_nav_column(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# One\n\nAlpha text.\n\n# Two\n\nBeta text.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    p = store.preprocessing_dir / "structure.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "id": u.id,
            "region": (u.meta or {}).get("region", "body"),
            "kind": u.kind,
            "title": u.title,
            "level": 1,
            "rel_path": (u.meta or {}).get("rel_path", ""),
            "nav": "no" if u.id == "ch02" else "yes",
        }
        for u in store.load_publication().units
    ]
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["id", "region", "kind", "title", "level", "rel_path", "nav"]
        )
        w.writeheader()
        w.writerows(rows)
    res = runner.invoke(app, ["restructure", "--workspace", str(store.dir)])
    assert res.exit_code == 0, res.output
    assert "结构已登记" in res.output
