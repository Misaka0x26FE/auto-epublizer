# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""显式批准的精确替换：只读预检、持久备份、可恢复事务；非多文件瞬时原子。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from auto_common.markdown import inline_code_chunks, markdown_chunks
from auto_common.workspace import RunStore, atomic_write_json
from auto_translator.review.fidelity import fidelity_flags
from auto_translator.review.g0 import check_alignment, count_heading_levels, md_align_drift

RULE_VERSION = "safe-repair-1"
_CLOSED = {"applied", "rolled_back"}


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inside(store: RunStore, rel: str) -> Path:
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise ValueError("修复路径必须是工作区内相对路径")
    path = store.dir / rel
    if not path.resolve().is_relative_to(store.dir.resolve()) or any(
        p.is_symlink() for p in [path, *path.parents] if p != store.dir.parent
    ):
        raise ValueError(f"修复路径越界或含符号链接：{rel}")
    return path


def _directory(store: RunStore) -> Path:
    return _inside(store, "preprocessing/repair-transactions")


def _read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("修复事务/计划必须是 JSON 对象")
    return data


def assert_no_pending(store: RunStore) -> None:
    """未决事务禁止普通 CLI 继续；坏日志亦不能按不存在处理。"""
    for path in sorted(_directory(store).glob("*.json")):
        data = _read(_inside(store, path.relative_to(store.dir).as_posix()))
        if data.get("status") not in _CLOSED:
            raise ValueError("存在未决修复事务；请先运行 repair recover，不得继续普通处理")


def _allowed(store: RunStore) -> dict[str, str]:
    result = {}
    for unit in store.load_publication().units:
        rel = str(unit.meta.get("rel_path") or "")
        if rel:
            for region in ("structured", "translation"):
                result[f"{region}/{rel}"] = unit.id
            result[f"translation/align/{unit.id}.jsonl"] = unit.id
    return result


def _shape(value: Any, keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} 字段缺失或含未知列")


def _identity(store: RunStore, plan: dict[str, Any]) -> None:
    _shape(plan, {"schema_version", "rule_version", "source_sha256", "edits"}, "修复计划")
    if plan["schema_version"] != "1" or plan["rule_version"] != RULE_VERSION:
        raise ValueError("修复工具/规则版本不匹配")
    pub = store.load_publication()
    if (
        plan["source_sha256"] != pub.meta.source_sha256
        or _hash(_inside(store, pub.meta.source).read_bytes()) != plan["source_sha256"]
    ):
        raise ValueError("修复源件身份不匹配")


def _conservation(before: str, after: str, *, markdown: bool) -> None:
    # 保守边界：页码、标记和链接不得改；原词只允许保留/增加，不允许偷偷删除。
    for pattern in (
        r"\[\^[^\]]+\]",
        r"\{\{[^}]+\}\}",
        r"!?\[[^\]]*\]\([^)]*\)",
        r"\d+",
        r"<[^>]+>",
    ):
        if Counter(re.findall(pattern, before)) != Counter(re.findall(pattern, after)):
            raise ValueError("修复不得改变注码、插入标记、页码或链接")
    if Counter(re.findall(r"[A-Za-z]+", before)) - Counter(re.findall(r"[A-Za-z]+", after)):
        raise ValueError("修复不得删除原词；先保留原词并独立核证")
    if markdown and (
        count_heading_levels(before) != count_heading_levels(after)
        or [s for k, s in markdown_chunks(before) if k != "text"]
        != [s for k, s in markdown_chunks(after) if k != "text"]
    ):
        raise ValueError("修复不得改变标题层级或代码字面量")
    if markdown and [s for code, s in inline_code_chunks(before) if code] != [
        s for code, s in inline_code_chunks(after) if code
    ]:
        raise ValueError("修复不得改变行内代码字面量")


def _prepare(store: RunStore, plan: dict[str, Any]) -> list[dict[str, Any]]:
    _identity(store, plan)
    if not isinstance(plan["edits"], list) or not plan["edits"]:
        raise ValueError("修复清单不能为空")
    allowed = _allowed(store)
    rows = []
    seen = set()
    for edit in plan["edits"]:
        _shape(edit, {"unit", "path", "sha256", "old", "new", "approved", "evidence"}, "修复项")
        rel = edit["path"]
        path = _inside(store, rel)
        if rel not in allowed or allowed[rel] != edit["unit"] or rel in seen:
            raise ValueError("修复目标/单元身份不符或重复文件（每文件一条精确替换）")
        seen.add(rel)
        if edit["approved"] is not True:
            raise ValueError("修复项未明确批准")
        evidence = edit["evidence"]
        _shape(evidence, {"path", "sha256", "page"}, "源证据")
        ep = _inside(store, evidence["path"])
        if (
            type(evidence["page"]) is not int
            or evidence["page"] < 1
            or not ep.is_file()
            or _hash(ep.read_bytes()) != evidence["sha256"]
        ):
            raise ValueError("修复证据缺失或摘要/页码不符")
        before = path.read_bytes()
        text = before.decode("utf-8")
        old, new = edit["old"], edit["new"]
        if _hash(before) != edit["sha256"]:
            raise ValueError(f"修复基线已变更：{rel}")
        if (
            text.startswith("\ufeff")
            or not isinstance(old, str)
            or not isinstance(new, str)
            or not old
            or not new
            or old == new
            or text.count(old) != 1
        ):
            raise ValueError("修复须 UTF-8 无 BOM、非空且唯一精确旧字串，不允许歧义替换")
        after = text.replace(old, new, 1).encode("utf-8")
        _conservation(text, after.decode("utf-8"), markdown=path.suffix == ".md")
        rows.append(
            {
                "path": rel,
                "unit": edit["unit"],
                "before": before.hex(),
                "after": after.hex(),
                "old_sha256": _hash(before),
                "new_sha256": _hash(after),
            }
        )
    _validate_overlay(store, rows)
    return rows


def _validate_overlay(store: RunStore, rows: list[dict[str, Any]]) -> None:
    """整组内存候选核源保真和 md/align；不写临时工作区或出版状态。"""
    overlay = {r["path"]: bytes.fromhex(r["after"]).decode("utf-8") for r in rows}
    touched = {r["unit"] for r in rows}

    def text(rel: str) -> str | None:
        path = _inside(store, rel)
        return (
            overlay[rel]
            if rel in overlay
            else (path.read_text(encoding="utf-8") if path.is_file() else None)
        )

    for unit in store.load_publication().units:
        if unit.id not in touched:
            continue
        rel = str(unit.meta.get("rel_path") or "")
        source, target = text(f"structured/{rel}"), text(f"translation/{rel}")
        align = text(f"translation/align/{unit.id}.jsonl")
        if not source:
            raise ValueError("修复后源单元缺失或为空")
        if target is None and align is None:
            continue
        if not target or not align:
            raise ValueError("修复译文必须具有完整 md 与 align 配对")
        segments = [json.loads(line) for line in align.splitlines() if line.strip()]
        if not all(isinstance(r, dict) for r in segments):
            raise ValueError("align 行必须是对象")
        if not all(
            type(r.get("seq")) is int
            and isinstance(r.get("src"), str)
            and isinstance(r.get("tgt"), str)
            for r in segments
        ):
            raise ValueError("align 必须含整数 seq 与文本 src/tgt")
        flags = check_alignment(segments) + fidelity_flags(source, segments)
        if any(f.blocking for f in flags) or md_align_drift(target, segments):
            raise ValueError("修复全量预检失败：源保真或 md/align 漂移")


def _replace_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.repair")
    try:
        with tmp.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        _sync_directory(path.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def _journal_rows(store: RunStore, journal: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = _allowed(store)
    rows = journal.get("files")
    if not isinstance(rows, list) or not rows:
        raise ValueError("事务缺持久备份")
    seen = set()
    for row in rows:
        _shape(row, {"path", "unit", "before", "after", "old_sha256", "new_sha256"}, "事务文件")
        path = _inside(store, row["path"])
        if row["path"] not in allowed or allowed[row["path"]] != row["unit"] or row["path"] in seen:
            raise ValueError("事务目标不在当前单元中或重复")
        seen.add(row["path"])
        if (
            _hash(bytes.fromhex(row["before"])) != row["old_sha256"]
            or _hash(bytes.fromhex(row["after"])) != row["new_sha256"]
        ):
            raise ValueError("事务备份摘要不匹配")
        if not path.is_file() or _hash(path.read_bytes()) not in {
            row["old_sha256"],
            row["new_sha256"],
        }:
            raise ValueError("事务目标出现他人新改动，拒绝覆盖")
    return rows


def _sync_directory(path: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _persist(path: Path, journal: dict[str, Any]) -> None:
    atomic_write_json(path, journal)
    # 日志和目标的目录入口均落盘；不宣称跨文件原子可见。
    _sync_directory(path.parent)
    _sync_directory(path.parent.parent)


def _rollback(store: RunStore, path: Path, journal: dict[str, Any]) -> None:
    rows = _journal_rows(store, journal)  # 任何一个冲突即整组拒绝，无部分恢复。
    for row in rows:
        target = _inside(store, row["path"])
        if _hash(target.read_bytes()) != row["old_sha256"]:
            _replace_bytes(target, bytes.fromhex(row["before"]))
    journal["status"] = "rolled_back"
    _persist(path, journal)


def apply_plan(store: RunStore, plan: dict[str, Any], *, apply: bool = False) -> dict[str, Any]:
    """默认完全只读；实际写入先持久化含全部旧/新字节的事务日志。"""
    assert_no_pending(store)
    _identity(store, plan)
    identity = _hash(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode())
    journal_path = _directory(store) / f"{identity}.json"
    if journal_path.is_file():
        journal = _read(journal_path)
        if journal.get("plan_sha256") != identity or journal.get("rule_version") != RULE_VERSION:
            raise ValueError("事务身份/规则版本不匹配")
        if journal.get("status") == "applied":
            rows = _journal_rows(store, journal)
            if all(
                _hash(_inside(store, row["path"]).read_bytes()) == row["new_sha256"] for row in rows
            ):
                return {"status": "already_applied", "plan_sha256": identity}
            raise ValueError("已应用计划的文件已变化，不允许重放")
    rows = _prepare(store, plan)
    if not apply:
        return {"status": "dry_run", "plan_sha256": identity, "files": [r["path"] for r in rows]}
    with store.run_lock():
        assert_no_pending(store)
        rows = _prepare(store, plan)
        journal = {
            "rule_version": RULE_VERSION,
            "plan_sha256": identity,
            "status": "pending",
            "files": rows,
        }
        _persist(journal_path, journal)
        try:
            for row in rows:
                path = _inside(store, row["path"])
                if _hash(path.read_bytes()) != row["old_sha256"]:
                    raise ValueError("预检后文件发生变化，拒绝覆盖")
                _replace_bytes(path, bytes.fromhex(row["after"]))
            journal["status"] = "applied"
            _persist(journal_path, journal)
        except Exception as exc:
            try:
                journal["status"] = "pending"
                _persist(journal_path, journal)
                _rollback(store, journal_path, journal)
            except Exception as recovery_error:
                raise ValueError(f"修复失败且回滚未完成，保留未决事务：{recovery_error}") from exc
            raise ValueError(f"修复失败，已整组回滚：{exc}") from exc
    return {
        "status": "applied",
        "plan_sha256": identity,
        "next": "重新 import/notes register（按变更范围），build、qa 并独立交付审计",
    }


def recover(store: RunStore) -> dict[str, Any]:
    """显式恢复未决组；全量核当前仅为计划旧/新版本后回滚。"""
    with store.run_lock():
        pending = [(p, _read(p)) for p in sorted(_directory(store).glob("*.json"))]
        pending = [(p, j) for p, j in pending if j.get("status") not in _CLOSED]
        for _, journal in pending:
            _journal_rows(store, journal)
        for path, journal in pending:
            _rollback(store, path, journal)
    return {"status": "rolled_back" if pending else "no_pending", "transactions": len(pending)}
