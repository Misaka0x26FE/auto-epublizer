"""通用 Markdown 结构必须在最终 XHTML 中保真。"""

import xml.etree.ElementTree as ET

import pytest

from auto_epublizer.build.html import markdown_to_xhtml


@pytest.mark.parametrize(
    ("source", "selector", "text", "attributes"),
    [
        ("**bold *italic* bold**", ".//strong/em", "italic", {}),
        (
            "[example][ref]\n\n[ref]: https://example.org",
            ".//a",
            "example",
            {"href": "https://example.org"},
        ),
        ("- parent\n  - child", ".//ul/li/ul/li", "child", {}),
        ("![alt](media/figure(1).png)", ".//img", None, {"src": "media/figure(1).png"}),
    ],
)
def test_standard_markdown_structure(source, selector, text, attributes):
    root = ET.fromstring("<root>" + markdown_to_xhtml(source) + "</root>")
    element = root.find(selector)
    assert element is not None
    assert element.text == text
    for key, value in attributes.items():
        assert element.get(key) == value


def test_note_marker_inside_code_is_literal():
    from auto_epublizer.build.html import NoteRef

    html = markdown_to_xhtml(
        "`[^ref-000001]` and [^ref-000001]",
        note_refs={"ref-000001": NoteRef("ref-000001", "n-000001", 1)},
        href_by_note={"n-000001": "ch01.xhtml"},
    )
    root = ET.fromstring('<root xmlns:epub="http://www.idpf.org/2007/ops">' + html + "</root>")
    assert root.find(".//code").text == "[^ref-000001]"
    assert len(root.findall(".//a")) == 1


def test_multiline_inline_code_is_byte_literal():
    """出版契约：代码内容逐字保留，连行内代码里的换行也不折叠成空格。"""
    literal = "start\n::: example\n[]{#literal} \\>\nend"
    root = ET.fromstring("<root>" + markdown_to_xhtml(f"**`{literal}`**") + "</root>")
    assert root.find(".//strong/code").text == literal


def test_autolink_becomes_anchor_without_angle_brackets():
    root = ET.fromstring(
        "<root>" + markdown_to_xhtml("see <https://example.org/a_b_c>") + "</root>"
    )
    anchor = root.find(".//a")
    assert anchor is not None
    assert anchor.get("href") == "https://example.org/a_b_c"
    assert anchor.text == "https://example.org/a_b_c"
    assert "<" not in (root.find(".//p").text or "")


def test_image_only_paragraph_becomes_figure_with_caption():
    root = ET.fromstring("<root>" + markdown_to_xhtml("![图注](media/a.png)") + "</root>")
    figure = root.find(".//figure")
    assert figure is not None and figure.get("class") == "imgfig"
    assert root.find(".//figure/figcaption").text == "图注"
