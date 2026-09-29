#!/usr/bin/env python3
"""RTL PDF 抽取校验：把「pymupdf + RTL 重排」与 poppler ``pdftotext`` 逐页比对。

``pdftotext``（poppler）实现完整 Unicode 双向算法（UAX#9），作为**逻辑序 oracle**。
指标：两侧各自归一化（剥方向控制符 + NFKC）后，去掉标点得到词序串，算
``difflib.SequenceMatcher(autojunk=False).ratio()``——**autojunk 必须关**，否则波斯语
高频字符会被判为 junk，相似度假性坍缩到 ~1%。

残差主要来自行/段切分差异（pymupdf 与 poppler 的换行/合并策略不同），非顺序错误。

用法::

    uv run --project auto-epublizer python scripts/verify_rtl_pdf.py <pdf> \
        [--pages 1,10,50] [--sample 10] [--min 0.90]

未给 ``--pages`` 时按 ``--sample`` 均匀抽样。均值 ≥ ``--min`` 退出码 0，否则 1。
"""

from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path

import pymupdf as fitz

from auto_epublizer.ingest.pdf_reader import _page_blocks
from auto_epublizer.ingest.rtl import detect_book_rtl, normalize_rtl

# 去标点：只保留字母/数字/下划线（含阿拉伯字母区）
_PUNCT_RE = re.compile(r"[^\w\u0600-\u06ff]", re.UNICODE)


def _word_stream(text: str) -> str:
    """归一化 + 去标点，得到可比对的词序串。"""
    normalized = normalize_rtl(text)
    return "".join(_PUNCT_RE.sub("", tok) for tok in normalized.split())


def _mine(page: fitz.Page) -> str:
    return "\n".join(b.get("text", "") for b in _page_blocks(page, rtl=True))


def _oracle(pdf: str, page_no: int) -> str:
    out = subprocess.run(
        ["pdftotext", "-f", str(page_no), "-l", str(page_no), pdf, "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout


def _sample_pages(page_count: int, sample: int) -> list[int]:
    if page_count <= sample:
        return list(range(1, page_count + 1))
    step = page_count / sample
    return sorted({min(page_count, int(i * step) + 1) for i in range(sample)})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RTL PDF 抽取 vs pdftotext oracle 校验")
    ap.add_argument("pdf", help="PDF 路径")
    ap.add_argument("--pages", help="逗号分隔的页号（1 起）")
    ap.add_argument("--sample", type=int, default=10, help="均匀抽样页数（默认 10）")
    ap.add_argument("--min", dest="min_ratio", type=float, default=0.90, help="均值下限")
    args = ap.parse_args(argv)

    pdf = str(Path(args.pdf))
    doc = fitz.open(pdf)
    try:
        page_count = doc.page_count
        if args.pages:
            pages = [int(x) for x in args.pages.split(",") if x.strip()]
        else:
            pages = _sample_pages(page_count, args.sample)
        pages = [p for p in pages if 1 <= p <= page_count]

        prescan = [doc[i].get_text() for i in range(min(page_count, 20))]
        print(f"book RTL(auto, 前 {len(prescan)} 页预扫描): {detect_book_rtl(prescan)}")
        print(f"pages: {len(pages)} / {page_count}")

        ratios: list[float] = []
        for pno in pages:
            mine = _word_stream(_mine(doc[pno - 1]))
            orac = _word_stream(_oracle(pdf, pno))
            ratio = difflib.SequenceMatcher(None, mine, orac, autojunk=False).ratio()
            ratios.append(ratio)
            flag = "OK " if ratio >= args.min_ratio else "LOW"
            print(f"  p{pno:>4}: {ratio:.4%} {flag} (mine={len(mine)}, oracle={len(orac)})")
        mean = sum(ratios) / len(ratios) if ratios else 0.0
        print(f"mean word-order similarity: {mean:.4%} (min={args.min_ratio:.2%})")
        return 0 if mean >= args.min_ratio else 1
    finally:
        doc.close()


if __name__ == "__main__":
    sys.exit(main())
