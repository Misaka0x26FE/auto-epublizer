"""四层结构归类与清洗纯函数。

- classify_units：把归一化单元映射到 frontmatter/body/backmatter 与稳定 ID；
- strip_page_numbers：剔除独立页码；
- clean_header_footer：按页分组识别并剔除跨页重复的页眉页脚短行。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..ingest.models import KIND_HEADING, SourceDocument, SourceSegment, SourceUnit

_REGION_FRONT = "frontmatter"
_REGION_BODY = "body"
_REGION_BACK = "backmatter"
_REGION_COVER = "cover"

# 标题关键词 → (region, kind)
_TITLE_KEYWORDS: list[tuple[tuple[str, ...], str, str]] = [
    (("封面", "cover"), _REGION_COVER, "cover"),
    (("书名页", "标题页", "titlepage", "title page"), _REGION_FRONT, "titlepage"),
    (("版权", "copyright"), _REGION_FRONT, "copyright"),
    (("献词", "题献", "dedication"), _REGION_FRONT, "dedication"),
    (("他序", "序言", "序", "foreword"), _REGION_FRONT, "foreword"),
    (("前言", "自序", "preface", "引言"), _REGION_FRONT, "preface"),
    (("目录", "目次", "toc", "contents", "table of contents"), _REGION_FRONT, "toc"),
    (("后记", "跋", "afterword"), _REGION_BACK, "afterword"),
    (("附录", "appendix", "appendix a"), _REGION_BACK, "appendix"),
    (("注释", "尾注", "notes", "endnotes"), _REGION_BACK, "notes"),
    (("参考文献", "参考书目", "bibliography", "references"), _REGION_BACK, "bibliography"),
    (("索引", "index"), _REGION_BACK, "index"),
    (("术语表", "glossary"), _REGION_BACK, "glossary"),
]

_PAGE_NUMBER_RE = re.compile(r"^[\s\-—–·]*\d{1,4}[\s\-—–·]*$")
_PAGE_LABEL_RE = re.compile(r"^(?:第?\s*\d{1,4}\s*页?|[pP]\d{1,4})$")


@dataclass(frozen=True)
class ClassifiedUnit:
    unit: SourceUnit
    region: str
    kind: str
    unit_id: str
    rel_path: str  # 相对 structured/ 的 md 路径


def _classify_title(title: str) -> tuple[str, str]:
    lowered = (title or "").lower()
    for keywords, region, kind in _TITLE_KEYWORDS:
        for kw in keywords:
            if kw in lowered:
                return region, kind
    return _REGION_BODY, "chapter"


def classify_units(doc: SourceDocument) -> list[ClassifiedUnit]:
    """把归一化单元归类为四层结构并分配稳定 ID。"""
    result: list[ClassifiedUnit] = []
    chapter_no = 0
    for unit in doc.units:
        region, kind = _classify_title(unit.title)
        if region == _REGION_COVER:
            unit_id, rel_path = "cover", "cover.md"
        elif region == _REGION_FRONT:
            name = kind if kind != "toc" else "toc"
            unit_id, rel_path = f"front-{name}", f"frontmatter/{name}.md"
        elif region == _REGION_BACK:
            name = kind
            unit_id, rel_path = f"back-{name}", f"backmatter/{name}.md"
        else:
            chapter_no += 1
            unit_id = f"ch{chapter_no:02d}"
            rel_path = f"body/{unit_id}.md"
        result.append(
            ClassifiedUnit(
                unit=unit,
                region=region,
                kind=kind,
                unit_id=unit_id,
                rel_path=rel_path,
            )
        )
    return result


def strip_page_numbers(segments: list[SourceSegment]) -> list[SourceSegment]:
    """剔除独立成段的页码。"""
    out: list[SourceSegment] = []
    idx = 0
    for s in segments:
        text = s.source.strip()
        if _PAGE_NUMBER_RE.match(text) or _PAGE_LABEL_RE.match(text):
            continue
        s = s.model_copy(update={"index": idx})
        out.append(s)
        idx += 1
    return out


def _short(text: str, limit: int = 40) -> bool:
    return 0 < len(text) <= limit


def clean_header_footer(
    segments: list[SourceSegment], *, min_pages: int = 3
) -> list[SourceSegment]:
    """按 source_page 分组，剔除跨页重复的页眉页脚短行。

    同一文本在 >=50% 的页首或页末出现即视为页眉/页脚。
    """
    groups: dict[int, list[SourceSegment]] = {}
    for s in segments:
        groups.setdefault(s.meta.get("source_page") or 0, []).append(s)

    pages = sorted(groups)
    if len(pages) < min_pages:
        return segments

    header_candidates: dict[str, int] = {}
    footer_candidates: dict[str, int] = {}
    for pg in pages:
        segs = groups[pg]
        text_segs = [s for s in segs if s.kind != KIND_HEADING and _short(s.source.strip())]
        if text_segs:
            header_candidates[text_segs[0].source.strip()] = (
                header_candidates.get(text_segs[0].source.strip(), 0) + 1
            )
            footer_candidates[text_segs[-1].source.strip()] = (
                footer_candidates.get(text_segs[-1].source.strip(), 0) + 1
            )

    threshold = max(2, int(len(pages) * 0.5))
    drop = {t for t, n in header_candidates.items() if n >= threshold}
    drop |= {t for t, n in footer_candidates.items() if n >= threshold}

    if not drop:
        return segments

    out: list[SourceSegment] = []
    idx = 0
    for s in segments:
        text = s.source.strip()
        if _short(text) and text in drop:
            continue
        s = s.model_copy(update={"index": idx})
        out.append(s)
        idx += 1
    return out


def clean_unit(unit: SourceUnit) -> SourceUnit:
    """对单元应用页码剔除与页眉页脚清洗。"""
    segments = strip_page_numbers(unit.segments)
    segments = clean_header_footer(segments)
    return unit.model_copy(update={"segments": segments})
