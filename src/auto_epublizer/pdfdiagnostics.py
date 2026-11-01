# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""以源段落文字绑定 PDF 字号样本，独立检查实测纸张与版心溢出。"""

from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

import pymupdf

_PREFIX = 24
_VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "wbr",
}


def _normal(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).replace("\u00ad", "").split())


@dataclass
class FontSamples:
    prefixes: dict[str, tuple[str, str] | None] = field(default_factory=dict)
    source_chars: Counter = field(default_factory=Counter)


class _Paragraphs(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str, bool]] = []
        self.paragraph: tuple[str, list[str]] | None = None
        self.samples = FontSamples()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID:
            return
        _, kind, excluded = self.stack[-1] if self.stack else ("", "body", False)
        classes = set((dict(attrs).get("class") or "").split())
        if tag == "aside" or classes & {"footnote", "footnotes", "fn"}:
            kind = "notes"
        excluded = excluded or tag in {"head", "script", "style", "table", "pre", "code"}
        self.stack.append((tag, kind, excluded))
        if tag == "p" and not excluded:
            self.paragraph = (kind, [])

    def handle_data(self, data: str) -> None:
        if self.paragraph and self.stack and not self.stack[-1][2]:
            self.paragraph[1].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self.paragraph:
            kind, parts = self.paragraph
            text = _normal("".join(parts))
            self.samples.source_chars[kind] += len(text)
            if len(text) >= _PREFIX:
                key = text[:_PREFIX]
                previous = self.samples.prefixes.get(key)
                if key not in self.samples.prefixes:
                    self.samples.prefixes[key] = (kind, text[:64])
                elif previous is None or previous[0] != kind:
                    self.samples.prefixes[key] = None  # 正文/注文同形时保持未知
            self.paragraph = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def collect_font_samples(html: str) -> FontSamples:
    """收集正文/注文段落的文字前缀；表格、标题和代码不作正文字号证据。"""
    parser = _Paragraphs()
    parser.feed(html)
    parser.close()
    return parser.samples


def _sample_spans(spans: list[dict], samples: FontSamples, counts: dict[str, Counter]) -> None:
    parts: list[str] = []
    offsets: list[tuple[int, int, float]] = []
    length = 0
    for span in spans:
        text = _normal(span["text"])
        parts.append(text)
        offsets.append((length, length + len(text), round(float(span["size"]), 2)))
        length += len(text)
    text = "".join(parts)
    pos = 0
    while pos + _PREFIX <= len(text):
        sample = samples.prefixes.get(text[pos : pos + _PREFIX])
        if sample is None:
            pos += 1
            continue
        kind, source = sample
        matched = _PREFIX
        while (
            matched < len(source)
            and pos + matched < len(text)
            and source[matched] == text[pos + matched]
        ):
            matched += 1
        for start, end, size in offsets:
            overlap = max(0, min(end, pos + matched) - max(start, pos))
            if overlap:
                counts[kind][size] += overlap
        pos += matched


def diagnose_pdf(
    doc: pymupdf.Document,
    *,
    samples: FontSamples,
    body_pt: float,
    note_pt: float,
    size_mm: tuple[int, int],
    margins_mm: tuple[float, float, float, float],
    cover: bool = False,
    marker_values: set[str] | None = None,
) -> dict[str, Any]:
    """实测字号（字符加权众数）、纸张尺寸和越界位置；证据不足明确 unknown。"""
    counts: dict[str, Counter] = {"body": Counter(), "notes": Counter()}
    findings: list[dict[str, Any]] = []
    overflow_pages: set[int] = set()
    overflow_count = 0
    top, outer, bottom, inner = (value * 72 / 25.4 for value in margins_mm)
    width, height = (value * 72 / 25.4 for value in size_mm)

    def check_box(page: pymupdf.Page, bbox: tuple, kind: str, text: str = "") -> None:
        nonlocal overflow_count
        x0, y0, x1, y1 = bbox
        if (
            x0 < inner - 2
            or x1 > page.rect.width - outer + 2
            or y0 < top - 2
            or y1 > page.rect.height - bottom + 2
        ):
            overflow_count += 1
            overflow_pages.add(page.number + 1)
            if overflow_count <= 100:
                findings.append(
                    {
                        "level": "error",
                        "code": "E_PDF_OVERFLOW",
                        "page": page.number + 1,
                        "kind": kind,
                        "bbox": list(bbox),
                        "text": text[:80],
                    }
                )

    for page in doc:
        if abs(page.rect.width - width) > 1 or abs(page.rect.height - height) > 1:
            findings.append(
                {
                    "level": "error",
                    "code": "E_PDF_PAGE_SIZE",
                    "page": page.number + 1,
                    "actual_pt": [page.rect.width, page.rect.height],
                    "expected_mm": list(size_mm),
                }
            )
        if cover and page.number == 0:
            continue
        for image in page.get_image_info():
            check_box(page, image["bbox"], "image")
        flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
        for block in page.get_text("dict", flags=flags)["blocks"]:
            if "lines" not in block:
                continue
            spans = [
                span
                for line in block["lines"]
                for span in line["spans"]
                if span["text"].strip() not in (marker_values or set())
            ]
            _sample_spans(spans, samples, counts)
            for span in spans:
                if span["text"].strip():
                    check_box(page, span["bbox"], "text", span["text"])
    fonts: dict[str, dict[str, Any]] = {}
    for kind, expected in (("body", body_pt), ("notes", note_pt)):
        distribution = counts[kind]
        total = sum(distribution.values())
        observed, weight = distribution.most_common(1)[0] if total else (None, 0)
        known = total >= _PREFIX and weight / total >= 0.6
        fonts[kind] = {
            "status": "measured" if known else "unknown",
            "requested_pt": expected,
            "observed_pt": observed if known else None,
            "sample_chars": total,
            "source_chars": samples.source_chars[kind],
            "distribution": {str(k): v for k, v in sorted(distribution.items())},
        }
        if known and abs(observed / expected - 1) > 0.05:
            findings.append(
                {
                    "level": "error",
                    "code": "E_PDF_FONT_SCALE",
                    "kind": kind,
                    "requested_pt": expected,
                    "observed_pt": observed,
                    "ratio": round(observed / expected, 4),
                }
            )
        elif not known and samples.source_chars[kind] >= _PREFIX:
            findings.append({"level": "warning", "code": "W_PDF_FONT_SAMPLE_UNKNOWN", "kind": kind})
    failed = any(f["level"] == "error" for f in findings)
    return {
        "status": "fail"
        if failed
        else "pass"
        if fonts["body"]["status"] == "measured"
        else "unknown",
        "fonts": fonts,
        "overflow_pages": sorted(overflow_pages),
        "overflow_count": overflow_count,
        "findings": findings,
        "font_tolerance": 0.05,
        "bbox_tolerance_pt": 2,
        "scope": ["source_bound_paragraph_fonts", "text_span_bounds", "raster_draw_bounds"],
    }
