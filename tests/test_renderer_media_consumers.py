"""Consumer regressions for literal code/table text and packaged inline SVG."""

from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from auto_common.workspace import Publication, PublicationMeta
from auto_epublizer.build import build_epub, collect_media
from auto_epublizer.build.html import render_document, subheading_anchors
from auto_epublizer.media_paths import epub_member_path
from auto_epublizer.qa.audit import audit_epub

XHTML = "{http://www.w3.org/1999/xhtml}"
SVG = "{http://www.w3.org/2000/svg}"
OPF = "{http://www.idpf.org/2007/opf}"
XLINK = "{http://www.w3.org/1999/xlink}"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)


def _package(tmp_path: Path, md: str, media: list[tuple[str, bytes]] | None = None) -> Path:
    pub = Publication(slug="book", meta=PublicationMeta(title="Book", language="en"))
    return build_epub(
        pub,
        [
            {
                "id": "ch01",
                "kind": "chapter",
                "region": "body",
                "title": "Book",
                "anchors": subheading_anchors(md, "ch01"),
            }
        ],
        [("ch01.xhtml", render_document("Book", md, lang="en", unit_id="ch01"))],
        lang="en",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "book.epub",
        media_files=media,
    )


def test_table_hashes_survive_packaging_and_audit(tmp_path: Path) -> None:
    out = _package(tmp_path, "# Book\n\n| Number | Code |\n| --- | --- |\n| # 1 | `# comment` |\n")
    with zipfile.ZipFile(out) as zf:
        root = ET.fromstring(zf.read("OEBPS/ch01.xhtml"))
    cells = root.findall(f".//{XHTML}td")
    assert ["".join(cell.itertext()) for cell in cells] == ["# 1", "# comment"]
    assert cells[1].find(f"{XHTML}code") is not None
    audit = audit_epub(out)
    assert audit.ok
    assert not [f for f in audit.findings if f.code == "W_RESIDUE"]


@pytest.mark.parametrize("fence", ["```", "```html", "~~~html", "````html"])
def test_html_code_is_visible_and_not_navigation(tmp_path: Path, fence: str) -> None:
    closing = fence[: len(fence) - len(fence.lstrip("`~"))]
    code = (
        "<div>\n\n## not a heading\n::: example\n\\\n"
        "[^literal]: not a footnote\n"
        "<script>alert(1)</script>\n</div>"
    )
    md = f"# Book\n{fence}\n{code}\n{closing}\n## Real heading\nBody.\n"
    out = _package(tmp_path, md)
    with zipfile.ZipFile(out) as zf:
        root = ET.fromstring(zf.read("OEBPS/ch01.xhtml"))
        nav = ET.fromstring(zf.read("OEBPS/nav.xhtml"))
    rendered = root.find(f".//{XHTML}pre/{XHTML}code")
    assert rendered is not None
    assert rendered.text == code + "\n"
    assert root.find(f".//{XHTML}script") is None
    assert root.find(f".//{XHTML}div") is None
    real_heading = root.find(f".//{XHTML}h2")
    assert real_heading is not None and real_heading.text == "Real heading"
    assert any(
        a.get("href") == "ch01.xhtml#" + real_heading.attrib["id"] for a in nav.iter(f"{XHTML}a")
    )
    assert "not a heading" not in "".join(nav.itertext())
    assert not [f for f in audit_epub(out).findings if f.code == "W_RESIDUE"]


@pytest.mark.parametrize("attribute", ["href", "xlink:href"])
def test_inline_svg_packages_image_identity(tmp_path: Path, attribute: str) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    filename = "cover 100%2F & art.png"
    (media_root / filename).write_bytes(PNG)
    md = (
        "# Book\n\n```{=html}\n"
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1 1">\n'
        f'<image width="1" height="1" {attribute}="cover%20100%252F%20%26%20art.png"/>\n'
        "</svg>\n```\n"
    )
    rewritten, media, dropped = collect_media(md, media_root)
    assert not dropped
    out = _package(tmp_path, rewritten, media)
    with zipfile.ZipFile(out) as zf:
        root = ET.fromstring(zf.read("OEBPS/ch01.xhtml"))
        opf = ET.fromstring(zf.read("OEBPS/content.opf"))
        item = next(i for i in opf.iter(f"{OPF}item") if i.get("href") == "ch01.xhtml")
        assert "svg" in item.get("properties", "").split()
        image = root.find(f".//{SVG}image")
        assert image is not None
        href = image.attrib[XLINK + "href" if attribute == "xlink:href" else "href"]
        member = epub_member_path("OEBPS/ch01.xhtml", href)
        assert member == f"OEBPS/media/{filename}"
        assert zf.read(member) == PNG
        assert any(
            epub_member_path("OEBPS/content.opf", i.attrib["href"]) == member
            for i in opf.iter(f"{OPF}item")
        )
    assert audit_epub(out).ok


def test_svg_missing_image_is_not_silently_removed(tmp_path: Path) -> None:
    md = '# Book\n\n```{=html}\n<svg xmlns="http://www.w3.org/2000/svg"><image href="missing.png"/></svg>\n```'
    rewritten, media, dropped = collect_media(md, tmp_path)
    assert dropped == ["missing.png"]
    out = _package(tmp_path, rewritten, media)
    audit = audit_epub(out)
    assert not audit.ok
    assert any(f.code == "E_IMG_SRC" for f in audit.findings)


def test_svg_does_not_read_outside_media_root(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    outside = tmp_path / "private.png"
    outside.write_bytes(PNG)
    (media_root / "escape.png").symlink_to(outside)
    md = '```{=html}\n<svg xmlns="http://www.w3.org/2000/svg"><image href="escape.png"/></svg>\n```'
    _, media, dropped = collect_media(md, media_root)
    assert media == []
    assert dropped == ["escape.png"]


@pytest.mark.parametrize("wrapper", ["`", "``", "```\n", "~~~html\n"])
def test_displayed_image_code_does_not_collect_media(tmp_path: Path, wrapper: str) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    (media_root / "existing.png").write_bytes(PNG)
    code = '![literal](existing.png) <image href="missing.png"/> []{#literal} \\> ::: example'
    closing = wrapper.strip().replace("html", "")
    if "\n" in wrapper:
        md = f"# Book\n\n{wrapper}{code}\n{closing}\n"
        expected = code + "\n"
    else:
        md = f"# Book\n\nExample: {wrapper}{code}{closing}.\n"
        expected = code
    rewritten, media, dropped = collect_media(md, media_root)
    assert rewritten == md
    assert not media and not dropped
    out = _package(tmp_path, rewritten, media)
    with zipfile.ZipFile(out) as zf:
        root = ET.fromstring(zf.read("OEBPS/ch01.xhtml"))
        opf = ET.fromstring(zf.read("OEBPS/content.opf"))
    rendered = root.find(f".//{XHTML}code")
    assert rendered is not None and rendered.text == expected
    assert root.find(f".//{XHTML}img") is None
    assert root.find(f".//{SVG}image") is None
    assert root.find(f".//{XHTML}a[@id='literal']") is None
    item = next(i for i in opf.iter(f"{OPF}item") if i.get("href") == "ch01.xhtml")
    assert "svg" not in item.get("properties", "").split()
    assert audit_epub(out).ok


def test_pandoc_fragmented_svg_is_packaged_as_real_cover(tmp_path: Path) -> None:
    (tmp_path / "cover.png").write_bytes(PNG)
    md = (
        '```{=html}\n<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1 1">\n```\n'
        '`<image width="1" height="1" xlink:href="cover.png">`{=html}'
        "`</image>`{=html}\n"
        "```{=html}\n</svg>\n```\n"
    )
    rewritten, media, dropped = collect_media(md, tmp_path)
    assert not dropped
    out = build_epub(
        Publication(slug="book", meta=PublicationMeta(title="Book", language="en")),
        [
            {"id": "cover", "kind": "cover", "region": "front", "title": "Cover"},
            {"id": "ch01", "kind": "chapter", "region": "body", "title": "Book"},
        ],
        [
            ("cover.xhtml", render_document("Cover", rewritten, lang="en")),
            ("ch01.xhtml", render_document("Book", "# Book\n\nBody.", lang="en")),
        ],
        media_files=media,
        cover_media="media/cover.png",
        lang="en",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "cover.epub",
    )
    with zipfile.ZipFile(out) as zf:
        root = ET.fromstring(zf.read("OEBPS/cover.xhtml"))
        opf = ET.fromstring(zf.read("OEBPS/content.opf"))
        item = next(i for i in opf.iter(f"{OPF}item") if i.get("href") == "cover.xhtml")
        assert "svg" in item.get("properties", "").split()
        image = root.find(f".//{SVG}image")
        assert image is not None
        member = epub_member_path("OEBPS/cover.xhtml", image.attrib[XLINK + "href"])
        assert member == "OEBPS/media/cover.png"
        assert zf.read(member) == PNG
    assert audit_epub(out).ok


def test_inline_code_context_preserves_multiline_literals(tmp_path: Path) -> None:
    literal = "start\n::: example\n[]{#literal} \\>\nend"
    out = _package(tmp_path, f"# Book\n\n**`{literal}`**\n")
    with zipfile.ZipFile(out) as zf:
        root = ET.fromstring(zf.read("OEBPS/ch01.xhtml"))
    code = root.find(f".//{XHTML}strong/{XHTML}code")
    assert code is not None and code.text == literal
    assert root.find(f".//{XHTML}a[@id='literal']") is None
    assert audit_epub(out).ok


def test_unbound_svg_xlink_is_rejected_not_repaired(tmp_path: Path) -> None:
    md = (
        "# Book\n\n```{=html}\n"
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<image xlink:href="cover.png"/></svg>\n```'
    )
    with pytest.raises(ET.ParseError, match="unbound prefix"):
        _package(tmp_path, md)
