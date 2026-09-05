"""预处理事实收集与落盘：preprocessing/facts.json + facts.md。

全部确定性、零 token。facts 是 agent 做方案决策（plan.md）与分层理解
（global/units/terms/risks）的唯一事实输入；agent 待办清单内嵌于 facts.md。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from auto_common.workspace import RunStore, atomic_write_json

from ..doctor import capabilities_summary, collect_capabilities
from ..structure import count_empty_units
from . import sniff as sniff_mod
from .sniff import SniffError  # noqa: F401  (re-export 供调用方)

# 版权残句特征（与 g0 strip_copyright_boilerplate 同源，供体检引用）
_COPYRIGHT_MARKERS = (
    "All rights reserved",
    "First published",
    "Printed in",
    "Library of Congress Cataloging",
    "British Library Cataloguing",
)

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_LATIN = re.compile(r"[A-Za-z]+")


def _count_words(text: str) -> int:
    """粗略词数：CJK 按字符、拉丁按空格词。"""
    return len(_CJK.findall(text)) + len(_LATIN.findall(text))


def _unit_facts(store: RunStore) -> list[dict[str, Any]]:
    """逐单元统计：region/kind/标题/字符数/词数/段数/句数（读 structured md）。"""
    from auto_translator.translation.align import split_sentences

    pub = store.load_publication()
    units: list[dict[str, Any]] = []
    for u in pub.units:
        rel = (u.meta or {}).get("rel_path")
        p = store.structured_dir / rel if rel else None
        chars = words = paras = sents = 0
        if p and p.is_file():
            text = p.read_text(encoding="utf-8")
            chars = len(text)
            words = _count_words(text)
            paras = len([b for b in re.split(r"\n\s*\n", text) if b.strip()])
            sents = len(split_sentences(text))
        units.append(
            {
                "id": u.id,
                "kind": u.kind,
                "region": (u.meta or {}).get("region", "body"),
                "title": u.title,
                "rel_path": rel or "",
                "chars": chars,
                "words": words,
                "paragraphs": paras,
                "sentences": sents,
            }
        )
    return units


def _media_facts(store: RunStore) -> dict[str, Any]:
    media_dir = store.structured_dir / "raw" / "media"
    files = (
        sorted(
            p.relative_to(store.structured_dir / "raw").as_posix()
            for p in media_dir.rglob("*")
            if p.is_file()
        )
        if media_dir.is_dir()
        else []
    )
    cover_candidates = [f for f in files if "cover" in f.lower()]
    return {"count": len(files), "files": files, "cover_candidates": cover_candidates}


def _checks_facts(store: RunStore, sniff_facts: dict[str, Any]) -> dict[str, Any]:
    """内容体检：版权残句 / 空壳单元 / DRM / 扫描件与乱码（PDF）。"""
    texts: list[str] = []
    titles: list[str] = []
    pub = store.load_publication()
    for u in pub.units:
        rel = (u.meta or {}).get("rel_path")
        p = store.structured_dir / rel if rel else None
        if p and p.is_file():
            texts.append(p.read_text(encoding="utf-8"))
            titles.append(u.title)
    copyright_units = [
        title
        for title, text in zip(titles, texts, strict=False)
        if any(m in title or m in text for m in _COPYRIGHT_MARKERS)
    ]
    checks: dict[str, Any] = {
        "copyright_residual_units": copyright_units,
        "empty_shell_units": count_empty_units(texts, titles),
        "drm": bool(sniff_facts.get("drm")),
    }
    if sniff_facts.get("kind") == "pdf":
        checks["scanned"] = bool(sniff_facts.get("scanned"))
        checks["garbled_ratio"] = sniff_facts.get("garbled_ratio", 0.0)
    return checks


def collect_facts(store: RunStore, config) -> dict[str, Any]:
    """收集全部预处理事实（确定性、零 token）。"""
    pub = store.load_publication()
    source_path = store.dir / pub.meta.source
    sniff_facts = sniff_mod.sniff(source_path) if source_path.is_file() else {"kind": "unknown"}

    units = _unit_facts(store)
    totals = {
        "units": len(units),
        "chars": sum(u["chars"] for u in units),
        "words": sum(u["words"] for u in units),
        "sentences": sum(u["sentences"] for u in units),
        # token 粗估（保守：chars/2）；仅用于规划，非计费依据
        "estimated_tokens": sum(u["chars"] for u in units) // 2,
    }
    capabilities = capabilities_summary(collect_capabilities(config, ping=False))

    suggestions = _route_suggestions(sniff_facts, capabilities)
    return {
        "source": {
            "file": pub.meta.source,
            "sha256": pub.meta.source_sha256,
            "size_bytes": source_path.stat().st_size if source_path.is_file() else 0,
            **sniff_facts,
        },
        "capabilities": capabilities,
        "structure": {"units": units, "totals": totals},
        "media": _media_facts(store),
        "checks": _checks_facts(store, sniff_facts),
        "suggestions": suggestions,
        "agent_todo": [
            "preprocessing/capabilities.md：自报五维能力边界（multimodal/search/模型/外部 API/工作量），见 references/preprocessing.md §1.1",
            "preprocessing/plan.md：结合 capabilities 与 suggestions 写处理方案决策（路由+依据）",
            "preprocessing/global.md：主要内容/中心思想/语言风格/叙事结构",
            "preprocessing/units/<id>.md：每章梗概/思想/登场人物/术语注意",
            "preprocessing/terms.csv：术语预提取（列格式=glossary.csv；翻译前可经 import --terms 导入）",
            "preprocessing/risks.md：难段落/多语/文化梗/术语冲突预判",
            "preprocessing/report.md：汇总报告（翻译前输入锚点）",
        ],
    }


def _ocr_routing(caps: dict[str, Any]) -> list[str]:
    """扫描件路由提示（确定性；最终决策见 preprocessing/plan.md）。

    优先级（2026-09 更新）：**MinerU 外部 API 最优先**（版面分析，可识别
    换行/插图/表格/公式）——key 未配置时先询问用户；无 key 才退次选：
    传统 OCR（只识别字符）+ agent 逐页阅读 OCR 产物补换行、期间找插图。
    """
    c = caps["capabilities"]
    if c.get("mineru", {}).get("available"):
        return [
            "扫描件路由：首选 MinerU 外部 API（MINERU_API_KEY 已配置；"
            "pdf.backend=auto 时 init 自动走 MinerU，版面/换行/插图由其识别）"
        ]
    out = [
        "扫描件路由：最优先方案是 MinerU 外部 API（能识别换行/插图/版面，"
        "传统 OCR 只识别字符）——请先询问用户是否有 MinerU API key"
    ]
    if c.get("tesseract", {}).get("available") or c.get("ocrmypdf", {}).get("available"):
        out.append(
            "次选（无 key 时）：传统 OCR（tesseract/ocrmypdf 可用，先重建文字层再入库）"
            "+ agent 逐页阅读 OCR 产物补换行、看 raw/pages/ 页图找插图"
        )
    elif c.get("rapidocr", {}).get("available"):
        out.append(
            "次选（无 key 时）：RapidOCR 离线 OCR（init 自动走 pdf.ocr: auto）"
            "+ agent 逐页阅读 OCR 产物补换行、看 raw/pages/ 页图找插图"
        )
    else:
        out.append(
            "无可用 OCR 手段——询问用户：提供 MinerU key、其他 OCR 手段，或手工 OCR 后重跑"
            "（若你可看图〔multimodal 自报〕，可自行视觉兜底难页）"
        )
    return out


def _route_suggestions(sniff_facts: dict[str, Any], capabilities: dict[str, Any]) -> list[str]:
    """确定性路由提示（非决策；决策由 agent 写 plan.md）。"""
    caps = capabilities["capabilities"]
    out: list[str] = []
    kind = sniff_facts.get("kind")
    if kind in ("epub", "docx", "html") and not caps["pandoc"]["available"]:
        out.append("pandoc 缺失：该输入需先安装 pandoc，或由用户转为 PDF/TXT/MD")
    if kind == "epub" and sniff_facts.get("drm"):
        out.append("EPUB 含加密描述（DRM）：无法直接解析，需用户提供无 DRM 来源")
    if kind == "pdf":
        if sniff_facts.get("scanned"):
            out.extend(_ocr_routing(capabilities))
        elif not sniff_facts.get("has_text_layer"):
            out.append("PDF 文字层判定异常：请人工复核")
        if sniff_facts.get("garbled_ratio", 0) > 0.02:
            out.append(
                f"乱码率偏高（{sniff_facts.get('garbled_ratio')}）：文字层可能损坏，考虑重新 OCR"
            )
    if kind in ("txt", "md"):
        out.append("纯文本输入：按标题启发式切分章节")
    return out


def render_facts_md(facts: dict[str, Any]) -> str:
    """facts.md：人类可读 + agent 待办。"""
    src = facts["source"]
    lines = [
        "# 预处理事实（facts.md）",
        "",
        "## 源文件",
        "",
        f"- 文件：`{src.get('file')}`（{src.get('kind')}，{src.get('size_bytes', 0)} 字节）",
        f"- sha256：`{src.get('sha256', '')[:16]}…`",
    ]
    meta = src.get("metadata") or {}
    if meta:
        lines.append("- 元数据：" + "；".join(f"{k}={v}" for k, v in meta.items() if v))
    if src.get("kind") == "pdf":
        lines.append(
            f"- 文字层：{'有' if src.get('has_text_layer') else '无（扫描件）'}，"
            f"{src.get('page_count')} 页，空文字层比例 {src.get('empty_text_ratio')}"
        )
        if src.get("toc"):
            lines.append(f"- 书签 TOC：{len(src['toc'])} 条")
    if src.get("kind") == "epub":
        lines.append(
            f"- DRM：{'是（无法解析）' if src.get('drm') else '无'}；spine {src.get('spine_count')} 项"
        )
        if src.get("toc"):
            lines.append(f"- 目录：{len(src['toc'])} 条")

    totals = facts["structure"]["totals"]
    lines += [
        "",
        "## 规模",
        "",
        f"- 单元 {totals['units']}：字符 {totals['chars']} / 词 {totals['words']} / 句 {totals['sentences']}"
        f"（token 粗估 ≈{totals['estimated_tokens']}）",
        "",
        "## 结构清单",
        "",
        "| id | region | kind | 标题 | 字符 | 句数 |",
        "|---|---|---|---|---|---|",
    ]
    for u in facts["structure"]["units"]:
        lines.append(
            f"| {u['id']} | {u['region']} | {u['kind']} | {u['title'][:24]} | {u['chars']} | {u['sentences']} |"
        )

    checks = facts["checks"]
    lines += ["", "## 体检", ""]
    if checks.get("drm"):
        lines.append("- ⚠ DRM：无法直接解析")
    if checks.get("scanned"):
        lines.append("- ⚠ 扫描件（空文字层比例超阈值）")
    if checks.get("garbled_ratio"):
        lines.append(f"- 乱码率：{checks['garbled_ratio']}")
    if checks.get("empty_shell_units"):
        lines.append(f"- 空壳单元：{checks['empty_shell_units']}（build 时自动跳过）")
    if checks.get("copyright_residual_units"):
        lines.append(
            f"- 版权残句单元：{len(checks['copyright_residual_units'])}（{', '.join(checks['copyright_residual_units'])}）"
        )
    if not any(
        [
            checks.get("drm"),
            checks.get("scanned"),
            checks.get("garbled_ratio"),
            checks.get("empty_shell_units"),
            checks.get("copyright_residual_units"),
        ]
    ):
        lines.append("- 无异常")

    media = facts["media"]
    lines += [
        "",
        "## 媒体",
        "",
        f"- 文件 {media['count']} 个"
        + (f"；封面候选 {len(media['cover_candidates'])}" if media["cover_candidates"] else ""),
    ]

    caps = facts["capabilities"]
    lines += ["", "## 环境能力快照（doctor）", ""]
    for name, item in caps["capabilities"].items():
        lines.append(f"- {'✓' if item['available'] else '✗'} {name}")
    lines.append(f"- multimodal：{'是' if caps['multimodal'] else '待 agent 自报（能否看图）'}")
    lines.append(f"- search：{'有' if caps['search'] else '待 agent 自报（是否有网络搜索工具）'}")

    lines += ["", "## 路由提示（确定性；最终决策见 preprocessing/plan.md）", ""]
    for s in facts["suggestions"]:
        lines.append(f"- {s}")

    lines += ["", "## agent 待办", ""]
    for todo in facts["agent_todo"]:
        lines.append(f"- [ ] {todo}")
    lines.append("")
    return "\n".join(lines)


def write_facts(store: RunStore, facts: dict[str, Any]) -> tuple[Path, Path]:
    """落盘 preprocessing/facts.json（原子）+ facts.md；返回两者路径。"""
    pre = store.preprocessing_dir
    pre.mkdir(parents=True, exist_ok=True)
    json_path = pre / "facts.json"
    md_path = pre / "facts.md"
    atomic_write_json(json_path, facts)
    md_path.write_text(render_facts_md(facts), encoding="utf-8")
    return json_path, md_path
