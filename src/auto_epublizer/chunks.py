# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""分块作业暂存（D1/D2）：导出、按序拼回与覆盖对账。

chunk 不是第二份译文权威：它只是 ``preprocessing/chunks/<unit>/`` 下的作业暂存。
正式产物仍是 ``translation/<rel>.md`` 与 ``translation/align/<unit>.jsonl``；
assemble 通过预检后一次事务写入两者，失败按日志恢复旧版本。

块身份 = ``unit + 序号 + 源摘要``：源文改动会让导出失效；已存在的译文分块不被
重导出覆盖；译文块数量/顺序/摘要与索引不符时拒绝拼回。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from auto_common.workspace import RunStore

SCHEMA_VERSION = 1
RULE_VERSION = "chunk-1"
DEFAULT_MAX_CHARS = 4000
_FENCE = re.compile(r"^(```|~~~)")


def chunk_root(store: RunStore) -> Path:
    return store.preprocessing_dir / "chunks"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_blocks(md: str) -> list[str]:
    """按空行切块，围栏代码块内部不切；保留块内原始文本。"""
    blocks: list[str] = []
    current: list[str] = []
    fenced = False
    for line in md.splitlines():
        if _FENCE.match(line.strip()):
            fenced = not fenced
        if not fenced and not line.strip():
            if current:
                blocks.append("\n".join(current).strip("\n"))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current).strip("\n"))
    return [b for b in blocks if b.strip()]


def _group(blocks: list[str], max_chars: int) -> list[list[str]]:
    groups: list[list[str]] = []
    current: list[str] = []
    size = 0
    for block in blocks:
        if current and size + len(block) > max_chars:
            groups.append(current)
            current, size = [], 0
        current.append(block)
        size += len(block)
    if current:
        groups.append(current)
    return groups


def _unit_rel(store: RunStore, unit_id: str) -> str:
    for entry in store.load_publication().units:
        if entry.id == unit_id:
            rel = str(entry.meta.get("rel_path") or "")
            if rel:
                return rel
    raise ValueError(f"单元不存在或缺 rel_path：{unit_id}")


def export_chunks(
    store: RunStore, *, unit_ids: list[str] | None = None, max_chars: int = DEFAULT_MAX_CHARS
) -> dict[str, Any]:
    """导出分块暂存；已有译文分块保留，不覆盖。"""
    if max_chars < 200:
        raise ValueError("max_chars 至少 200")
    root = chunk_root(store)
    exported: list[dict[str, Any]] = []
    for unit_id in unit_ids or [u.id for u in store.load_publication().units]:
        rel = _unit_rel(store, unit_id)
        source_path = store.structured_dir / rel
        if not source_path.is_file():
            raise ValueError(f"源单元文件不存在：{rel}")
        md = source_path.read_text(encoding="utf-8")
        source_digest = _digest(md)
        unit_dir = root / unit_id
        index_path = unit_dir / "index.json"
        if index_path.is_file():
            try:
                prior = json.loads(index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                prior = {}
            if prior.get("source_sha256") and prior["source_sha256"] != source_digest:
                raise ValueError(
                    f"源文已变更，分块索引拒绝静默改写：{unit_id}（先运行 "
                    f"chunk reset --unit {unit_id} --apply 归档旧分块，再重新导出）"
                )
            if prior.get("max_chars") != max_chars or prior.get("rule_version") != RULE_VERSION:
                raise ValueError(
                    f"分块参数/规则版本已变化，索引拒绝静默改写：{unit_id}（先运行 "
                    f"chunk reset --unit {unit_id} --apply）"
                )
        blocks = split_blocks(md)
        chunks: list[dict[str, Any]] = []
        kept = 0
        for seq, group in enumerate(_group(blocks, max_chars), start=1):
            text = "\n\n".join(group) + "\n"
            name = f"{seq:04d}.md"
            path = unit_dir / name
            if path.is_file():
                kept += 1  # 已有分块（含已译作业）不覆盖
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            chunks.append(
                {
                    "seq": seq,
                    "chunk_id": f"{unit_id}-{seq:04d}",
                    "file": name,
                    "translation_file": f"{seq:04d}.zh.md",
                    "source_sha256": _digest(text),
                    "chars": len(text),
                    "blocks": len(group),
                }
            )
        index = {
            "schema": SCHEMA_VERSION,
            "rule_version": RULE_VERSION,
            "unit": unit_id,
            "source_rel": rel,
            "source_sha256": _digest(md),
            "max_chars": max_chars,
            "chunks": chunks,
        }
        unit_dir.mkdir(parents=True, exist_ok=True)
        tmp = index_path.with_name(index_path.name + ".tmp")
        tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, index_path)
        exported.append(
            {"unit": unit_id, "chunks": len(chunks), "path": str(index_path), "kept": kept}
        )
    return {"units": exported, "root": str(root)}


def _safe_rel(value: Any) -> str:
    pure = PurePosixPath(str(value or ""))
    if not str(value or "").strip() or pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"分块索引路径非法：{value!r}")
    return pure.as_posix()


def _safe_name(value: Any) -> str:
    text = str(value or "")
    if not text or "/" in text or "\\" in text or text in {".", ".."}:
        raise ValueError(f"分块文件名非法：{value!r}")
    return text


def _load_index(store: RunStore, unit_id: str) -> dict[str, Any]:
    unit_id = _safe_name(unit_id)
    path = chunk_root(store) / unit_id / "index.json"
    if not path.is_file():
        raise ValueError(f"分块索引不存在：{path}（先运行 chunk export）")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
        raise ValueError("分块索引 schema 不是 1")
    if data.get("rule_version") != RULE_VERSION:
        raise ValueError(f"分块索引规则版本不是 {RULE_VERSION}（需重新导出）")
    data["source_rel"] = _safe_rel(data.get("source_rel"))
    for chunk in data.get("chunks") or []:
        if not isinstance(chunk, dict):
            raise ValueError("分块索引 chunks 元素不是对象")
        chunk["file"] = _safe_name(chunk.get("file"))
        chunk["translation_file"] = _safe_name(chunk.get("translation_file"))
    return data


def _heading_line(md: str) -> str | None:
    for line in md.splitlines():
        if line.startswith("# "):
            return line
    return None


def _align_text(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def assemble_unit(
    store: RunStore, unit_id: str, *, apply: bool = False, force: bool = False
) -> dict[str, Any]:
    """预检并拼回正式 translation/align；默认只读，``apply=True`` 才事务写入。

    正式译文已存在且与新拼回内容不同时拒绝覆盖（先核对/备份，确需覆盖用 ``force``）。
    """
    unit_id = _safe_name(unit_id)
    index = _load_index(store, unit_id)
    rel = str(index.get("source_rel") or "")
    source_path = store.structured_dir / rel
    if not source_path.is_file():
        raise ValueError(f"源单元文件不存在：{rel}")
    source_md = source_path.read_text(encoding="utf-8")
    if _digest(source_md) != index.get("source_sha256"):
        raise ValueError(f"源文已变更：{unit_id}（重新导出分块再翻译）")

    unit_dir = chunk_root(store) / unit_id
    source_blocks_by_seq: dict[int, list[str]] = {}
    for chunk in index.get("chunks") or []:
        seq = int(chunk["seq"])
        chunk_path = unit_dir / str(chunk["file"])
        if not chunk_path.is_file():
            raise ValueError(f"分块缺文件：{chunk_path}")
        text = chunk_path.read_text(encoding="utf-8")
        if _digest(text) != chunk.get("source_sha256"):
            raise ValueError(f"分块内容与索引不符：{chunk_path}")
        source_blocks_by_seq[seq] = split_blocks(text)

    translated_blocks: list[str] = []
    align_rows: list[dict[str, Any]] = []
    seq_counter = 0
    heading_seen = False
    for chunk in index.get("chunks") or []:
        seq = int(chunk["seq"])
        tpath = unit_dir / str(chunk["translation_file"])
        if not tpath.is_file():
            raise ValueError(f"缺译文分块：{tpath}")
        t_text = tpath.read_text(encoding="utf-8")
        t_blocks = split_blocks(t_text)
        s_blocks = source_blocks_by_seq[seq]
        if len(t_blocks) != len(s_blocks):
            raise ValueError(
                f"{chunk['chunk_id']} 块数不一致：源 {len(s_blocks)} / 译 {len(t_blocks)}"
            )
        for s_block, t_block in zip(s_blocks, t_blocks, strict=True):
            translated_blocks.append(t_block)
            if s_block.lstrip().startswith("#"):
                heading_seen = True
                continue  # 标题由单元首行承载，不进 align
            seq_counter += 1
            align_rows.append(
                {
                    "seq": seq_counter,
                    "src": s_block,
                    "tgt": t_block,
                    "note": None,
                }
            )
    if not translated_blocks:
        raise ValueError(f"单元没有可拼回的内容：{unit_id}")
    if not heading_seen:
        raise ValueError(f"译文缺单元标题行（# …）：{unit_id}")

    md_text = "\n\n".join(translated_blocks).rstrip() + "\n"
    align_path = store.translation_dir / "align" / f"{unit_id}.jsonl"
    tgt_path = store.translation_dir / rel
    preview = {
        "unit": unit_id,
        "rel_path": rel,
        "chunks": len(index.get("chunks") or []),
        "blocks": len(translated_blocks),
        "align_rows": len(align_rows),
        "translation": str(tgt_path),
        "align": str(align_path),
        "applied": False,
    }
    if not apply:
        return preview

    tgt_path = store.translation_dir / rel
    if not force:
        conflicts: list[str] = []
        if tgt_path.is_file():
            existing_md = tgt_path.read_text(encoding="utf-8")
            if existing_md != md_text:
                conflicts.append(str(tgt_path))
        if align_path.is_file():
            existing_align = align_path.read_text(encoding="utf-8")
            if existing_align != _align_text(align_rows):
                conflicts.append(str(align_path))
        if conflicts:
            raise ValueError(
                "正式译文/对照表已有新编辑，分块拼回拒绝覆盖："
                + "、".join(conflicts)
                + "（核对后用 --force）"
            )
    journal_path = _write_journal(store, unit_id, tgt_path, align_path)
    try:
        _atomic_write(tgt_path, md_text.encode("utf-8"))
        align_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_align = align_path.with_name(align_path.name + ".tmp")
        tmp_align.write_text(_align_text(align_rows), encoding="utf-8")
        os.replace(tmp_align, align_path)
    except BaseException:
        _restore_journal(store, journal_path)
        raise
    _close_journal(store, journal_path)
    store.log_event("chunk_assembled", unit=unit_id, chunks=preview["chunks"])
    return {**preview, "applied": True}


def _journal_dir(store: RunStore) -> Path:
    return store.preprocessing_dir / "chunk-transactions"


def _journal_rel(store: RunStore, path: Path) -> str:
    try:
        return path.resolve().relative_to(store.dir.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _write_journal(store: RunStore, unit_id: str, tgt: Path, align: Path) -> Path:
    journal_dir = _journal_dir(store)
    journal_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 1,
        "id": uuid.uuid4().hex,
        "unit": unit_id,
        "status": "pending",
        "files": [
            {
                "path": _journal_rel(store, path),
                "existed": path.is_file(),
                "old": base64.b64encode(path.read_bytes()).decode("ascii")
                if path.is_file()
                else "",
            }
            for path in (tgt, align)
        ],
    }
    path = journal_dir / f"{payload['id']}.json"
    _atomic_write(path, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return path


def _close_journal(store: RunStore, path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["status"] = "applied"
    _atomic_write(path, json.dumps(data, ensure_ascii=False).encode("utf-8"))


def _restore_journal(store: RunStore, path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    translation_root = store.translation_dir.resolve()
    errors: list[str] = []
    for item in data.get("files") or []:
        raw = Path(str(item.get("path") or ""))
        target = (store.dir / raw if not raw.is_absolute() else raw).resolve()
        if not target.is_relative_to(translation_root):
            errors.append(f"事务日志指向工作区译文目录之外，已拒绝：{raw}")
            continue
        if item.get("existed"):
            _atomic_write(target, base64.b64decode(str(item.get("old") or "")))
        else:
            target.unlink(missing_ok=True)
    data["status"] = "rolled_back"
    _atomic_write(path, json.dumps(data, ensure_ascii=False).encode("utf-8"))
    return errors


def reset_unit(store: RunStore, unit_id: str, *, apply: bool = False) -> dict[str, Any]:
    """归档某单元旧分块（源文变更后显式重置）；默认只预览目标目录。"""
    unit_id = _safe_name(unit_id)
    unit_dir = chunk_root(store) / unit_id
    if not unit_dir.is_dir():
        raise ValueError(f"分块目录不存在：{unit_dir}")
    index_path = unit_dir / "index.json"
    digest = ""
    if index_path.is_file():
        try:
            digest = str(
                json.loads(index_path.read_text(encoding="utf-8")).get("source_sha256") or ""
            )
        except json.JSONDecodeError:
            digest = ""
    target = unit_dir.with_name(f"{unit_id}.stale-{(digest or 'unknown')[:8]}")
    if target.exists():
        target = unit_dir.with_name(
            f"{unit_id}.stale-{(digest or 'unknown')[:8]}-{uuid.uuid4().hex[:6]}"
        )
    if apply:
        os.replace(unit_dir, target)
        store.log_event("chunk_reset", unit=unit_id, archived=str(target))
    return {"unit": unit_id, "source": str(unit_dir), "target": str(target), "apply": apply}


def import_tr(store: RunStore, source_root: str | Path, *, apply: bool = False) -> dict[str, Any]:
    """把旧 ``.tr/<unit>/NNN.zh.md`` 显式导入分块暂存（不猜、不覆盖已有译文）。

    只在分块索引已存在且文件数与块数一致时导入；默认只预检。
    """
    root = Path(source_root)
    if not root.is_dir():
        raise ValueError(f".tr 目录不存在：{root}")
    units: list[dict[str, Any]] = []
    for unit_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        unit_id = _safe_name(unit_dir.name)
        index = _load_index(store, unit_id)
        files = sorted(unit_dir.glob("*.zh.md"))
        expected = len(index.get("chunks") or [])
        if len(files) != expected:
            raise ValueError(f"{unit_id} 的 .tr 文件数 {len(files)} 与分块数 {expected} 不一致")
        for chunk, path in zip(index["chunks"], files, strict=True):
            target = chunk_root(store) / unit_id / str(chunk["translation_file"])
            units.append(
                {
                    "unit": unit_id,
                    "source": str(path),
                    "target": str(target),
                    "overwrites": target.exists(),
                }
            )
    if apply:
        for row in units:
            target = Path(row["target"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(Path(row["source"]).read_bytes())
    return {"apply": apply, "files": len(units), "units": units}


def recover_chunks(store: RunStore) -> dict[str, Any]:
    """恢复未完成的分块事务（pending）；坏日志报错而非静默跳过。"""
    restored: list[str] = []
    errors: list[str] = []
    for path in sorted(_journal_dir(store).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if data.get("status") != "pending":
            continue
        errors.extend(_restore_journal(store, path))
        restored.append(str(data.get("unit") or path.stem))
    return {"restored": restored, "errors": errors}


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
