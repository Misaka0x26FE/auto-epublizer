# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""只读质量证据；不登记状态、不重跑 QA、不生成语义验收结论。"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from auto_common.markdown import inline_code_chunks, markdown_chunks
from auto_common.workspace import RunStore
from auto_translator.review.fidelity import fidelity_flags
from auto_translator.review.g0 import md_align_drift
from auto_translator.translation.align import read_align

from .build import slug_file
from .media_paths import epub_member_path
from .qa.artifacts import report_state
from .qa.notes_audit import _norm_md, audit_notes_epub
from .qa.provenance import audit_provenance

RULE_VERSION = "quality-evidence-1"
_EPUB = "{http://www.idpf.org/2007/ops}"


def validate_workspace_paths(store: RunStore) -> None:
    """在读取工作区声明的正文路径前拒绝越界/符号链接逃逸。"""
    pub = store.load_publication()
    pairs = [(store.dir / pub.meta.source, store.source_dir)] if pub.meta.source else []
    for unit in pub.units:
        rel = str((unit.meta or {}).get("rel_path") or "")
        if rel:
            pairs.extend(
                (base / rel, base) for base in (store.structured_dir, store.translation_dir)
            )
        pairs.append((store.unit_align_path(unit.id), store.translation_dir / "align"))
    pairs.extend(
        (base / "notes.json", base) for base in (store.structured_dir, store.translation_dir)
    )
    pairs.extend(
        (store.dir / rel, store.dir)
        for rel in (
            "report.json",
            "analysis/glossary.csv",
            "analysis/glossary_conflicts.jsonl",
            "analysis/style.md",
            "preprocessing/facts.json",
            "preprocessing/catalog.csv",
            "preprocessing/repairs.jsonl",
            "preprocessing/note_candidates.jsonl",
            "preprocessing/style_exemptions.csv",
            "preprocessing/terminology_exemptions.csv",
        )
    )
    for path, base in pairs:
        if not path.resolve().is_relative_to(base.resolve()) or path.resolve() == base.resolve():
            raise ValueError(f"证据路径越出允许目录：{path.name}")


def _without_markers(md: str) -> str:
    return "".join(
        "".join(
            part if code else re.sub(r"\[\^[^\]\s]+\]", "", part)
            for code, part in inline_code_chunks(chunk)
        )
        if kind == "text"
        else chunk
        for kind, chunk in markdown_chunks(md)
    )


def _body_text(node: ET.Element) -> str:
    tag = node.tag.rsplit("}", 1)[-1]
    types = set(node.get(_EPUB + "type", "").split())
    classes = set(node.get("class", "").split())
    if (
        tag in {"head", "script", "style"}
        or types & {"footnote", "endnote", "noteref", "footnotes"}
        or classes & {"software-provenance", "noteref"}
    ):
        return ""
    return (node.text or "") + "".join(_body_text(child) + (child.tail or "") for child in node)


def _package_documents(zf: zipfile.ZipFile) -> tuple[str, list[str]]:
    container = ET.fromstring(zf.read("META-INF/container.xml"))
    opf_path = next(n.attrib["full-path"] for n in container.iter() if n.tag.endswith("}rootfile"))
    opf = ET.fromstring(zf.read(opf_path))
    items = {
        n.get("id"): epub_member_path(opf_path, n.get("href", ""))
        for n in opf.iter()
        if n.tag.endswith("}item")
    }
    return opf_path, [
        items[n.get("idref")]
        for n in opf.iter()
        if n.tag.endswith("}itemref") and items.get(n.get("idref"))
    ]


def collect_quality_evidence(
    store: RunStore,
    entries: list[dict[str, Any]],
    render_inputs: dict[str, dict[str, Any]],
    *,
    epub: Path,
    notes_context: dict[str, Any] | None,
    notes_error: str | None = None,
    external_source: Path | None = None,
    copies: list[Path] | None = None,
) -> dict[str, Any]:
    """从当前文件与成品重做机械对账；所有缺证/人工事项显式输出。"""
    pub = store.load_publication()
    checks: list[dict[str, Any]] = []
    hashes: dict[str, str | None] = {}

    def digest(path: Path, key: str) -> str | None:
        value = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        hashes[key] = value
        return value

    def add(identity: str, status: str, scope: str, **evidence: Any) -> None:
        checks.append(
            {"id": identity, "status": status, "scope": scope, "mode": "redo", "evidence": evidence}
        )

    source_hash = digest(store.dir / pub.meta.source, "source") if pub.meta.source else None
    add(
        "source_identity",
        "pass" if source_hash and source_hash == pub.meta.source_sha256 else "fail",
        "actual source bytes vs registration",
        actual=source_hash,
        registered=pub.meta.source_sha256,
    )
    external_hash = (
        digest(external_source, "external_source") if external_source is not None else None
    )
    add(
        "external_source",
        "unknown"
        if external_source is None
        else ("pass" if external_hash and external_hash == source_hash else "fail"),
        "explicit external source only",
        actual=external_hash,
    )
    epub_hash = digest(epub, "epub")
    digest(store.publication_path, "publication")
    digest(store.report_path, "qa_report")
    for name in (
        "structured/notes.json",
        "translation/notes.json",
        "preprocessing/note_candidates.jsonl",
    ):
        digest(store.dir / name, name)
    if store.report_path.is_file():
        try:
            old = json.loads(store.report_path.read_text(encoding="utf-8"))
            if not isinstance(old, dict):
                raise ValueError("report 顶层不是对象")
            state = report_state(store)
            registered_epub = Path(old.get("artifacts_epub") or "")
            if not registered_epub.is_absolute():
                registered_epub = store.dir / registered_epub
            if registered_epub.absolute() != epub.absolute():
                state = {**state, "stale": True, "reason": "different_product"}
            add(
                "qa_report_binding",
                "fail" if state.get("stale") else ("pass" if state.get("released") else "unknown"),
                "existing QA report freshness, not content acceptance",
                state=state,
            )
        except ValueError as exc:
            add("qa_report_binding", "fail", "existing QA report", error=str(exc))
    else:
        add("qa_report_binding", "unknown", "no QA report; evidence does not run checker")

    try:
        if not epub_hash:
            raise ValueError("缺少实际 EPUB 文件")
        with zipfile.ZipFile(epub) as zf:
            opf_path, spine = _package_documents(zf)
            for entry in entries:
                uid = str(entry["id"])
                rel = str(entry.get("rel_path") or "")
                for region in ("structured", "translation"):
                    if rel:
                        digest(store.dir / region / rel, f"{region}:{uid}")
                align_path = store.unit_align_path(uid)
                digest(align_path, f"align:{uid}")
                rows = read_align(align_path)
                if rows and (store.structured_dir / rel).is_file():
                    findings = fidelity_flags(
                        (store.structured_dir / rel).read_text(encoding="utf-8"), rows
                    )
                    status = (
                        "fail"
                        if any(f.blocking for f in findings)
                        else ("manual" if findings else "pass")
                    )
                    add(
                        f"align_source:{uid}",
                        status,
                        uid,
                        findings=[
                            {"check": f.check, "message": f.message, "data": f.data}
                            for f in findings
                        ],
                    )
                else:
                    add(
                        f"align_source:{uid}",
                        "unknown",
                        uid,
                        reason="align or structured document missing",
                    )
                target_path = store.translation_dir / rel
                if rows and target_path.is_file():
                    drift = md_align_drift(target_path.read_text(encoding="utf-8"), rows)
                    add(
                        f"md_align:{uid}",
                        "fail" if drift else "pass",
                        uid,
                        findings=drift,
                        rows=len(rows),
                    )
                else:
                    add(
                        f"md_align:{uid}",
                        "unknown",
                        uid,
                        reason="not applicable to source-only output or align missing",
                    )
                selected = render_inputs.get(uid)
                if not selected:
                    add(f"epub_body:{uid}", "unknown", uid, reason="unit has no render input")
                    continue
                member = epub_member_path(opf_path, slug_file(uid) + ".xhtml")
                if member not in spine:
                    add(
                        f"epub_body:{uid}",
                        "fail",
                        uid,
                        reason="unit not in actual spine",
                        member=member,
                    )
                    continue
                root = ET.fromstring(zf.read(member))
                body = root.find("{*}body")
                if body is None:
                    add(f"epub_body:{uid}", "fail", uid, reason="missing body")
                    continue
                heading = body.find("{*}h1")
                if heading is not None:
                    body.remove(heading)
                actual = re.sub(r"\s+", "", _body_text(body))
                md = re.sub(r"\A\s*# [^\n]*(?:\n|$)", "", selected["markdown"], count=1)
                expected = _norm_md(_without_markers(md))
                # 空串不能靠包含测试或 H1 命中冒充完整正文；有据纯标题单元可零对零。
                add(
                    f"epub_body:{uid}",
                    "pass" if expected == actual else "fail",
                    uid,
                    source=selected["source"],
                    expected_chars=len(expected),
                    actual_chars=len(actual),
                    expected_sha256=hashlib.sha256(expected.encode()).hexdigest(),
                    actual_sha256=hashlib.sha256(actual.encode()).hexdigest(),
                )
        provenance = audit_provenance(
            store,
            entries,
            epub,
            prefer_translation=any(v["source"] == "translation" for v in render_inputs.values()),
            notes_registered=bool(notes_context),
        )
        add(
            "package_provenance",
            "pass" if provenance.ok else "fail",
            "mechanical package/units/media/navigation",
            findings=provenance.findings,
        )
    except (OSError, ValueError, KeyError, StopIteration, zipfile.BadZipFile, ET.ParseError) as exc:
        add("epub_read", "fail", "actual package", error=str(exc))
    if notes_error:
        add("registered_notes", "fail", "registered set only", error=notes_error)
    elif notes_context and epub_hash:
        result = audit_notes_epub(
            epub,
            source_notes=notes_context["data"],
            target_notes=notes_context.get("target"),
            media_root=store.structured_dir / "raw" / "media",
        )
        add(
            "registered_notes",
            "pass" if result.ok else "fail",
            "registered set only; not source inventory",
            notes=len(notes_context["data"].get("notes") or []),
            findings=result.findings,
        )
    else:
        add("registered_notes", "unknown", "no registered inventory or product")
    for index, path in enumerate(copies or [], start=1):
        value = digest(path, f"copy:{index}")
        add(
            f"copy:{index}",
            "pass" if value and epub_hash and value == epub_hash else "fail",
            "explicit expected artifact copy",
            sha256=value,
        )
    if not copies:
        add("copies", "unknown", "no expected copies supplied")
    add(
        "source_note_inventory",
        "manual",
        "source pages, note tails and unregistered notes require independent review",
    )
    add(
        "semantic_acceptance",
        "manual",
        "names/index columns/source TOC and page readability not machine-certified",
    )
    payload = {"rules": RULE_VERSION, "hashes": hashes, "checks": checks}
    return {
        "schema_version": "1",
        "rule_version": RULE_VERSION,
        "input_digest": hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
        "input_hashes": hashes,
        "checks": checks,
    }
