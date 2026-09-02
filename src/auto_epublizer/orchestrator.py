"""Orchestrator：薄 façade，只装配与路由，不直接调用领域函数、不持有线程池。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import analysis as analysis_mod
from . import review as review_mod
from . import translation as translation_mod
from .build import build_epub
from .build.html import render_bilingual_document, render_document, slug_file
from .config import Config
from .ingest import load_document
from .llm import create_client
from .llm.base import LLMClient
from .qa import audit_epub, generate_report, run_epubcheck
from .structure import rebuild_structure, write_structured
from .translation.align import read_align
from .workspace import RunStore, init_workspace


class OrchestrationError(RuntimeError):
    """编排失败，向 CLI 显示的中文错误。"""


def make_client(config: Config) -> LLMClient:
    return create_client(config.llm)


def init(
    input_path: str,
    *,
    config: Config | None = None,
    target_language: str | None = None,
    references: list[str] | None = None,
    workspace_dir: str | None = None,
) -> RunStore:
    return init_workspace(
        input_path,
        config=config,
        target_language=target_language,
        references=references,
        workspace_dir=workspace_dir,
    )


def convert(store: RunStore, *, output: str | None = None) -> Path:
    """仅转换：ingest + structure + build + qa。"""
    doc = load_document(store.dir / store.load_publication().meta.source, store=store)
    pub = store.load_publication()
    entries = rebuild_structure(doc, pub)
    write_structured(store, doc, entries)
    store.set_units(entries)
    for e in entries:
        store.set_unit_status(e["id"], "split")

    pub = store.load_publication()
    out_path = Path(output) if output else store.output_dir / f"{pub.slug}.epub"
    # convert 不翻译：正文是源语言，EPUB 语言标注须用源语言（未检测时为 und）。
    lang = pub.meta.language or "und"
    content = []
    for e in entries:
        structured = store.structured_dir / e["rel_path"]
        if not structured.is_file():
            continue
        md_text = structured.read_text(encoding="utf-8")
        content.append(
            (
                f"{slug_file(e['id'])}.xhtml",
                render_document(e["title"], md_text, lang=lang),
            )
        )
    build_epub(
        pub,
        entries,
        content,
        lang=lang,
        modified="2026-01-01T00:00:00Z",
        out_path=out_path,
    )
    for e in entries:
        store.set_unit_status(e["id"], "built")
    store.log_event("convert_built", slug=pub.slug, units=len(entries), output=str(out_path))
    return out_path


def analyze(store: RunStore, client: LLMClient, *, tier: str = "cheap") -> dict[str, Any]:
    return analysis_mod.analyze(store, client, tier=tier)


def translate(
    store: RunStore,
    client: LLMClient,
    *,
    target_language: str | None = None,
    tier: str = "strong",
    bilingual: bool = False,
) -> dict[str, Any]:
    return translation_mod.translate(store, client, target_lang=target_language, tier=tier)


def review(store: RunStore, client: LLMClient) -> dict[str, Any]:
    return review_mod.review(store, client)


def build(store: RunStore, *, bilingual: bool = False, output: str | None = None) -> Path:
    """从译文（缺省回退源文）构建 EPUB；双语时输出 -bi.epub。"""
    pub = store.load_publication()
    entries = [
        {
            "id": u.id,
            "kind": u.kind,
            "region": (u.meta or {}).get("region", "body"),
            "title": u.title,
            "rel_path": (u.meta or {}).get("rel_path", ""),
        }
        for u in pub.units
    ]
    if not entries:
        raise OrchestrationError("工作区无内容单元；请先 init/convert")
    suffix = "-bi" if bilingual else ""
    out_path = Path(output) if output else store.output_dir / f"{pub.slug}{suffix}.epub"
    lang = pub.meta.target_language or "zh-CN"
    src_lang = pub.meta.language or "und"
    content = []
    for e in entries:
        rel = e.get("rel_path")
        if not rel:
            continue
        if bilingual:
            rows = read_align(store.unit_align_path(e["id"]))
            if not rows:
                continue
            content.append(
                (
                    f"{slug_file(e['id'])}.xhtml",
                    render_bilingual_document(e["title"], rows, lang_src=src_lang, lang_tgt=lang),
                )
            )
            continue
        tgt = store.translation_dir / rel
        src = store.structured_dir / rel
        md_path = tgt if tgt.is_file() else src
        if not md_path.is_file():
            continue
        md_text = md_path.read_text(encoding="utf-8")
        content.append(
            (f"{slug_file(e['id'])}.xhtml", render_document(e["title"], md_text, lang=lang))
        )
    build_epub(
        pub,
        entries,
        content,
        lang=lang,
        modified="2026-01-01T00:00:00Z",
        out_path=out_path,
    )
    for e in entries:
        store.set_unit_status(e["id"], "built")
    store.log_event("built", slug=pub.slug, bilingual=bilingual, output=str(out_path))
    return out_path


def qa(store: RunStore, *, epub_path: str | None = None) -> dict[str, Any]:
    pub = store.load_publication()
    epub = Path(epub_path) if epub_path else store.output_dir / f"{pub.slug}.epub"
    if not epub.is_file():
        raise OrchestrationError(f"成品不存在：{epub}；请先 build/convert")
    audit = audit_epub(epub)
    epubcheck = run_epubcheck(epub)
    report = generate_report(pub.slug, audit, epubcheck, epub_path=str(epub))
    store.save_qa(report.to_dict())
    return report.to_dict()


def status(store: RunStore, *, as_json: bool = False) -> dict[str, Any]:
    pub = store.load_publication()
    data = {
        "slug": pub.slug,
        "title": pub.meta.title,
        "target_language": pub.meta.target_language,
        "units_total": len(pub.units),
        "units": [
            {"id": u.id, "kind": u.kind, "title": u.title, "status": u.status} for u in pub.units
        ],
    }
    return data
