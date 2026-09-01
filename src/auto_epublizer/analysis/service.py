"""analysis 服务：分层理解生成 + 术语播种 + 语言/体裁检测。

产出（对齐 docs/development-plan.md C5）：
- ``analysis/overview.md`` 全书概览；
- ``analysis/global.md`` 全局理解；
- ``analysis/units/<id>.md`` 每单元理解；
- ``analysis/keypoints.md`` 重点内容；
- ``analysis/style.md`` 文体档案；
- ``analysis/glossary.csv`` 术语播种（三态 seed）+ ``characters.csv`` 人物表；
- 更新 ``publication.json`` 的 meta.language / meta.genre 与单元状态 analyzed。
"""

from __future__ import annotations

from typing import Any

from ..agents.analyzer import AnalyzerAgent
from ..genre.langprofile import get_langprofile
from ..genre.profiles import get_profile
from ..glossary import (
    STATUS_SEED,
    Glossary,
    GlossaryEntry,
    load_glossary_csv,
    save_glossary_csv,
)
from ..llm.base import LLMClient
from ..workspace import RunStore
from .detect import detect_genre, detect_language


def render_style_md(
    genre: str,
    *,
    detect: str,
    lang: str,
    style: dict[str, Any] | None = None,
) -> str:
    """按文体档案 + 语言指引生成 analysis/style.md。"""
    profile = get_profile(genre)
    langprofile = get_langprofile(lang)
    lines = [
        "# 文体档案（style.md）",
        "",
        "```yaml",
        f"genre: {genre}",
        f"detect: {detect}",
    ]
    style_vals = style or {}
    if style_vals:
        lines.append("style:")
        for k, v in style_vals.items():
            lines.append(f"  {k}: {v}")
    lines.append("term_types: [" + ", ".join(profile.term_types) + "]")
    lines.append("review_focus: [" + ", ".join(profile.review_focus) + "]")
    lines.append("source_only_types: [" + ", ".join(profile.source_only_types) + "]")
    lines.append("```")
    lines.append("")
    lines.append("## 翻译指引（文体）")
    for rule in profile.translation_rules:
        lines.append(f"- {rule}")
    lines.append("")
    lines.append(f"## 语言指引（源语言 {lang}）")
    for g in langprofile.guidance:
        lines.append(f"- {g}")
    lines.append("")
    return "\n".join(lines)


def _seed_glossary(
    entries: list[dict[str, Any]],
    *,
    term_types: tuple[str, ...],
    existing: Glossary,
) -> list[GlossaryEntry]:
    """把 agent 提取的术语播种进术语库（不覆盖既有译法）。"""
    added: list[GlossaryEntry] = []
    for item in entries:
        source = (item.get("source") or "").strip()
        target = (item.get("target") or "").strip()
        if not source:
            continue
        if existing.lookup(source):
            continue
        t = (item.get("type") or "term").strip()
        if term_types and t not in term_types:
            t = "term"
        entry = GlossaryEntry(
            source=source,
            target=target,
            type=t,
            aliases=list(item.get("aliases") or []),
            gender=(item.get("gender") or "").strip(),
            note=(item.get("note") or "").strip(),
            status=STATUS_SEED,
        )
        existing.add(entry)
        added.append(entry)
    return added


def _unit_texts(store: RunStore) -> list[dict[str, Any]]:
    """读取 structured/ 下所有单元正文，返回 [{id,title,text,rel_path}]。"""
    pub = store.load_publication()
    out: list[dict[str, Any]] = []
    for unit in pub.units:
        rel_path = (unit.meta or {}).get("rel_path")
        if not rel_path:
            continue
        p = store.structured_dir / rel_path
        if not p.is_file():
            continue
        out.append(
            {
                "id": unit.id,
                "title": unit.title,
                "text": p.read_text(encoding="utf-8"),
                "rel_path": rel_path,
            }
        )
    return out


def analyze(store: RunStore, client: LLMClient, *, tier: str = "cheap") -> dict[str, Any]:
    """执行分层理解并落盘；返回摘要。"""
    pub = store.load_publication()
    units = _unit_texts(store)
    full_text = "\n\n".join(u["text"] for u in units)

    lang = pub.meta.language or detect_language(full_text)
    genre = pub.meta.genre or detect_genre(full_text)
    profile = get_profile(genre)

    agent = AnalyzerAgent(client, tier=tier)

    # style.md
    store.analysis_dir.mkdir(parents=True, exist_ok=True)
    (store.analysis_dir / "style.md").write_text(
        render_style_md(genre, detect="auto" if not pub.meta.genre else "explicit", lang=lang),
        encoding="utf-8",
    )

    # overview / global / keypoints
    overview = agent.overview(full_text[:6000])
    global_md = agent.global_understanding(full_text[:6000])
    (store.analysis_dir / "overview.md").write_text(
        f"# 内容概要（overview.md）\n\n{overview}\n", encoding="utf-8"
    )
    (store.analysis_dir / "global.md").write_text(
        f"# 全局理解（global.md）\n\n{global_md}\n", encoding="utf-8"
    )

    # 每单元理解
    units_dir = store.analysis_dir / "units"
    units_dir.mkdir(parents=True, exist_ok=True)
    keypoints: list[str] = []
    for u in units:
        md = agent.unit_understanding(u["title"], u["text"][:4000], global_md[:1200])
        safe = u["id"].replace("/", "-")
        (units_dir / f"{safe}.md").write_text(
            f"# {u['title']} 单元理解\n\n{md}\n", encoding="utf-8"
        )
        keypoints.append(f"- {u['title']}：{md.strip().splitlines()[0] if md.strip() else ''}")
    (store.analysis_dir / "keypoints.md").write_text(
        "# 重点内容（keypoints.md）\n\n" + "\n".join(keypoints) + "\n", encoding="utf-8"
    )

    # 术语播种 + 人物表
    glossary_path = store.analysis_dir / "glossary.csv"
    existing = Glossary(load_glossary_csv(glossary_path))
    seeds = agent.seed_terms(full_text[:8000], profile.term_types)
    _seed_glossary(seeds, term_types=profile.term_types, existing=existing)
    save_glossary_csv(glossary_path, existing.entries())

    if profile.needs_characters:
        characters = agent.characters(full_text[:8000])
        if characters:
            import csv

            with open(
                store.analysis_dir / "characters.csv", "w", encoding="utf-8", newline=""
            ) as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=[
                        "source",
                        "target",
                        "aliases",
                        "gender",
                        "role",
                        "first_chapter",
                        "note",
                    ],
                )
                w.writeheader()
                for c in characters:
                    w.writerow(
                        {
                            "source": c.get("source", ""),
                            "target": c.get("target", ""),
                            "aliases": "",
                            "gender": c.get("gender", ""),
                            "role": c.get("role", ""),
                            "first_chapter": "",
                            "note": c.get("note", ""),
                        }
                    )

    # 回填元数据 + 状态
    from ..workspace import update_meta

    update_meta(store, language=lang, genre=genre)
    for u in units:
        store.set_unit_status(u["id"], "analyzed")
    store.log_event("analysis_saved", has_analysis=True, units=len(units), lang=lang, genre=genre)

    return {"language": lang, "genre": genre, "units": len(units), "terms_seeded": len(seeds)}
