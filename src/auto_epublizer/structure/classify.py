# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""四层结构归类与清洗纯函数。

- classify_units：把归一化单元映射到 frontmatter/body/backmatter 与稳定 ID；
- strip_page_numbers：剔除**有版式证据**的独立页码；
- clean_header_footer：按页分组识别并剔除跨页重复的页眉页脚短行。

清洗只删除可证明是版式家具的段：页码标签、带装饰的页码、以及有 ``source_page``
定位且跨页构成递增序列的裸数字。证据不足的独立数字（年份、诗歌编号、表格数字）
原样保留，并作为候选写进清洗台账，绝不按「长得像页码」静默删除。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..ingest.models import KIND_HEADING, SourceDocument, SourceSegment, SourceUnit

_REGION_FRONT = "frontmatter"
_REGION_BODY = "body"
_REGION_BACK = "backmatter"
_REGION_COVER = "cover"

# 标题关键词 → (region, kind)
_TITLE_KEYWORDS: list[tuple[tuple[str, ...], str, str]] = [
    (("封面", "cover"), _REGION_COVER, "cover"),
    (
        ("半书名页", "简书名页", "half-title", "half title", "half title page"),
        _REGION_FRONT,
        "half-title",
    ),
    (("书名页", "标题页", "titlepage", "title page"), _REGION_FRONT, "titlepage"),
    (("版权", "copyright"), _REGION_FRONT, "copyright"),
    (("献词", "题献", "dedication"), _REGION_FRONT, "dedication"),
    (("他序", "序言", "序", "foreword"), _REGION_FRONT, "foreword"),
    (("前言", "自序", "preface", "引言"), _REGION_FRONT, "preface"),
    (("目录", "目次", "toc", "contents", "table of contents"), _REGION_FRONT, "toc"),
    (("后记", "跋", "afterword"), _REGION_BACK, "afterword"),
    (("附录", "appendix", "appendix a"), _REGION_BACK, "appendix"),
    (("注释", "尾注", "notes", "endnotes"), _REGION_BACK, "notes"),
    (
        (
            "参考文献",
            "参考书目",
            "bibliography",
            "references",
            "sources and literature",
            "sources & literature",
        ),
        _REGION_BACK,
        "bibliography",
    ),
    (("索引", "index"), _REGION_BACK, "index"),
    (("术语表", "glossary"), _REGION_BACK, "glossary"),
]

_PAGE_NUMBER_RE = re.compile(r"^[\s\-—–·]*\d{1,4}[\s\-—–·]*$")
_PAGE_LABEL_RE = re.compile(r"^(?:第\s*\d{1,4}\s*页|\d{1,4}\s*页|[pP]\d{1,4})$")
_BARE_PAGE_RE = re.compile(r"^\d{1,4}$")
_PAGE_DECORATION = frozenset("-—–·•")
_PAGE_FURNITURE_KINDS = frozenset({"cover", "titlepage", "half-title"})


@dataclass(frozen=True)
class CleanRemoval:
    """一条被清洗或待核的段（``index`` 是清洗前在单元内的原始序号）。"""

    index: int
    source: str
    reason: str
    page: int | None = None


@dataclass(frozen=True)
class CleanReport:
    """单元清洗台账：``removed`` 是已删项，``candidates`` 是证据不足的保留项。"""

    removed: tuple[CleanRemoval, ...] = field(default_factory=tuple)
    candidates: tuple[CleanRemoval, ...] = field(default_factory=tuple)

    def merge(self, other: CleanReport) -> CleanReport:
        return CleanReport(
            removed=self.removed + other.removed,
            candidates=self.candidates + other.candidates,
        )

    def as_dict(self) -> dict[str, list[dict[str, object]]]:
        def rows(items: tuple[CleanRemoval, ...]) -> list[dict[str, object]]:
            return [
                {"index": r.index, "source": r.source, "reason": r.reason, "page": r.page}
                for r in items
            ]

        return {"removed": rows(self.removed), "candidates": rows(self.candidates)}


@dataclass(frozen=True)
class ClassifiedUnit:
    unit: SourceUnit
    region: str
    kind: str
    unit_id: str
    rel_path: str  # 相对 structured/ 的 md 路径


def _keyword_hit(lowered: str, kw: str) -> bool:
    """判断标题是否命中关键词。

    ASCII 关键词（cover/titlepage/index…）按**词边界**匹配，避免子串误判——
    如 ``cover`` 不应命中 ``Covert``（真实事故：Pentagon Papers 的
    "Chapter 5 The Covert War…" 被误判为封面，与真正的封面同 id 而互相覆盖）。
    含中文的关键词仍按子串匹配（中文无词边界，且关键词本身即完整词）。
    """
    if kw.isascii():
        pattern = r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])"
        return re.search(pattern, lowered) is not None
    return kw in lowered


def _classify_title(title: str) -> tuple[str, str]:
    lowered = (title or "").lower()
    for keywords, region, kind in _TITLE_KEYWORDS:
        for kw in keywords:
            if _keyword_hit(lowered, kw):
                return region, kind
    return _REGION_BODY, "chapter"


# 前置页内容标记（issue #31 ③）：无书签 PDF 的首个聚合单元若是标题页/版权页内容
# （短、含 copyright/isbn/书名页 等），归 frontmatter 而非 body 章节。
_FRONT_MATTER_MARKERS = (
    "copyright",
    "all rights reserved",
    "isbn",
    "©",
    "title page",
    "书名页",
    "版权",
)


def _norm_title(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or "").casefold())


def _is_early_short_unit(unit: SourceUnit) -> bool:
    """非首单元的书名页判据：内容短且位于前几页。

    仅凭“标题等于书名”会把同名正文章节误判成书名页（整章不清理页码/页眉、
    按标题页排版）；因此要求短内容 + 起始页在前 4 页，或首单元。
    """
    text = "\n".join(segment.source for segment in unit.segments)
    if len(text) > 2000:
        return False
    pages = [
        int(segment.meta.get("source_page"))
        for segment in unit.segments
        if isinstance(segment.meta.get("source_page"), int)
    ]
    return not pages or max(pages) <= 4


def _looks_like_front_matter(unit: SourceUnit) -> bool:
    text = "\n".join(s.source for s in unit.segments)
    if not text or len(text) > 2000:
        return False
    lowered = text.lower()
    return any(m in lowered for m in _FRONT_MATTER_MARKERS)


def classify_units(doc: SourceDocument) -> list[ClassifiedUnit]:
    """把归一化单元归类为四层结构并分配稳定 ID。

    同类辅文出现多个时（如 Appendix A/B）自动加序号（back-appendix、back-appendix-2），
    保证 unit_id 与 rel_path 全局唯一。
    """
    result: list[ClassifiedUnit] = []
    chapter_no = 0
    aux_counts: dict[tuple[str, str], int] = {}
    for idx, unit in enumerate(doc.units):
        region, kind = _classify_title(unit.title)
        title_match = bool(
            _norm_title(doc.title) and _norm_title(unit.title) == _norm_title(doc.title)
        )
        if (
            region == _REGION_BODY
            and unit.meta.get("aggregated")
            and (
                _looks_like_front_matter(unit)
                or (title_match and (idx == 0 or _is_early_short_unit(unit)))
            )
        ):
            region, kind = _REGION_FRONT, "titlepage"  # 无书签 PDF 的标题/版权页
        if region == _REGION_COVER:
            # 封面也可能有多个（front/back cover 等）：与辅文一致地加序号，
            # 否则多个覆盖单元共用 id/rel_path 会互相覆盖并丢内容。
            aux_counts[(region, kind)] = aux_counts.get((region, kind), 0) + 1
            n = aux_counts[(region, kind)]
            suffix = "" if n == 1 else f"-{n}"
            unit_id = f"cover{suffix}"
            rel_path = f"cover{suffix}.md"
        elif region == _REGION_FRONT:
            aux_counts[(region, kind)] = aux_counts.get((region, kind), 0) + 1
            n = aux_counts[(region, kind)]
            suffix = "" if n == 1 else f"-{n}"
            unit_id = f"front-{kind}{suffix}"
            rel_path = f"frontmatter/{kind}{suffix}.md"
        elif region == _REGION_BACK:
            aux_counts[(region, kind)] = aux_counts.get((region, kind), 0) + 1
            n = aux_counts[(region, kind)]
            suffix = "" if n == 1 else f"-{n}"
            unit_id = f"back-{kind}{suffix}"
            rel_path = f"backmatter/{kind}{suffix}.md"
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


def _page_of(segment: SourceSegment) -> int | None:
    page = segment.meta.get("source_page")
    return int(page) if isinstance(page, int) else None


def _page_number_evidence(segments: list[SourceSegment]) -> tuple[set[int], set[int]]:
    """返回（有证据的页码序号，证据不足的保留候选序号）。

    证据分层：
    1. ``第 12 页`` / ``p12`` 等显式页码标签；
    2. 带装饰符的页码（``- 12 -`` / ``· 12 ·``）；
    3. 有 ``source_page`` 定位、位于页首/页末、跨 >=5 页且与页序偏移 0–3 的递增裸数字。
    其余裸数字一律保留；页首/页末的裸数字作为候选上报，交由 agent 判断。
    """
    strong: set[int] = set()
    bare_by_page: dict[int, list[int]] = {}
    for i, s in enumerate(segments):
        text = s.source.strip()
        if s.kind == KIND_HEADING or not text:
            continue
        if _PAGE_LABEL_RE.fullmatch(text):
            strong.add(i)
            continue
        if not _PAGE_NUMBER_RE.fullmatch(text):
            continue
        if any(ch in _PAGE_DECORATION for ch in text):
            strong.add(i)
            continue
        page = _page_of(s)
        if page is not None and _BARE_PAGE_RE.fullmatch(text):
            bare_by_page.setdefault(page, []).append(i)

    positions: dict[int, list[int]] = {}
    for i, s in enumerate(segments):
        page = _page_of(s)
        if page is not None:
            positions.setdefault(page, []).append(i)

    boundary: dict[int, list[int]] = {}
    for page, idxs in bare_by_page.items():
        page_idxs = positions.get(page) or idxs
        first, last = page_idxs[0], page_idxs[-1]
        near = [i for i in idxs if i in (first, last)]
        if near:
            boundary[page] = near

    chain = _monotonic_page_chain(segments, boundary)
    strong |= chain
    candidates = {i for idxs in boundary.values() for i in idxs} - chain
    return strong, candidates


def _monotonic_page_chain(
    segments: list[SourceSegment], boundary: dict[int, list[int]]
) -> set[int]:
    """跨页页首/页末裸数字：只认与页序接近（偏移 0–3）、连续 >=5 页的序列。

    年份（1968…）、诗歌/章节编号通常远离页序，或跨页不足 5 页；证据不足时不删除。
    """
    pages = [
        page
        for page in sorted(boundary)
        if any(0 <= int(segments[i].source.strip()) - page <= 3 for i in boundary[page])
    ]
    if len(pages) < 5:
        return set()
    best: list[int] = []
    for start in range(len(pages)):
        chain: list[int] = []
        last: int | None = None
        for page in pages[start:]:
            values = sorted(
                (int(segments[i].source.strip()), i)
                for i in boundary[page]
                if 0 <= int(segments[i].source.strip()) - page <= 3
            )
            pick: tuple[int, int] | None = None
            for value, index in values:
                if last is None or (last < value <= last + 3):
                    pick = (value, index)
                    break
            if pick is None:
                if last is not None:
                    break
                continue
            last = pick[0]
            chain.append(pick[1])
        if len(chain) > len(best):
            best = chain
    return set(best) if len(best) >= 5 else set()


def _strip_page_numbers(
    segments: list[SourceSegment], origins: list[int]
) -> tuple[list[SourceSegment], list[CleanRemoval], list[CleanRemoval], list[int]]:
    strong, candidates = _page_number_evidence(segments)
    out: list[SourceSegment] = []
    out_origins: list[int] = []
    removed: list[CleanRemoval] = []
    kept: list[CleanRemoval] = []
    for i, s in enumerate(segments):
        text = s.source.strip()
        if i in strong:
            removed.append(CleanRemoval(origins[i], text, "page_number", _page_of(s)))
            continue
        if i in candidates:
            kept.append(CleanRemoval(origins[i], text, "page_number_unverified", _page_of(s)))
        out.append(s.model_copy(update={"index": len(out)}))
        out_origins.append(origins[i])
    return out, removed, kept, out_origins


def strip_page_numbers(segments: list[SourceSegment]) -> list[SourceSegment]:
    """剔除有版式证据的独立页码（证据不足的裸数字保留）。"""
    out, _removed, _kept, _origins = _strip_page_numbers(segments, list(range(len(segments))))
    return out


def _short(text: str, limit: int = 40) -> bool:
    return 0 < len(text) <= limit


def _clean_header_footer(
    segments: list[SourceSegment],
    origins: list[int],
    *,
    min_pages: int = 3,
    title: str = "",
) -> tuple[list[SourceSegment], list[CleanRemoval], list[CleanRemoval]]:
    positions: dict[int, list[int]] = {}
    for i, s in enumerate(segments):
        positions.setdefault(s.meta.get("source_page") or 0, []).append(i)

    sizes = sorted(
        float(s.meta.get("source_font_size") or 0)
        for s in segments
        if s.kind != KIND_HEADING and float(s.meta.get("source_font_size") or 0) > 0
    )
    median_size = sizes[(len(sizes) - 1) // 2] if sizes else 0.0
    page_max: dict[int, float] = {}
    for s in segments:
        page = s.meta.get("source_page") or 0
        size = float(s.meta.get("source_font_size") or 0)
        if size > page_max.get(page, 0.0):
            page_max[page] = size

    pages = sorted(positions)
    if len(pages) < min_pages:
        return segments, [], []

    header_candidates: dict[str, int] = {}
    footer_candidates: dict[str, int] = {}
    roles: dict[int, str] = {}
    boundary: set[int] = set()
    for pg in pages:
        text_idx = [
            i
            for i in positions[pg]
            if segments[i].kind != KIND_HEADING and _short(segments[i].source.strip())
        ]
        if not text_idx:
            continue
        first, last = text_idx[0], text_idx[-1]
        boundary.update((first, last))
        roles.setdefault(first, "header")
        roles.setdefault(last, "footer")
        header_candidates[segments[first].source.strip()] = (
            header_candidates.get(segments[first].source.strip(), 0) + 1
        )
        footer_candidates[segments[last].source.strip()] = (
            footer_candidates.get(segments[last].source.strip(), 0) + 1
        )

    threshold = max(2, int(len(pages) * 0.5))
    drop = {t for t, n in header_candidates.items() if n >= threshold}
    drop |= {t for t, n in footer_candidates.items() if n >= threshold}
    if not drop:
        return segments, [], []

    out: list[SourceSegment] = []
    removed: list[CleanRemoval] = []
    candidates: list[CleanRemoval] = []
    for i, s in enumerate(segments):
        text = s.source.strip()
        if i in boundary and s.kind != KIND_HEADING and _short(text) and text in drop:
            role = roles.get(i, "boundary")
            reason = "repeated_header" if role == "header" else "repeated_footer"
            size = float(s.meta.get("source_font_size") or 0)
            page = s.meta.get("source_page") or 0
            # 版面正交判据（issue #97）：书名页标题常是整页最大字号，即使跨页重复
            # 也不是页眉。字号证据不足（OCR 无行框/全页同字号）时才按文本重复删除。
            if (
                page_max.get(page)
                and size >= page_max[page] * 0.98
                and median_size
                and size >= median_size * 1.25
                and title
                and (
                    _norm_title(text) == _norm_title(title)
                    or (len(_norm_title(text)) >= 5 and _norm_title(text) in _norm_title(title))
                )
            ):
                candidates.append(
                    CleanRemoval(origins[i], text, reason + "_large_font_kept", _page_of(s))
                )
                out.append(s.model_copy(update={"index": len(out)}))
                continue
            removed.append(CleanRemoval(origins[i], text, reason, _page_of(s)))
            continue
        out.append(s.model_copy(update={"index": len(out)}))
    return out, removed, candidates


def clean_header_footer(
    segments: list[SourceSegment], *, min_pages: int = 3
) -> list[SourceSegment]:
    """按 source_page 分组，剔除跨页重复的页眉页脚短行。

    同一文本在 >=50% 的页首或页末出现即视为页眉/页脚。**只删除页首/页末的那次出现**：
    同文若也出现在页中，那是正文（书名页书名、章内引文等），不是版式家具；
    标题段（``kind == "heading"``）保留其结构角色，即使与页眉同文。
    字号显著大于正文中位数且为页内最大时只记为候选，不删除（书名页标题）。
    """
    out, _removed, _candidates = _clean_header_footer(
        segments, list(range(len(segments))), min_pages=min_pages
    )
    return out


def clean_unit_with_report(
    unit: SourceUnit, *, kind: str | None = None
) -> tuple[SourceUnit, CleanReport]:
    """清洗单元并返回台账；``kind`` 用归类结果，避免按标题重新判定书名页/封面。"""
    _region, derived = _classify_title(unit.title)
    effective = kind or derived
    if effective in _PAGE_FURNITURE_KINDS:
        return unit, CleanReport()
    segments, removed, candidates, origins = _strip_page_numbers(
        unit.segments, list(range(len(unit.segments)))
    )
    segments, header_removed, header_candidates = _clean_header_footer(
        segments, origins, title=unit.title
    )
    report = CleanReport(
        removed=tuple(removed + header_removed),
        candidates=tuple(candidates + header_candidates),
    )
    return unit.model_copy(update={"segments": segments}), report


def clean_unit(unit: SourceUnit, *, kind: str | None = None) -> SourceUnit:
    """对单元应用页码剔除与页眉页脚清洗。

    书名页/封面整页都是内容：书名、副题、编者、出版年都可能与「页眉」或「页码」
    同形（issue #97），因此这两类单元原样保留，不做版式家具剔除。
    ``kind`` 传入归类结果时以它为准（聚合单元可能按内容判为书名页）。
    """
    cleaned, _report = clean_unit_with_report(unit, kind=kind)
    return cleaned
