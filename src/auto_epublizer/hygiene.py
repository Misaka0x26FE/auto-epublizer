# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""译文卫生扫描（C1，只读、确定性、全部 advisory）。

只报**可定位候选**，不判断词义、不改文本、不替代 agent 审校：

- ``primitive_word``：中文正文中残留的源语言词（拉丁词 ≥4 字母）；
- ``unbalanced_quote``：引号/括号配对失衡（按整单元统计，允许跨段引文）；
- ``duplicate_word``：相邻重复词（ASCII 词或 ≥2 字中文词）；
- ``half_sentence``：正文块未以终止标点收束；
- ``long_paragraph``：超长块（默认 1200 字符）；
- ``tail_loss``：以逗号/顿号/连词/破折号收尾，疑似丢尾。

负对照：围栏代码与行内代码不参与；书目/索引/术语表单元跳过；常见缩写点不触发
``half_sentence``；冒号引导句的下一块存在时不触发 ``tail_loss``；跨段引文在整单元
范围内配对。语义词义错误不在本扫描的证明范围。
"""

from __future__ import annotations

import json
import re
from typing import Any

from auto_common.markdown import inline_code_chunks
from auto_translator.review.fidelity import content_blocks

_TERMINAL = "。！？!?；;…."
_CLOSERS = '”』」》）)]"'
_ABBREV = re.compile(
    r"(?:\b(?:e\.g|i\.e|etc|vs|cf|fig|no|vol|pp|ed|trans|approx|ca)\.)$", re.IGNORECASE
)
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'-]{3,}")
_DUPLICATE_ASCII = re.compile(r"\b([A-Za-z]{2,})\s+\1\b", re.IGNORECASE)
_DUPLICATE_CJK = re.compile(r"([\u4e00-\u9fff]{2,4})\1")
_TAIL = re.compile(r"(?:[，,、—–-]|(?:和|与|及|或|而|但是|以及|the|and|of|to|in|for))\s*$", re.I)
_QUOTE_PAIRS = (("“", "”"), ("『", "』"), ("「", "」"), ("（", "）"), ("(", ")"), ("《", "》"))
_SKIP_UNIT_KINDS = {"bibliography", "index", "glossary", "toc"}
_SKIP_LATIN = {
    "epub",
    "html",
    "http",
    "https",
    "isbn",
    "doi",
    "pdf",
    "url",
    "www",
    "auto",
    "epublizer",
}


def _block_texts(md_text: str) -> list[str]:
    """正文块（跳过标题/纯注释）；围栏代码原样返回供调用方识别并跳过。"""
    return content_blocks(md_text)


def _is_code(block: str) -> bool:
    stripped = block.lstrip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def _plain_without_inline_code(text: str) -> str:
    return "".join(part for is_code, part in inline_code_chunks(text) if not is_code)


def _quote_issues(text: str) -> list[dict[str, Any]]:
    findings = []
    for left, right in _QUOTE_PAIRS:
        if text.count(left) != text.count(right):
            findings.append(
                {
                    "code": "unbalanced_quote",
                    "detail": {
                        "open": text.count(left),
                        "close": text.count(right),
                        "pair": left + right,
                    },
                }
            )
    if text.count('"') % 2:
        findings.append(
            {"code": "unbalanced_quote", "detail": {"pair": '""', "count": text.count('"')}}
        )
    return findings


def _block_findings(block: str, *, next_block: str | None, long_limit: int) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    plain = "".join(part for is_code, part in inline_code_chunks(block) if not is_code)
    for match in _DUPLICATE_ASCII.finditer(plain):
        findings.append(
            {
                "code": "duplicate_word",
                "detail": {"word": match.group(1), "span": list(match.span())},
            }
        )
    for match in _DUPLICATE_CJK.finditer(plain):
        findings.append(
            {
                "code": "duplicate_word",
                "detail": {"word": match.group(1), "span": list(match.span())},
            }
        )
    stripped = plain.rstrip()
    if len(stripped) >= long_limit:
        findings.append(
            {"code": "long_paragraph", "detail": {"chars": len(stripped), "limit": long_limit}}
        )
    tail_char = stripped[-1:] if stripped else ""
    ends_terminal = bool(tail_char) and (tail_char in _TERMINAL or tail_char in _CLOSERS)
    colon_lead = tail_char in ":：" and next_block is not None
    list_like = bool(re.match(r"^\s*(?:[-*+]|\d+[.)])\s", block))
    if stripped and not ends_terminal and not colon_lead and not list_like:
        if not _ABBREV.search(stripped):
            findings.append(
                {
                    "code": "half_sentence",
                    "detail": {"tail": stripped[-20:], "chars": len(stripped)},
                }
            )
        if _TAIL.search(stripped):
            findings.append({"code": "tail_loss", "detail": {"tail": stripped[-20:]}})
    # 残词只对**中文正文**成立：纯英文/注释性整块不按“未翻译”处理。
    if re.search(r"[\u4e00-\u9fff]", plain):
        glossless = re.sub(r"[（(][^）)]*[）)]", "", plain)
        glossless = re.sub(r"《[^》]*》|“[^”]*”|『[^』]*』", "", glossless)
        for word in _LATIN_WORD.findall(glossless):
            if word.lower() in _SKIP_LATIN:
                continue
            findings.append({"code": "primitive_word", "detail": {"word": word}})
    return findings


def scan_unit(
    unit_id: str,
    md_text: str,
    *,
    long_limit: int = 1200,
    seq_spans: dict[int, tuple[int, int]] | None = None,
) -> list[dict[str, Any]]:
    """扫描一个单元，返回带块号/上下文/seq 区间（如可推）的候选。"""
    blocks = [block for block in _block_texts(md_text)]
    findings: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, start=1):
        if _is_code(block):
            continue
        next_block = blocks[index] if index < len(blocks) else None
        span = (seq_spans or {}).get(index)
        for item in _block_findings(block, next_block=next_block, long_limit=long_limit):
            findings.append(
                {
                    "unit": unit_id,
                    "block": index,
                    "seq_range": list(span) if span else None,
                    "context": " ".join(block.split())[:60],
                    **item,
                }
            )
    text_blocks = [block for block in blocks if not _is_code(block)]
    for item in _quote_issues("".join(_plain_without_inline_code(block) for block in text_blocks)):
        findings.append({"unit": unit_id, "block": None, "seq_range": None, "context": "", **item})
    return findings


def scan_workspace(store: Any, *, unit_id: str | None = None) -> dict[str, Any]:
    """只读扫描 translation md 与译注；coverage 明确扫了什么、跳了什么。"""
    pub = store.load_publication()
    units: list[dict[str, Any]] = []
    all_findings: list[dict[str, Any]] = []
    scanned: list[str] = []
    skipped_kind: list[str] = []
    missing_translation: list[str] = []
    for unit in pub.units:
        if unit_id and unit.id != unit_id:
            continue
        rel = (unit.meta or {}).get("rel_path")
        if str(unit.kind or "") in _SKIP_UNIT_KINDS:
            skipped_kind.append(unit.id)
            continue
        path = store.translation_dir / str(rel) if rel else None
        if path is None or not path.is_file():
            missing_translation.append(unit.id)
            continue
        md_text = path.read_text(encoding="utf-8")
        spans: dict[int, tuple[int, int]] = {}
        align_path = store.unit_align_path(unit.id)
        if align_path.is_file():
            from auto_translator.review.g0 import align_block_spans
            from auto_translator.translation.align import read_align

            block_spans, _issues = align_block_spans(
                md_text, read_align(align_path), title=unit.title
            )
            spans = {
                int(span["block"]): (int(span["seq_start"]), int(span["seq_end"]))
                for span in block_spans
            }
        findings = scan_unit(unit.id, md_text, seq_spans=spans)
        units.append({"unit": unit.id, "findings": len(findings), "status": "read_only"})
        all_findings.extend(findings)
        scanned.append(unit.id)

    notes_path = store.translation_dir / "notes.json"
    notes_scope = "none"
    notes_scanned: list[str] = []
    notes_skipped: list[str] = []
    if notes_path.is_file():
        try:
            payload = json.loads(notes_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"translation/notes.json 解析失败（不是 0 个问题）：{exc.msg} @line {exc.lineno}"
            ) from None
        if not isinstance(payload, dict):
            raise ValueError("translation/notes.json 必须是 JSON 对象")
        all_notes = [item for item in payload.get("notes") or [] if isinstance(item, dict)]
        if unit_id is None:
            notes_scope = "all"
            selected = all_notes
        else:
            referenced = {
                str(ref.get("note_id"))
                for ref in payload.get("references") or []
                if isinstance(ref, dict) and str(ref.get("unit") or "") == unit_id
            }
            if referenced:
                notes_scope = "referenced"
                selected = [n for n in all_notes if str(n.get("note_id")) in referenced]
                notes_skipped = [
                    str(n.get("note_id"))
                    for n in all_notes
                    if str(n.get("note_id")) not in referenced
                ]
            else:
                notes_scope = "unmapped"
                selected = []
                notes_skipped = [str(n.get("note_id")) for n in all_notes]
        for note in selected:
            target = str(note.get("target_markdown") or "")
            if not target.strip():
                continue
            findings = scan_unit(f"notes:{note.get('note_id')}", target)
            for item in findings:
                item["note_id"] = note.get("note_id")
            all_findings.extend(findings)
            notes_scanned.append(str(note.get("note_id")))
            if findings:
                units.append(
                    {
                        "unit": f"notes:{note.get('note_id')}",
                        "findings": len(findings),
                        "status": "read_only",
                    }
                )
    counts: dict[str, int] = {}
    for item in all_findings:
        counts[item["code"]] = counts.get(item["code"], 0) + 1
    return {
        "writes": False,
        "units": units,
        "findings": all_findings,
        "counts": counts,
        "coverage": {
            "units_scanned": scanned,
            "units_skipped_kind": skipped_kind,
            "units_missing_translation": missing_translation,
            "notes_scope": notes_scope,
            "notes_scanned": notes_scanned,
            "notes_skipped": notes_skipped,
        },
    }
