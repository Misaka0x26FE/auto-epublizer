"""页边界证据导出（issue #14 / #10-B3；确定性、零 token）。

四层切分把**页/行边界当段落边界**，数字版又把印刷页眉/页底注内联进正文流，导致
大量碎片段。语义合并必须由 agent 判定（``references/repair.md`` 明令禁止阈值合并脚本），
本模块只补**定位证据**的通用能力：扫 ``structured/raw/page-*.json``，为每对相邻页输出
边界证据（两侧最近的存活行 + 回溯到 ``structured/*.md`` 的块号），供 agent 逐条裁定
（merge/keep/unresolved），再由既有确定性手段应用。

产物 ``preprocessing/breaks.jsonl``，每行：

``{"unit","page","kind","prev_line","next_line","prev_block","next_block","candidate"}``

- ``kind``：当前为 ``"page_boundary"``；
- ``unit`` / ``prev_block`` / ``next_block``：把两侧文本回溯到 structured md 的单元与
  块号（1 基；找不到为 ``null``）；
- ``candidate``：启发式「疑为跨页断段」（前一行不以句末标点收尾）。**RTL 源不可靠**
  （句号常被搬到下一词首），故只作参考，不作判据。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from auto_common.workspace import RunStore, read_json

_TERMINAL = ".!?…。！？؛۔"


def _page_lines(path: Path) -> tuple[int, list[str]] | None:
    """读单页 raw json → (page_idx, 非空文本行)。非 ``type=text`` 块跳过。"""
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return None
    page_no = int(data.get("page_idx") or 0)
    lines: list[str] = []
    for block in data.get("blocks") or []:
        if (block.get("type") or "") != "text":
            continue
        for line in str(block.get("text") or "").splitlines():
            line = line.strip()
            if line:
                lines.append(line)
    if not lines:
        return None
    return page_no, lines


def _unit_blocks(store: RunStore) -> list[tuple[str, list[str]]]:
    """读各单元 structured md → [(unit_id, 按空行切分的块)]（回溯用）。"""
    pub = store.load_publication()
    out: list[tuple[str, list[str]]] = []
    for u in pub.units:
        rel = (u.meta or {}).get("rel_path")
        p = store.structured_dir / rel if rel else None
        if not p or not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        out.append((u.id, blocks))
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _locate(unit_blocks: list[tuple[str, list[str]]], line: str) -> tuple[str | None, int | None]:
    """把一行文本回溯到 (unit_id, 块号 1 基)；找不到返回 (None, None)。"""
    needle = _norm(line)
    if not needle:
        return None, None
    for unit_id, blocks in unit_blocks:
        for idx, block in enumerate(blocks, start=1):
            if needle in _norm(block):
                return unit_id, idx
    return None, None


def _is_candidate(prev_line: str) -> bool:
    """启发式：前一行不以句末标点收尾 → 疑为跨页断段（RTL 不可靠，仅参考）。"""
    prev = (prev_line or "").rstrip()
    return bool(prev) and prev[-1] not in _TERMINAL


def collect_breaks(store: RunStore) -> list[dict[str, Any]]:
    """扫 raw 页 JSON，产出相邻页边界证据清单（确定性）。"""
    raw = store.structured_dir / "raw"
    if not raw.is_dir():
        return []
    per_page = [r for p in sorted(raw.glob("page-*.json")) if (r := _page_lines(p)) is not None]
    per_page.sort(key=lambda t: t[0])
    unit_blocks = _unit_blocks(store)
    breaks: list[dict[str, Any]] = []
    for i in range(len(per_page) - 1):
        page_no, lines = per_page[i]
        _next_no, next_lines = per_page[i + 1]
        prev_line = lines[-1]
        next_line = next_lines[0]
        unit, prev_block = _locate(unit_blocks, prev_line)
        if unit is None:
            unit, prev_block = _locate(unit_blocks, next_line)
        _next_unit, next_block = _locate(unit_blocks, next_line)
        breaks.append(
            {
                "unit": unit,
                "page": page_no,
                "kind": "page_boundary",
                "prev_line": prev_line[:200],
                "next_line": next_line[:200],
                "prev_block": prev_block,
                "next_block": next_block,
                "candidate": _is_candidate(prev_line),
            }
        )
    return breaks
