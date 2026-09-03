"""结构重建：把归一化的单元序列重建为出版物四层结构（frontmatter/body/backmatter）。

含清洗纯函数：标题层级、页眉页脚/页码剔除、阅读顺序（占位）、脚注配对（占位）、
表格保形（占位）、插入元素提取、source_page 溯源。
"""

from __future__ import annotations

from .classify import classify_units, clean_header_footer, strip_page_numbers
from .rebuild import (
    StructureError,
    count_empty_units,
    rebuild_structure,
    skip_empty_unit,
    unit_heading,
    write_structured,
)

__all__ = [
    "StructureError",
    "classify_units",
    "clean_header_footer",
    "count_empty_units",
    "rebuild_structure",
    "skip_empty_unit",
    "strip_page_numbers",
    "unit_heading",
    "write_structured",
]
