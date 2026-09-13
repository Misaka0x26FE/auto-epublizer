"""Orchestrator：薄 façade，只装配与路由，不直接调用领域函数、不持有线程池。

唯一 LLM 原则：编排层不做任何 LLM 调用——理解/翻译/审校由操作 CLI 的 agent 完成，
这里只装配确定性领域服务（ingest/structure/build/qa/preprocess）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from auto_common.config import Config
from auto_common.workspace import RunStore, init_workspace, read_json
from auto_translator.translation.align import read_align

from .build import build_epub, collect_media
from .build.html import render_bilingual_document, render_document, slug_file
from .ingest import load_document
from .qa import audit_epub, generate_report, run_epubcheck
from .qa.provenance import audit_provenance
from .structure import rebuild_structure, skip_empty_unit, unit_heading, write_structured


class OrchestrationError(RuntimeError):
    """编排失败，向 CLI 显示的中文错误。"""


def init(
    input_path: str,
    *,
    config: Config | None = None,
    target_language: str | None = None,
    references: list[str] | None = None,
    workspace_dir: str | None = None,
) -> RunStore:
    store = init_workspace(
        input_path,
        config=config,
        target_language=target_language,
        references=references,
        workspace_dir=workspace_dir,
    )
    prepare_structure(store, config=config)
    return store


def structure_entries(store: RunStore) -> list[dict[str, Any]]:
    """从 publication.units 构建构建期 entries（含目录层级 level）。"""
    pub = store.load_publication()
    return [
        {
            "id": u.id,
            "kind": u.kind,
            "region": (u.meta or {}).get("region", "body"),
            "title": u.title,
            "level": int((u.meta or {}).get("level") or 1),
            "rel_path": (u.meta or {}).get("rel_path", ""),
        }
        for u in pub.units
    ]


def _ocr_backend_if_needed(store: RunStore, config: Config | None = None):
    """PDF 源且 rapidocr 可用时返回 OCR 后端（按 config.pdf.ocr 控制），否则 None。

    - ``pdf.ocr: auto``（默认）→ 可用即启用；
    - ``pdf.ocr: off`` → 禁用；
    - 其他值 → 视为要求强制启用，不可用时明确报错。
    """
    import importlib.util

    pub = store.load_publication()
    if not pub.meta.source.lower().endswith(".pdf"):
        return None
    cfg = config or Config()
    ocr_setting = (cfg.pdf.ocr or "auto").lower()
    if ocr_setting == "off":
        return None
    spec = importlib.util.find_spec("rapidocr_onnxruntime")
    if spec is None:
        if ocr_setting == "auto":
            return None
        raise OrchestrationError(
            "pdf.ocr 要求启用 OCR，但未安装 rapidocr-onnxruntime（uv sync --extra ocr）"
        )
    from .ingest.ocr import RapidOcrBackend

    return RapidOcrBackend()


def _mineru_client_if_preferred(store: RunStore, config: Config | None = None):
    """MinerU 路由决策（扫描件最优先：版面/换行/插图识别，传统 OCR 只识别字符）。

    - ``pdf.backend: mineru`` → 强制 MinerU（缺 MINERU_API_KEY 时明确报错）；
    - ``pdf.backend: pymupdf`` → 禁用；
    - ``auto``（默认）→ 扫描件（嗅探判定）且 key 存在 → MinerU；
      文字层 PDF 仍走 pymupdf（离线、零成本）。
    """
    import os

    from .ingest.mineru import MineruClient

    pub = store.load_publication()
    if not pub.meta.source.lower().endswith(".pdf"):
        return None
    cfg = config or Config()
    backend = (cfg.pdf.backend or "auto").lower()
    if backend == "pymupdf":
        return None
    key = os.environ.get("MINERU_API_KEY", "")
    if not key:
        if backend == "mineru":
            raise OrchestrationError(
                "pdf.backend=mineru 需要环境变量 MINERU_API_KEY（未检测到；"
                "请向用户询问 MinerU API key）"
            )
        return None
    if backend == "mineru":
        return MineruClient(key)
    # auto：仅扫描件优先走 MinerU
    from .preprocess.sniff import sniff

    src = store.dir / pub.meta.source
    try:
        facts = sniff(src) if src.is_file() else {}
    except ValueError:
        facts = {}
    if facts.get("scanned"):
        return MineruClient(key)
    return None


def prepare_structure(store: RunStore, *, config: Config | None = None) -> list[dict[str, Any]]:
    """解析源文件并写入四层结构（幂等）：structured/ + units 清单 + split 状态。"""
    cfg = config or Config()
    doc = load_document(
        store.dir / store.load_publication().meta.source,
        store=store,
        ocr_backend=_ocr_backend_if_needed(store, cfg),
        mineru_client=_mineru_client_if_preferred(store, cfg),
        mineru_model=cfg.pdf.mineru_model,
        mineru_language=cfg.pdf.mineru_language,
    )
    pub = store.load_publication()
    entries = rebuild_structure(doc, pub)
    write_structured(store, doc, entries)
    store.set_units(entries)
    for e in entries:
        store.set_unit_status(e["id"], "split")
    store.log_event("structure_written", units=len(entries))
    return entries


def ensure_structure(store: RunStore) -> list[dict[str, Any]]:
    """已拆分且 structured 文件齐全则复用，否则执行结构拆分（幂等）。"""
    entries = structure_entries(store)
    if entries and all(
        e["rel_path"] and (store.structured_dir / e["rel_path"]).is_file() for e in entries
    ):
        return entries
    return prepare_structure(store)


def _source_language(store: RunStore, pub: Any, entries: list[dict[str, Any]]) -> str:
    """EPUB 源语言标注：优先元数据；缺省用确定性脚本启发式采样源文判定。

    convert/build 不跑 analyze，语言元数据可能缺失（此前一律 und）。此处以
    detect_language（纯函数启发式）采样首个非空单元判定：拉丁/未知脚本默认 en，
    若样本完全不含拉丁字母（无法判定脚本）则诚实返回 und。
    """
    lang = pub.meta.language or ""
    if lang:
        return lang
    sample = ""
    for e in entries:
        rel = e.get("rel_path")
        if not rel:
            continue
        path = store.structured_dir / rel
        if path.is_file():
            try:
                sample = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
        if sample.strip():
            break
    sample = sample[:4000]
    if not sample.strip():
        return "und"
    from auto_translator.analysis.detect import detect_language

    detected = detect_language(sample)
    if detected == "en" and not re.search("[A-Za-z]", sample):
        return "und"
    return detected


def convert(
    store: RunStore,
    *,
    output: str | None = None,
    theme: str | None = None,
    nav_depth: int | None = None,
) -> Path:
    """仅转换：ingest + structure + build（源语言正文）。"""
    entries = ensure_structure(store)
    if not entries:
        raise OrchestrationError("源文件无可解析的内容单元")
    pub = store.load_publication()
    # convert 不翻译：正文是源语言，EPUB 语言标注须用源语言（启发式检测兜底）。
    lang = _source_language(store, pub, entries)
    return _render_and_pack(
        store,
        pub,
        entries,
        lang=lang,
        output=output,
        suffix="",
        bilingual=False,
        event="convert_built",
        prefer_translation=False,
        theme=theme or Config().output.theme,
        nav_depth=nav_depth,
    )


def _render_and_pack(
    store: RunStore,
    pub: Any,
    entries: list[dict[str, Any]],
    *,
    lang: str,
    output: str | None,
    suffix: str,
    bilingual: bool,
    event: str,
    prefer_translation: bool,
    theme: str = "standard",
    nav_depth: int | None = None,
) -> Path:
    """构建内核（convert/build 共用）：渲染内容文档 + 收集媒体 + 打包 EPUB。

    脚注语义化（epub-template-spec §6）：每单元一份 FootnoteState（章内独立编号，
    注码 ``[N]``），``[^label]`` 引用与定义渲染为标准弹窗注释（noteref/footnote）。
    主题层（epub-template-spec §5）：``theme`` 选择预置排版主题。
    目录投影（epub-template-spec §3）：``nav_depth`` 限制 nav/NCX 嵌套深度。
    封面：cover 单元的首个图片 → ``cover-image`` 属性 + spine ``linear="no"``。
    """
    from .build.html import FootnoteState

    nav_depth = nav_depth if nav_depth is not None else Config().output.nav_depth
    out_path = Path(output) if output else store.output_dir / f"{pub.slug}{suffix}.epub"
    src_lang = _source_language(store, pub, entries)
    media_root = store.structured_dir / "raw" / "media"
    content = []
    media: dict[str, bytes] = {}
    media_dropped: dict[str, list[str]] = {}
    cover_media: str | None = None
    for e in entries:
        rel = e.get("rel_path")
        if not rel:
            continue
        if bilingual:
            rows = read_align(store.unit_align_path(e["id"]))
            if not rows:
                continue
            heading = unit_heading("\n".join(r.get("tgt", "") for r in rows))
            if heading:
                e["title"] = heading
            content.append(
                (
                    f"{slug_file(e['id'])}.xhtml",
                    render_bilingual_document(e["title"], rows, lang_src=src_lang, lang_tgt=lang),
                )
            )
            continue
        structured = store.structured_dir / rel
        translation = store.translation_dir / rel
        if prefer_translation:
            md_path = translation if translation.is_file() else structured
        else:
            md_path = structured
        if not md_path.is_file():
            continue
        md_text = md_path.read_text(encoding="utf-8")
        if skip_empty_unit(md_text, e["title"]):
            continue
        heading = unit_heading(md_text)
        if heading:
            e["title"] = heading
        md_text, unit_media, dropped = collect_media(md_text, media_root)
        if dropped:
            media_dropped[e["id"]] = dropped
        for epub_path, data in unit_media:
            media[epub_path] = data
        if e.get("kind") == "cover" and unit_media and cover_media is None:
            cover_media = unit_media[0][0]
        content.append(
            (
                f"{slug_file(e['id'])}.xhtml",
                render_document(
                    e["title"],
                    md_text,
                    lang=lang,
                    unit_id=e["id"],
                    fn_state=FootnoteState(),  # 每单元一份：章内独立编号
                ),
            )
        )
    if media_dropped:
        # 构建期静默丢弃留痕（交付审计 S1.3）：主对账由 provenance E_MEDIA_EPUB_LOST 兜底
        store.log_event("media_dropped", refs=media_dropped)
    build_epub(
        pub,
        entries,
        content,
        lang=lang,
        modified="2026-01-01T00:00:00Z",
        out_path=out_path,
        media_files=list(media.items()),
        theme=theme,
        cover_media=cover_media,
        nav_depth=nav_depth,
    )
    for e in entries:
        store.set_unit_status(e["id"], "built")
    store.log_event(event, slug=pub.slug, output=str(out_path))
    return out_path


def preprocess(store: RunStore, *, config: Config | None = None) -> dict[str, Any]:
    """预处理事实收集（确定性、零 token）：嗅探/元数据/TOC/体检/规模 → preprocessing/facts.*。

    预处理是 agent 任务：本函数只产出事实与 agent 待办清单；方案决策与分层理解由
    agent 写 preprocessing/{plan,global,units,terms,risks,report}。带 input 的新书走
    init（含 OCR 路由）后调用本函数；已有工作区可幂等刷新 facts。
    """
    from .preprocess import collect_facts, write_facts

    cfg = config or Config()
    facts = collect_facts(store, cfg)
    json_path, md_path = write_facts(store, facts)
    store.log_event(
        "preprocess_facts_written",
        kind=facts["source"].get("kind"),
        units=facts["structure"]["totals"]["units"],
    )
    return {"facts": facts, "facts_json": str(json_path), "facts_md": str(md_path)}


def build(
    store: RunStore,
    *,
    bilingual: bool = False,
    output: str | None = None,
    theme: str | None = None,
    nav_depth: int | None = None,
) -> Path:
    """从译文（缺省回退源文）构建 EPUB；双语时输出 -bi.epub。"""
    pub = store.load_publication()
    entries = structure_entries(store)
    if not entries:
        raise OrchestrationError("工作区无内容单元；请先 init/convert")
    lang = pub.meta.target_language or "zh-CN"
    return _render_and_pack(
        store,
        pub,
        entries,
        lang=lang,
        output=output,
        suffix="-bi" if bilingual else "",
        bilingual=bilingual,
        event="built",
        prefer_translation=True,
        theme=theme or Config().output.theme,
        nav_depth=nav_depth,
    )


def _latest_review_result(store: RunStore) -> dict[str, Any] | None:
    """读取最新一次审校运行的 result.json（目录名按时间戳可排序）。"""
    if not store.reviews_dir.is_dir():
        return None
    candidates = sorted(store.reviews_dir.glob("review-*/result.json"))
    if not candidates:
        return None
    return read_json(candidates[-1])


def _unit_doc_flags(store: RunStore, rel_path: str) -> list[Any]:
    """单元级文档结构检查（structured vs translation 全文）：表格形状守恒。

    两侧文件都存在才比对；返回 G0Flag 列表（check="table"）。
    """
    from auto_translator.review import table_shape_flags

    src_path = store.structured_dir / rel_path
    tgt_path = store.translation_dir / rel_path
    if not (src_path.is_file() and tgt_path.is_file()):
        return []
    src_md = src_path.read_text(encoding="utf-8")
    tgt_md = tgt_path.read_text(encoding="utf-8")
    return table_shape_flags(src_md, tgt_md)


def import_translations(
    store: RunStore,
    *,
    unit_id: str | None = None,
    terms_path: str | None = None,
    mark_reviewed: bool = False,
) -> dict[str, Any]:
    """把 agent 手写的 translation/ + align/ 登记进工作区（路径 B 一等入口）。

    对每个单元校验：translation md 与 align 文件存在、seq 连续 1..N、无空译文。
    结构性错误（断号/空译文/缺文件）阻断该单元并给出中文清单；
    长度比/术语命中为 advisory 告警，不阻断。通过后推进状态 translated → aligned。

    术语闭环：读取 agent 维护的 glossary.csv（--terms 可再导入新术语提案），
    冲突检测后外置到 analysis/glossary_conflicts.jsonl 供 agent 裁决。

    ``mark_reviewed=True``（--reviewed）：把处于 ``aligned`` 的单元推进为
    ``reviewed``（审校通过的显式登记入口；reviewed/built 跳过、低于 aligned 不动）。
    """
    from auto_translator.glossary import (
        Glossary,
        load_glossary_csv,
        read_conflicts_jsonl,
        save_glossary_csv,
        write_conflicts_jsonl,
    )
    from auto_translator.review import check_alignment, g0_unit_flags
    from auto_translator.translation.align import read_align

    pub = store.load_publication()
    glossary_path = store.analysis_dir / "glossary.csv"
    conflicts_path = store.analysis_dir / "glossary_conflicts.jsonl"

    # 可选：批量导入 agent 提取的新术语提案（propose 三态判定）
    if terms_path:
        glossary = Glossary(load_glossary_csv(glossary_path))
        proposed = load_glossary_csv(terms_path)
        for entry in proposed:
            if entry.source and entry.target:
                glossary.propose(entry.source, entry.target, type=entry.type, note=entry.note)
        save_glossary_csv(glossary_path, glossary.entries())

    glossary = Glossary(load_glossary_csv(glossary_path))
    imported: list[str] = []
    failed: list[dict[str, Any]] = []
    warned: list[dict[str, Any]] = []
    skipped: list[str] = []

    for unit in pub.units:
        if unit_id and unit.id != unit_id:
            continue
        # 已完成单元安全跳过（状态与续跑不变量）：reviewed/built 不重导，
        # 避免把审校结论状态打回 aligned（重导修订稿前须先重走审校）。
        if unit.status in ("reviewed", "built"):
            skipped.append(unit.id)
            continue
        rel_path = (unit.meta or {}).get("rel_path")
        if not rel_path:
            skipped.append(unit.id)
            continue
        tgt_path = store.translation_dir / rel_path
        align_path = store.unit_align_path(unit.id)
        structured_path = store.structured_dir / rel_path
        structured_md = (
            structured_path.read_text(encoding="utf-8") if structured_path.is_file() else None
        )
        errors: list[str] = []
        if not tgt_path.is_file():
            errors.append(f"缺少译文文件：{tgt_path}")
        rows = read_align(align_path) if align_path.is_file() else []
        if not rows:
            errors.append(f"缺少对照表或对照表为空：{align_path}")
        if rows:
            for f in check_alignment(rows):
                # 结构性错误：断号/空原文/空译文；「对照表为空」已在上面覆盖
                if f.message != "对照表为空":
                    errors.append(f"对照表 {f.message}")
        # 表格形状守恒（S4.2）：译文文档结构性损坏，阻断登记（严于 marker/fidelity
        # 的 advisory——坏表格会直接进 build 产物）
        for f in _unit_doc_flags(store, rel_path):
            errors.append(f"表格形状：{f.message}（{f.data}）")
        # md↔align 全文一致性（交付审计 S1.1）：md 是 build 输入、align 是校验基准，
        # 一侧缺内容（图片段/脚注/段落）即阻断登记——防缺陷直达成品
        if tgt_path.is_file() and rows:
            from auto_translator.review import md_align_drift

            for d in md_align_drift(tgt_path.read_text(encoding="utf-8"), rows, title=unit.title):
                errors.append(f"文档一致性：{d}")
        for f in g0_unit_flags(rows, glossary, structured_md=structured_md):
            # 源保真反向违例（src 不在源文中）= 对照表不可信，阻断登记；
            # 其余硬缺陷类（terminology/marker/footnote）与前向缺块（fidelity）、
            # advisory（length）收进告警：import 期不阻断，漏修被 G5 放行门兜底
            if f.check == "fidelity" and "不在源文中" in f.message:
                errors.append(f"源保真：{f.message}（seq={f.data.get('seq')}）")
                continue
            if f.check in ("length", "terminology", "marker", "footnote", "fidelity"):
                warned.append({"unit": unit.id, "check": f.check, "message": f.message})
        if errors:
            failed.append({"unit": unit.id, "errors": errors})
            continue
        # 勘误先例留痕：按句 src 命中的已知讹误补 note（corr:wrong→right）并写回
        from auto_translator.review import annotate_correction_notes
        from auto_translator.translation.align import write_align

        write_align(align_path, annotate_correction_notes(rows))
        store.set_unit_status(unit.id, "translated")
        store.set_unit_status(unit.id, "aligned")
        imported.append(unit.id)

    # 术语冲突检测与外置（agent 裁决后写回 CSV）
    conflicts = glossary.detect_conflicts()
    prior = len(read_conflicts_jsonl(conflicts_path))
    written = write_conflicts_jsonl(conflicts_path, conflicts)
    new_conflicts = prior + written

    # --reviewed：审校通过的显式登记（aligned → reviewed，幂等）
    reviewed: list[str] = []
    if mark_reviewed:
        for unit in pub.units:
            if unit_id and unit.id != unit_id:
                continue
            if unit.status == "aligned":
                store.set_unit_status(unit.id, "reviewed")
                reviewed.append(unit.id)

    if imported:
        store.log_event("import_translated", units=imported)
    if reviewed:
        store.log_event("import_reviewed", units=reviewed)
    return {
        "imported": imported,
        "failed": failed,
        "warnings": warned,
        "skipped": skipped,
        "conflicts_open": new_conflicts,
        "reviewed": reviewed,
    }


def set_meta(
    store: RunStore,
    *,
    title: str | None = None,
    creator: str | None = None,
    translator: str | None = None,
    publisher: str | None = None,
    date: str | None = None,
    rights: str | None = None,
) -> dict[str, Any]:
    """更新 DC 元数据（agent 补全/核对 facts 嗅探值、译者署名的唯一写入口）。

    仅显式传入的字段会被更新（None=不动；空串=清空该字段）。
    publication.json 状态只经 CLI 命令推进，agent 不手工编辑。
    """
    pub = store.load_publication()
    updates: dict[str, str | None] = {
        "title": title,
        "creator": creator,
        "translator": translator,
        "publisher": publisher,
        "date": date,
        "rights": rights,
    }
    changed = [k for k, v in updates.items() if v is not None]
    for k in changed:
        setattr(pub.meta, k, updates[k])
    if not changed:
        raise OrchestrationError("未指定任何要更新的字段（--title/--creator/--translator/…）")
    store.save_publication(pub)
    store.log_event("meta_update", fields=changed)
    return {"updated": changed, "meta": pub.meta.model_dump()}


def g0_check(store: RunStore, *, unit_id: str | None = None) -> dict[str, Any]:
    """G0 零 token 静态校验（独立命令；翻译/导入后立即跑，不必等到 qa）。"""
    from auto_translator.glossary import Glossary, load_glossary_csv
    from auto_translator.review import g0_unit_flags

    pub = store.load_publication()
    flags: list[dict[str, Any]] = []
    checked: list[str] = []
    for unit in pub.units:
        if unit_id and unit.id != unit_id:
            continue
        rows = read_align(store.unit_align_path(unit.id))
        if not rows:
            continue
        checked.append(unit.id)
        rel_path = (unit.meta or {}).get("rel_path")
        structured_path = store.structured_dir / rel_path if rel_path else None
        structured_md = (
            structured_path.read_text(encoding="utf-8")
            if structured_path and structured_path.is_file()
            else None
        )
        for f in g0_unit_flags(
            rows,
            Glossary(load_glossary_csv(store.analysis_dir / "glossary.csv")),
            structured_md=structured_md,
        ):
            flags.append({"unit": unit.id, "check": f.check, "message": f.message, "data": f.data})
        for f in _unit_doc_flags(store, rel_path) if rel_path else []:
            flags.append({"unit": unit.id, "check": f.check, "message": f.message, "data": f.data})
    return {"checked_units": checked, "flags": flags}


def _collect_g0_flags(store: RunStore, config: Config | None = None) -> list[dict[str, Any]]:
    """对所有已对齐单元执行 G0 零 token 静态校验，返回告警（dict 列表）。"""
    from auto_translator.glossary import Glossary, load_glossary_csv
    from auto_translator.review import g0_unit_flags

    cfg = config or Config()
    glossary = Glossary(load_glossary_csv(store.analysis_dir / "glossary.csv"))
    flags: list[dict[str, Any]] = []
    for unit in store.load_publication().units:
        rows = read_align(store.unit_align_path(unit.id))
        if not rows:
            continue
        rel_path = (unit.meta or {}).get("rel_path")
        structured_path = store.structured_dir / rel_path if rel_path else None
        structured_md = (
            structured_path.read_text(encoding="utf-8")
            if structured_path and structured_path.is_file()
            else None
        )
        for f in g0_unit_flags(
            rows,
            glossary,
            too_short=float(cfg.qc.length_ratio.get("too_short", 0.30)),
            too_long=float(cfg.qc.length_ratio.get("too_long", 3.0)),
            structured_md=structured_md,
        ):
            flags.append({"unit": unit.id, "check": f.check, "message": f.message, "data": f.data})
        for f in _unit_doc_flags(store, rel_path) if rel_path else []:
            flags.append({"unit": unit.id, "check": f.check, "message": f.message, "data": f.data})
    return flags


def _toc_missing_from_facts(store: RunStore, entries: list[dict[str, Any]]) -> list[str]:
    """facts 源 TOC vs 单元标题对账（postprocessing-spec §2.3 W_TOC_MISSING 线索）。

    无 facts.json 时返回空（不告警）。匹配规则：标题相等或互为子串。
    """
    facts_path = store.preprocessing_dir / "facts.json"
    if not facts_path.is_file():
        return []
    try:
        facts = read_json(facts_path)
    except (OSError, ValueError):
        return []
    toc = (facts.get("source") or {}).get("toc") or []
    titles = [str(e.get("title") or "").strip() for e in entries]
    titles = [t for t in titles if t]
    missing: list[str] = []
    for item in toc:
        raw = item.get("title") if isinstance(item, dict) else str(item)
        title = str(raw or "").strip()
        if not title:
            continue
        if not any(title == t or title in t or t in title for t in titles):
            missing.append(title)
    return missing


def qa(
    store: RunStore, *, epub_path: str | None = None, config: Config | None = None
) -> dict[str, Any]:
    from auto_translator.glossary import read_conflicts_jsonl

    pub = store.load_publication()
    epub = Path(epub_path) if epub_path else store.output_dir / f"{pub.slug}.epub"
    if not epub.is_file():
        raise OrchestrationError(f"成品不存在：{epub}；请先 build/convert")
    jar = (config.qc.epubcheck.jar or None) if config is not None else None
    epubcheck = run_epubcheck(epub, jar_path=jar)
    nav_depth = config.output.nav_depth if config is not None else Config().output.nav_depth
    entries = structure_entries(store)
    # 先跑溯源审计拿到目录投影豁免集（与 build 同一 nav_depth），再解包结构审计
    provenance = audit_provenance(store, entries, epub, nav_depth=nav_depth)
    audit = audit_epub(epub, nav_exempt=set(provenance.nav_exempt))
    review_result = _latest_review_result(store)
    g0_flags = _collect_g0_flags(store, config)
    toc_missing = _toc_missing_from_facts(store, entries)
    total_sentences = sum(len(read_align(store.unit_align_path(u.id))) for u in pub.units)
    # 术语冲突未裁决数（S1.1 放行硬门：裁决写回前 qa 不放行）
    glossary_conflicts_open = sum(
        1
        for c in read_conflicts_jsonl(store.analysis_dir / "glossary_conflicts.jsonl")
        if c.get("status") == "open"
    )
    # 源盘点未决项（S4.4）：catalog.csv 存在时 unresolved 阻断放行
    catalog_rows = read_catalog(store)
    catalog_unresolved_open = (
        sum(1 for r in catalog_rows if r["status"] == "unresolved")
        if catalog_rows is not None
        else 0
    )
    report = generate_report(
        pub.slug,
        audit,
        epubcheck,
        epub_path=str(epub),
        review=review_result,
        g0_flags=g0_flags,
        total_sentences=total_sentences,
        provenance=provenance.to_dict(),
        toc_missing=toc_missing,
        glossary_conflicts_open=glossary_conflicts_open,
        catalog_unresolved_open=catalog_unresolved_open,
    )
    if toc_missing:
        report.provenance_findings.append(
            {
                "level": "warning",
                "code": "W_TOC_MISSING",
                "message": "源 TOC 缺失条目：" + "、".join(toc_missing),
            }
        )
    # 命名规范（postprocessing-spec P2）：成品文件名应以 slug 为前缀
    if not epub.stem.startswith(pub.slug):
        report.provenance_findings.append(
            {
                "level": "warning",
                "code": "W_NAMING",
                "message": f"成品命名与 slug 不符：{epub.name}（期望前缀 {pub.slug}）",
            }
        )
    store.save_qa(report.to_dict())
    return report.to_dict()


def read_catalog(store: RunStore) -> list[dict[str, Any]] | None:
    """读取源内容盘点（preprocessing/catalog.csv；S4.4 SourceCatalog 最小形态）。

    文件不存在 → None（全部检查跳过，零破坏）。列契约：
    ``item,kind,status,locator,unit_id,note``——kind ∈ toc|figure|table|footnote|
    section|physical；status ∈ included|physical|excluded|unresolved；
    included 行 unit_id 必填。取值非法/列缺失 → OrchestrationError（带行号）。
    """
    import csv

    path = store.preprocessing_dir / "catalog.csv"
    if not path.is_file():
        return None
    kinds = {"toc", "figure", "table", "footnote", "section", "physical"}
    statuses = {"included", "physical", "excluded", "unresolved"}
    required = ["item", "kind", "status", "locator", "unit_id", "note"]
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):
            raise OrchestrationError(f"catalog.csv 列契约不符（要求 {','.join(required)}）：{path}")
        for i, row in enumerate(reader, start=2):
            if not (row.get("item") or "").strip():
                raise OrchestrationError(f"catalog.csv 第 {i} 行：item 为空")
            if (row.get("kind") or "") not in kinds:
                raise OrchestrationError(f"catalog.csv 第 {i} 行：kind 非法（{row.get('kind')}）")
            status_val = row.get("status") or ""
            if status_val not in statuses:
                raise OrchestrationError(f"catalog.csv 第 {i} 行：status 非法（{status_val}）")
            if status_val == "included" and not (row.get("unit_id") or "").strip():
                raise OrchestrationError(f"catalog.csv 第 {i} 行：included 项缺 unit_id")
            if status_val == "excluded" and not (row.get("note") or "").strip():
                raise OrchestrationError(f"catalog.csv 第 {i} 行：excluded 项 note 必填理由")
            rows.append({k: (row.get(k) or "").strip() for k in required})
    return rows


def status(store: RunStore, *, as_json: bool = False) -> dict[str, Any]:
    pub = store.load_publication()
    units_out: list[dict[str, Any]] = []
    stale: list[dict[str, str]] = []
    for u in pub.units:
        has_translation = (
            bool((u.meta or {}).get("rel_path"))
            and (store.translation_dir / u.meta["rel_path"]).is_file()
        )
        has_align = store.unit_align_path(u.id).is_file()
        units_out.append(
            {
                "id": u.id,
                "kind": u.kind,
                "title": u.title,
                "status": u.status,
                "has_translation": has_translation,
                "has_align": has_align,
            }
        )
        # 产物-状态对账：agent 手写了产物但未 import 登记 → 提示 stale
        if (has_translation or has_align) and u.status in ("pending", "split", "analyzed"):
            stale.append(
                {"id": u.id, "status": u.status, "reason": "translation_present_not_imported"}
            )
    # 预处理对账：facts 已生成但 agent 理解产物未完成（todo.md + global.md +
    # capabilities.md 必备，见 docs/plans/preprocessing-plan-v2.md capabilities 契约
    # 与 references/preprocessing.md §2.0 todo.md 要求）
    has_preprocessing = (store.preprocessing_dir / "facts.json").is_file()
    preprocessing_complete = (
        has_preprocessing
        and (store.preprocessing_dir / "todo.md").is_file()
        and (store.preprocessing_dir / "global.md").is_file()
        and (store.preprocessing_dir / "capabilities.md").is_file()
    )
    if has_preprocessing and not preprocessing_complete:
        stale.append(
            {
                "id": "preprocessing",
                "status": "facts_written",
                "reason": "preprocessing_plan_missing",
            }
        )
    # 源内容盘点对账（S4.4）：catalog.csv 存在时校验 included 绑定与未决项
    catalog_rows = read_catalog(store)
    catalog: dict[str, Any] = {"present": False}
    if catalog_rows is not None:
        unit_ids = {u.id for u in pub.units}
        catalog = {
            "present": True,
            "items": len(catalog_rows),
            "included_bound": all(
                r["status"] != "included" or r["unit_id"] in unit_ids for r in catalog_rows
            ),
            "unresolved": sum(1 for r in catalog_rows if r["status"] == "unresolved"),
        }
        if not catalog["included_bound"]:
            stale.append(
                {"id": "catalog", "status": "included_unbound", "reason": "catalog_binding_broken"}
            )
    data = {
        "slug": pub.slug,
        "title": pub.meta.title,
        "target_language": pub.meta.target_language,
        "units_total": len(pub.units),
        "units": units_out,
        "has_preprocessing": has_preprocessing,
        "preprocessing_complete": preprocessing_complete,
        "catalog": catalog,
        "stale": stale,
    }
    return data
