# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""对照表重建的显式应用事务（B4）。

默认完全只读（dry-run）；``apply=True`` 才写入，并且：

- 计划绑定源件摘要、每个单元的 translation/align 基线摘要；预检后文件变化即拒绝；
- 全量预检（seq 连续、md↔align 文本一致、源保真反向不通过则阻断）在写盘前完成；
- 先持久化含旧字节的事务日志，再逐文件替换；任一失败按日志恢复旧件；
- 成功后重新登记 ``meta.align_structure`` 与导入摘要，并把 reviewed/built 回退到
  aligned（旧审校/成品结论随摘要失效）。

这不是多文件瞬时原子：日志与目标分步落盘，恢复是显式入口（与 safe_repair 同族）。
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from auto_common.workspace import RunStore, atomic_write_json
from auto_translator.review import (
    align_block_spans,
    fidelity_flags,
    md_align_drift,
    structure_digest,
)
from auto_translator.translation.align import write_align

RULE_VERSION = "align-rebuild-1"
_CLOSED = {"applied", "rolled_back"}
_OPEN = {"pending", "rollback_incomplete"}


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _journal_dir(store: RunStore) -> Path:
    return store.preprocessing_dir / "align-rebuild-transactions"


def _read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("对照表重建事务必须是 JSON 对象")
    return data


def _rows_payload(rows: list[dict[str, Any]]) -> bytes:
    import tempfile

    handle, name = tempfile.mkstemp(suffix=".jsonl")
    os.close(handle)
    tmp = Path(name)
    try:
        write_align(tmp, rows)
        return tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)


def _shape(plan: dict[str, Any]) -> None:
    if set(plan) != {"schema_version", "rule_version", "source_sha256", "units"}:
        raise ValueError("重建计划字段缺失或含未知列")
    if plan["schema_version"] != "1" or plan["rule_version"] != RULE_VERSION:
        raise ValueError("重建工具/规则版本不匹配")


def _unit_plan(store: RunStore, entry: dict[str, Any]) -> dict[str, Any]:
    if set(entry) != {
        "unit",
        "translation_sha256",
        "align_sha256",
        "rows",
        "approved",
    }:
        raise ValueError("重建单元字段缺失或含未知列")
    if entry["approved"] is not True:
        raise ValueError(f"重建单元未明确批准：{entry.get('unit')}")
    unit = store.load_publication().unit(str(entry["unit"]))
    if unit is None:
        raise ValueError(f"单元不存在：{entry['unit']}")
    rel = (unit.meta or {}).get("rel_path")
    if not rel:
        raise ValueError(f"单元缺 rel_path：{unit.id}")
    tgt_path = store.translation_dir / str(rel)
    if not tgt_path.is_file():
        raise ValueError(f"缺少译文文件：{tgt_path}")
    tgt_bytes = tgt_path.read_bytes()
    if _hash(tgt_bytes) != entry["translation_sha256"]:
        raise ValueError(f"译文基线已变更：{unit.id}")
    align_path = store.unit_align_path(unit.id)
    current_align = align_path.read_bytes() if align_path.is_file() else b""
    rows = entry["rows"]
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"对照表为空：{unit.id}")
    seqs = [int(row.get("seq") or 0) for row in rows]
    if seqs != list(range(1, len(rows) + 1)):
        raise ValueError(f"seq 不连续：{unit.id}")
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("src") or "").strip():
            raise ValueError(f"存在空原文：{unit.id}")
        if not str(row.get("tgt") or "").strip():
            raise ValueError(f"存在空译文：{unit.id}")
    md = tgt_bytes.decode("utf-8")
    drift = md_align_drift(md, rows, title=unit.title)
    if drift:
        raise ValueError(f"译文与对照表不一致：{unit.id}：{drift[0]}")
    structured_path = store.structured_dir / str(rel)
    if not structured_path.is_file():
        raise ValueError(f"缺少结构化源文，无法核对对照表：{unit.id}")
    blocking = [
        flag
        for flag in fidelity_flags(structured_path.read_text(encoding="utf-8"), rows)
        if flag.blocking
    ]
    if blocking:
        raise ValueError(f"对照表 src 不在源文中：{unit.id}：{blocking[0].message}")
    spans, issues = align_block_spans(md, rows, title=unit.title)
    if issues:
        raise ValueError(f"块身份无法确定：{unit.id}：{issues[0]}")
    new_bytes = _rows_payload(rows)
    new_digest = structure_digest(spans)
    baseline = (unit.meta or {}).get("align_structure")
    if align_path.is_file() and current_align == new_bytes and baseline == new_digest:
        status = "already_applied"
    else:
        # 只有确实需要写入时才要求旧基线仍匹配：成功后用原计划重试应幂等。
        if entry["align_sha256"] is not None and _hash(current_align) != entry["align_sha256"]:
            raise ValueError(f"对照表基线已变更：{unit.id}")
        status = "pending"
    return {
        "unit": unit.id,
        "path": align_path.relative_to(store.dir).as_posix(),
        "before": current_align,
        "after": new_bytes,
        "old_sha256": _hash(current_align),
        "new_sha256": _hash(new_bytes),
        "align_structure": new_digest,
        "status": status,
    }


def _persist(path: Path, journal: dict[str, Any]) -> None:
    atomic_write_json(path, journal)


def _replace(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.rebuild")
    try:
        with tmp.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _open_journals(store: RunStore) -> list[Path]:
    directory = _journal_dir(store)
    if not directory.is_dir():
        return []
    result = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = _read(path)
        except (ValueError, OSError):
            result.append(path)
            continue
        if str(data.get("status")) in _OPEN:
            result.append(path)
    return result


def assert_no_pending_align(store: RunStore) -> None:
    """存在未决重对齐事务时，普通写操作必须停下等显式恢复。"""
    if _open_journals(store):
        raise ValueError("存在未决重对齐事务；请先运行 align-apply --recover 或 repair recover")


def _restore_journal(store: RunStore, path: Path, journal: dict[str, Any]) -> list[str]:
    """按日志恢复文件与单元登记；返回失败项（空=全部恢复）。"""
    errors: list[str] = []
    files = journal.get("files") or []
    for item in files:
        target = store.dir / str(item.get("path") or "")
        try:
            if not target.is_file():
                errors.append(f"{item.get('unit')}:文件缺失")
                continue
            current = _hash(target.read_bytes())
            if current == item.get("new_sha256"):
                _replace(target, bytes.fromhex(str(item.get("before") or "")))
            elif current != item.get("old_sha256"):
                errors.append(f"{item.get('unit')}:文件已被他人改动")
        except (OSError, ValueError):
            errors.append(f"{item.get('unit')}:文件恢复失败")
    for item in reversed(files):
        status_before = item.get("status_before")
        meta_before = item.get("meta_before")
        if status_before is None or meta_before is None:
            continue
        try:
            store.restore_unit_registration(
                str(item.get("unit")), status=str(status_before), meta=meta_before
            )
        except (OSError, ValueError):
            errors.append(f"{item.get('unit')}:状态恢复失败")
    return errors


def recover_align_rebuild(store: RunStore) -> dict[str, Any]:
    """显式恢复中断/未完成的重对齐事务（repair recover 与 align-apply --recover 共用）。"""
    with store.run_lock():
        paths = _open_journals(store)
        incomplete: list[str] = []
        for path in paths:
            journal = _read(path)
            errors = _restore_journal(store, path, journal)
            journal["status"] = "rolled_back" if not errors else "rollback_incomplete"
            journal["restore_errors"] = errors
            _persist(path, journal)
            if errors:
                incomplete.append(path.name)
    if not paths:
        return {"status": "nothing_to_recover", "transactions": 0}
    if incomplete:
        return {"status": "incomplete", "transactions": len(paths), "incomplete": incomplete}
    return {"status": "recovered", "transactions": len(paths)}


def apply_align_rebuild(
    store: RunStore, plan: dict[str, Any], *, apply: bool = False
) -> dict[str, Any]:
    """默认只读预检；``apply=True`` 时写日志、替换并登记新基线。"""
    _shape(plan)
    pub = store.load_publication()
    if plan["source_sha256"] != pub.meta.source_sha256:
        raise ValueError("重建源件身份不匹配")
    units = plan["units"]
    if not isinstance(units, list) or not units:
        raise ValueError("重建计划没有单元")
    prepared = [_unit_plan(store, entry) for entry in units]
    identity = _hash(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode())
    journal_path = _journal_dir(store) / f"{identity}.json"
    if all(item["status"] == "already_applied" for item in prepared):
        return {"status": "already_applied", "plan_sha256": identity}
    if not apply:
        return {
            "status": "dry_run",
            "plan_sha256": identity,
            "units": [
                {
                    "unit": item["unit"],
                    "path": item["path"],
                    "align_structure": item["align_structure"],
                    "old_sha256": item["old_sha256"],
                    "new_sha256": item["new_sha256"],
                }
                for item in prepared
            ],
        }
    with store.run_lock():
        assert_no_pending_align(store)
        prepared = [_unit_plan(store, entry) for entry in units]
        snapshot_pub = store.load_publication()
        snapshots = {
            unit.id: {
                "status": unit.status,
                "meta": json.loads(json.dumps(unit.meta or {})),
            }
            for unit in snapshot_pub.units
        }
        journal = {
            "rule_version": RULE_VERSION,
            "plan_sha256": identity,
            "status": "pending",
            "files": [
                {
                    "path": item["path"],
                    "unit": item["unit"],
                    "status_before": snapshots.get(item["unit"], {}).get("status"),
                    "meta_before": snapshots.get(item["unit"], {}).get("meta"),
                    "before": item["before"].hex(),
                    "old_sha256": item["old_sha256"],
                    "new_sha256": item["new_sha256"],
                    "align_structure": item["align_structure"],
                }
                for item in prepared
            ],
        }
        _journal_dir(store).mkdir(parents=True, exist_ok=True)
        _persist(journal_path, journal)
        try:
            for item in prepared:
                path = store.dir / item["path"]
                if _hash(path.read_bytes()) != item["old_sha256"]:
                    raise ValueError("预检后文件发生变化，拒绝覆盖")
                _replace(path, item["after"])
            for item in prepared:
                unit = store.load_publication().unit(item["unit"])
                if unit is None:
                    continue
                if unit.status in ("reviewed", "built"):
                    store.set_unit_status(unit.id, "aligned")
                store.record_unit_content(unit.id, align_structure=item["align_structure"])
            journal["status"] = "applied"
            _persist(journal_path, journal)
        except Exception as exc:
            errors = _restore_journal(store, journal_path, journal)
            journal["status"] = "rolled_back" if not errors else "rollback_incomplete"
            journal["restore_errors"] = errors
            _persist(journal_path, journal)
            if errors:
                raise ValueError(
                    "回滚未完成，事务保持未决；请修复故障后运行 align-apply --recover："
                    f"{exc}；失败项：{'、'.join(errors)}"
                ) from None
            raise ValueError(f"对照表重建失败，已回滚：{exc}") from None
    return {
        "status": "applied",
        "plan_sha256": identity,
        "units": [item["unit"] for item in prepared],
    }
