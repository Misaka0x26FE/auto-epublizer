"""句级对齐：拆句 + 生成 align/<id>.jsonl 对照表（纯函数）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# 句末标点（中英文），拆分时保留标点
_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;.])\s*|\n+")


def split_sentences(text: str) -> list[str]:
    """按句末标点拆分句子；空句剔除。"""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENT_SPLIT.split(text) if p and p.strip()]
    return parts


def align_rows(src: str, tgt: str) -> list[dict[str, Any]]:
    """把一段源文与译文的句子按序对齐，产出 {seq,src,tgt,note}。

    允许拆/并句：以句数多的一侧为准，缺句侧补空串并在 note 声明。
    """
    src_sents = split_sentences(src)
    tgt_sents = split_sentences(tgt)
    n = max(len(src_sents), len(tgt_sents))
    rows: list[dict[str, Any]] = []
    for i in range(n):
        s = src_sents[i] if i < len(src_sents) else ""
        t = tgt_sents[i] if i < len(tgt_sents) else ""
        note = None
        if not s or not t:
            note = "split" if len(src_sents) != len(tgt_sents) else "miss"
        rows.append({"seq": i + 1, "src": s, "tgt": t, "note": note})
    return rows


def write_align(path: str | Path, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_align(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
