# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""Orchestrator：薄 façade，只装配与路由，不直接调用领域函数、不持有线程池。

唯一 LLM 原则：编排层不做任何 LLM 调用——理解/翻译/审校由操作 CLI 的 agent 完成，
这里只装配确定性领域服务（ingest/structure/build/qa/preprocess）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from auto_common.config import Config
from auto_common.workspace import RunStore, init_workspace, read_json
from auto_translator.translation.align import read_align

from . import __version__
from .build import build_epub, collect_media, subheading_anchors
from .build.html import render_document, slug_file
from .ingest import load_document
from .preprocess.artifacts import read_catalog, read_repairs
from .qa import artifacts_digest, audit_epub, audit_notes_epub, generate_report, run_epubcheck
from .qa.artifacts import report_state
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
    progress: Any | None = None,
) -> RunStore:
    store = init_workspace(
        input_path,
        config=config,
        target_language=target_language,
        references=references,
        workspace_dir=workspace_dir,
        original=original,
        producer=f"auto-epublizer@{__version__}",  # 来源标识（#40 §5.2）
    )
    prepare_structure(store, config=config, progress=progress)
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
            # nav=false：单元进 spine 但不进目录（献词页等前置噪声页）
            "nav": (u.meta or {}).get("nav", True) is not False,
        }
        for u in pub.units
    ]


def _ocr_backend_if_needed(store: RunStore, config: Config | None = None):
    """PDF 源且 rapidocr 可用时返回 OCR 后端（按 config.pdf.ocr 控制），否则 None。

    - ``pdf.ocr: auto``（默认）→ 可用即启用；
    - ``pdf.ocr: off`` → 禁用；
    - 其他值 → 视为要求强制启用，不可用时明确报错。

    能力探测归 ``ingest.ocr``（C 组最小重构）；本函数只做路由装配。
    """
    pub = store.load_publication()
    if not pub.meta.source.lower().endswith(".pdf"):
        return None
    cfg = config or Config()
    ocr_setting = (cfg.pdf.ocr or "auto").lower()
    if ocr_setting == "off":
        return None
    from .ingest.ocr import RapidOcrBackend, rapidocr_available

    if not rapidocr_available():
        if ocr_setting == "auto":
            return None
        raise OrchestrationError(
            "pdf.ocr 要求启用 OCR，但未安装 rapidocr-onnxruntime（uv sync --extra ocr）"
        )
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


def prepare_structure(
    store: RunStore, *, config: Config | None = None, progress: Any | None = None
) -> list[dict[str, Any]]:
    """解析源文件并写入四层结构（幂等）：structured/ + units 清单 + split 状态。

    ``progress``：可选回调 ``(page_no, total) → None``，长任务（PDF 逐页）进度提示。
    """
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
        progress=progress,
    )
    pub = store.load_publication()
    entries = rebuild_structure(doc, pub)
    write_structured(store, doc, entries)
    pub.meta.processing_tools = doc.meta["processing_tools"]
    store.save_publication(pub)
    store.set_units(entries)
    for e in entries:
        store.set_unit_status(e["id"], "split")
    store.log_event(
        "structure_written", units=len(entries), processing_tools=pub.meta.processing_tools
    )
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
    """EPUB 源语言标注：优先元数据；缺省采样首个非空单元，交 detect 域判定。

    convert/build 不跑 analyze，语言元数据可能缺失（此前一律 und）。采样与截断
    （IO）留在这里；判定规则（含「en 但无拉丁字母 → und」）归
    ``detect_source_language``（C 组：决策规则迁出编排层）。
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
    from auto_translator.analysis.detect import detect_source_language

    return detect_source_language(sample[:4000])


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
        event="convert_built",
        prefer_translation=False,
        theme=theme or Config().output.theme,
        nav_depth=nav_depth,
    )


def _render_inputs(
    store: RunStore, entries: list[dict[str, Any]], *, mode: str
) -> dict[str, dict[str, Any]]:
    """一次选择实际渲染输入；注文计划和渲染循环共享宿主及来源。"""
    inputs: dict[str, dict[str, Any]] = {}
    for entry in entries:
        uid = str(entry["id"])
        rel = entry.get("rel_path")
        if not rel:
            continue
        translated = store.translation_dir / rel
        use_translation = mode == "translation" and translated.is_file()
        path = translated if use_translation else store.structured_dir / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if not skip_empty_unit(text, entry.get("title") or ""):
            inputs[uid] = {
                "source": "translation" if use_translation else "source",
                "markdown": text,
            }
    return inputs


def _note_plan(
    store: RunStore,
    pub: Any,
    entries: list[dict[str, Any]],
    source_data: dict[str, Any],
    *,
    unit_sources: dict[str, str],
) -> dict[str, Any]:
    """构造全书注释计划（N4，确定性）：作用域显示号 + 宿主单元 + 回链 + 文本。

    规则：
    - 显示号：原印正整数号优先；符号号按引用顺序分配，跳过全作用域预留的数字号；
    - 宿主：注文渲染在 spine 序中**第一个引用它的单元**；跨文件引用 href 指回宿主；
    - 未引用注文（``orphan_ok``）：优先取自身 source_locations 单元，缺失时仅允许
      有效 scope_id 单元；无法定位时拒绝构建，不猜书首；
    - 文本来源：由实际渲染输入决定；同一宿主选择同时供绑定校验、构建和成品审计使用。
    """

    order_index = {str(e["id"]): i for i, e in enumerate(entries)}
    file_by_unit = {str(e["id"]): f"{slug_file(e['id'])}.xhtml" for e in entries}
    rel_by_unit = {u.id: (u.meta or {}).get("rel_path") for u in pub.units}
    notes_by_id: dict[str, dict[str, Any]] = {
        str(n.get("note_id")): n
        for n in (source_data.get("notes") or [])
        if isinstance(n, dict) and n.get("note_id")
    }
    by_unit: dict[str, list[dict[str, Any]]] = {}
    for r in source_data.get("references") or []:
        if isinstance(r, dict) and r.get("unit"):
            by_unit.setdefault(str(r["unit"]), []).append(r)

    def _md(unit: str) -> str:
        rel = rel_by_unit.get(unit)
        p = store.structured_dir / rel if rel else None
        return p.read_text(encoding="utf-8") if p is not None and p.is_file() else ""

    ordered: list[tuple[int, int, str, dict[str, Any]]] = []
    md_cache: dict[str, str] = {}
    for unit, rs in by_unit.items():
        md = md_cache.setdefault(unit, _md(unit))
        for r in rs:
            rid = str(r.get("ref_id") or "")
            pos = md.find(f"[^{rid}]")
            ordered.append((order_index.get(unit, 1 << 30), pos if pos >= 0 else 1 << 30, unit, r))
    ordered.sort(key=lambda t: (t[0], t[1]))

    counters: dict[str, int] = {}
    used_numbers: dict[str, set[int]] = {}
    for note in notes_by_id.values():
        label = str(note.get("source_label") or "").strip()
        if label.isdecimal() and int(label) > 0:
            used_numbers.setdefault(str(note.get("scope_id") or ""), set()).add(int(label))
    number_by_note: dict[str, int] = {}
    ref_info: dict[str, dict[str, Any]] = {}
    host: dict[str, str] = {}
    backlinks: dict[str, list[str]] = {}

    def _display_number(note: dict[str, Any], scope: str) -> int:
        """显示号：**原书注号优先**，否则按作用域计数。

        原书注号就是读者在纸书上看到的号。原书若存在未被正文引用的注（或编号
        跳号），按引用顺序重排会把后续全部注的号顶前一位——与纸书对不上。
        登记门已保证 ``(scope_id, source_label)`` 唯一，故注号在作用域内不冲突；
        注号非正整数时才退回作用域计数，并跳过已占用的号。
        """
        label = str(note.get("source_label") or "").strip()
        if label.isdecimal():
            n = int(label)
            if n > 0:
                return n
        taken = used_numbers.setdefault(scope, set())
        n = counters.get(scope, 0) + 1
        while n in taken:
            n += 1
        counters[scope] = n
        taken.add(n)
        return n

    for _, _, unit, r in ordered:
        nid = str(r.get("note_id") or "")
        note = notes_by_id.get(nid)
        if note is None:
            continue
        scope = str(note.get("scope_id") or unit)
        if nid not in number_by_note:
            # 显示号按**注文**分配（一注多引同号）；跨作用域独立
            n = _display_number(note, scope)
            number_by_note[nid] = n
            used_numbers.setdefault(scope, set()).add(n)
        rid = str(r.get("ref_id") or "")
        ref_info[rid] = {
            "note_id": nid,
            "number": number_by_note[nid],
            "unit": unit,
            "file": file_by_unit.get(unit, ""),
        }
        host.setdefault(nid, unit)
        backlinks.setdefault(nid, []).append(f"{file_by_unit.get(unit, '')}#{rid}")
    for nid in sorted(notes_by_id):
        if nid in host:
            continue
        note = notes_by_id[nid]
        scope = str(note.get("scope_id") or "")
        n = _display_number(note, scope)
        number_by_note[nid] = n
        used_numbers.setdefault(scope, set()).add(n)
        # 注文自己的位置优先；跨页多位置按已核证清单顺序取首个有效宿主。
        host_unit = next(
            (
                str(loc["unit"])
                for loc in note.get("source_locations") or []
                if isinstance(loc, dict) and str(loc.get("unit") or "") in order_index
            ),
            scope if scope in order_index else "",
        )
        if not host_unit:
            raise OrchestrationError(f"孤注 {nid} 缺少可解析宿主单元：须核证 source_locations")
        host[nid] = host_unit
        ref_info[f"__orphan__{nid}"] = {
            "note_id": nid,
            "number": number_by_note[nid],
            "unit": host[nid],
            "file": file_by_unit.get(host[nid], ""),
        }
    return {
        "ref_info": ref_info,
        "host": host,
        "backlinks": backlinks,
        "number_by_note": number_by_note,
        "notes_by_id": notes_by_id,
        "targets": {},
        "translated_note_ids": {
            nid for nid, unit in host.items() if unit_sources.get(unit) == "translation"
        },
        "file_by_unit": file_by_unit,
        # 渲染层需要 note_id → 宿主文件（跨文件 href 用；与宿主单元一致）
        "href_by_note": {nid: file_by_unit.get(u, "") for nid, u in host.items()},
        "units_missing": sorted(set(by_unit) - set(order_index)),
    }


def _render_and_pack(
    store: RunStore,
    pub: Any,
    entries: list[dict[str, Any]],
    *,
    lang: str,
    output: str | None,
    event: str,
    prefer_translation: bool,
    theme: str = "standard",
    nav_depth: int | None = None,
) -> Path:
    """构建内核（convert/build 共用）：渲染内容文档 + 收集媒体 + 打包 EPUB。

    脚注语义化（epub-template-spec §6）：每单元一份 FootnoteState（章内独立编号，
    注码 ``[N]``），``[^label]`` 引用与定义渲染为标准注释语义（noteref/footnote）。
    主题层（epub-template-spec §5）：``theme`` 选择预置排版主题。
    目录投影（epub-template-spec §3）：``nav_depth`` 限制 nav/NCX 嵌套深度。
    封面：cover 单元的首个图片 → ``cover-image`` 属性 + spine ``linear="no"``。
    """
    from . import notes as notes_mod
    from .build.html import FootnoteState, NoteItem, NoteRef

    nav_depth = nav_depth if nav_depth is not None else Config().output.nav_depth
    out_path = Path(output) if output else store.output_dir / f"{pub.slug}.epub"
    media_root = store.structured_dir / "raw" / "media"
    content = []
    media: dict[str, bytes] = {}
    media_dropped: dict[str, list[str]] = {}
    cover_media: str | None = None
    built_ids: list[str] = []
    fallback_ids: list[str] = []
    render_mode = "translation" if prefer_translation else "source"
    render_inputs = _render_inputs(store, entries, mode=render_mode)
    notes_ctx = _load_notes_context(store, pub, entries=entries, render_inputs=render_inputs)
    note_plan = notes_ctx.get("plan") if notes_ctx is not None else None

    def _note_items_for(unit_id: str) -> list[NoteItem]:
        """按同一计划渲染该宿主的注文，不再另行推断文本来源。"""
        items: list[NoteItem] = []
        if note_plan is None:
            return items
        for nid, host_unit in note_plan["host"].items():
            if host_unit != unit_id:
                continue
            number = int(note_plan["number_by_note"].get(nid) or 0)
            if nid in note_plan["translated_note_ids"]:
                t = note_plan["targets"].get(nid)
                if t is None or not str(t.get("target_markdown") or "").strip():
                    raise OrchestrationError(
                        f"译文构建缺译注：{nid}（宿主单元 {unit_id}）；"
                        "补齐 translation/notes.json 后重新 import"
                    )
                text = str(t["target_markdown"])
            else:
                text = str((note_plan["notes_by_id"].get(nid) or {}).get("source_markdown") or "")
            text, note_media, note_dropped = collect_media(text, media_root)
            if note_dropped:
                media_dropped[f"notes/{nid}"] = note_dropped
            for epub_path, data in note_media:
                media[epub_path] = data
            items.append(
                NoteItem(
                    note_id=nid,
                    number=number,
                    text_md=text,
                    backlinks=tuple(note_plan["backlinks"].get(nid, [])),
                )
            )
        return items

    for e in entries:
        render_input = render_inputs.get(str(e["id"]))
        if render_input is None:
            continue
        unit_refs: dict[str, NoteRef] = {}
        unit_items: list[NoteItem] = []
        if note_plan is not None:
            for rid, info in note_plan["ref_info"].items():
                if info["unit"] != e["id"] or rid.startswith("__orphan__"):
                    continue
                unit_refs[rid] = NoteRef(ref_id=rid, note_id=info["note_id"], number=info["number"])
        if prefer_translation and render_input["source"] == "source":
            fallback_ids.append(e["id"])
        md_text = render_input["markdown"]
        # 未配对引用不得静默：正文标记必须都在登记计划内（登记门/导入门之外的构建兜底）
        if note_plan is not None:
            unknown = [m for m in notes_mod.extract_markers(md_text) if m not in unit_refs]
            if unknown:
                raise OrchestrationError(
                    f"{e['id']}：构建发现未登记标记 {'、'.join('[' + '^' + u + ']' for u in unknown[:5])}"
                    "（不得静默丢弃；先 notes register / import 登记）"
                )
        heading = unit_heading(md_text)
        if heading:
            e["title"] = heading
        # 锚点级目录（epub-template-spec §3）：与渲染源同一 md 提取子标题锚点
        # （id 与 markdown_to_xhtml 自动 id 规则一致，nav 链接不悬空）。
        e["anchors"] = subheading_anchors(md_text, e["id"])
        md_text, unit_media, dropped = collect_media(md_text, media_root)
        if dropped:
            media_dropped[e["id"]] = dropped
        for epub_path, data in unit_media:
            media[epub_path] = data
        if e.get("kind") == "cover" and unit_media and cover_media is None:
            cover_media = unit_media[0][0]
        if note_plan is not None:
            unit_items = _note_items_for(e["id"])
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
                    note_refs=unit_refs or None,
                    note_items=unit_items or None,
                    href_by_note=note_plan["href_by_note"] if note_plan else None,
                ),
            )
        )
    if note_plan is not None:
        referenced_units = {v["unit"] for v in note_plan["ref_info"].values()}
        dropped = sorted(referenced_units - set(built_ids))
        if dropped:
            raise OrchestrationError(
                "以下单元的注释引用未进入成品（不得静默丢弃）：" + "、".join(dropped[:8])
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
        render_mode=render_mode,
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


def evidence_breaks(store: RunStore, *, output: str | None = None) -> dict[str, Any]:
    """产出页边界证据 ``preprocessing/breaks.jsonl``（issue #14 / #10-B3）。

    只**定位证据**（相邻页两侧存活行 + 回溯到 structured 的块号），不做语义合并——
    merge/keep/unresolved 的裁定仍由 agent 完成（references/repair.md）。
    """
    import json

    from .preprocess.evidence import collect_breaks

    rows = collect_breaks(store)
    out_path = Path(output) if output else store.preprocessing_dir / "breaks.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    store.log_event("evidence_breaks_written", count=len(rows))
    return {
        "breaks": len(rows),
        "candidates": sum(1 for r in rows if r.get("candidate")),
        "path": str(out_path),
    }


def rebuild(
    store: RunStore, *, config: Config | None = None, progress: Any | None = None
) -> dict[str, Any]:
    """原地重建 ``structured/``（含 raw/）与 facts（issue #30 §4.2，``preprocess --force``）。

    从 ``source/`` 重新 ingest → 覆盖 structured/ → 重算 facts。单元状态被重置为
    ``split``（既有译文变 stale，需重新走 import）；调用方须显式 ``--force`` 表达该意图。
    用于「preprocess 误中断后恢复」，无需人工搬目录。
    """
    import shutil

    if store.structured_dir.exists():
        shutil.rmtree(store.structured_dir)
    prepare_structure(store, config=config, progress=progress)
    return preprocess(store, config=config)


def build(
    store: RunStore,
    *,
    output: str | None = None,
    theme: str | None = None,
    nav_depth: int | None = None,
) -> Path:
    """从译文（缺省回退源文）构建 EPUB。"""
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


def _g0_thresholds(cfg: Config) -> dict[str, Any]:
    """G0 长度比阈值（三条调用链——import/g0/qa——统一从此取，口径一致；issue #39）。

    ``min_src_chars``：短源保护——源文去空白后不足该字符数时不做比值判定
    （判据与理由见 ``auto_translator.review.g0.MIN_SRC_CHARS``）。**译文为空**
    检查不看源长，不受该保护影响。
    """
    lr = cfg.qc.length_ratio
    return {
        "too_short": float(lr.get("too_short", 0.30)),
        "too_long": float(lr.get("too_long", 3.0)),
        "min_src_chars": int(lr.get("min_src_chars", 20)),
    }


def import_translations(
    store: RunStore,
    *,
    unit_id: str | None = None,
    terms_path: str | None = None,
    mark_reviewed: bool = False,
    force: bool = False,
    config: Config | None = None,
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
    from auto_translator.glossary.csv_io import load_terminology_exemptions
    from auto_translator.review import check_alignment, g0_unit_flags, is_heading_only
    from auto_translator.translation.align import read_align

    pub = store.load_publication()
    exemptions = load_terminology_exemptions(store.preprocessing_dir / "terminology_exemptions.csv")
    from .preprocess.artifacts import read_style_exemptions

    style_exemptions = read_style_exemptions(store)
    glossary_path = store.analysis_dir / "glossary.csv"
    conflicts_path = store.analysis_dir / "glossary_conflicts.jsonl"

    # 可选：批量导入 agent 提取的新术语提案（propose 三态判定）
    # 显式坏输入在写回前失败（issue #36）：路径相对 cwd 解析（不做工作区回退），
    # 不存在直接报错，避免「导入完成、告警=0」被误读为成功。
    terms_info: dict[str, Any] | None = None
    if terms_path:
        terms_file = Path(terms_path)
        if not terms_file.is_file():
            raise OrchestrationError(
                f"术语提案文件不存在：{terms_file.resolve()}"
                "（相对路径按当前工作目录解析；本命令不做工作区相对路径回退）"
            )
        proposed = load_glossary_csv(terms_file)
        usable = [e for e in proposed if e.source and e.target]
        if usable:
            glossary = Glossary(load_glossary_csv(glossary_path))
            for entry in usable:
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
        terms_info = {
            "path": str(terms_file),
            "proposed": len(usable),
            "skipped": len(proposed) - len(usable),
        }

    glossary = Glossary(load_glossary_csv(glossary_path))
    # 导入门按实际待导入单元的引用需求惰性读取译注；源登记校验不读取无关译注。
    notes_ctx = _load_notes_context(store, pub)
    from . import notes as notes_mod

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
        translation_md = tgt_path.read_text(encoding="utf-8") if tgt_path.is_file() else None
        errors: list[str] = []
        pending_reasons: list[str] = []
        if not tgt_path.is_file():
            pending_reasons.append(f"缺少译文文件：{tgt_path}")
        rows = read_align(align_path) if align_path.is_file() else []
        if not rows and not (is_heading_only(structured_md) and is_heading_only(translation_md)):
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
        if translation_md is not None and rows:
            from auto_translator.review import md_align_drift

            for d in md_align_drift(translation_md, rows, title=unit.title):
                errors.append(f"文档一致性：{d}")
        # N 阶段翻译导入门：译文原位标记守恒 + 所需译注齐全（源注文已登记时启用）
        if notes_ctx is not None:
            unit_refs = [
                r
                for r in (notes_ctx["data"].get("references") or [])
                if isinstance(r, dict) and str(r.get("unit") or "") == unit.id
            ]
            if unit_refs:
                found = notes_mod.extract_markers(translation_md or "")
                want = {str(r.get("ref_id")) for r in unit_refs}
                for rid in sorted(want - set(found)):
                    errors.append(f"注释标记：译文缺 [^{rid}]（引用丢失）")
                for rid in sorted(set(found) - want):
                    errors.append(f"注释标记：译文出现未登记标记 [^{rid}]")
                for rid in sorted(want & set(found)):
                    if found.count(rid) != 1:
                        errors.append(
                            f"注释标记：[^{rid}] 在译文中出现 {found.count(rid)} 次（应恰好 1 次）"
                        )
                need = {str(r.get("note_id")) for r in unit_refs}
                if "target_loaded" not in notes_ctx:
                    target_path = notes_mod.translation_notes_path(store)
                    try:
                        notes_ctx["target"] = (
                            notes_mod.read_notes_json(target_path)
                            if target_path.is_file()
                            else None
                        )
                    except notes_mod.NotesError as error:
                        notes_ctx["target_error"] = str(error)
                    notes_ctx["target_loaded"] = True
                if notes_ctx.get("target_error"):
                    errors.append(f"译注：{notes_ctx['target_error']}")
                target = notes_ctx.get("target")
                if target is None:
                    errors.append(
                        f"译注：缺 translation/notes.json（本单元引用 {len(need)} 条注文，须完整译注）"
                    )
                else:
                    for e in notes_mod.validate_translation_notes(
                        notes_ctx["data"],
                        target,
                        source_notes_digest=str(notes_ctx["digest"]),
                        required_note_ids=need,
                    ):
                        errors.append(f"译注：{e}")
        for f in g0_unit_flags(
            rows,
            glossary,
            structured_md=structured_md,
            translation_md=translation_md,
            **_g0_thresholds(config or Config()),
            exempt_sources=exemptions.get(unit.id, {}),
            language_exempt=style_exemptions.get(unit.id, []),
            source_language=pub.meta.language or "auto",
            target_language=pub.meta.target_language or "zh-CN",
        ):
            # 源保真：反向失配（blocking=True，src 不在源文中）= 对照表不可信，阻断登记；
            # 前向缺块（blocking=False，可能为合法剔除）与其余硬缺陷类/advisory 收进告警：
            # 其余硬缺陷类（terminology/marker/footnote/heading）与前向缺块
            # （fidelity）、advisory（length）收进告警：import 期不阻断，
            # 漏修被 G5 放行门兜底
            if f.check == "fidelity" and f.blocking:
                errors.append(f"源保真：{f.message}（seq={f.data.get('seq')}）")
                continue
            if f.check in ("language", "length", "length_review") and f.blocking:
                errors.append(f"{f.check}：{f.message}（seq={f.data.get('seq')}）")
                continue
            if f.check in (
                "length",
                "terminology",
                "terminology_exempt",
                "language_exempt",
                "length_review_exempt",
                "marker",
                "footnote",
                "footnote_suspect",
                "heading",
                "fidelity",
            ):
                warned.append(
                    {
                        "unit": unit.id,
                        "check": f.check,
                        "message": f.message,
                        "blocking": bool(f.blocking),
                    }
                )
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
    # 分开两个数（issue #35）：written = 本次新增外置；conflicts_open = 账本里待裁决总数
    # （含历史 open，已裁决的 resolved 不计）。不再把「文件已有行数」报成本次检出。
    conflicts = glossary.detect_conflicts()
    written = write_conflicts_jsonl(conflicts_path, conflicts)
    conflicts_open = sum(
        1 for c in read_conflicts_jsonl(conflicts_path) if c.get("status") == "open"
    )

    # --reviewed：审校通过的显式登记（aligned → reviewed，幂等）
    reviewed: list[str] = []
    if mark_reviewed:
        accepted = set(imported) | set(revalidated)
        for unit in store.load_publication().units:
            if unit.id in accepted and unit.status == "aligned":
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
        "conflicts_new": written,
        "conflicts_open": conflicts_open,
        "terms": terms_info,
        "reviewed": reviewed,
    }


def _assert_no_unregistered_notes(store: RunStore, pub: Any) -> None:
    """源件有注文却没登记时**硬失败**（T12-3）。

    ``pub.notes`` 为空 → 注文门被整体跳过；若无条件跳过，「源文有注、成品没注」
    就会一路绿灯放行。故此处查两处证据：

    1. ``structured/notes.json`` 存在且含注文（说明核证过但没 ``notes register``）；
    2. 正文里出现 ``[^ref-…]`` 原位标记（说明正文有引用而登记缺失）。

    两处都没有 → 仅表示无机器证据，保持转换兼容；不能据此宣称源件无注，
    仍须 agent 独立源清点。
    """
    from . import notes as notes_mod

    npath = notes_mod.source_notes_path(store)
    if npath.is_file():
        try:
            data = notes_mod.read_notes_json(npath)
        except notes_mod.NotesError as exc:
            raise OrchestrationError(f"源注文清单不可读：{exc}") from exc
        if data.get("notes") or data.get("references"):
            raise OrchestrationError(
                "structured/notes.json 有已核证的源注文，但 publication.json.notes 为空："
                "须跑 notes register（注文门不得静默跳过）"
            )
        errors = notes_mod.validate_source_notes(
            data,
            source_sha256=pub.meta.source_sha256,
            unit_ids={u.id for u in pub.units},
        )
        if errors or data.get("inventory") != "none":
            raise OrchestrationError("源注文清单未通过登记契约：" + "；".join(errors))
    for unit in pub.units:
        rel = (unit.meta or {}).get("rel_path")
        if not rel:
            continue
        path = store.structured_dir / rel
        if not path.is_file():
            continue
        if notes_mod.extract_markers(path.read_text(encoding="utf-8")):
            raise OrchestrationError(
                f"正文 {rel} 有注文原位标记 [^ref-…]，但 publication.json.notes 为空："
                "须跑 notes register（注文门不得静默跳过）"
            )


def _load_notes_context(
    store: RunStore,
    pub: Any,
    *,
    entries: list[dict[str, Any]] | None = None,
    render_inputs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """校验源登记；给定实际输入时，按逐注宿主计划加载并绑定真正使用的译注。"""
    from . import notes as notes_mod

    if not pub.notes:
        _assert_no_unregistered_notes(store, pub)
        return None
    npath = notes_mod.source_notes_path(store)
    if not npath.is_file():
        raise OrchestrationError(
            "已登记注释但 structured/notes.json 缺失（须重新核证并 notes register）"
        )
    digest = notes_mod.file_digest(npath)
    if digest != str(pub.notes.get("source_notes_sha256") or ""):
        raise OrchestrationError(
            "structured/notes.json 与登记摘要不一致（源注文已变更）：须重跑 notes register"
            "（必要时重译受影响注文）"
        )
    try:
        data = notes_mod.read_notes_json(npath)
        context: dict[str, Any] = {"data": data, "digest": digest, "target": None}
        if render_inputs is None or data.get("inventory") != "present":
            return context
        active = [e for e in (entries or []) if str(e["id"]) in render_inputs]
        if not active:
            raise OrchestrationError("没有可承载已登记注文的内容单元")
        plan = _note_plan(
            store,
            pub,
            active,
            data,
            unit_sources={uid: item["source"] for uid, item in render_inputs.items()},
        )
        if plan["units_missing"]:
            raise OrchestrationError(
                "注释引用的单元未参与构建："
                + "、".join(plan["units_missing"][:8])
                + "（不得静默丢弃引用）"
            )
        required = plan["translated_note_ids"]
        if required:
            tpath = notes_mod.translation_notes_path(store)
            if not tpath.is_file():
                raise OrchestrationError(
                    "译文注文宿主缺 translation/notes.json（须补齐译注并重跑 import）"
                )
            target = notes_mod.read_notes_json(tpath)
            if str(target.get("source_notes_sha256") or "") != digest:
                raise OrchestrationError(
                    "译注绑定的源注文摘要不符（structured/notes.json 已变更，须重译受影响注文）"
                )
            rows = target.get("notes")
            if isinstance(rows, list):
                target = {
                    **target,
                    "notes": [
                        note
                        for note in rows
                        if isinstance(note, dict) and str(note.get("note_id") or "") in required
                    ],
                }
            errors = notes_mod.validate_translation_notes(
                data, target, source_notes_digest=digest, required_note_ids=required
            )
            if errors:
                raise OrchestrationError("实际使用的译注无效：" + "；".join(errors[:8]))
            context["target"] = target
            plan["targets"] = {note["note_id"]: note for note in target["notes"]}
        context["plan"] = plan
        return context
    except notes_mod.NotesError as error:
        raise OrchestrationError(str(error)) from error


def notes_candidates(store: RunStore, *, output: str | None = None) -> dict[str, Any]:
    """导出注释候选（N1，零 token）：structured/ 正文 → preprocessing/note_candidates.jsonl。

    候选身份不带行号（内容哈希），重跑保留已有处置；只读取结构化正文，不修改。
    """
    from . import notes as notes_mod

    pub = store.load_publication()
    md_by_unit: dict[str, str] = {}
    for u in pub.units:
        rel = (u.meta or {}).get("rel_path")
        p = store.structured_dir / rel if rel else None
        if p is not None and p.is_file():
            md_by_unit[u.id] = p.read_text(encoding="utf-8")
    rows = notes_mod.extract_candidates(md_by_unit)
    prior = {
        str(r.get("candidate_id")): r
        for r in notes_mod.read_candidates(notes_mod.candidates_path(store))
    }
    kept = 0
    for r in rows:
        prev = prior.get(str(r.get("candidate_id")))
        if prev is not None and prev.get("disposition") in notes_mod.CANDIDATE_DISPOSITIONS:
            r["disposition"] = prev["disposition"]
            # F1：稳定身份绑定随处置一并保留（重跑不丢核证结果）
            for key in ("note_id", "ref_id"):
                if prev.get(key):
                    r[key] = prev[key]
            kept += 1
    out_path = Path(output) if output else notes_mod.candidates_path(store)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    by_kind: dict[str, int] = {}
    for r in rows:
        by_kind[str(r["kind"])] = by_kind.get(str(r["kind"]), 0) + 1
    return {
        "path": str(out_path),
        "candidates": len(rows),
        "dispositions_kept": kept,
        "by_kind": by_kind,
    }


def register_notes(store: RunStore) -> dict[str, Any]:
    """登记 ``structured/notes.json``（分离登记门）：契约校验 + 摘要写入 publication.json。

    阻断项：schema/源哈希绑定；盘点结论不得留在 unverified；注文与引用身份、作用域、
    双位置证据、未决状态；正文原位标记 ↔ 引用双向对账（present 时）；候选处置未决。
    通过后仅把**摘要**写入 ``publication.json.notes``（状态只经 CLI 推进）。
    """
    from . import notes as notes_mod

    pub = store.load_publication()
    path = notes_mod.source_notes_path(store)
    data = notes_mod.read_notes_json(path)
    unit_ids = {u.id for u in pub.units}
    source_sha256 = (str(pub.meta.source_sha256) or "").strip() or None
    errors = notes_mod.validate_source_notes(data, source_sha256=source_sha256, unit_ids=unit_ids)
    inventory = str(data.get("inventory") or "")
    if inventory == "unverified":
        errors.append("盘点结论仍是 unverified：须核证为 present（有注且已建绑定）或 none（无注）")
    if inventory == "present":
        md_by_unit: dict[str, str] = {}
        for u in pub.units:
            rel = (u.meta or {}).get("rel_path")
            p = store.structured_dir / rel if rel else None
            if p is not None and p.is_file():
                md_by_unit[u.id] = p.read_text(encoding="utf-8")
        refs = [r for r in (data.get("references") or []) if isinstance(r, dict)]
        errors.extend(notes_mod.validate_markers_vs_references(md_by_unit, refs))
    cands = notes_mod.read_candidates(notes_mod.candidates_path(store))
    if cands:
        errors.extend(notes_mod.validate_candidates(cands))
        # P1/F1：核证结论必须绑定稳定身份并与注文/引用图确定性对账
        errors.extend(notes_mod.validate_candidates_vs_graph(cands, data))
    if errors:
        raise OrchestrationError("注释登记失败：\n- " + "\n- ".join(errors))
    summary = notes_mod.registration_summary(data, notes_mod.file_digest(path))
    pub.notes = summary
    store.save_publication(pub)
    store.log_event("notes_registered", summary=summary)
    return {"summary": summary}


def notes_status(store: RunStore) -> dict[str, Any]:
    """注释登记状态（只读）：登记摘要、文件摘要是否失效、候选处置进度。"""
    from . import notes as notes_mod

    pub = store.load_publication()
    src = notes_mod.source_notes_path(store)
    tgt = notes_mod.translation_notes_path(store)
    cand = notes_mod.candidates_path(store)
    digest = notes_mod.file_digest(src) if src.is_file() else None
    registered = pub.notes
    stale = bool(
        registered and digest and str(registered.get("source_notes_sha256") or "") != digest
    )
    cands = notes_mod.read_candidates(cand)
    pending = [c for c in cands if c.get("disposition") not in notes_mod.CANDIDATE_DISPOSITIONS]
    return {
        "registered": registered,
        "source_notes": {"path": str(src), "exists": src.is_file(), "digest": digest},
        "translation_notes": {"path": str(tgt), "exists": tgt.is_file()},
        "candidates": {
            "path": str(cand),
            "exists": cand.is_file(),
            "total": len(cands),
            "pending": len(pending),
        },
        "stale": stale,
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


def _qa_requires_align(store: RunStore, unit: Any) -> bool:
    """该单元必须进入 G0：有译文文件，或状态已进入译文族。

    仅源文回退不要求对照表；纯标题也必须进入 G0 检查标题层级，
    空对照表例外由共享的源译双侧纯标题判据决定。
    """
    rel = (unit.meta or {}).get("rel_path")
    has_translation = bool(rel) and (store.translation_dir / rel).is_file()
    return has_translation or unit.status in ("translated", "aligned", "reviewed")


def g0_check(
    store: RunStore, *, unit_id: str | None = None, config: Config | None = None
) -> dict[str, Any]:
    """G0 零 token 静态校验（独立命令；翻译/导入后立即跑，不必等到 qa）。"""
    from auto_translator.glossary import Glossary, load_glossary_csv
    from auto_translator.glossary.csv_io import load_terminology_exemptions
    from auto_translator.review import g0_unit_flags

    cfg = config or Config()
    pub = store.load_publication()
    exemptions = load_terminology_exemptions(store.preprocessing_dir / "terminology_exemptions.csv")
    from .preprocess.artifacts import read_style_exemptions

    style_exemptions = read_style_exemptions(store)
    flags: list[dict[str, Any]] = []
    checked: list[str] = []
    for unit in pub.units:
        if unit_id and unit.id != unit_id:
            continue
        rows = read_align(store.unit_align_path(unit.id))
        if not rows and not _qa_requires_align(store, unit):
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
            **_g0_thresholds(cfg),
            exempt_sources=exemptions.get(unit.id, {}),
            language_exempt=style_exemptions.get(unit.id, []),
            source_language=pub.meta.language or "auto",
            target_language=pub.meta.target_language or "zh-CN",
        ):
            flags.append(_flag_dict(unit.id, f))
        for f in _unit_doc_flags(store, rel_path) if rel_path else []:
            flags.append(_flag_dict(unit.id, f))
    return {"checked_units": checked, "flags": flags}


def _collect_g0_flags(store: RunStore, config: Config | None = None) -> list[dict[str, Any]]:
    """对所有已对齐单元执行 G0 零 token 静态校验，返回告警（dict 列表）。"""
    from auto_translator.glossary import Glossary, load_glossary_csv
    from auto_translator.glossary.csv_io import load_terminology_exemptions
    from auto_translator.review import g0_unit_flags

    cfg = config or Config()
    glossary = Glossary(load_glossary_csv(store.analysis_dir / "glossary.csv"))
    exemptions = load_terminology_exemptions(store.preprocessing_dir / "terminology_exemptions.csv")
    from .preprocess.artifacts import read_style_exemptions

    style_exemptions = read_style_exemptions(store)
    flags: list[dict[str, Any]] = []
    pub = store.load_publication()
    for unit in pub.units:
        rows = read_align(store.unit_align_path(unit.id))
        if not rows and not _qa_requires_align(store, unit):
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
            structured_md=structured_md,
            translation_md=translation_md,
            **_g0_thresholds(cfg),
            exempt_sources=exemptions.get(unit.id, {}),
            language_exempt=style_exemptions.get(unit.id, []),
            source_language=pub.meta.language or "auto",
            target_language=pub.meta.target_language or "zh-CN",
        ):
            flags.append(_flag_dict(unit.id, f))
        for f in _unit_doc_flags(store, rel_path) if rel_path else []:
            flags.append(_flag_dict(unit.id, f))
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
    optional = ["nav"]
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
        if reader.fieldnames is None or list(reader.fieldnames) not in (
            list(required),
            list(required) + optional,
        ):
            raise OrchestrationError(
                f"structure.csv 列契约不符（要求 {','.join(required)}"
                f"[+可选 {','.join(optional)}]）：{path}"
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
            nav_cell = (
                (row.get("nav") or "").strip().lower() if "nav" in (reader.fieldnames or []) else ""
            )
            if nav_cell and nav_cell not in ("yes", "no", "true", "false", "1", "0"):
                raise OrchestrationError(
                    f"structure.csv 第 {lineno} 行 nav 非法（yes/no）：{nav_cell!r}"
                )
            rows.append(
                {
                    "id": uid,
                    "region": region,
                    "kind": kind,
                    "title": title,
                    "level": level,
                    "rel_path": rel,
                    "nav": nav_cell not in ("no", "false", "0"),
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
        if r.get("nav") is False:
            meta["nav"] = False
        else:
            meta.pop("nav", None)
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
                and ((prior.meta or {}).get("nav", True) is not False)
                == (r.get("nav") is not False)
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

    from .qa.notes_audit import epub_render_mode

    pub = store.load_publication()
    epub = Path(epub_path) if epub_path else store.output_dir / f"{pub.slug}.epub"
    if not epub.is_file():
        raise OrchestrationError(f"成品不存在：{epub}；请先 build/convert")
    jar = (config.qc.epubcheck.jar or None) if config is not None else None
    epubcheck = run_epubcheck(epub, jar_path=jar)
    nav_depth = config.output.nav_depth if config is not None else Config().output.nav_depth
    entries = structure_entries(store)
    mode = epub_render_mode(epub)
    render_inputs = _render_inputs(store, entries, mode=mode or "translation")
    # N 阶段成品注释门（N5）：独立解析成品 XHTML 对账已登记注释；未登记则跳过
    # 构建模式取自成品 OPF；逐注文的实际宿主计划同时约束译注绑定与期望文本。
    notes_audit_dict: dict[str, Any] | None = None
    try:
        if pub.notes and mode is None:
            raise OrchestrationError("成品缺少有效 aep:render-mode，须重新 build/convert")
        notes_ctx = _load_notes_context(
            store,
            pub,
            entries=entries,
            render_inputs=render_inputs if pub.notes else None,
        )
    except OrchestrationError as e:
        notes_audit_dict = {
            "findings": [{"level": "error", "code": "E_NOTES_STALE", "message": str(e)}],
            "missing": ["stale"],
            "orphan": [],
        }
        notes_ctx = None
    if notes_ctx is not None:
        notes_result = audit_notes_epub(
            epub,
            source_notes=notes_ctx["data"],
            target_notes=notes_ctx.get("target"),
            media_root=store.structured_dir / "raw" / "media",
        )
        notes_audit_dict = {
            "findings": [dict(f) for f in notes_result.findings],
            "missing": list(notes_result.missing),
            "orphan": list(notes_result.orphan),
        }
    # 已核证且未过期的登记图将旧注释计数/必须有回链判据移交独立产品门。
    notes_registered = notes_ctx is not None
    provenance = audit_provenance(
        store,
        entries,
        epub,
        nav_depth=nav_depth,
        prefer_translation=mode != "source",
        notes_registered=notes_registered,
    )
    audit = audit_epub(
        epub,
        nav_exempt=set(provenance.nav_exempt),
        notes_registered=notes_registered,
        notes_context={
            f"OEBPS/{slug_file(entry['id'])}.xhtml": {
                "unit": str(entry["id"]),
                "kind": str(entry.get("kind", "")),
                "markdown": render_inputs[str(entry["id"])]["markdown"],
                "input_path": (
                    "translation"
                    if render_inputs[str(entry["id"])]["source"] == "translation"
                    else "structured"
                )
                + "/"
                + str(entry["rel_path"]),
            }
            for entry in entries
            if str(entry["id"]) in render_inputs
        },
    )
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
        notes_audit=notes_audit_dict,
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
    # 统一为同一文件引用；保留符号链接，后续重定向也必须使报告失效。
    epub_location = epub.absolute()
    try:
        recorded_epub = str(epub_location.relative_to(store.dir.absolute()))
    except ValueError:
        recorded_epub = str(epub_location)
    # 相对 store.dir 的引用只拼接一次；摘要与保存值必须使用同一口径。
    report.artifacts_digest = artifacts_digest(store, epub_path=recorded_epub)
    report.artifacts_epub = recorded_epub
    store.save_qa(report.to_dict())
    return report.to_dict()


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


def _flag_dict(unit_id: str, f: Any) -> dict[str, Any]:
    """G0Flag → 机器可读 dict（含 ``blocking``：advisory/硬门的统一判据，B 组真值表）。"""
    return {
        "unit": unit_id,
        "check": f.check,
        "message": f.message,
        "data": f.data,
        "blocking": bool(getattr(f, "blocking", True)),
    }


def _notes_next_task(store: RunStore, pub: Any) -> dict[str, Any] | None:
    """N 阶段前置注释任务（零 token 纯对账）：候选未决 / 未登记 / 摘要失效。

    只在书里**确实出现注文候选**时进入注释流程（否则无注书不增加步骤）；
    候选文件缺失时现算一次（只读，不落盘）。
    """
    from . import notes as notes_mod

    cands = notes_mod.read_candidates(notes_mod.candidates_path(store))
    src_notes = notes_mod.source_notes_path(store)
    if not cands and not src_notes.is_file() and not pub.notes:
        md_by_unit: dict[str, str] = {}
        for u in pub.units:
            rel = (u.meta or {}).get("rel_path")
            p = store.structured_dir / rel if rel else None
            if p is not None and p.is_file():
                md_by_unit[u.id] = p.read_text(encoding="utf-8")
        cands = notes_mod.extract_candidates(md_by_unit)
    if cands:
        pending = [c for c in cands if c.get("disposition") not in notes_mod.CANDIDATE_DISPOSITIONS]
        if pending:
            return _task(
                "notes_verify",
                f"核证注释候选：{len(pending)} 条未决（回看源件后写 disposition=note|not_note；"
                "判 note 的须绑定稳定身份：引用型候选写 ref_id、注文型候选写 note_id，"
                "并把这些注文/引用写入 structured/notes.json）",
                done_when={"file": "preprocessing/note_candidates.jsonl"},
            )
        if not pub.notes:
            return _task(
                "notes_register",
                "候选已全部处置：写 structured/notes.json（注文/引用/正文原位标记）并运行 notes register",
                done_when={"cmd": "notes register"},
            )
    if pub.notes:
        digest = notes_mod.file_digest(src_notes) if src_notes.is_file() else None
        if not digest or str(pub.notes.get("source_notes_sha256") or "") != digest:
            return _task(
                "notes_register",
                "structured/notes.json 已变更：重跑 notes register（必要时重译受影响注文）",
                done_when={"cmd": "notes register"},
            )
        return None
    if src_notes.is_file():
        return _task(
            "notes_register",
            "运行 notes register 登记已核证的 structured/notes.json",
            done_when={"cmd": "notes register"},
        )
    return None


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
    # B2. 注释结构化（N 阶段）：候选未决 / 未登记 / 摘要失效 → 先于分析与翻译
    notes_task = _notes_next_task(store, pub)
    if notes_task is not None:
        return [notes_task]
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
    #    P2：`report`/`notes`/`catalog` 是**伪 stale 项**（不是真实单元）——按 stale 类型
    #    分派 build/qa/notes register/catalog 修复，绝不可路由成 `import --unit report`
    #    （否则执行后同一任务持续返回）。
    _unit_ids = {u.id for u in pub.units}
    for s in stale:
        if s["id"] == "preprocessing":
            continue
        reason = str(s.get("reason") or "")
        if s["id"] not in _unit_ids:
            if reason == "report_stale":
                return [
                    _task(
                        "build", "报告证据已过期：重建 EPUB（build）", done_when={"cmd": "build"}
                    ),
                    _task(
                        "qa",
                        "重建后重跑 qa（放行结论须对应当前产物）",
                        done_when={"cmd": "qa"},
                    ),
                ]
            if reason == "notes_changed_since_register":
                return [
                    _task(
                        "notes_register",
                        "注释登记已失效：重跑 notes register（必要时重译受影响注文）",
                        done_when={"cmd": "notes register"},
                    )
                ]
            if reason == "catalog_binding_broken":
                return [
                    _task(
                        "repair",
                        "源盘点 included 项未绑定单元：修 preprocessing/catalog.csv",
                        done_when={"file": "preprocessing/catalog.csv"},
                    )
                ]
            continue  # 未知伪项：不当作真实单元 import
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


def _is_tool_tree(d: Path) -> bool:
    """是否是 CLI 自身的仓库/开发树（其 ``template/publication.json`` 是脚手架）。

    工作根内常放一份工具仓库副本（``<base>/auto-epublizer/``，见 #33 现场布局），
    其中的 ``template/`` 会被递归扫描误当工作区，使台账多出 ``sample-volume-*``
    一类脚手架条目并虚增单元/词数。
    """
    return (d / "pyproject.toml").is_file() and (d / "src" / "auto_epublizer").is_dir()


def status_all(base_dir: str | Path) -> list[dict[str, Any]]:
    """多工作区总览（issue #32）：扫描 base_dir 下的 auto-epublizer 工作区。

    每项给出机器可重算字段：slug/title/units_total/unit_status/words、
    ``has_report``、``released``/``released_reason``、``facts_created_at``，以及
    三档进度 ``progress``（released / built_not_released / preprocessing）——
    呼应 #32 的「进度三档口径」，免得文档层与 CLI 层各造一套词。

    **布局容错**（R0，2026-10-05 现场核对）：真实工作区常嵌套一层
    （``<base>/<slug>/book/publication.json``），故递归查找（限深 3、跳过隐藏目录）；
    并按 ``schema_version`` 过滤，跳过同目录下别的工具的工作区（如 ``epub-builder``）。
    """
    from datetime import datetime

    from auto_common.workspace.models import SCHEMA_VERSION

    base = Path(base_dir).resolve()
    rows: list[dict[str, Any]] = []
    if not base.is_dir():
        return rows
    for pub_file in sorted(base.rglob("publication.json")):
        try:
            rel = pub_file.relative_to(base)
        except ValueError:
            continue
        if len(rel.parts) - 1 > 3 or any(p.startswith(".") for p in rel.parts[:-1]):
            continue
        ws = pub_file.parent
        # 跳过 CLI 自身仓库树（issue #33）：base 自身若是仓库（用户在仓库内扫描）不跳过，
        # 保持原行为；只排除嵌套在工作根里的工具目录副本。
        if any(p != base and _is_tool_tree(p) for p in ws.parents):
            continue
        try:
            pub = read_json(pub_file)
        except (OSError, ValueError):
            continue
        if pub.get("schema_version") != SCHEMA_VERSION:
            continue  # 跳过其它工具的工作区（epub-builder/v1alpha1 等）
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
        report_stale = False
        if report_path.is_file():
            report_info = report_state(RunStore(ws))
            report_stale = bool(report_info["stale"])
            progress = (
                "released"
                if (report_info["released"] and not report_stale)
                else "built_not_released"
            )
        else:
            progress = "preprocessing"
        published_slug = pub.get("slug")
        # 嵌套布局：<base>/<slug>/book/publication.json 的 slug 常被写成 "book"，
        # 故优先取 base 下的一级目录名做标签，避免同名歧义（R0）。
        fallback_slug = rel.parts[0] if rel.parts else ws.name
        slug = published_slug if published_slug and published_slug != "book" else fallback_slug
        rows.append(
            {
                "slug": slug,
                "title": (pub.get("meta") or {}).get("title", ""),
                "units_total": len(units),
                "unit_status": counts,
                "words": ((facts.get("structure") or {}).get("totals") or {}).get("words"),
                "has_report": report_path.is_file(),
                "released": report.get("released"),
                "released_reason": report.get("released_reason"),
                "report_stale": report_stale,
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

    def cell(value: object) -> str:
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("|", "\\|")
            .replace("\r", " ")
            .replace("\n", " ")
        )

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
            f"| {cell(r['slug'])} | {cell(r['title'])} | {created} | {r['progress']} | "
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
    # B2 报告失效对账：报告声称 released 但产物已变 → 过期（不得当当前证据）
    report_info = report_state(store)
    if report_info["stale"]:
        stale.append({"id": "report", "status": "stale", "reason": "report_stale"})
    # N 阶段注释登记对账（只读）：摘要、失效与候选未决
    notes_state = notes_status(store)
    if notes_state["stale"]:
        stale.append({"id": "notes", "status": "stale", "reason": "notes_changed_since_register"})
    data = {
        "slug": pub.slug,
        "title": pub.meta.title,
        "target_language": pub.meta.target_language,
        "units_total": len(pub.units),
        "units": units_out,
        "has_preprocessing": has_preprocessing,
        "preprocessing_complete": preprocessing_complete,
        "catalog": catalog,
        "notes": notes_state,
        "report": report_info,
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
