# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""注文媒体身份：真实 collect_media → render_document → build_epub 消费者回归。"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from auto_common.workspace import Publication, PublicationMeta, Unit
from auto_epublizer.build import build_epub, collect_media
from auto_epublizer.build.html import NoteItem, NoteRef, render_document
from auto_epublizer.qa import audit_epub
from auto_epublizer.qa.notes_audit import NotesAuditResult, audit_notes_epub, epub_render_mode

_NOTE_ID = "n-000001"
_REF_ID = "ref-000001"
_UNIT = "ch01"


def _src_notes(source_markdown: str) -> dict[str, Any]:
    """创建最小已登记一注一引。"""
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


def _tgt_notes(target_markdown: str) -> dict[str, Any]:
    """创建参与构建的译注记录。"""
    return {
        "schema_version": "1",
        "source_notes_sha256": "0" * 64,
        "notes": [{"note_id": _NOTE_ID, "target_markdown": target_markdown}],
    }


def _write_media(root: Path, name: str, data: bytes = b"PNG") -> None:
    """写入临时源资源。"""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@pytest.fixture
def media_root(tmp_path: Path) -> Path:
    """使用与生产相同的源媒体根布局。"""
    root = tmp_path / "structured" / "raw" / "media"
    root.mkdir(parents=True)
    return root


def _production_epub(
    tmp_path: Path,
    media_root: Path,
    note_md: str,
    *,
    package_media: bool = True,
) -> tuple[Path, list[str]]:
    """通过收集、注文渲染和真实打包生成临时 EPUB。"""
    rewritten, media, dropped = collect_media(note_md, media_root)
    page = render_document(
        "第一章",
        f"正文[^{_REF_ID}]。",
        lang="zh-CN",
        unit_id=_UNIT,
        note_refs={_REF_ID: NoteRef(_REF_ID, _NOTE_ID, 1)},
        note_items=[NoteItem(_NOTE_ID, 1, rewritten, (f"{_UNIT}.xhtml#{_REF_ID}",))],
        href_by_note={_NOTE_ID: f"{_UNIT}.xhtml"},
    )
    pub = Publication(
        slug="book",
        meta=PublicationMeta(title="测试书", creator="作者", target_language="zh-CN"),
        units=[Unit(id=_UNIT, kind="chapter", title="第一章")],
    )
    epub = build_epub(
        pub,
        [{"id": _UNIT, "region": "body", "title": "第一章"}],
        [(f"{_UNIT}.xhtml", page)],
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "book.epub",
        media_files=media if package_media else [],
    )
    return epub, dropped


def _audit(epub: Path, root: Path, md: str, *, translated: bool = True) -> NotesAuditResult:
    """以原始登记文本审计，不使用改写后的 Markdown 重建期望。"""
    return audit_notes_epub(
        epub,
        source_notes=_src_notes(md),
        target_notes=_tgt_notes(md) if translated else None,
        media_root=root,
    )


def _codes(result: NotesAuditResult) -> set[str]:
    """取审计错误码。"""
    return {finding["code"] for finding in result.findings}


@pytest.mark.parametrize(
    ("ref", "name"),
    [
        ("pic.png", "pic.png"),
        ("中文.png", "中文.png"),
        ("sub/中文.png", "sub/中文.png"),
        ("media/sub/pic.png", "sub/pic.png"),
        ("raw/media/sub/pic.png", "sub/pic.png"),
        ("./raw/media/sub/pic.png", "sub/pic.png"),
        ("old/location/pic.png", "pic.png"),
        ("a (1).png", "a (1).png"),
        ("%41.png", "%41.png"),
        ("A.png", "A.png"),
    ],
)
def test_source_paths_survive_production_chain(
    tmp_path: Path, media_root: Path, ref: str, name: str
) -> None:
    """所有原收集器合法路由保持有效，源路径与 URL 编码不混用。"""
    _write_media(media_root, name)
    md = f"带图注文 ![x]({ref})。"
    epub, dropped = _production_epub(tmp_path, media_root, md)
    assert dropped == []
    with zipfile.ZipFile(epub) as archive:
        assert archive.read(f"OEBPS/media/{name}") == b"PNG"
        page = archive.read("OEBPS/ch01.xhtml").decode()
        assert f'src="media/{quote(name)}"' in page
    result = _audit(epub, media_root, md)
    assert result.ok, result.findings
    general = audit_epub(epub)
    assert general.ok, general.findings


@pytest.mark.parametrize(
    ("src", "name"),
    [
        ("pic.png", "pic.png"),
        ("media/中文.png", "中文.png"),
        ("media/%E4%B8%AD%E6%96%87.png", "中文.png"),
        ("raw/media/sub/%E4%B8%AD%E6%96%87.png", "sub/中文.png"),
        ("media/%2541.png", "%41.png"),
        ("media/%41.png", "A.png"),
        ("media/a%20%281%29.png", "a (1).png"),
        ("media/pic.png?width=20&amp;height=30#fragment", "pic.png"),
    ],
)
def test_html_image_urls_are_decoded_once(
    tmp_path: Path, media_root: Path, src: str, name: str
) -> None:
    """HTML URL 解码一次，转成 Markdown 后不得再次按源路径收集。"""
    _write_media(media_root, name)
    md = f'<img src="{src}" alt="x"/> 图的说明。'
    epub, dropped = _production_epub(tmp_path, media_root, md)
    assert dropped == []
    result = _audit(epub, media_root, md)
    assert result.ok, result.findings


def test_html_figure_and_placeholder_keep_encoded_identity(
    tmp_path: Path, media_root: Path
) -> None:
    """figure 包裹和 pandoc 占位也只收集一次。"""
    _write_media(media_root, "中文.png")
    _write_media(media_root, "%41.png")
    md = (
        '<figure><a href="x"><img src="raw/media/%E4%B8%AD%E6%96%87.png"/></a></figure>'
        '\n\n[x]{.image .placeholder original-image-src="raw/media/%41.png"}'
    )
    rewritten, media, dropped = collect_media(md, media_root)
    assert dropped == []
    assert dict(media) == {"media/中文.png": b"PNG", "media/%41.png": b"PNG"}
    assert "media/%2541.png" in rewritten
    assert "media/%E4%B8%AD%E6%96%87.png" in rewritten


@pytest.mark.parametrize("html", [False, True])
def test_same_basename_different_dir_is_not_accepted(
    tmp_path: Path, media_root: Path, html: bool
) -> None:
    """完整目录身份不可用 basename 集合补偿。"""
    _write_media(media_root, "a/same.png", b"PNG-A")
    _write_media(media_root, "b/same.png", b"PNG-B")
    expected = '<img src="a/same.png"/>' if html else "![x](a/same.png)"
    actual = '<img src="b/same.png"/>' if html else "![x](b/same.png)"
    epub, dropped = _production_epub(tmp_path, media_root, actual)
    assert dropped == []
    result = _audit(epub, media_root, expected)
    assert "E_NOTES_MEDIA_MISSING" in _codes(result), result.findings


@pytest.mark.parametrize(("expected", "actual"), [("%41.png", "A.png"), ("A.png", "%41.png")])
def test_literal_percent_and_decoded_name_cannot_impersonate_each_other(
    tmp_path: Path, media_root: Path, expected: str, actual: str
) -> None:
    """同时存在的字面百分号文件和解码名必须保持不同身份。"""
    _write_media(media_root, "%41.png", b"LITERAL")
    _write_media(media_root, "A.png", b"DECODED")
    epub, dropped = _production_epub(tmp_path, media_root, f"![x]({actual})")
    assert dropped == []
    result = _audit(epub, media_root, f"![x]({expected})")
    assert "E_NOTES_MEDIA_MISSING" in _codes(result), result.findings


def test_literal_percent_and_decoded_name_both_survive_packaging(
    tmp_path: Path, media_root: Path
) -> None:
    """同一注文同时引用两个资源，URL、ZIP 名和字节均须保持不同。"""
    _write_media(media_root, "%41.png", b"LITERAL")
    _write_media(media_root, "A.png", b"DECODED")
    md = "![x](%41.png)\n\n![y](A.png)"
    epub, dropped = _production_epub(tmp_path, media_root, md)
    assert dropped == []
    with zipfile.ZipFile(epub) as archive:
        assert archive.read("OEBPS/media/%41.png") == b"LITERAL"
        assert archive.read("OEBPS/media/A.png") == b"DECODED"
        page = archive.read("OEBPS/ch01.xhtml").decode()
        assert 'src="media/%2541.png"' in page
        assert 'src="media/A.png"' in page
    result = _audit(epub, media_root, md)
    assert result.ok, result.findings


def test_zip_member_names_are_literal(tmp_path: Path, media_root: Path) -> None:
    """ZIP 中的 %41 不得经第二次解码冒充 A。"""
    _write_media(media_root, "A.png")
    md = "![x](A.png)"
    epub, dropped = _production_epub(tmp_path, media_root, md)
    assert dropped == []
    tampered = tmp_path / "wrong-member.epub"
    with zipfile.ZipFile(epub) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            name = "OEBPS/media/%41.png" if info.filename == "OEBPS/media/A.png" else info.filename
            target.writestr(name, source.read(info))
    result = _audit(tampered, media_root, md)
    assert "E_NOTES_MEDIA_ABSENT" in _codes(result), result.findings
    assert {"E_MANIFEST_HREF", "E_IMG_SRC"} <= {
        finding.code for finding in audit_epub(tampered).findings
    }


def test_encoded_url_lookalike_is_not_a_literal_zip_member(
    tmp_path: Path, media_root: Path
) -> None:
    """编码 URL 的原样 ZIP 名不能冒充一次解码后的百分号文件。"""
    _write_media(media_root, "%41.png")
    epub, _ = _production_epub(tmp_path, media_root, "![x](%41.png)")
    tampered = tmp_path / "encoded-lookalike.epub"
    with zipfile.ZipFile(epub) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            name = (
                "OEBPS/media/%2541.png" if info.filename == "OEBPS/media/%41.png" else info.filename
            )
            target.writestr(name, source.read(info))
    assert {"E_MANIFEST_HREF", "E_IMG_SRC"} <= {
        finding.code for finding in audit_epub(tampered).findings
    }


def test_media_absent_from_package_is_flagged(tmp_path: Path, media_root: Path) -> None:
    """渲染含图片但打包漏资源，必须阻断。"""
    _write_media(media_root, "pic.png")
    md = "![x](pic.png)"
    epub, dropped = _production_epub(tmp_path, media_root, md, package_media=False)
    assert dropped == []
    result = _audit(epub, media_root, md)
    assert "E_NOTES_MEDIA_ABSENT" in _codes(result), result.findings


@pytest.mark.parametrize("translated", [False, True])
def test_missing_source_cannot_be_hidden_by_rendered_image(
    tmp_path: Path, media_root: Path, translated: bool
) -> None:
    """源资源缺失时即使成品已有图，源文回退和译注都必须阻断。"""
    _write_media(media_root, "%41.png")
    _write_media(media_root, "A.png")
    md = "![x](%41.png)"
    epub, dropped = _production_epub(tmp_path, media_root, md)
    assert dropped == []
    (media_root / "%41.png").unlink()
    result = _audit(epub, media_root, md, translated=translated)
    assert "E_NOTES_MEDIA_MISSING" in _codes(result), result.findings


@pytest.mark.parametrize("symlink", [False, True])
def test_outside_media_root_is_not_read(tmp_path: Path, media_root: Path, symlink: bool) -> None:
    """越界相对路径和符号链接不得读取外部媒体。"""
    external = tmp_path / "secret.png"
    external.write_bytes(b"SECRET")
    if symlink:
        (media_root / "escape.png").symlink_to(external)
        ref = "escape.png"
    else:
        ref = "../../../secret.png"
    md = f"![x]({ref})"
    epub, dropped = _production_epub(tmp_path, media_root, md)
    assert dropped == [ref]
    with zipfile.ZipFile(epub) as archive:
        assert not any(name.startswith("OEBPS/media/") for name in archive.namelist())
    result = _audit(epub, media_root, md)
    assert "E_NOTES_MEDIA_MISSING" in _codes(result), result.findings


@pytest.mark.parametrize("mode", ["source", "translation", "invalid", ""])
def test_epub_render_mode_reads_container_selected_opf(tmp_path: Path, mode: str) -> None:
    """只读 container 指向的 OPF；非法或缺失模式返回 None。"""
    epub = tmp_path / "mode.epub"
    container = (
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="custom/package.opf"/></rootfiles></container>'
    )
    meta = f'<meta property="aep:render-mode">{mode}</meta>' if mode else ""
    opf = f'<package xmlns="http://www.idpf.org/2007/opf"><metadata>{meta}</metadata></package>'
    with zipfile.ZipFile(epub, "w") as archive:
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("custom/package.opf", opf)
        archive.writestr("OEBPS/content.opf", "not the selected OPF")
    assert epub_render_mode(epub) == (mode if mode in {"source", "translation"} else None)


def test_epub_render_mode_missing_or_malformed_metadata(tmp_path: Path) -> None:
    """旧成品、缺失及损坏包都不猜测模式。"""
    epub = tmp_path / "broken.epub"
    assert epub_render_mode(epub) is None
    epub.write_bytes(b"not a ZIP")
    assert epub_render_mode(epub) is None
    with zipfile.ZipFile(epub, "w") as archive:
        archive.writestr("META-INF/container.xml", "<broken")
    assert epub_render_mode(epub) is None
