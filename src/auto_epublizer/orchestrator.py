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

from .build import build_epub, collect_media, subheading_anchors
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
    original: str | None = None,
) -> RunStore:
    store = init_workspace(
        input_path,
        config=config,
        target_language=target_language,
        references=references,
        workspace_dir=workspace_dir,
        original=original,
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
        mineru_batch_pages=cfg.pdf.mineru_batch_pages,
        rtl=cfg.pdf.rtl,
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
    built_ids: list[str] = []
    fallback_ids: list[str] = []
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
            built_ids.append(e["id"])
            continue
        structured = store.structured_dir / rel
        translation = store.translation_dir / rel
        if prefer_translation:
            md_path = translation if translation.is_file() else structured
            if md_path is structured:
                fallback_ids.append(e["id"])
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
        # 锚点级目录（epub-template-spec §3）：与渲染源同一 md 提取子标题锚点
        # （id 与 markdown_to_xhtml 自动 id 规则一致，nav 链接不悬空）。
        # 双语文档不挂锚点（由 align 行渲染，无子标题元素）。
        e["anchors"] = subheading_anchors(md_text, e["id"])
        md_text, unit_media, dropped = collect_media(md_text, media_root)
        if dropped:
            media_dropped[e["id"]] = dropped
        for epub_path, data in unit_media:
            media[epub_path] = data
        if e.get("kind") == "cover" and unit_media and cover_media is None:
            cover_media = unit_media[0][0]
        built_ids.append(e["id"])
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
    # 状态推进：只把**确实打包了译文**的单元推进为 built。
    # 源文回退（无译文）的单元保持原状态——否则 import 会把 built 当「已完成」永久
    # 跳过，译文再也登记不进来（现场报告 #8：冒烟 build 之后登记路径整体失效）。
    for uid in built_ids:
        if prefer_translation and uid in fallback_ids:
            continue
        store.set_unit_status(uid, "built")
    store.log_event(
        event, slug=pub.slug, output=str(out_path), fallback_units=sorted(set(fallback_ids))
    )
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


def rebuild(store: RunStore, *, config: Config | None = None) -> dict[str, Any]:
    """原地重建 ``structured/``（含 raw/）与 facts（issue #30 §4.2，``preprocess --force``）。

    从 ``source/`` 重新 ingest → 覆盖 structured/ → 重算 facts。单元状态被重置为
    ``split``（既有译文变 stale，需重新走 import）；调用方须显式 ``--force`` 表达该意图。
    用于「preprocess 误中断后恢复」，无需人工搬目录。
    """
    import shutil

    if store.structured_dir.exists():
        shutil.rmtree(store.structured_dir)
    prepare_structure(store, config=config)
    return preprocess(store, config=config)


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
    force: bool = False,
) -> dict[str, Any]:
    """把 agent 手写的 translation/ + align/ 登记进工作区（路径 B 一等入口）。

    对每个单元校验：translation md 与 align 文件存在、seq 连续 1..N、无空译文。
    结构性错误（断号/空译文/缺文件）阻断该单元并给出中文清单；
    长度比/术语命中为 advisory 告警，不阻断。通过后推进状态 translated → aligned。

    术语闭环：读取 agent 维护的 glossary.csv（--terms 可再导入新术语提案），
    冲突检测后外置到 analysis/glossary_conflicts.jsonl 供 agent 裁决。

    ``mark_reviewed=True``（--reviewed）：把处于 ``aligned`` 的单元推进为
    ``reviewed``（审校通过的显式登记入口；reviewed/built 跳过、低于 aligned 不动）。

    ``force=True``（--force，issue #13）：对 ``reviewed``/``built`` 单元**重跑**全套
    阻断校验——供交付后修订译文时重新登记。通过则保持原状态（不回退，护住审校结论）；
    失败则把该单元回退 ``aligned`` 并给出清单，待修复后重导。
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
                glossary.propose(
                    entry.source,
                    entry.target,
                    type=entry.type,
                    note=entry.note,
                    # aliases/gender/reading 必须一并透传：G0 术语命中读的是落盘的
                    # glossary.csv，丢了别名则 OCR 损坏变体（ü→ii 之类）永不命中。
                    aliases=entry.aliases,
                    gender=entry.gender,
                    reading=entry.reading,
                )
        save_glossary_csv(glossary_path, glossary.entries())

    glossary = Glossary(load_glossary_csv(glossary_path))
    imported: list[str] = []
    revalidated: list[str] = []
    pending: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    warned: list[dict[str, Any]] = []
    skipped: list[str] = []

    for unit in pub.units:
        if unit_id and unit.id != unit_id:
            continue
        # 已完成单元安全跳过（状态与续跑不变量）：reviewed/built 不重导，
        # 避免把审校结论状态打回 aligned（重导修订稿前须先重走审校）。
        # --force 显式要求重校验时除外（issue #13）。
        was_done = unit.status in ("reviewed", "built")
        if was_done and not force:
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
        pending_reasons: list[str] = []
        if not tgt_path.is_file():
            pending_reasons.append(f"缺少译文文件：{tgt_path}")
        rows = read_align(align_path) if align_path.is_file() else []
        if not rows:
            pending_reasons.append(f"缺少对照表或对照表为空：{align_path}")
        if pending_reasons:
            # 未译单元是「待译」不是「失败」：也不继续跑文档/表格/术语检查——
            # 否则会为源文的**每个块**刷出一条「源文块未进对照表」告警
            # （现场报告 #8：4 个已译单元 + 12 个未译单元 → 1318 条无效告警）。
            pending.append({"unit": unit.id, "reasons": pending_reasons})
            continue
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
        translation_md: str | None = None
        if tgt_path.is_file() and rows:
            from auto_translator.review import md_align_drift

            translation_md = tgt_path.read_text(encoding="utf-8")
            for d in md_align_drift(translation_md, rows, title=unit.title):
                errors.append(f"文档一致性：{d}")
        for f in g0_unit_flags(
            rows, glossary, structured_md=structured_md, translation_md=translation_md
        ):
            # 源保真反向违例（src 不在源文中）= 对照表不可信，阻断登记；
            # 其余硬缺陷类（terminology/marker/footnote/heading）与前向缺块
            # （fidelity）、advisory（length）收进告警：import 期不阻断，
            # 漏修被 G5 放行门兜底
            if f.check == "fidelity" and "不在源文中" in f.message:
                errors.append(f"源保真：{f.message}（seq={f.data.get('seq')}）")
                continue
            if f.check in ("length", "terminology", "marker", "footnote", "heading", "fidelity"):
                warned.append({"unit": unit.id, "check": f.check, "message": f.message})
        if errors:
            if force and was_done:
                # --force 重校验失败：显式回退 aligned，待修复后重导（不静默）
                store.set_unit_status(unit.id, "aligned")
                errors.append("--force 重校验失败：状态已回退 aligned")
            failed.append({"unit": unit.id, "errors": errors})
            continue
        # 勘误先例留痕：按句 src 命中的已知讹误补 note（corr:wrong→right）并写回
        from auto_translator.review import annotate_correction_notes
        from auto_translator.translation.align import write_align

        write_align(align_path, annotate_correction_notes(rows))
        if was_done and force:
            # 重校验通过：保持原状态（不回退，护住审校/构建结论）
            revalidated.append(unit.id)
        else:
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
    if revalidated:
        store.log_event("import_revalidated", units=revalidated)
    if reviewed:
        store.log_event("import_reviewed", units=reviewed)
    return {
        "imported": imported,
        "revalidated": revalidated,
        "pending": pending,
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
        tgt_path = store.translation_dir / rel_path if rel_path else None
        translation_md = (
            tgt_path.read_text(encoding="utf-8") if tgt_path and tgt_path.is_file() else None
        )
        for f in g0_unit_flags(
            rows,
            Glossary(load_glossary_csv(store.analysis_dir / "glossary.csv")),
            structured_md=structured_md,
            translation_md=translation_md,
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
        tgt_path = store.translation_dir / rel_path if rel_path else None
        translation_md = (
            tgt_path.read_text(encoding="utf-8") if tgt_path and tgt_path.is_file() else None
        )
        for f in g0_unit_flags(
            rows,
            glossary,
            too_short=float(cfg.qc.length_ratio.get("too_short", 0.30)),
            too_long=float(cfg.qc.length_ratio.get("too_long", 3.0)),
            structured_md=structured_md,
            translation_md=translation_md,
        ):
            flags.append({"unit": unit.id, "check": f.check, "message": f.message, "data": f.data})
        for f in _unit_doc_flags(store, rel_path) if rel_path else []:
            flags.append({"unit": unit.id, "check": f.check, "message": f.message, "data": f.data})
    return flags


def _norm_title(text: Any) -> str:
    """源文标题规范化（对账用）：NFKC + 去连字符 + 统一字母变体 + **只留字母/数字**。

    只保留 Unicode 类别 L*/N*：一并去掉标点/括号（源书签与正文标题常见 `»…«` vs `«…»`
    的差异）、空格、零宽、阿拉伯附加符号。在**源文语言空间**对账（facts 源 TOC 与
    structured 标题同为源语言）；译文标题不参与。
    """
    import unicodedata

    s = unicodedata.normalize("NFKC", str(text or ""))
    s = s.replace("\u0640", "")  # tatweel（类别 Lm，否则会被 L/N 滤网放行）
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
    s = s.casefold()
    return "".join(ch for ch in s if unicodedata.category(ch)[0] in ("L", "N"))


def _title_match(a: str, b: str) -> bool:
    """规范化标题匹配：全等，或较短者为较长者的子串（过短不参与子串匹配，防误命中）。"""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and short in long


def _toc_missing_from_facts(store: RunStore, entries: list[dict[str, Any]]) -> list[str]:
    """facts 源 TOC vs 单元标题 + 单元内锚点对账（postprocessing-spec §2.3 W_TOC_MISSING）。

    升级（#16 S-B）：在**源文语言空间**把源书签映射到 ``unit`` 或 ``unit#anchor``（按标题
    规范化后全等/子串），只有真正映射不上的才计入缺失——使告警反映**真实覆盖缺口**，而非
    「书签数 vs 单元数」的量差。标题空间的锚点标签来自 structured/ 的 level≥2 子标题。
    页码兜底未实现：EPUB 源无页码、PDF 单元级页码范围未提供，退化为标题匹配（见
    docs/plans/2026-10-04-backlog-three-items.md §1.4 S-B 设计约束 2）。
    """
    facts_path = store.preprocessing_dir / "facts.json"
    if not facts_path.is_file():
        return []
    try:
        facts = read_json(facts_path)
    except (OSError, ValueError):
        return []
    toc = (facts.get("source") or {}).get("toc") or []
    labels: list[str] = []
    for e in entries:
        labels.append(_norm_title(e.get("title")))
        rel = e.get("rel_path") or ""
        md_path = store.structured_dir / rel if rel else None
        if md_path is not None and md_path.is_file():
            try:
                md = md_path.read_text(encoding="utf-8")
            except OSError:
                md = ""
            labels.extend(_norm_title(a.get("title")) for a in subheading_anchors(md, e["id"]))
    labels = [x for x in labels if x]
    missing: list[str] = []
    for item in toc:
        raw = item.get("title") if isinstance(item, dict) else str(item)
        title = str(raw or "").strip()
        if not title:
            continue
        norm = _norm_title(title)
        if not any(_title_match(norm, lab) for lab in labels):
            missing.append(title)
    return missing


def read_repairs(store: RunStore) -> list[dict[str, Any]] | None:
    """读取语义整备留痕（preprocessing/repairs.jsonl；S2 契约）。

    文件不存在 → None（全部检查跳过，零破坏）。每行一个修复动作：
    ``unit`` 必填且必须存在于 publication.units；``kind``（见下）/``status``
    （done|unresolved）枚举；``summary`` 必填非空；``evidence`` 为工作区相对
    路径且必须存在（防杜撰）；``pages``/``count`` 非法类型报错。
    违反 → OrchestrationError（中文提示，带行号）。
    """
    import json

    path = store.preprocessing_dir / "repairs.jsonl"
    if not path.is_file():
        return None
    kinds = {
        "line_join",
        "hyphen",
        "ocr_char",
        "mojibake",
        "punct",
        "header_footer",
        "footnote",
        "order",
        "heading",
        "boundary",
        "classification",
        "garbage",
        "media",
        "metadata",
        "other",
    }
    statuses = {"done", "unresolved"}
    unit_ids = {u.id for u in store.load_publication().units}
    rows: list[dict[str, Any]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise OrchestrationError(f"repairs.jsonl 第 {lineno} 行不是合法 JSON：{e}") from None
        if not isinstance(row, dict):
            raise OrchestrationError(f"repairs.jsonl 第 {lineno} 行必须是 JSON 对象")
        unit = str(row.get("unit") or "")
        kind = str(row.get("kind") or "")
        status = str(row.get("status") or "")
        summary = str(row.get("summary") or "").strip()
        if not unit:
            raise OrchestrationError(f"repairs.jsonl 第 {lineno} 行 unit 必填")
        # 结构重建可能删除单元（issue #23）：引用了已消失单元的历史行**不阻断 qa**，
        # 标记 unit_missing 交由 qa 出 warning（done 是已完成的历史动作，unresolved 也
        # 只降级提示，避免整条流水线中断）。
        unit_missing = unit not in unit_ids
        if kind not in kinds:
            raise OrchestrationError(f"repairs.jsonl 第 {lineno} 行 kind 非法：{kind!r}")
        if status not in statuses:
            raise OrchestrationError(f"repairs.jsonl 第 {lineno} 行 status 非法：{status!r}")
        if not summary:
            raise OrchestrationError(f"repairs.jsonl 第 {lineno} 行 summary 必填")
        evidence = row.get("evidence")
        if evidence:
            ev = Path(str(evidence))
            if ev.is_absolute() or ".." in ev.parts or not (store.dir / ev).is_file():
                raise OrchestrationError(
                    f"repairs.jsonl 第 {lineno} 行 evidence 不存在或非法：{evidence!r}"
                )
        pages = row.get("pages")
        if pages is not None and (
            not isinstance(pages, list) or not all(isinstance(p, int) for p in pages)
        ):
            raise OrchestrationError(f"repairs.jsonl 第 {lineno} 行 pages 必须是整数数组")
        count = row.get("count")
        if count is not None and not isinstance(count, int):
            raise OrchestrationError(f"repairs.jsonl 第 {lineno} 行 count 必须是整数")
        row = {**row, "unit_missing": True} if unit_missing else row
        rows.append(row)
    return rows


def restructure(store: RunStore) -> dict[str, Any]:
    """登记 agent 重建的单元结构（preprocessing/structure.csv → publication.json）。

    契约（docs/semantic-repair.md §3.3）：列 ``id,region,kind,title,level,rel_path``
    （utf-8-sig 容 BOM）；id 唯一合法、region 与路径前缀一致、kind/level 枚举、
    文件存在且首行 ``# title`` 与清单一致、structured/（除 raw/）无孤儿 md。
    状态语义：同 id 且 (rel_path,title,level,kind,region) 未变 → 保留原状态；
    有变 → 回退 ``split``（重译重 import）；新 id → ``split``；消失 id → 提示孤儿。
    """
    import csv

    from auto_common.workspace.models import Unit

    path = store.preprocessing_dir / "structure.csv"
    if not path.is_file():
        raise OrchestrationError(f"缺少结构清单：{path}（先写 preprocessing/structure.csv）")
    required = ["id", "region", "kind", "title", "level", "rel_path"]
    regions = {"cover", "frontmatter", "body", "backmatter"}
    kinds = {
        "cover",
        "titlepage",
        "copyright",
        "dedication",
        "foreword",
        "preface",
        "toc",
        "afterword",
        "appendix",
        "notes",
        "bibliography",
        "index",
        "glossary",
        "chapter",
    }
    id_re = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
    heading_re = re.compile(r"^#\s+(.*)$")
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or list(reader.fieldnames) != required:
            raise OrchestrationError(
                f"structure.csv 列契约不符（要求 {','.join(required)}）：{path}"
            )
        for lineno, row in enumerate(reader, start=2):
            uid = (row.get("id") or "").strip()
            region = (row.get("region") or "").strip()
            kind = (row.get("kind") or "").strip()
            title = (row.get("title") or "").strip()
            rel = (row.get("rel_path") or "").strip()
            try:
                level = int((row.get("level") or "").strip())
            except ValueError:
                raise OrchestrationError(
                    f"structure.csv 第 {lineno} 行 level 非法：{row.get('level')!r}"
                ) from None
            if not id_re.match(uid):
                raise OrchestrationError(f"structure.csv 第 {lineno} 行 id 非法：{uid!r}")
            if uid in seen_ids:
                raise OrchestrationError(f"structure.csv 第 {lineno} 行 id 重复：{uid}")
            seen_ids.add(uid)
            if region not in regions:
                raise OrchestrationError(f"structure.csv 第 {lineno} 行 region 非法：{region!r}")
            if kind not in kinds:
                raise OrchestrationError(f"structure.csv 第 {lineno} 行 kind 非法：{kind!r}")
            if not 1 <= level <= 6:
                raise OrchestrationError(f"structure.csv 第 {lineno} 行 level 越界（1–6）：{level}")
            rel_path = Path(rel)
            if rel_path.is_absolute() or ".." in rel_path.parts or not rel.endswith(".md"):
                raise OrchestrationError(f"structure.csv 第 {lineno} 行 rel_path 非法：{rel!r}")
            if region == "cover":
                if rel != "cover.md":
                    raise OrchestrationError(
                        f"structure.csv 第 {lineno} 行 cover 的 rel_path 必须是 cover.md：{rel!r}"
                    )
            elif not rel.startswith(f"{region}/"):
                raise OrchestrationError(
                    f"structure.csv 第 {lineno} 行 rel_path 与 region 不符（应 {region}/ 前缀）：{rel!r}"
                )
            f_path = store.structured_dir / rel
            if not f_path.is_file():
                raise OrchestrationError(f"structure.csv 第 {lineno} 行文件不存在：{rel}")
            first = next(
                (ln for ln in f_path.read_text(encoding="utf-8").splitlines() if ln.strip()), ""
            )
            m = heading_re.match(first)
            if not m:
                raise OrchestrationError(
                    f"structure.csv 第 {lineno} 行文件首行必须是 `# 标题`：{rel}"
                )
            head = re.sub(r"\s*\{#[^}]*\}\s*$", "", m.group(1)).strip()
            if head != title:
                raise OrchestrationError(
                    f"structure.csv 第 {lineno} 行 title 与文件首行不一致：{title!r} vs {head!r}"
                )
            rows.append(
                {
                    "id": uid,
                    "region": region,
                    "kind": kind,
                    "title": title,
                    "level": level,
                    "rel_path": rel,
                }
            )

    known = {r["rel_path"] for r in rows}
    actual = {
        p.relative_to(store.structured_dir).as_posix()
        for p in store.structured_dir.rglob("*.md")
        if "raw" not in p.relative_to(store.structured_dir).parts
    }
    orphans = sorted(actual - known)
    if orphans:
        raise OrchestrationError(
            "structured/ 存在未登记的 md（会从 spine 静默丢出）：" + "、".join(orphans[:8])
        )
    pub = store.load_publication()
    existing = {u.id: u for u in pub.units}
    units: list[Unit] = []
    reset: list[str] = []
    added: list[str] = []
    for r in rows:
        prior = existing.get(r["id"])
        meta = dict(prior.meta) if prior else {}
        meta.update({"rel_path": r["rel_path"], "region": r["region"], "level": r["level"]})
        if prior is None:
            status = "split"
            added.append(r["id"])
        else:
            unchanged = (
                (prior.meta or {}).get("rel_path") == r["rel_path"]
                and prior.title == r["title"]
                and int((prior.meta or {}).get("level") or 1) == r["level"]
                and prior.kind == r["kind"]
                and (prior.meta or {}).get("region") == r["region"]
            )
            status = prior.status if unchanged else "split"
            if not unchanged:
                reset.append(r["id"])
        units.append(Unit(id=r["id"], kind=r["kind"], title=r["title"], status=status, meta=meta))
    removed = sorted(set(existing) - {r["id"] for r in rows})
    store.replace_units(units)
    store.log_event("restructured", units=len(units), reset=reset, added=added, removed=removed)
    return {"units": len(units), "reset": reset, "added": added, "removed": removed}


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
    # 语义整备留痕（S2）：unresolved 仅 W 级提示（文本疑点，非内容缺失）
    repairs = read_repairs(store)
    repairs_unresolved = sum(1 for r in repairs or [] if r.get("status") == "unresolved")
    repairs_stale_unit = sum(1 for r in repairs or [] if r.get("unit_missing"))
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
        repairs_total=len(repairs or []),
        repairs_unresolved=repairs_unresolved,
    )
    if repairs_unresolved:
        report.provenance_findings.append(
            {
                "level": "warning",
                "code": "W_REPAIR_UNRESOLVED",
                "message": f"语义整备有 {repairs_unresolved} 项未决修复（见 "
                "preprocessing/repairs.jsonl）；能修则修，确属存疑的记入交付记录",
            }
        )
    if repairs_stale_unit:
        report.provenance_findings.append(
            {
                "level": "warning",
                "code": "W_REPAIR_STALE_UNIT",
                "message": f"语义整备有 {repairs_stale_unit} 行引用的单元已被结构重建删除"
                "（见 preprocessing/repairs.jsonl）；历史行可忽略，unresolved 行请重挂现存单元",
            }
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
    # 交付审计（S1.4）：全部单元构建完成但无交付记录 → 提示按清单执行（不阻断）
    all_built = bool(pub.units) and all(u.status == "built" for u in pub.units)
    if all_built and not list(store.reviews_dir.glob("delivery-*.md")):
        report.provenance_findings.append(
            {
                "level": "warning",
                "code": "W_DELIVERY_AUDIT_MISSING",
                "message": "全部单元已构建但缺少交付审计记录（reviews/delivery-*.md）；"
                "交付前按 references/delivery.md 执行全量校验并写记录",
            }
        )
    store.save_qa(report.to_dict())
    return report.to_dict()


def read_catalog(store: RunStore) -> list[dict[str, Any]] | None:
    """读取源内容盘点（preprocessing/catalog.csv；S4.4 SourceCatalog 最小形态）。

    文件不存在 → None（全部检查跳过，零破坏）。列契约：
    ``item,kind,status,locator,unit_id,note``——kind ∈ toc|figure|table|footnote|
    section|physical；status ∈ included|physical|excluded|unresolved|absent；
    included 行 unit_id 必填；excluded/absent 行 note 必填理由。
    ``absent`` = 源件本身不含该内容（如题注所指插图不在源包里）——既非「有意排除」，
    也非「未决」，因此不阻断放行（现场报告 #8：缺图只能记 unresolved 或谎称 excluded）。
    取值非法/列缺失 → OrchestrationError（带行号）。
    """
    import csv

    path = store.preprocessing_dir / "catalog.csv"
    if not path.is_file():
        return None
    kinds = {"toc", "figure", "table", "footnote", "section", "physical"}
    statuses = {"included", "physical", "excluded", "unresolved", "absent"}
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
            if status_val in ("excluded", "absent") and not (row.get("note") or "").strip():
                raise OrchestrationError(f"catalog.csv 第 {i} 行：{status_val} 项 note 必填理由")
            rows.append({k: (row.get(k) or "").strip() for k in required})
    return rows


def _task(
    kind: str,
    hint: str,
    *,
    unit: str | None = None,
    done_when: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造一条 next_tasks 任务卡指针（S1：kind/hint/unit?/done_when）。"""
    task: dict[str, Any] = {"kind": kind, "hint": hint}
    if unit is not None:
        task["unit"] = unit
    task["done_when"] = done_when if done_when is not None else {"cmd": kind}
    return task


def _derive_next_tasks(
    store: RunStore,
    pub: Any,
    units_out: list[dict[str, Any]],
    stale: list[dict[str, str]],
    *,
    has_preprocessing: bool,
    preprocessing_complete: bool,
) -> list[dict[str, Any]]:
    """从现有状态机/产物对账派生「下一任务」机器指针（S1，零 token 纯函数）。

    与 ``references/workflow.md`` 的路由伪代码一一对应：按执行顺序排列，弱模型只取
    首条执行，完成后重跑 ``status`` 刷新。``done_when`` 是判据的机器表述（跑哪条命令 /
    查哪个文件），供将来任务循环脚本消费。不新增第二份状态源。
    """
    pre = store.preprocessing_dir
    # A. 预处理：无 facts → 先 preprocess；有 facts 缺理解产物 → 逐文件补
    if not has_preprocessing:
        return [
            _task(
                "preprocess",
                "运行 preprocess 生成 facts（init + 零 token 事实收集）",
                done_when={"cmd": "preprocess"},
            )
        ]
    if not preprocessing_complete:
        for name in ("capabilities.md", "global.md", "todo.md"):
            if not (pre / name).is_file():
                return [
                    _task(
                        "write_preprocessing",
                        f"撰写 preprocessing/{name}",
                        done_when={"file": f"preprocessing/{name}"},
                    )
                ]
    # B. 语义整备：facts 有可疑信号且尚无留痕 → 先整备
    if not (pre / "repairs.jsonl").is_file():
        try:
            facts = read_json(pre / "facts.json")
            signals = int((facts.get("repair_signals") or {}).get("units") or 0)
        except (OSError, ValueError, TypeError):
            signals = 0
        if signals:
            return [
                _task(
                    "repair",
                    f"语义整备：{signals} 个单元有可疑信号，按 references/repair.md 修复并写留痕",
                    done_when={"file": "preprocessing/repairs.jsonl"},
                )
            ]
    # C. 理解层 analysis（可选层）：overview/global 皆无 → 逐单元分析（每批 ≤5，防贪多）
    if (
        not (store.analysis_dir / "overview.md").is_file()
        and not (store.analysis_dir / "global.md").is_file()
    ):
        batch = [u for u in units_out if u["status"] in ("pending", "split")][:5]
        if batch:
            return [
                _task(
                    "analyze",
                    f"分析 {u['id']}（写 analysis/units/{u['id']}.md）",
                    unit=u["id"],
                    done_when={"file": f"analysis/units/{u['id']}.md"},
                )
                for u in batch
            ]
    # D. 译文/对齐已落盘但状态未推进（stale）→ 先 import 登记
    for s in stale:
        if s["id"] == "preprocessing":
            continue
        return [
            _task(
                "import",
                f"登记 {s['id']} 的译文与对齐表（import --unit {s['id']}）",
                unit=s["id"],
                done_when={"cmd": "import", "unit": s["id"]},
            )
        ]
    status_of = {u["id"]: u["status"] for u in units_out}
    # E. 已登记未审校 → 先审校（保持单元级原子循环：translate → import → review → 下一个；
    #    否则会把整个 review 阶段推到全书翻译完之后，弱模型上下文过重——2026-10-05 实测修正）
    for u in pub.units:
        if status_of[u.id] in ("translated", "aligned"):
            return [
                _task(
                    "review",
                    f"审校 {u.id}（G1–G3 语义审校，写 reviews/ 后 import --reviewed）",
                    unit=u.id,
                    done_when={"cmd": "import", "unit": u.id, "reviewed": True},
                )
            ]
    # F. 未翻译 → 翻译（一次只给一个单元 id）
    for u in pub.units:
        if status_of[u.id] in ("pending", "split"):
            return [
                _task(
                    "translate",
                    f"翻译 {u.id}（读 structured → 写 translation/ + align/ → import）",
                    unit=u.id,
                    done_when={"cmd": "import", "unit": u.id},
                )
            ]
    # G. 全部 reviewed/built → build → qa → delivery
    if pub.units and all(s in ("reviewed", "built") for s in status_of.values()):
        if not list(store.output_dir.glob("*.epub")):
            return [_task("build", "封装 EPUB（build）", done_when={"cmd": "build"})]
        if not store.report_path.is_file():
            return [
                _task("qa", "运行 qa（epubcheck + 解包审计 + 放行报告）", done_when={"cmd": "qa"})
            ]
        if not list(store.reviews_dir.glob("delivery-*.md")):
            return [
                _task(
                    "delivery",
                    "交付审计（按 references/delivery.md 全量校验并写记录）",
                    done_when={"file": "reviews/delivery-<ts>.md"},
                )
            ]
    return []


def status_all(base_dir: str | Path) -> list[dict[str, Any]]:
    """多工作区总览（issue #32）：扫描 base_dir 下所有含 publication.json 的工作区。

    每项给出机器可重算字段：slug/title/units_total/unit_status/words、
    ``has_report``、``released``/``released_reason``、``facts_created_at``，以及
    三档进度 ``progress``（released / built_not_released / preprocessing）——
    呼应 #32 的「进度三档口径」，免得文档层与 CLI 层各造一套词。
    """
    from datetime import datetime

    base = Path(base_dir)
    rows: list[dict[str, Any]] = []
    if not base.is_dir():
        return rows
    for pub_file in sorted(base.glob("*/publication.json")):
        ws = pub_file.parent
        try:
            pub = read_json(pub_file)
        except (OSError, ValueError):
            continue
        units = pub.get("units") or []
        counts: dict[str, int] = {}
        for u in units:
            st = str(u.get("status") or "?")
            counts[st] = counts.get(st, 0) + 1
        facts_path = ws / "preprocessing" / "facts.json"
        facts: dict[str, Any] = {}
        if facts_path.is_file():
            try:
                facts = read_json(facts_path)
            except (OSError, ValueError):
                facts = {}
        report_path = ws / "report.json"
        report: dict[str, Any] = {}
        if report_path.is_file():
            try:
                report = read_json(report_path)
            except (OSError, ValueError):
                report = {}
        if report_path.is_file() and report.get("released"):
            progress = "released"
        elif report_path.is_file():
            progress = "built_not_released"
        else:
            progress = "preprocessing"
        rows.append(
            {
                "slug": pub.get("slug") or ws.name,
                "title": (pub.get("meta") or {}).get("title", ""),
                "units_total": len(units),
                "unit_status": counts,
                "words": ((facts.get("structure") or {}).get("totals") or {}).get("words"),
                "has_report": report_path.is_file(),
                "released": report.get("released"),
                "released_reason": report.get("released_reason"),
                "progress": progress,
                "facts_created_at": (
                    datetime.fromtimestamp(facts_path.stat().st_mtime).isoformat()
                    if facts_path.is_file()
                    else None
                ),
            }
        )
    return rows


def render_ledger(rows: list[dict[str, Any]]) -> str:
    """把 ``status_all`` 结果渲染为跨书台账 markdown（issue #32 §3 六字段）。

    前四字段（开工日期/进度/单元/词数）机器可重算；领域/摘要两列留空待 agent 补。
    """
    lines = [
        "# 工作台账",
        "",
        "> 前四个数据列由 `auto-epublizer status --all` 机器可重算；「领域」「摘要」由 agent 撰写。",
        "",
        "| slug | 书名 | 开工日期 | 进度 | 单元 | 词 | 领域 | 摘要 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        created = (r.get("facts_created_at") or "")[:10]
        lines.append(
            f"| {r['slug']} | {r['title']} | {created} | {r['progress']} | "
            f"{r['units_total']} | {r.get('words') or ''} |  |  |"
        )
    lines += [
        "",
        "数据来源：开工日期=`preprocessing/facts.json` mtime；进度=`report.json` 的 released/"
        "released_reason（无 report.json 记 preprocessing）；单元/词=`publication.json` 与 facts。",
    ]
    return "\n".join(lines) + "\n"


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
        "next_tasks": _derive_next_tasks(
            store,
            pub,
            units_out,
            stale,
            has_preprocessing=has_preprocessing,
            preprocessing_complete=preprocessing_complete,
        ),
    }
    return data
