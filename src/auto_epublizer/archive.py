# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""旧批次归档（F1/F2）：按 MANIFEST 身份/版本分组，默认只读预览。

身份只来自 ``MANIFEST.md`` 的显式字段（书名/作品/slug 与版本），不从目录名或
「终版」字样猜最新；缺版本、同版不同字节都列为未决。``.archive`` 中已有的同名
批次会被识别为已归档，避免重复打包。F1 只计算计划；写入/移动是 F2 的显式事务。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ARCHIVE_DIR = ".archive"
_BOOK_KEYS = ("书名", "作品", "书", "book", "title", "slug")
_VERSION_KEYS = ("版本", "version")
_BATCH_KEYS = ("批次", "batch")
_VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+)*)$", re.IGNORECASE)


def _parse_manifest(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 2:
            key, value = cells[0], cells[1]
        elif ":" in stripped or "：" in stripped:
            key, value = re.split(r"[:：]", stripped, maxsplit=1)
        else:
            continue
        key = key.strip().strip("*`# ")
        value = value.strip().strip("*`")
        if key and value:
            fields.setdefault(key, value)
    return fields


def _pick(fields: dict[str, str], keys: tuple[str, ...]) -> str | None:
    lowered = {key.casefold(): value for key, value in fields.items()}
    for key in keys:
        if key.casefold() in lowered:
            return lowered[key.casefold()]
    return None


def _version_key(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    match = _VERSION_RE.match(value.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


@dataclass(frozen=True)
class Batch:
    name: str
    path: Path
    book: str | None
    version: str | None
    version_key: tuple[int, ...] | None
    manifest_sha256: str
    artifacts_sha256: str
    errors: tuple[str, ...]

    def preview(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path.as_posix(),
            "book": self.book,
            "version": self.version,
            "manifest_sha256": self.manifest_sha256,
            "artifacts_sha256": self.artifacts_sha256,
            "errors": list(self.errors),
        }


def _artifacts_digest(path: Path) -> str:
    """批次产物字节身份（除 MANIFEST.md 外的全部文件，按相对路径排序）。"""
    digest = hashlib.sha256()
    files = sorted(
        (item for item in path.rglob("*") if item.is_file() and item.name != "MANIFEST.md"),
        key=lambda item: item.relative_to(path).as_posix(),
    )
    for item in files:
        digest.update(item.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(item.read_bytes()).hexdigest().encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _batch(path: Path) -> Batch:
    errors: list[str] = []
    manifest = path / "MANIFEST.md"
    if not manifest.is_file():
        return Batch(path.name, path, None, None, None, "", "", ("missing_manifest",))
    payload = manifest.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    fields = _parse_manifest(payload.decode("utf-8", "replace"))
    book = _pick(fields, _BOOK_KEYS)
    version = _pick(fields, _VERSION_KEYS)
    version_key = _version_key(version)
    if not book:
        errors.append("missing_book")
    if version is None:
        errors.append("missing_version")
    elif version_key is None:
        errors.append("unparseable_version")
    return Batch(
        path.name, path, book, version, version_key, digest, _artifacts_digest(path), tuple(errors)
    )


def _subdirs(root: Path, *, skip_archive: bool) -> list[Path]:
    if not root.is_dir():
        return []
    result = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.is_symlink():
            continue
        if skip_archive and path.name == ARCHIVE_DIR:
            continue
        result.append(path)
    return result


def plan_archive(outbox: str | Path) -> dict[str, Any]:
    """只读归档预览：按书身份分组，最高版本保留，其余待归档；不写文件。"""
    root = Path(outbox)
    if not root.is_dir():
        raise ValueError(f"outbox 目录不存在或不是目录：{root}")
    archived_dir = root / ARCHIVE_DIR
    if archived_dir.is_symlink():
        raise ValueError(f"归档目录不能是符号链接：{archived_dir}")
    current = [_batch(path) for path in _subdirs(root, skip_archive=True)]
    archived = [_batch(path) for path in _subdirs(archived_dir, skip_archive=False)]

    groups: dict[str, list[Batch]] = {}
    unresolved = []
    for batch in current:
        if batch.book is None or batch.version_key is None:
            unresolved.append({"batch": batch.preview(), "reason": ",".join(batch.errors)})
            continue
        groups.setdefault(batch.book, []).append(batch)

    keep: list[dict[str, Any]] = []
    move: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for book, batches in sorted(groups.items()):
        ordered = sorted(batches, key=lambda item: item.version_key or ())
        top = ordered[-1]
        same_top = [item for item in ordered if item.version_key == top.version_key]
        if len(same_top) > 1 and len({item.manifest_sha256 for item in same_top}) > 1:
            conflicts.append(
                {
                    "book": book,
                    "version": top.version,
                    "batches": [item.name for item in same_top],
                    "reason": "same_version_different_manifest",
                }
            )
            continue
        if len(same_top) > 1 and len({item.artifacts_sha256 for item in same_top}) > 1:
            conflicts.append(
                {
                    "book": book,
                    "version": top.version,
                    "batches": [item.name for item in same_top],
                    "reason": "same_version_different_artifacts",
                }
            )
            continue
        keep.append(top.preview())
        for batch in ordered:
            if batch is top:
                continue
            move.append(batch.preview())
    archived_keys = {
        (batch.book, batch.version_key): batch
        for batch in archived
        if batch.book and batch.version_key
    }
    already_archived = [
        {
            "batch": batch.preview(),
            "archived_path": archived_keys[(batch.book, batch.version_key)].path.as_posix(),
        }
        for batch in current
        if batch.book and (batch.book, batch.version_key) in archived_keys
    ]
    return {
        "schema_version": "1",
        "writes": False,
        "outbox": root.as_posix(),
        "archive": archived_dir.as_posix(),
        "current_total": len(current),
        "archived_total": len(archived),
        "keep": keep,
        "to_archive": move,
        "conflicts": conflicts,
        "unresolved": unresolved,
        "already_archived": already_archived,
        "note": "身份/版本只读 MANIFEST；缺版本或同版不同字节不猜最新，F1 不写任何文件",
    }


def _docs_dir(outbox: Path, docs_dir: str | Path | None) -> Path:
    return Path(docs_dir) if docs_dir else outbox.parent / "docs"


def _gitignore_path(gitignore: str | Path | None, outbox: Path) -> Path:
    return Path(gitignore) if gitignore else outbox.parent / ".gitignore"


def _outbox_rel(outbox: Path, gitignore: Path) -> str:
    try:
        return outbox.resolve().relative_to(gitignore.parent.resolve()).as_posix()
    except ValueError:
        return outbox.name


def _link_edits(
    docs_dir: Path, outbox_name: str, names: list[str]
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    edits: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    if not docs_dir.is_dir():
        return edits, payloads
    for path in sorted(docs_dir.rglob("*.md")):
        if path.is_symlink() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        updated = text
        counts: dict[str, int] = {}
        for name in names:
            needle = f"{outbox_name}/{name}/"
            replacement = f"{outbox_name}/{ARCHIVE_DIR}/{name}/"
            found = updated.count(needle)
            if found and needle not in replacement:
                updated = updated.replace(needle, replacement)
                counts[name] = found
        if updated != text:
            edits.append(
                {
                    "path": path.as_posix(),
                    "relative": path.relative_to(docs_dir).as_posix(),
                    "occurrences": sum(counts.values()),
                    "batches": sorted(counts),
                }
            )
            payloads[path.as_posix()] = updated.encode("utf-8")
    return edits, payloads


def _gitignore_rules(outbox_rel: str) -> list[str]:
    return [
        f"{outbox_rel}/{ARCHIVE_DIR}/*/epub/",
        f"{outbox_rel}/{ARCHIVE_DIR}/*/pdf/",
    ]


def _gitignore_plan(path: Path, rules: list[str]) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    missing = [rule for rule in rules if rule not in text.splitlines()]
    updated = text
    if missing:
        if updated and not updated.endswith("\n"):
            updated += "\n"
        if updated and "# 旧批次归档" not in updated:
            updated += "\n# 旧批次归档（archive 自动维护）\n"
        updated += "\n".join(missing) + "\n"
    return {
        "path": path.as_posix(),
        "rules": rules,
        "missing": missing,
        "changed": bool(missing),
        "before": text.encode("utf-8"),
        "after": updated.encode("utf-8"),
    }


def plan_archive_transaction(
    outbox: str | Path,
    *,
    docs_dir: str | Path | None = None,
    gitignore: str | Path | None = None,
) -> dict[str, Any]:
    """F2 只读事务预览：移动、文档链接、忽略规则与冲突/跳过。"""
    root = Path(outbox)
    if docs_dir is not None and not Path(docs_dir).is_dir():
        raise ValueError(f"docs 目录不存在或不是目录：{Path(docs_dir)}")
    base = plan_archive(root)
    docs = _docs_dir(root, docs_dir)
    ignore = _gitignore_path(gitignore, root)
    moves = []
    skipped = []
    for entry in base["to_archive"]:
        src = Path(entry["path"])
        dest = root / ARCHIVE_DIR / entry["name"]
        if dest.exists():
            skipped.append({**entry, "reason": "archive_target_exists"})
            continue
        moves.append({"name": entry["name"], "source": src.as_posix(), "target": dest.as_posix()})
    edits, _payloads = _link_edits(docs, root.name, [item["name"] for item in moves])
    ignore_plan = _gitignore_plan(ignore, _gitignore_rules(_outbox_rel(root, ignore)))
    return {
        **base,
        "docs_dir": docs.as_posix(),
        "gitignore": {
            key: value for key, value in ignore_plan.items() if key not in {"before", "after"}
        },
        "moves": moves,
        "skipped": skipped,
        "link_edits": edits,
        "writes": False,
    }


def _journal_dir(outbox: Path) -> Path:
    return outbox / ARCHIVE_DIR / ".transactions"


def _persist(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_archive_transaction(
    outbox: str | Path,
    *,
    docs_dir: str | Path | None = None,
    gitignore: str | Path | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """显式应用归档；先预检，失败按日志回滚，重跑幂等。"""
    root = Path(outbox)
    plan = plan_archive_transaction(root, docs_dir=docs_dir, gitignore=gitignore)
    if not apply:
        return plan
    if not plan["moves"] and not plan["link_edits"] and not plan["gitignore"]["changed"]:
        return {
            "status": "up_to_date",
            "writes": False,
            **{
                key: plan[key]
                for key in ("outbox", "keep", "to_archive", "conflicts", "unresolved")
            },
        }
    identity = hashlib.sha256(
        json.dumps(
            {"moves": plan["moves"], "links": plan["link_edits"], "gitignore": plan["gitignore"]},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    journal_path = _journal_dir(root) / f"{identity}.json"
    edit_payloads: dict[str, bytes] = {}
    for edit in plan["link_edits"]:
        path = Path(edit["path"])
        text = path.read_text(encoding="utf-8")
        for name in edit["batches"]:
            text = text.replace(f"{root.name}/{name}/", f"{root.name}/{ARCHIVE_DIR}/{name}/")
        edit_payloads[edit["path"]] = text.encode("utf-8")
    ignore_plan = _gitignore_plan(Path(plan["gitignore"]["path"]), plan["gitignore"]["rules"])
    journal = {
        "schema_version": "1",
        "status": "pending",
        "outbox": root.as_posix(),
        "moves": plan["moves"],
        "link_edits": [
            {
                "path": edit["path"],
                "before": Path(edit["path"]).read_bytes().hex(),
                "after": edit_payloads[edit["path"]].hex(),
            }
            for edit in plan["link_edits"]
        ],
        "gitignore": {
            "path": ignore_plan["path"],
            "before": ignore_plan["before"].hex(),
            "after": ignore_plan["after"].hex(),
        },
    }
    _persist(journal_path, journal)
    moved: list[dict[str, Any]] = []
    try:
        for move in plan["moves"]:
            source, target = Path(move["source"]), Path(move["target"])
            if target.exists():
                raise ValueError(f"归档目标已存在，拒绝覆盖：{target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            moved.append(move)
        for edit in plan["link_edits"]:
            path = Path(edit["path"])
            path.write_bytes(edit_payloads[edit["path"]])
        if ignore_plan["changed"]:
            Path(ignore_plan["path"]).write_bytes(ignore_plan["after"])
        journal["status"] = "applied"
        _persist(journal_path, journal)
    except Exception as exc:  # noqa: BLE001 - 回滚后按中文错误抛出
        for move in reversed(moved):
            source, target = Path(move["source"]), Path(move["target"])
            if target.exists() and not source.exists():
                shutil.move(str(target), str(source))
        for edit in journal["link_edits"]:
            Path(edit["path"]).write_bytes(bytes.fromhex(edit["before"]))
        if ignore_plan["changed"]:
            Path(ignore_plan["path"]).write_bytes(ignore_plan["before"])
        journal["status"] = "rolled_back"
        _persist(journal_path, journal)
        raise ValueError(f"归档失败，已回滚：{exc}") from None
    return {
        "status": "applied",
        "writes": True,
        "moved": [move["name"] for move in plan["moves"]],
        "link_files": len(plan["link_edits"]),
        "gitignore_changed": plan["gitignore"]["changed"],
        "transaction": journal_path.as_posix(),
    }


def recover_archive(outbox: str | Path) -> dict[str, Any]:
    """恢复未完成归档事务（进程中断后的显式入口）。"""
    root = Path(outbox)
    recovered = []
    for path in sorted(_journal_dir(root).glob("*.json")):
        journal = _read(path)
        if journal.get("status") != "pending":
            continue
        for move in reversed(journal.get("moves") or []):
            source, target = Path(move["source"]), Path(move["target"])
            if target.exists() and not source.exists():
                shutil.move(str(target), str(source))
        for edit in journal.get("link_edits") or []:
            Path(edit["path"]).write_bytes(bytes.fromhex(edit["before"]))
        ignore = journal.get("gitignore") or {}
        if ignore.get("path"):
            Path(ignore["path"]).write_bytes(bytes.fromhex(ignore["before"]))
        journal["status"] = "rolled_back"
        _persist(path, journal)
        recovered.append(path.as_posix())
    return {"status": "recovered" if recovered else "nothing_to_recover", "journals": recovered}
