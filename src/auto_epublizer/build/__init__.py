"""EPUB 3 直写：zipfile + lxml 构建，确定性输出（冻结时间戳）。

组件：mimetype（首位未压缩）、container.xml、OPF、nav.xhtml、NCX、封面、DC 元数据、
epub:type、landmarks、脚注双向跳转（占位，后续补齐）。
"""

from __future__ import annotations

from .writer import BuildError, build_epub

__all__ = ["BuildError", "build_epub"]