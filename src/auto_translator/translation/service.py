"""translation 服务：切片 → 分层上下文 → 段落翻译 → 句对齐 → 落盘。"""

from __future__ import annotations

import re
from typing import Any

from auto_common.llm.base import LLMClient
from auto_common.workspace import RunStore

from ..agents.translator import TranslatorAgent
from ..glossary import Glossary, load_glossary_csv, terms_in_text
from .align import align_rows, write_align
from .slice import chunk_paragraphs

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _parse_blocks(md_text: str) -> tuple[str, list[str]]:
    """把 structured md 解析为 (标题, 段落数组)。"""
    lines = md_text.splitlines()
    title = ""
    body: list[str] = []
    current: list[str] = []
    for line in lines:
        m = _HEADING_RE.match(line)
        if m and not title:
            title = m.group(2).strip()
        elif not line.strip():
            if current:
                body.append("\n".join(current).strip())
                current = []
        else:
            current.append(line)
    if current:
        body.append("\n".join(current).strip())
    return title, body


def _read_analysis(store: RunStore, unit_id: str) -> str:
    """读取分层理解上下文（概览/全局/单元理解），缺省静默跳过。

    来源优先级：analysis/（analyze 或 agent 直写）→ preprocessing/（agent 预处理产物）。
    """
    parts: list[str] = []
    for name in ("overview.md", "global.md", "keypoints.md"):
        p = store.analysis_dir / name
        if p.is_file():
            parts.append(p.read_text(encoding="utf-8"))
    if not parts:
        pre_global = store.preprocessing_dir / "global.md"
        if pre_global.is_file():
            parts.append(pre_global.read_text(encoding="utf-8"))
    unit_p = store.analysis_dir / "units" / f"{unit_id}.md"
    if unit_p.is_file():
        parts.append(unit_p.read_text(encoding="utf-8"))
    else:
        pre_unit = store.preprocessing_dir / "units" / f"{unit_id}.md"
        if pre_unit.is_file():
            parts.append(pre_unit.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def translate_unit(
    store: RunStore,
    client: LLMClient,
    *,
    unit_id: str,
    rel_path: str,
    glossary: Glossary,
    target_lang: str,
    tier: str,
) -> dict[str, Any]:
    """翻译单个单元：翻译正文 + 写 translation/<rel_path> 与 align/<id>.jsonl。"""
    agent = TranslatorAgent(client, tier=tier)
    src_path = store.structured_dir / rel_path
    title, paragraphs = _parse_blocks(src_path.read_text(encoding="utf-8"))

    blocks = ([title] if title else []) + paragraphs
    context = _read_analysis(store, unit_id)

    translated_blocks: list[str] = []
    rolling: list[str] = []
    for batch in chunk_paragraphs(blocks):
        batch_texts = [s.text for s in batch]
        terms = [
            (e.source, e.target)
            for e in terms_in_text("\n".join(batch_texts), glossary)
            if e.target
        ]
        ctx = context
        if rolling:
            ctx = (
                (ctx + "\n\n前文译文：\n" + "\n".join(rolling[-6:]))
                if ctx
                else "\n".join(rolling[-6:])
            )
        results = agent.translate_batch(batch_texts, context=ctx, terms=terms)
        # 续段回并到上一段
        for idx, s in enumerate(batch):
            text = "".join(results[idx]) if idx < len(results) else ""
            if s.cont and translated_blocks:
                translated_blocks[-1] += text
            else:
                translated_blocks.append(text)
        rolling.extend("".join(r) for r in results)

    # 重组译文 markdown（标题 + 段落）
    tgt_title = translated_blocks[0] if title else ""
    tgt_body = translated_blocks[1:] if title else translated_blocks
    lines: list[str] = []
    if title:
        lines.append(f"# {tgt_title}")
        lines.append("")
    for p in tgt_body:
        lines.append(p)
        lines.append("")
    translated_md = "\n".join(lines).rstrip() + "\n"

    tgt_path = store.translation_dir / rel_path
    tgt_path.parent.mkdir(parents=True, exist_ok=True)
    tgt_path.write_text(translated_md, encoding="utf-8")

    # 句级对齐：每块 src↔tgt 逐句对齐，全局 seq 连续
    rows: list[dict[str, Any]] = []
    seq = 0
    for s, t in zip(blocks, translated_blocks, strict=False):
        for row in align_rows(s, t):
            seq += 1
            rows.append({"seq": seq, "src": row["src"], "tgt": row["tgt"], "note": row["note"]})
    write_align(store.unit_align_path(unit_id), rows)

    return {"unit": unit_id, "blocks": len(blocks), "sentences": seq, "target_lang": target_lang}


def translate(
    store: RunStore,
    client: LLMClient,
    *,
    target_lang: str | None = None,
    tier: str = "strong",
    force: bool = False,
) -> dict[str, Any]:
    """翻译工作区单元（body/frontmatter/backmatter）。

    默认跳过已完成翻译的单元（translated/aligned/reviewed/built），断点续跑不重复计费；
    ``force=True`` 时全部重译。
    """
    pub = store.load_publication()
    target = target_lang or pub.meta.target_language or "zh-CN"
    glossary = Glossary(load_glossary_csv(store.analysis_dir / "glossary.csv"))

    done_statuses = {"translated", "aligned", "reviewed", "built"}
    translated = 0
    skipped = 0
    for unit in pub.units:
        rel_path = (unit.meta or {}).get("rel_path")
        if not rel_path:
            continue
        if not force and unit.status in done_statuses:
            skipped += 1
            continue
        info = translate_unit(
            store,
            client,
            unit_id=unit.id,
            rel_path=rel_path,
            glossary=glossary,
            target_lang=target,
            tier=tier,
        )
        translated += 1
        store.set_unit_status(unit.id, "translated")
        store.set_unit_status(unit.id, "aligned")
        store.log_event("batch_translated", unit=unit.id, sentences=info["sentences"])

    # 用量账本：一次运行增量只合并一次（run_id 幂等）
    from datetime import datetime

    run_id = f"translate-{datetime.now().astimezone().strftime('%Y%m%dT%H%M%S')}"
    store.merge_usage(client.usage_summary(), run_id=run_id)

    return {"units": translated, "skipped": skipped, "target_lang": target}
