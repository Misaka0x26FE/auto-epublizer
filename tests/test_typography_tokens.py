# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""版式参数的字节锁定：任何有意改变样式都必须显式更新常量与基线。

摘要值取自 2026-11-10（E4：EPUB 去 font-family、PDF 字体栈与封面/colophon CSS）
的实际输出。改动样式时须重新登记 ``tests/fixtures/typography/baseline.json``，
不允许「顺手」重录。
"""

from __future__ import annotations

import hashlib

import pytest

from auto_epublizer.build import _STYLE_CSS, theme_css
from auto_epublizer.pdfexport import PrintStyle
from auto_epublizer.typography import EPUB_THEMES, PRINT, css_number, em_number

#: 提取前（56720e7）三套主题 CSS 的 sha256
THEME_SHA256 = {
    "standard": "859921c5da54333b19799d9ea0c0d4edb9390e1b750cdd40e1594fd14bdf5493",
    "compact": "70fa2da14068ba00b7a490900e8ff7cfef30625937b4e5bb208a83af6a62e836",
    "spacious": "60c94db96ca1ec84963683004e9fd655970a2f45eb428396b7d904f124e58c4e",
}
#: 提取前功能性样式层
_STYLE_SHA256 = "af7d117ac487bf17f782a0a3f3050a8c371c202935c0c05e7947be28cd094140"
#: 提取前 PrintStyle() 默认 CSS（A5/10.5pt/1.55）
PDF_CSS_SHA256 = "c2b0eb2ef46dc7dc1fe245f563ee2ac61afbadde1606dabdff6b85ed0ddafb67"


def test_functional_style_layer_unchanged() -> None:
    assert hashlib.sha256(_STYLE_CSS.encode()).hexdigest() == _STYLE_SHA256


@pytest.mark.parametrize("theme", sorted(THEME_SHA256))
def test_theme_css_is_byte_identical(theme: str) -> None:
    css = theme_css(theme)
    assert hashlib.sha256(css.encode()).hexdigest() == THEME_SHA256[theme]
    assert "font-family" not in css
    assert "pt" not in css and "px" not in css


def test_pdf_css_is_byte_identical() -> None:
    css = PrintStyle().css()
    assert hashlib.sha256(css.encode()).hexdigest() == PDF_CSS_SHA256
    assert "10.5pt" in css and "8.5pt" in css


def test_unknown_theme_reports_options() -> None:
    with pytest.raises(ValueError) as excinfo:
        theme_css("fancy")
    message = str(excinfo.value)
    assert "fancy" in message
    for name in EPUB_THEMES:
        assert name in message


def test_epub_and_print_value_domains_stay_separate() -> None:
    # 同名语义（正文行距）在两端有独立取值，不共享数字。
    assert EPUB_THEMES["standard"].line_height == 1.7
    assert PRINT.line_height == 1.55
    assert EPUB_THEMES["compact"].indent_em is None
    assert PRINT.body_indent_em == 2.0
    # 预设值仍落在规范声明的范围内（epub-template-spec §5.3 / build 版式契约）。
    assert 1.0 <= min(t.line_height for t in EPUB_THEMES.values()) <= 3.0
    assert 4.0 <= PRINT.body_pt <= 24.0
    assert 4.0 <= PRINT.note_pt <= 20.0


def test_number_formatting_rules() -> None:
    assert css_number(2.0) == "2.0"  # line-height 保留 .0
    assert css_number(1.7) == "1.7"
    assert em_number(1.0) == "1"  # em 长度去掉无意义零
    assert em_number(0.6) == "0.6"


def test_print_style_defaults_come_from_tokens() -> None:
    style = PrintStyle()
    assert (style.size, style.body_pt, style.note_pt, style.line_height) == (
        PRINT.size,
        PRINT.body_pt,
        PRINT.note_pt,
        PRINT.line_height,
    )
    assert style.margins_mm == PRINT.margins_mm
    # 显式参数仍优先于 token 默认值（CLI 兼容）。
    assert PrintStyle(body_pt=12).css() != style.css()
