# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""注释结构化与绑定（N 阶段）：``notes.json`` 契约、候选盘点与确定性校验。

**职责边界**（单 LLM 原则）：本模块只做确定性计算——提取候选、校验契约、算摘要；
注文边界与引用关系的**语义核证由 agent 完成**（写 ``structured/notes.json`` 与正文
原位标记），CLI 只登记、搬运、渲染与对账。

权威产物（N2）：

- ``structured/notes.json``：源注文 + 源引用与定位证据的**权威**；
- ``translation/notes.json``：以相同 ``note_id`` 保存完整译注（不复制源引用/位置）；
- 正文 Markdown 只保留原位标记 ``[^ref-000123]``（标记即 ``ref_id``，不编码显示号）；
- ``publication.json.notes``：CLI 写入的登记摘要（agent 不手改官方状态）。

盘点结论三态（N1）：``present``（有注且已核证）/ ``none``（经核证无注）/
``unverified``（尚未核证）。``none`` 是核证结论而非「检测数为零」。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from auto_common.markdown import inline_code_chunks, markdown_chunks

SCHEMA_VERSION = "1"

# 原位标记：``[^ref-000123]``（标记文本即 ref_id；生成器保证身份稳定、不重排）
MARKER_RE = re.compile(r"\[\^(ref-\d{6,})\]")
_ID_RE = re.compile(r"^(?:n|ref)-\d{6,}$")
_NOTE_ID_RE = re.compile(r"^n-\d{6,}$")
_REF_ID_RE = re.compile(r"^ref-\d{6,}$")

INVENTORY_STATES = ("present", "none", "unverified")
NOTE_STATUSES = ("verified", "unresolved")
CANDIDATE_KINDS = ("marker", "pandoc_ref", "definition", "numbered_paragraph")
CANDIDATE_DISPOSITIONS = ("note", "not_note")

# 注文集中排版：行首 `241 Kubetzky, Drütte-Prozeß.`（数字 + 空白；不含 `1.` 列表形态）
_NUMBERED_PARA_RE = re.compile(r"^(\d{1,3})\s+(\S.*)$")
_PANDOC_DEF_RE = re.compile(r"^\[\^([^\]\s]+)\]:", re.MULTILINE)
# 旧记法 pandoc 行内引用 `[^label]`（``ref-`` 前缀的已是原位标记，跳过）
_PANDOC_REF_RE = re.compile(r"\[\^([^\]\s]+)\]")

_MAX_CANDIDATE_TEXT = 200


def extract_candidates(md_by_unit: dict[str, str]) -> list[dict[str, Any]]:
    """确定性候选盘点（N1）：从结构化正文提取注文/引用候选 + 定位证据。

    四类高精度候选（宁少勿滥；每条由 agent 核证后标 disposition）：

    - ``marker``：句末/上标/括号式注码（复用 auto_translator 的注号识别，含负对照）；
    - ``pandoc_ref``：旧记法行内引用 ``[^label]``；
    - ``definition``：pandoc 定义行 ``[^label]:``；
    - ``numbered_paragraph``：行首「数字 + 空白」的注文式段落（集中注文典型形态）。

    候选身份由 ``unit|kind|label|text``（重复出现加序号）哈希得出，**不含行号**：
    在别处插入内容后重跑，已有处置不丢。只读取，不修改结构化正文。
    """
    from auto_translator.review.g0 import footnote_numbers

    seen: dict[tuple[str, str, str, str], int] = {}
    out: list[dict[str, Any]] = []

    def _emit(unit: str, kind: str, label: str, lineno: int, text: str) -> None:
        head = text[:_MAX_CANDIDATE_TEXT]
        key = (unit, kind, label, head)
        occ = seen.get(key, 0)
        seen[key] = occ + 1
        cid = "c-" + hashlib.sha1(f"{unit}|{kind}|{label}|{head}|{occ}".encode()).hexdigest()[:10]
        out.append(
            {
                "candidate_id": cid,
                "unit": unit,
                "kind": kind,
                "label": label,
                "line": lineno,
                "text": head,
                "disposition": None,
            }
        )

    for unit, md in sorted(md_by_unit.items()):
        visible = "".join(
            "".join(
                "".join("\n" if c == "\n" else " " for c in text) if code else text
                for code, text in inline_code_chunks(chunk)
            )
            if kind == "text"
            else "".join("\n" if c == "\n" else " " for c in chunk)
            for kind, chunk in markdown_chunks(md or "")
        )
        for lineno, line in enumerate(visible.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            for num in sorted(footnote_numbers(stripped)):
                _emit(unit, "marker", str(num), lineno, stripped)
            for m in _PANDOC_REF_RE.finditer(stripped):
                label = m.group(1)
                if _REF_ID_RE.match(label):
                    continue  # 已是原位标记（稳定身份），不是候选
                _emit(unit, "pandoc_ref", label, lineno, stripped)
            m_def = _PANDOC_DEF_RE.match(stripped)
            if m_def:
                _emit(unit, "definition", m_def.group(1), lineno, stripped)
            m_num = _NUMBERED_PARA_RE.match(stripped)
            if m_num and len(m_num.group(2)) >= 8:
                _emit(unit, "numbered_paragraph", m_num.group(1), lineno, stripped)
    return out


class NotesError(ValueError):
    """notes.json / 候选文件的契约违例（可预期错误，中文消息）。"""


def source_notes_path(store: Any) -> Path:
    return store.structured_dir / "notes.json"


def translation_notes_path(store: Any) -> Path:
    return store.translation_dir / "notes.json"


def candidates_path(store: Any) -> Path:
    return store.preprocessing_dir / "note_candidates.jsonl"


def file_digest(path: str | Path) -> str:
    """文件内容摘要（sha256 hex）；文件不存在抛 NotesError。"""
    p = Path(path)
    if not p.is_file():
        raise NotesError(f"文件不存在：{p}")
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_notes_json(path: str | Path) -> dict[str, Any]:
    """读 notes.json；不存在或非法 JSON 时给出中文错误。"""
    p = Path(path)
    if not p.is_file():
        raise NotesError(f"注释文件不存在：{p}（先按 references/notes.md 核证并写入）")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise NotesError(f"注释文件不是合法 JSON：{p}（{e}）") from None
    if not isinstance(data, dict):
        raise NotesError(f"注释文件顶层必须是对象：{p}")
    return data


def extract_markers(md_text: str) -> list[str]:
    """按出现顺序提取正文原位标记；围栏和行内代码字面量不是引用。"""
    return [
        rid
        for kind, chunk in markdown_chunks(md_text or "")
        if kind == "text"
        for code, text in inline_code_chunks(chunk)
        if not code
        for rid in MARKER_RE.findall(text)
    ]


def _digest_of_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_str(v: Any) -> bool:
    return isinstance(v, str)


def validate_source_notes(
    data: dict[str, Any],
    *,
    source_sha256: str | None,
    unit_ids: set[str],
) -> list[str]:
    """校验 ``structured/notes.json``（分离登记门）；返回中文错误清单（空=通过）。

    正文原位标记 ↔ 引用的双向对账由 :func:`validate_markers_vs_references` 单独执行
    （调用方在标记已落地时调用）。
    """
    errors: list[str] = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {SCHEMA_VERSION!r}：{data.get('schema_version')!r}")
    stored_hash = str(data.get("source_sha256") or "")
    if source_sha256 and stored_hash and stored_hash != source_sha256:
        errors.append("source_sha256 与 publication.json 不一致（源文件已变更，须重新核证）")
    if not stored_hash:
        errors.append("缺 source_sha256（绑定源内容身份，防同名换内容）")
    inventory = data.get("inventory")
    if inventory not in INVENTORY_STATES:
        errors.append(f"inventory 必须是 {INVENTORY_STATES} 之一：{inventory!r}")

    notes = data.get("notes")
    references = data.get("references")
    if not isinstance(notes, list):
        errors.append("notes 必须是数组")
        notes = []
    if not isinstance(references, list):
        errors.append("references 必须是数组")
        references = []
    if inventory == "none" and (notes or references):
        errors.append("inventory=none（经核证无注）时 notes/references 必须为空")
    if inventory == "present" and not notes:
        errors.append("inventory=present 时 notes 不得为空")

    note_ids: set[str] = set()
    labels: set[tuple[str, str]] = set()  # (scope_id, source_label) 供重复注号提示
    orphan_notes: list[str] = []
    for i, n in enumerate(notes):
        where = f"notes[{i}]"
        if not isinstance(n, dict):
            errors.append(f"{where} 必须是对象")
            continue
        nid = str(n.get("note_id") or "")
        if not _NOTE_ID_RE.match(nid):
            errors.append(f"{where}.note_id 格式非法（应形如 n-000123）：{nid!r}")
        elif nid in note_ids:
            errors.append(f"{where}.note_id 重复：{nid}")
        else:
            note_ids.add(nid)
        scope = str(n.get("scope_id") or "")
        if not scope:
            errors.append(f"{where}.scope_id 不得为空（须经来源确认的章/节）")
        label = str(n.get("source_label") or "").strip()
        if not label:
            errors.append(f"{where}.source_label 不得为空（原书显示号）")
        # 渲染数字号会转成整数；01/1、全角数字与 ASCII 不得变成同一显示号。
        key = (scope, str(int(label)) if label.isdecimal() and int(label) > 0 else label)
        if key in labels:
            # 同作用域同号是复制粘贴痕迹；跨作用域同号合法（各章重号）
            errors.append(f"{where} 与已有注文同作用域同注号（scope={scope}, label={label}）")
        labels.add(key)
        if not str(n.get("source_markdown") or "").strip():
            errors.append(f"{where}.source_markdown 不得为空（完整源注文）")
        locs = n.get("source_locations")
        if not isinstance(locs, list) or not locs:
            errors.append(f"{where}.source_locations 不得为空（注文自身位置的证据）")
        status = str(n.get("status") or "")
        if status not in NOTE_STATUSES:
            errors.append(f"{where}.status 必须是 {NOTE_STATUSES} 之一：{status!r}")
        elif status == "unresolved":
            errors.append(f"{where}.status=unresolved：未决注文不得登记（须先核证或标记非注）")
        if not str(n.get("note_type") or ""):
            errors.append(f"{where}.note_type 不得为空（footnote/endnote/sidenote…）")

    ref_ids: set[str] = set()
    referenced_notes: set[str] = set()
    refs_by_unit: dict[str, list[dict[str, Any]]] = {}
    for i, r in enumerate(references):
        where = f"references[{i}]"
        if not isinstance(r, dict):
            errors.append(f"{where} 必须是对象")
            continue
        rid = str(r.get("ref_id") or "")
        if not _REF_ID_RE.match(rid):
            errors.append(f"{where}.ref_id 格式非法（应形如 ref-000123）：{rid!r}")
        elif rid in ref_ids:
            errors.append(f"{where}.ref_id 重复：{rid}")
        else:
            ref_ids.add(rid)
        nid = str(r.get("note_id") or "")
        if nid not in note_ids:
            errors.append(f"{where}.note_id 未在 notes 中登记：{nid!r}")
        else:
            referenced_notes.add(nid)
        unit = str(r.get("unit") or "")
        if unit not in unit_ids:
            errors.append(f"{where}.unit 不是 publication.json 中的单元：{unit!r}")
        else:
            refs_by_unit.setdefault(unit, []).append(r)
        if not str(r.get("scope_id") or ""):
            errors.append(f"{where}.scope_id 不得为空（注号作用域）")
        if r.get("status") not in NOTE_STATUSES:
            errors.append(f"{where}.status 必须是 {NOTE_STATUSES} 之一：{r.get('status')!r}")

    for n in notes:
        if isinstance(n, dict):
            nid = str(n.get("note_id") or "")
            if nid and nid not in referenced_notes and not n.get("orphan_ok"):
                orphan_notes.append(nid)
    if orphan_notes:
        errors.append(
            "以下注文没有任何引用；确属原书未引用注文时须在条目上显式 orphan_ok=true 并写"
            f" orphan_reason：{'、'.join(sorted(orphan_notes)[:8])}"
        )
    return errors


def validate_markers_vs_references(
    md_by_unit: dict[str, str],
    references: list[dict[str, Any]],
) -> list[str]:
    """正文原位标记 ↔ 已登记引用 双向对账（翻译导入门/登记门的共用判据）。

    每个引用在**其单元正文**中必须恰好出现一次；正文中不得出现未登记的标记。
    同一 ref_id 在多处引用应拆成多条 references（每条独立 ref_id），故「恰好一次」
    不与「一注多引」冲突。
    """
    errors: list[str] = []
    per_unit_refs: dict[str, list[str]] = {}
    for r in references:
        if isinstance(r, dict) and r.get("unit"):
            per_unit_refs.setdefault(str(r["unit"]), []).append(str(r.get("ref_id") or ""))
    for unit, md in sorted(md_by_unit.items()):
        found = extract_markers(md)
        want = per_unit_refs.get(unit, [])
        want_set, found_set = set(want), set(found)
        missing = sorted(want_set - found_set)
        unknown = sorted(found_set - want_set)
        for rid in missing:
            errors.append(f"{unit}：正文缺原位标记 [^{rid}]（引用丢失）")
        for rid in unknown:
            errors.append(f"{unit}：正文出现未登记的标记 [^{rid}]")
        for rid in want_set & found_set:
            n = found.count(rid)
            if n != 1:
                errors.append(f"{unit}：标记 [^{rid}] 出现 {n} 次（应恰好 1 次）")
    for unit in sorted(set(per_unit_refs) - set(md_by_unit)):
        for rid in sorted(set(per_unit_refs[unit])):
            errors.append(f"{unit}：引用 {rid} 所在单元缺结构化正文")
    return errors


def validate_translation_notes(
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    source_notes_digest: str,
    required_note_ids: set[str] | None = None,
) -> list[str]:
    """校验 ``translation/notes.json``（翻译导入门的一部分）。

    ``required_note_ids``：当前批次必须齐全的注文（按已翻译单元引用推导）；
    其余注文允许暂缺（未翻译完的书）。
    """
    errors: list[str] = []
    if target.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"译注 schema_version 必须是 {SCHEMA_VERSION!r}")
    if str(target.get("source_notes_sha256") or "") != source_notes_digest:
        errors.append("译注绑定的源注文摘要不符（structured/notes.json 已变更，须重译受影响注文）")
    src_ids = {
        str(n.get("note_id"))
        for n in (source.get("notes") or [])
        if isinstance(n, dict) and n.get("note_id")
    }
    tgt_notes = target.get("notes")
    if not isinstance(tgt_notes, list):
        errors.append("译注 notes 必须是数组")
        return errors
    seen: set[str] = set()
    provided: set[str] = set()
    for i, t in enumerate(tgt_notes):
        where = f"译注 notes[{i}]"
        if not isinstance(t, dict):
            errors.append(f"{where} 必须是对象")
            continue
        nid = str(t.get("note_id") or "")
        if not _NOTE_ID_RE.match(nid):
            errors.append(f"{where}.note_id 格式非法：{nid!r}")
        elif nid in seen:
            errors.append(f"{where}.note_id 重复：{nid}")
        else:
            seen.add(nid)
        if nid not in src_ids:
            errors.append(f"{where}.note_id 不在源注文中：{nid!r}")
        if not str(t.get("target_markdown") or "").strip():
            errors.append(f"{where}.target_markdown 不得为空（完整译注）")
        else:
            provided.add(nid)
    if required_note_ids is not None:
        missing = sorted(required_note_ids - provided)
        if missing:
            errors.append(f"以下注文缺完整译注（{len(missing)} 条）：{'、'.join(missing[:8])}")
    return errors


def validate_candidates(data_lines: list[dict[str, Any]]) -> list[str]:
    """候选盘点核证完整性：每条候选必须有明确处置（note/not_note），未决不得开始翻译。"""
    errors: list[str] = []
    unresolved: list[str] = []
    for i, row in enumerate(data_lines):
        cid = str(row.get("candidate_id") or f"candidates[{i}]")
        disp = row.get("disposition")
        if disp not in CANDIDATE_DISPOSITIONS:
            unresolved.append(cid)
    if unresolved:
        errors.append(
            f"注释候选未全部处置（{len(unresolved)} 条未决）：{'、'.join(unresolved[:8])}"
            "；每条候选须标 disposition=note|not_note 并写核证依据"
        )
    return errors


def _cand_binding(row: dict[str, Any]) -> tuple[str, str]:
    """候选上的稳定身份绑定：返回 (kind, id)。kind ∈ {"ref","note",""}。"""
    nid = str(row.get("note_id") or "").strip()
    rid = str(row.get("ref_id") or "").strip()
    if rid:
        return "ref", rid
    if nid:
        return "note", nid
    return "", ""


# 引用型候选（正文注号出现处）→ ref_id；注文型候选（注文文本）→ note_id
_REF_KINDS = ("marker", "pandoc_ref")
_NOTE_KINDS = ("definition", "numbered_paragraph")


def validate_candidates_vs_graph(
    candidates: list[dict[str, Any]],
    source_notes: dict[str, Any],
) -> list[str]:
    """按稳定身份及注文位置证据对账，不按同号或文本前缀猜配。

    引用候选必须绑定同单元的独立引用；注文候选必须在绑定注文的位置表中
    留有 candidate_id 证据。跨页多位置、跨单元尾注及合法孤儿注均可绑定。
    """
    note_cands = [c for c in candidates if str(c.get("disposition") or "") == "note"]
    if not note_cands:
        return []
    inventory = str(source_notes.get("inventory") or "")
    if inventory == "none":
        return [
            f"已核证 {len(note_cands)} 条候选为 note，与 inventory=none 矛盾："
            "须登记 present（建注文/引用图）或把这些候选改判 not_note"
        ]
    if inventory != "present":
        return []
    notes_by_id = {
        str(n.get("note_id")): n
        for n in (source_notes.get("notes") or [])
        if isinstance(n, dict) and n.get("note_id")
    }
    refs_by_id = {
        str(r.get("ref_id")): r
        for r in (source_notes.get("references") or [])
        if isinstance(r, dict) and r.get("ref_id")
    }
    errors: list[str] = []
    used: dict[str, str] = {}
    for c in note_cands:
        cid = str(c.get("candidate_id") or "?")
        unit = str(c.get("unit") or "")
        label = str(c.get("label") or "").strip()
        kind = str(c.get("kind") or "")
        where = f"{cid}（{unit}，注号 {label or '—'}，{kind}）"
        bind_kind, bind_id = _cand_binding(c)
        if kind in _REF_KINDS:
            if bind_kind != "ref":
                errors.append(f"{where} 缺少 ref_id 绑定：须写明候选对应的稳定引用 id")
                continue
            ref = refs_by_id.get(bind_id)
            if ref is None:
                errors.append(f"{where} 绑定的 ref_id 不在登记图中：{bind_id}")
                continue
            if str(ref.get("unit") or "") != unit:
                errors.append(
                    f"{where} 绑定的引用属于其它单元（{ref.get('unit')}）：跨章同号不得互相冒充"
                )
                continue
            ref_label = str(ref.get("label_text") or "").strip()
            if label and ref_label and label != ref_label:
                errors.append(f"{where} 与绑定引用注号不一致（引用为 {ref_label}）")
                continue
            if bind_id in used:
                errors.append(f"{where} 与 {used[bind_id]} 重复绑定同一引用 {bind_id}")
                continue
            used[bind_id] = cid
        elif kind in _NOTE_KINDS:
            if not str(c.get("candidate_id") or "").strip():
                errors.append(f"{where} 缺少 candidate_id：注文位置证据必须绑定真实候选身份")
                continue
            if bind_kind != "note":
                errors.append(f"{where} 缺少 note_id 绑定：须写明候选对应的稳定注文 id")
                continue
            note = notes_by_id.get(bind_id)
            if note is None:
                errors.append(f"{where} 绑定的 note_id 不在登记图中：{bind_id}")
                continue
            locations = [
                loc
                for loc in (note.get("source_locations") or [])
                if isinstance(loc, dict) and loc.get("candidate_id") == cid
            ]
            if not locations:
                errors.append(f"{where} 绑定注文缺少 candidate_id 位置证据：{bind_id}")
                continue
            if any(
                field in loc and loc[field] != c.get(field)
                for loc in locations
                for field in ("unit", "line")
            ):
                errors.append(f"{where} 绑定注文的位置证据与候选 unit/line 不一致：{bind_id}")
        else:
            errors.append(f"{where} 未知候选种类：{kind!r}")
    return errors


def read_candidates(path: str | Path) -> list[dict[str, Any]]:
    """读候选 JSONL（不存在返回空表）；坏行给出中文错误。"""
    p = Path(path)
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            raise NotesError(f"候选文件第 {i} 行不是合法 JSON：{p}") from None
        if isinstance(row, dict):
            out.append(row)
    return out


def registration_summary(data: dict[str, Any], digest: str) -> dict[str, Any]:
    """publication.json.notes 的登记摘要（内容摘要 + 计数，无时间戳 → 幂等）。"""
    notes = [n for n in (data.get("notes") or []) if isinstance(n, dict)]
    refs = [r for r in (data.get("references") or []) if isinstance(r, dict)]
    scopes = sorted({str(n.get("scope_id") or "") for n in notes if n.get("scope_id")})
    return {
        "schema_version": SCHEMA_VERSION,
        "source_notes_sha256": digest,
        "inventory": str(data.get("inventory") or ""),
        "notes": len(notes),
        "references": len(refs),
        "scopes": len(scopes),
    }


def note_requirements(
    source: dict[str, Any],
    *,
    unit_ids: set[str],
) -> dict[str, set[str]]:
    """按单元列出该单元引用到的 note_id 集合（判定译注是否必需）。"""
    out: dict[str, set[str]] = {}
    for r in source.get("references") or []:
        if isinstance(r, dict) and str(r.get("unit") or "") in unit_ids:
            out.setdefault(str(r["unit"]), set()).add(str(r.get("note_id") or ""))
    return out
