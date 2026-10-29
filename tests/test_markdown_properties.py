# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""Markdown 渲染的性质测试：任意输入都必须产出良构 XHTML，代码内容逐字保真。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from auto_epublizer.build.html import markdown_to_xhtml

ROOT = '<root xmlns:epub="http://www.idpf.org/2007/ops">'

# 任意可打印文本（排除代理项与控制字符，它们在 XML 里本就非法）。
ANY_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc")),
    max_size=120,
)

# 代码跨度可能包含的“危险”字符：强调、链接、锚点、原始 HTML 语法都必须按字面保留。
CODE_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc"), blacklist_characters="`"),
    min_size=1,
    max_size=40,
)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(ANY_TEXT)
def test_any_text_renders_well_formed_xhtml(text: str) -> None:
    html = markdown_to_xhtml(text)
    ET.fromstring(ROOT + html + "</root>")
    assert markdown_to_xhtml(text) == html, "同一输入的渲染必须确定"


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(CODE_TEXT)
def test_code_span_keeps_literal_content(literal: str) -> None:
    root = ET.fromstring(ROOT + markdown_to_xhtml(f"前 `{literal}` 后") + "</root>")
    code = root.find(".//code")
    assert code is not None
    assert (code.text or "") == literal


@settings(max_examples=40, deadline=None)
@given(st.text(alphabet="标题内容 abc#*-", min_size=1, max_size=20))
def test_heading_is_never_swallowed_by_paragraph(text: str) -> None:
    root = ET.fromstring(ROOT + markdown_to_xhtml(f"# {text}") + "</root>")
    headings = root.findall(".//h1")
    assert len(headings) == 1
