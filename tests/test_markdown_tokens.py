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


def test_code_in_image_alt_is_text_not_markup():
    """alt/图注是属性与纯文本：行内代码只能贡献文字，不能带标记进属性。"""
    md = "![see `x < y` here](media/a.png)"
    root = ET.fromstring("<root>" + markdown_to_xhtml(md) + "</root>")
    assert root.find(".//figcaption").text == "see x < y here"
    assert root.find(".//img").get("alt") == "see x < y here"
    assert root.find(".//figcaption/code") is None


def test_private_use_text_cannot_collide_with_code():
    """正文出现私用区字符时，代码占位符不得把它当成自己的编号。"""
    root = ET.fromstring("<root>" + markdown_to_xhtml("\ue0001\ue000 与 `code`") + "</root>")
    assert root.find(".//code").text == "code"
    assert "\ue0001\ue000" in "".join(root.itertext())


def test_backticks_in_link_destination_are_not_code():
    """链接地址里的反引号是 URL 字符，不得先被当成代码跨度抽走。"""
    md = "[label](https://example.org/a`b`)"
    root = ET.fromstring("<root>" + markdown_to_xhtml(md) + "</root>")
    anchor = root.find(".//a")
    assert anchor is not None
    href = anchor.get("href")
    assert href.startswith("https://example.org/a") and "%EE%80%80" not in href.upper()
    assert "\ue000" not in href
    assert root.find(".//code") is None


@pytest.mark.parametrize(
    "source",
    [
        "## 见 [手册][ref]\n\n[ref]: https://example.org/manual",
        "| 列 | 值 |\n|---|---|\n| 见 [手册][ref] | 1 |\n\n[ref]: https://example.org/manual",
        "| 见 [手册][ref]\n\n[ref]: https://example.org/manual",
        "1. 见 [手册][ref]\n2. 另一条\n\n[ref]: https://example.org/manual",
    ],
)
def test_reference_links_resolve_in_publication_blocks(source):
    """引用式链接定义是全文档级的：标题/表格/诗行/有序列表块都要共享 env。"""
    root = ET.fromstring("<root>" + markdown_to_xhtml(source) + "</root>")
    anchor = root.find(".//a")
    assert anchor is not None
    assert anchor.get("href") == "https://example.org/manual"
    assert anchor.text == "手册"


def test_reference_link_in_heading_keeps_only_visible_label():
    """nav/`<title>` 是纯文本：引用式链接只保留标签，`[ref]` 不得漏进目录。"""
    from auto_epublizer.build.html import plain_label

    assert plain_label("小节 [手册][ref]") == "小节 手册"
    assert plain_label("[手册][]") == "手册"
    root = ET.fromstring(
        "<root>"
        + markdown_to_xhtml("## 小节 [手册][ref]\n\n[ref]: https://example.org/manual")
        + "</root>"
    )
    assert root.find(".//h2/a").text == "手册"
