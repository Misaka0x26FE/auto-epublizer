"""注释门媒体身份回归（增量审查 F4/F5 + §7.2）：真实临时 ZIP，不经构建渲染函数。

- F4：同名不同目录是两张图——`a/same.png` 期待不得被 `media/b/same.png` 冒充；
- F5：渲染 URL 可能 URI 转义（中文文件名），须统一到包内成员身份域，不得误报缺失；
- §7.2：注文 Markdown 里内嵌 HTML `<img>` 时，内容核对不得误报（媒体由专用核对负责）。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from auto_epublizer.qa.notes_audit import audit_notes_epub

_NOTE_ID = "n-000001"
_REF_ID = "ref-000001"
_UNIT = "ch01"
_SRC_DIGEST = "0" * 64


def _src_notes(source_markdown: str) -> dict:
    return {
        "schema_version": "1",
        "source_sha256": "1" * 64,
        "inventory": "present",
        "notes": [
            {
                "note_id": _NOTE_ID,
                "scope_id": _UNIT,
                "source_label": "1",
                "note_type": "footnote",
                "source_markdown": source_markdown,
                "source_locations": [{"kind": "page", "page": 3}],
                "status": "verified",
            }
        ],
        "references": [
            {
                "ref_id": _REF_ID,
                "note_id": _NOTE_ID,
                "unit": _UNIT,
                "scope_id": _UNIT,
                "label_text": "1",
                "status": "verified",
            }
        ],
    }


def _tgt_notes(target_markdown: str) -> dict:
    return {
        "schema_version": "1",
        "source_notes_sha256": _SRC_DIGEST,
        "notes": [{"note_id": _NOTE_ID, "target_markdown": target_markdown}],
    }


def _make_epub(tmp_path: Path, *, aside_html: str, media: dict[str, bytes]) -> Path:
    """最小成品：一个内容文档（noteref + aside + 回链）+ 给定媒体成员。"""
    body = (
        '<p>第一句话<a epub:type="noteref" role="doc-noteref" '
        f'id="{_REF_ID}" href="ch01.xhtml#fn-{_NOTE_ID}">[1]</a>。</p>\n'
        f'<aside epub:type="footnote" id="fn-{_NOTE_ID}">\n'
        f"<p>{aside_html} "
        f'<a epub:type="backlink" role="doc-backlink" href="ch01.xhtml#{_REF_ID}">↩</a></p>\n'
        "</aside>\n"
    )
    page = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
        f"<head><title>Ch</title></head><body>{body}</body></html>"
    )
    epub = tmp_path / "book.epub"
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("OEBPS/ch01.xhtml", page)
        for name, data in media.items():
            zf.writestr(f"OEBPS/{name}", data)
    return epub


def _codes(result) -> list[str]:
    return [f["code"] for f in result.findings]


def test_same_basename_different_dir_is_not_accepted(tmp_path: Path) -> None:
    """F4：期待 `a/same.png`、aside 实渲染 `media/b/same.png`（包内只有 B）→ 必须报缺图。"""
    note_md = "带图注文 ![x](media/a/same.png)。"
    epub = _make_epub(
        tmp_path,
        aside_html='<img src="media/b/same.png" alt="x"/>',
        media={"media/b/same.png": b"PNG-B"},
    )
    result = audit_notes_epub(
        epub,
        source_notes=_src_notes(note_md),
        target_notes=_tgt_notes("带图注文 ![x](media/a/same.png)。"),
    )
    assert "E_NOTES_MEDIA_MISSING" in _codes(result), result.findings


def test_url_encoded_chinese_filename_is_accepted(tmp_path: Path) -> None:
    """F5：渲染 URL 为 URI 转义、包内是原名 → 统一到成员身份域后不得误报。"""
    epub = _make_epub(
        tmp_path,
        aside_html='<img src="media/%E4%B8%AD%E6%96%87.png" alt="x"/> 带图注文。',
        media={"media/中文.png": b"PNG-CN"},
    )
    result = audit_notes_epub(
        epub,
        source_notes=_src_notes("带图注文 ![x](media/中文.png)。"),
        target_notes=_tgt_notes("带图注文 ![x](media/中文.png)。"),
    )
    assert _codes(result) == [], result.findings


def test_html_img_in_note_markdown_not_content_mismatch(tmp_path: Path) -> None:
    """§7.2：注文 Markdown 内嵌 HTML `<img>` → 内容核对不误报（媒体由专用核对负责）。"""
    html_note = '<img src="media/pic.png" alt="x"/> 图的说明。'
    epub = _make_epub(
        tmp_path,
        aside_html='<img src="media/pic.png" alt="x"/> 图的说明。',
        media={"media/pic.png": b"PNG"},
    )
    result = audit_notes_epub(
        epub,
        source_notes=_src_notes(html_note),
        target_notes=_tgt_notes(html_note),
    )
    assert _codes(result) == [], result.findings


def test_media_absent_from_package_is_flagged(tmp_path: Path) -> None:
    """负对照：aside 渲染了图但包内无该成员 → E_NOTES_MEDIA_ABSENT。"""
    epub = _make_epub(tmp_path, aside_html='<img src="media/nope.png" alt="x"/>', media={})
    result = audit_notes_epub(
        epub,
        source_notes=_src_notes("带图注文 ![x](media/nope.png)。"),
        target_notes=_tgt_notes("带图注文 ![x](media/nope.png)。"),
    )
    assert "E_NOTES_MEDIA_ABSENT" in _codes(result), result.findings


def test_missing_media_reported_even_when_target_notes_absent(tmp_path: Path) -> None:
    """源文回退模式（无译注）：媒体期待取 source_markdown，缺图仍须阻断。"""
    epub = _make_epub(tmp_path, aside_html="纯文本，无图", media={})
    result = audit_notes_epub(
        epub,
        source_notes=_src_notes("带图注文 ![x](media/a/same.png)。"),
        target_notes=None,
    )
    assert "E_NOTES_MEDIA_MISSING" in _codes(result), result.findings


def test_source_notes_reference_label_consistency_kept(tmp_path: Path) -> None:
    """不回归：正常一注一引（含图）仍通过（正对照与 F4/F5 相邻合法用例）。"""
    note_md = "带图注文 ![x](media/a/same.png)。"
    epub = _make_epub(
        tmp_path,
        aside_html='<img src="media/a/same.png" alt="x"/> 带图注文。',
        media={"media/a/same.png": b"PNG"},
    )
    result = audit_notes_epub(
        epub,
        source_notes=_src_notes(note_md),
        target_notes=_tgt_notes(note_md),
    )
    assert _codes(result) == [], result.findings


def test_json_dumps_not_required() -> None:
    """占位：确保模块可独立导入（避免测试收集期因未用导入失败）。"""
    assert json.dumps({"ok": True}) == '{"ok": true}'
