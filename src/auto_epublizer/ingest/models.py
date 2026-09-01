"""核心数据结构：Document → Unit → Segment。

Segment 是最小可对齐 / 可回填的翻译单元（通常一个段落或一个标题）；
Unit 对应工作区内容树的一个单元（章 / 节 / 辅文），带稳定 ID 与 kind；
Document 是一次归一化得到的整本书结构。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

KIND_TEXT = "text"
KIND_HEADING = "heading"


class SourceSegment(BaseModel):
    """一个可翻译 / 可对齐的源文片段。"""

    index: int  # 单元内序号（从 0 起）
    source: str
    kind: str = KIND_TEXT  # text | heading
    anchor: str | None = None  # 回填定位标记
    resource_href: str | None = None  # 物理资源路径
    cont: bool = False  # 超长段拆分后的续段
    meta: dict[str, Any] = Field(default_factory=dict)


class SourceUnit(BaseModel):
    """一个内容树单元（章 / 节 / 辅文）。"""

    id: str  # 稳定 ID，对应 publication.json 的 units[].id
    kind: str = "chapter"  # chapter | section | frontmatter | backmatter | ...
    title: str = ""
    segments: list[SourceSegment] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def text_segments(self) -> list[SourceSegment]:
        return [s for s in self.segments if s.source.strip()]


class SourceDocument(BaseModel):
    """一次归一化的整本书结构。"""

    title: str = ""
    source_path: str = ""
    fmt: str = "text"  # epub | docx | html | text | pdf
    units: list[SourceUnit] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
