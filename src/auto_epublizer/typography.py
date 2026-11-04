# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""版式参数（tokens）：EPUB 主题层与 PDF 印刷层共享语义、各自值域。

设计约束（P2）：

- **只提取，不改行为**：本模块的初值逐项等于 2026-11-03 基线的既有常量，
  提取前后生成的 CSS 必须逐字节相同（``tests/test_typography_tokens.py`` 锁定）。
- **不强行共享数值**：正文行距、注文行距、标题层级等语义在两端各有独立取值；
  同名语义（如 ``note_line_height``、``line_height``）只共享含义，不共享数字。
- **不作为用户配置面**：CLI 仍只暴露主题名与既有 PDF 参数；新增 token 需要单独
  评审兼容性与产物摘要绑定，不引入「覆盖所有格式的任意 token 字典」。

约定数值的文本形式：

- ``css_number``：保留一个小数位语义（``2.0`` 不写成 ``2``），用于 ``line-height``；
- ``em_number``：去掉无意义的小数零（``1.0`` → ``1``），用于 em 长度。
"""

from __future__ import annotations

from dataclasses import dataclass


def css_number(value: float) -> str:
    """``line-height`` 等需要保留 ``.0`` 的数值文本（1.7 → ``1.7``，2.0 → ``2.0``）。"""
    return repr(float(value))


def em_number(value: float) -> str:
    """em 长度文本（1.0 → ``1``，0.6 → ``0.6``），避免无意义的小数零。"""
    return f"{float(value):g}"


# ── EPUB 主题层（docs/epub-template-spec.zh.md §5.3）──────────────────────────


@dataclass(frozen=True, slots=True)
class EpubTheme:
    """一套 EPUB 主题的排版微调；不设字体名、字号、颜色。"""

    key: str
    font_family: str
    line_height: float
    indent_em: float | None = None
    align: str | None = None
    paragraph_margin_em: float = 0.6
    heading_align: str | None = None


EPUB_THEMES: dict[str, EpubTheme] = {
    "standard": EpubTheme(
        key="standard",
        font_family="serif",
        line_height=1.7,
        indent_em=2.0,
        align="justify",
        paragraph_margin_em=0.6,
        heading_align="center",
    ),
    "compact": EpubTheme(
        key="compact",
        font_family="sans-serif",
        line_height=1.4,
        indent_em=None,  # 未声明 = 阅读器默认（无缩进）
        align=None,  # 未声明 = start（随书写方向）
        paragraph_margin_em=0.8,
        heading_align=None,
    ),
    "spacious": EpubTheme(
        key="spacious",
        font_family="serif",
        line_height=2.0,
        indent_em=2.0,
        align="justify",
        paragraph_margin_em=1.0,
        heading_align="center",
    ),
}


def epub_theme_css(theme: str) -> str:
    """把一套主题 token 渲染为 CSS 片段（未知主题抛 ``KeyError``，由调用方翻译成中文）。"""
    spec = EPUB_THEMES[theme]
    parts = [
        "body {\n"
        f"  font-family: {spec.font_family};\n"
        f"  line-height: {css_number(spec.line_height)};\n"
        "}\n"
    ]
    paragraph = "p {\n"
    if spec.indent_em is not None:
        paragraph += f"  text-indent: {em_number(spec.indent_em)}em;\n"
    if spec.align is not None:
        paragraph += f"  text-align: {spec.align};\n"
    paragraph += f"  margin: 0 0 {em_number(spec.paragraph_margin_em)}em 0;\n}}\n"
    parts.append(paragraph)
    if spec.heading_align is not None:
        parts.append(f"h1, h2, h3, h4, h5, h6 {{\n  text-align: {spec.heading_align};\n}}\n")
    return "".join(parts)


# ── PDF 印刷层（skills/auto-epublizer/references/build.zh.md「版式契约」）──────


@dataclass(frozen=True, slots=True)
class PrintMetrics:
    """印刷版式的默认值与比例；``PrintStyle`` 的缺省值全部来自这里。"""

    size: str = "a5"
    body_pt: float = 10.5
    note_pt: float = 8.5
    line_height: float = 1.55
    margins_mm: tuple[int, int, int, int] = (18, 16, 20, 16)
    body_indent_em: float = 2.0
    #: h1–h4 相对正文字号的比例
    heading_scales: tuple[float, float, float, float] = (1.8, 1.43, 1.19, 1.05)
    #: h1–h3 的行高；h4–h6 未声明（继承正文行高）
    heading_line_heights: tuple[float | None, float | None, float | None, None] = (
        1.35,
        1.4,
        1.45,
        None,
    )
    #: h1–h4 段前/段后（em）
    heading_margins_em: tuple[tuple[float, float], ...] = (
        (1.1, 0.9),
        (1.0, 0.7),
        (0.9, 0.5),
        (0.8, 0.4),
    )
    quote_scale: float = 0.9
    quote_line_height: float = 1.5
    #: 引文段前 / 段后 / 左缩进（em）
    quote_margins_em: tuple[float, float, float] = (0.6, 0.6, 1.5)
    table_scale: float = 0.86
    #: 表格单元格纵向 / 横向内边距（em）
    table_cell_padding_em: tuple[float, float] = (0.12, 0.4)
    note_line_height: float = 1.4
    #: 注区段前 / 段后（em，第三位保留给未来段内间距）
    note_margins_em: tuple[float, float, float] = (0.2, 0.5, 0.0)
    note_paragraph_margin_bottom_em: float = 0.3
    #: 图版高度预算：页高减页边距后再减的固定余量（mm）
    image_budget_mm: float = 4.0
    #: 图版预算预留的注文行数
    image_note_lines: int = 3
    #: 紧跟标题的图版额外预留的标题行高倍数
    heading_image_lines: float = 3.35


PRINT = PrintMetrics()
