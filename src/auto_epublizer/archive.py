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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from auto_common.markdown import inline_code_chunks

ARCHIVE_DIR = ".archive"
_INLINE_TARGET = re.compile(r"(\]\(\s*<?)([^)\s>]+)(>?)")
_REF_TARGET = re.compile(r"(?m)^( {0,3}\[[^\]\n]+\]:\s*)(\S+)(.*)$")
_HTML_TARGET = re.compile(r"(?i)(\b(?:href|src)\s*=\s*[\"'])([^\"']+)([\"'])")


def _moved_target(target: str, *, outbox_name: str, name: str) -> str | None:
    """只改写链接目标中的批次目录段；相对前缀（../、./）原样保留。"""
    needle = f"{outbox_name}/{name}/"
    start = target.find(needle)
    while start != -1:
        boundary = start == 0 or target[start - 1] in "/\\"
        if boundary:
            replacement = f"{outbox_name}/{ARCHIVE_DIR}/{name}/"
            return target[:start] + replacement + target[start + len(needle) :]
        start = target.find(needle, start + 1)
    return None


def _rewrite_markdown_links(text: str, *, outbox_name: str, name: str) -> tuple[str, int]:
    """只改链接目标（内联/引用式/HTML href|src），跳过围栏与行内代码。"""
    count = 0

    def swap(target: str) -> str:
        nonlocal count
        moved = _moved_target(target, outbox_name=outbox_name, name=name)
        if moved is None:
            return target
        count += 1
        return moved

    def rewrite_segment(segment: str) -> str:
        segment = _INLINE_TARGET.sub(lambda m: m.group(1) + swap(m.group(2)) + m.group(3), segment)
        segment = _REF_TARGET.sub(lambda m: m.group(1) + swap(m.group(2)) + m.group(3), segment)
        return _HTML_TARGET.sub(lambda m: m.group(1) + swap(m.group(2)) + m.group(3), segment)

    out: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        rebuilt = "".join(
            part if is_code else rewrite_segment(part) for is_code, part in inline_code_chunks(line)
        )
        out.append(rebuilt)
    return "".join(out), count


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
class BatchBook:
    """批次内的一本书：身份、版本与产物摘要（来自 batch.json 或旧 MANIFEST.md）。"""

    book: str | None
    version: str | None
    version_key: tuple[int, ...] | None
    artifacts_sha256: str
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class Batch:
    name: str
    path: Path
    manifest_sha256: str
    artifacts_sha256: str
    books: tuple[BatchBook, ...]
    errors: tuple[str, ...]

    @property
    def book(self) -> str | None:
        return self.books[0].book if len(self.books) == 1 else None

    @property
    def version(self) -> str | None:
        return self.books[0].version if len(self.books) == 1 else None

    @property
    def version_key(self) -> tuple[int, ...] | None:
        return self.books[0].version_key if len(self.books) == 1 else None

    def preview(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path.as_posix(),
            "book": self.book,
            "version": self.version,
            "manifest_sha256": self.manifest_sha256,
            "artifacts_sha256": self.artifacts_sha256,
            "books": [
                {
                    "book": item.book,
                    "version": item.version,
                    "artifacts_sha256": item.artifacts_sha256,
                    "errors": list(item.errors),
                }
                for item in self.books
            ],
            "errors": list(self.errors),
        }


BATCH_SCHEMA = "auto-epublizer/batch/v1"


def _artifacts_digest(path: Path) -> str:
    """批次产物字节身份（除清单文件外的全部文件，按相对路径排序）。"""
    digest = hashlib.sha256()
    files = sorted(
        (
            item
            for item in path.rglob("*")
            if item.is_file()
            and item.name not in {"MANIFEST.md", "batch.json"}
            and not item.is_symlink()
        ),
        key=lambda item: item.relative_to(path).as_posix(),
    )
    for item in files:
        digest.update(item.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(item.read_bytes()).hexdigest().encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _book_digest(path: Path, artifacts: list[dict[str, Any]]) -> str:
    """按**实际文件字节**计算身份，声明值只用于校验，不拿来当冲突证据。"""
    digest = hashlib.sha256()
    for item in sorted(artifacts, key=lambda entry: str(entry.get("path"))):
        rel = str(item.get("path") or "")
        target = path / rel
        digest.update(rel.encode())
        digest.update(b"\0")
        if target.is_file():
            digest.update(hashlib.sha256(target.read_bytes()).hexdigest().encode())
        else:
            digest.update(b"missing")
        digest.update(b"\n")
    return digest.hexdigest()


def _batch_from_json(path: Path, payload: bytes) -> Batch:
    errors: list[str] = []
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return Batch(
            path.name, path, hashlib.sha256(payload).hexdigest(), "", (), ("invalid_batch_json",)
        )
    if not isinstance(data, dict) or data.get("schema_version") != BATCH_SCHEMA:
        return Batch(
            path.name,
            path,
            hashlib.sha256(payload).hexdigest(),
            "",
            (),
            ("unsupported_batch_schema",),
        )
    books: list[BatchBook] = []
    for index, raw in enumerate(data.get("books") or []):
        if not isinstance(raw, dict):
            errors.append(f"book[{index}]:not_object")
            continue
        book = str(raw.get("book") or "").strip() or None
        version = str(raw.get("version") or "").strip() or None
        key = _version_key(version)
        item_errors: list[str] = []
        if not book:
            item_errors.append("missing_book")
        if version is None:
            item_errors.append("missing_version")
        elif key is None:
            item_errors.append("unparseable_version")
        artifacts = raw.get("artifacts") or []
        if not isinstance(artifacts, list) or not artifacts:
            item_errors.append("missing_artifacts")
        for artifact in artifacts if isinstance(artifacts, list) else []:
            rel = str((artifact or {}).get("path") or "")
            declared = str((artifact or {}).get("sha256") or "")
            target = path / rel
            if not rel or not target.is_file():
                item_errors.append(f"artifact_missing:{rel}")
            elif declared and hashlib.sha256(target.read_bytes()).hexdigest() != declared:
                item_errors.append(f"artifact_changed:{rel}")
        books.append(
            BatchBook(
                book,
                version,
                key,
                _book_digest(path, artifacts if isinstance(artifacts, list) else []),
                tuple(item_errors),
            )
        )
    if not books:
        errors.append("missing_books")
    return Batch(
        path.name,
        path,
        hashlib.sha256(payload).hexdigest(),
        _artifacts_digest(path),
        tuple(books),
        tuple(errors),
    )


def _batch(path: Path) -> Batch:
    manifest = path / "MANIFEST.md"
    batch_json = path / "batch.json"
    if batch_json.is_file():
        if not manifest.is_file():
            return Batch(
                path.name,
                path,
                hashlib.sha256(batch_json.read_bytes()).hexdigest(),
                "",
                (),
                ("missing_manifest",),
            )
        return _batch_from_json(path, batch_json.read_bytes())
    if not manifest.is_file():
        return Batch(
            path.name, path, hashlib.sha256(b"").hexdigest(), "", (), ("missing_manifest",)
        )
    payload = manifest.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    fields = _parse_manifest(payload.decode("utf-8", "replace"))
    book = _pick(fields, _BOOK_KEYS)
    version = _pick(fields, _VERSION_KEYS)
    version_key = _version_key(version)
    errors: list[str] = []
    if not book:
        errors.append("missing_book")
    if version is None:
        errors.append("missing_version")
    elif version_key is None:
        errors.append("unparseable_version")
    artifacts = _artifacts_digest(path)
    return Batch(
        path.name,
        path,
        digest,
        artifacts,
        (BatchBook(book, version, version_key, artifacts, tuple(errors)),),
        (),
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


def _open_books(batch: Batch) -> list[BatchBook]:
    return [item for item in batch.books if item.book and item.version_key is not None]


def _unversioned_only(batch: Batch) -> bool:
    """只有「缺版本」问题（其余身份/产物均完整）的批次。"""
    return (
        bool(batch.books)
        and not batch.errors
        and all(
            item.version is None and set(item.errors) <= {"missing_version"} for item in batch.books
        )
    )


def _with_version_map(batch: Batch, mapping: dict[str, str]) -> Batch:
    if batch.name not in mapping:
        return batch
    version = str(mapping[batch.name] or "").strip()
    key = _version_key(version)
    if key is None:
        raise ValueError(f"version-map 的版本无法解析：{batch.name} → {version!r}")
    books: list[BatchBook] = []
    for item in batch.books:
        if item.version is not None and item.version != version:
            raise ValueError(
                f"version-map 与批次已有版本冲突：{batch.name}（{item.version} vs {version}）"
            )
        books.append(
            replace(
                item,
                version=version,
                version_key=key,
                errors=tuple(err for err in item.errors if err != "missing_version"),
            )
        )
    return replace(batch, books=tuple(books))


def plan_archive(
    outbox: str | Path,
    *,
    unversioned: str = "hold",
    version_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """只读归档预览：按书身份分组，最高版本保留，其余待归档；不写文件。

    冲突按**所有版本、两个位置**核对：同书同版多份但清单或产物字节不同即冲突，
    整组（含批次内其他书）不移动；多书批次只有在每本书都有更新交付时才整体归档。

    ``unversioned``：缺版本批次的显式策略。``hold``（默认）只列入未决；
    ``archive`` 才按“旧批次”移入 `.archive`（不参与版本比较，绝不按目录名猜版本）。
    ``version_map``：批次名→版本 的显式映射，只补缺版本，不覆盖已有版本。
    """
    if unversioned not in {"hold", "archive"}:
        raise ValueError(f"unversioned 只能是 hold 或 archive：{unversioned!r}")
    mapping = dict(version_map or {})
    root = Path(outbox)
    if not root.is_dir():
        raise ValueError(f"outbox 目录不存在或不是目录：{root}")
    archived_dir = root / ARCHIVE_DIR
    if archived_dir.is_symlink():
        raise ValueError(f"归档目录不能是符号链接：{archived_dir}")
    current = [_batch(path) for path in _subdirs(root, skip_archive=True)]
    archived = [_batch(path) for path in _subdirs(archived_dir, skip_archive=False)]
    known = {batch.name for batch in current}
    unknown = sorted(set(mapping) - known)
    if unknown:
        raise ValueError("version-map 含不存在的批次：" + "、".join(unknown))
    current = [_with_version_map(batch, mapping) for batch in current]
    unversioned_batches = [batch for batch in current if _unversioned_only(batch)]

    def batch_errors(batch: Batch) -> list[str]:
        return [*batch.errors, *(err for item in batch.books for err in item.errors)]

    unresolved = []
    for batch in current + archived:
        errors = batch_errors(batch)
        if not errors:
            continue
        if unversioned == "archive" and batch.name in {b.name for b in unversioned_batches}:
            continue
        entry = {"batch": batch.preview(), "reason": ",".join(errors)}
        if _unversioned_only(batch):
            entry["policy"] = unversioned
        unresolved.append(entry)
    valid = [batch for batch in current + archived if not batch_errors(batch)]

    positions: dict[tuple[str, tuple[int, ...]], list[tuple[Batch, BatchBook]]] = {}
    for batch in valid:
        for item in _open_books(batch):
            key = (item.book, item.version_key)
            positions.setdefault(key, []).append((batch, item))  # type: ignore[arg-type]

    conflicts: list[dict[str, Any]] = []
    blocked: set[str] = set()
    for (book, _key), items in sorted(positions.items()):
        if len(items) < 2:
            continue
        manifests = {batch.manifest_sha256 for batch, _ in items}
        artifacts = {item.artifacts_sha256 for _, item in items}
        if len(manifests) == 1 and len(artifacts) == 1:
            continue
        reason = (
            "same_version_different_artifacts"
            if len(artifacts) > 1
            else "same_version_different_manifest"
        )
        conflicts.append(
            {
                "book": book,
                "version": items[0][1].version,
                "batches": sorted(batch.name for batch, _ in items),
                "locations": sorted(
                    ("archive" if batch.path.parent.name == ARCHIVE_DIR else "top")
                    for batch, _ in items
                ),
                "reason": reason,
            }
        )
        blocked.update(batch.name for batch, _ in items)

    kept: dict[str, tuple[int, ...]] = {}
    for book, key in positions:
        if book not in kept or key > kept[book]:
            kept[book] = key
    keep_batches = sorted(
        {
            batch.name
            for batch in current
            if _open_books(batch)
            and all(
                item.book in kept and kept[item.book] == item.version_key
                for item in _open_books(batch)
            )
        }
    )
    keep = [
        batch.preview()
        for batch in current
        if batch.name in keep_batches and batch.name not in blocked
    ]
    move: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    for batch in current:
        if batch.name in blocked or batch.name in keep_batches:
            continue
        entries = _open_books(batch)
        if not entries:
            continue
        current_books = [item.book for item in entries if kept.get(item.book) == item.version_key]
        stale_books = [item.book for item in entries if kept.get(item.book) != item.version_key]
        if current_books and stale_books:
            held.append(
                {
                    "batch": batch.preview(),
                    "reason": "mixed_batch_has_current_book",
                }
            )
            continue
        if current_books:
            # 全部书都是当前版本：整批保留。
            continue
        move.append(batch.preview())

    archived_positions: dict[tuple[str, tuple[int, ...]], list[tuple[Batch, BatchBook]]] = {}
    for batch in archived:
        for item in _open_books(batch):
            archived_positions.setdefault((item.book, item.version_key), []).append(  # type: ignore[arg-type]
                (batch, item)
            )
    already_archived = []
    for batch in current:
        for item in _open_books(batch):
            matches = archived_positions.get((item.book, item.version_key)) or []
            for prior, prior_book in matches:
                if (
                    prior_book.artifacts_sha256 != item.artifacts_sha256
                    or prior.manifest_sha256 != batch.manifest_sha256
                ):
                    conflicts.append(
                        {
                            "book": item.book,
                            "version": item.version,
                            "batches": sorted([batch.name, prior.name]),
                            "locations": ["top", "archive"],
                            "reason": "same_version_archived_differs",
                        }
                    )
                    blocked.add(batch.name)
                    continue
                already_archived.append(
                    {
                        "batch": batch.preview(),
                        "archived_path": prior.path.as_posix(),
                    }
                )
    move = [entry for entry in move if entry["name"] not in blocked]
    keep = [entry for entry in keep if entry["name"] not in blocked]
    if unversioned == "archive":
        move.extend(
            {**batch.preview(), "reason": "unversioned_policy"}
            for batch in unversioned_batches
            if batch.name not in blocked
        )

    return {
        "schema_version": "1",
        "writes": False,
        "outbox": root.as_posix(),
        "archive": archived_dir.as_posix(),
        "current_total": len(current),
        "archived_total": len(archived),
        "keep": keep,
        "to_archive": move,
        "held": held,
        "conflicts": conflicts,
        "unresolved": unresolved,
        "already_archived": already_archived,
        "unversioned_policy": unversioned,
        "note": "身份/版本只读 batch.json 或 MANIFEST.md；同版不同清单或产物不猜最新，F1 不写任何文件",
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
            updated, found = _rewrite_markdown_links(updated, outbox_name=outbox_name, name=name)
            if found:
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


_MD_LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
# 引用式链接定义：`[标签]: ../outbox/batch/book.epub`（含 <> 包裹）
_MD_REF_DEF = re.compile(r"(?m)^\s*\[[^\]]+\]:\s*<?([^>\s]+)>?")
# HTML 链接：`href="../outbox/batch/book.epub"`
_HTML_HREF = re.compile(r"""href=["']([^"']+)["']""")


def _link_targets(text: str):
    """Markdown 内联/引用式与 HTML href 三类链接目标（顺序稳定、去重）。"""
    seen: set[str] = set()
    for pattern in (_MD_LINK, _MD_REF_DEF, _HTML_HREF):
        for match in pattern.finditer(text):
            target = match.group(1)
            if target in seen:
                continue
            seen.add(target)
            yield target


def _broken_after_archive(
    docs_dir: Path, outbox: Path, names: list[str], payloads: dict[str, bytes]
) -> list[dict[str, str]]:
    """改写后仍指向不存在源的链接（只核对本次归档涉及的批次目录）。

    预览阶段文件还没移动，因此把 ``.archive/<批次>/...`` 还原成 ``<批次>/...``
    检查源是否存在；这不是断链的完整证明，但能拦住替换路径拼错/批次名错。
    覆盖内联链接、引用式定义与 HTML ``href``；纯锚点/远程链接不查。
    """
    broken: list[dict[str, str]] = []
    outbox_name = outbox.name
    seen: set[tuple[str, str]] = set()
    candidates = sorted(docs_dir.rglob("*.md"))
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            continue
        payload = payloads.get(path.as_posix())
        text = (
            payload.decode("utf-8", errors="replace")
            if payload is not None
            else path.read_text(encoding="utf-8", errors="replace")
        )
        for target in _link_targets(text):
            if target.startswith(("http:", "https:", "mailto:", "#", "data:")):
                continue
            rel = unquote(target.split("#", 1)[0])
            if not rel:
                continue
            candidate = (path.parent / rel).resolve()
            rel_posix = candidate.as_posix()
            key = (path.as_posix(), rel_posix)
            if key in seen:
                continue
            marker = f"/{outbox_name}/{ARCHIVE_DIR}/"
            if marker in rel_posix:
                for name in names:
                    suffix = f"/{ARCHIVE_DIR}/{name}/"
                    if suffix not in rel_posix:
                        continue
                    source_rel = rel_posix.split(suffix, 1)[1]
                    source = outbox / name / source_rel
                    if not source.exists():
                        seen.add(key)
                        broken.append(
                            {
                                "file": path.as_posix(),
                                "link": target,
                                "expected_source": source.as_posix(),
                            }
                        )
                    break
                continue
            # 仍指向将移动的顶层批次（如 `./` 变体未被精确替换）：移动后必断。
            top = f"/{outbox_name}/"
            if top in rel_posix:
                rest = rel_posix.split(top, 1)[1]
                name = rest.split("/", 1)[0]
                if name in names and not rest.startswith(f"{ARCHIVE_DIR}/"):
                    seen.add(key)
                    broken.append(
                        {
                            "file": path.as_posix(),
                            "link": target,
                            "expected_source": (outbox / name / rest.split("/", 1)[1]).as_posix()
                            if "/" in rest
                            else (outbox / name).as_posix(),
                            "reason": "not_rewritten",
                        }
                    )
    return broken


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
    unversioned: str = "hold",
    version_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """F2 只读事务预览：移动、文档链接、忽略规则与冲突/跳过。"""
    root = Path(outbox)
    if docs_dir is not None and not Path(docs_dir).is_dir():
        raise ValueError(f"docs 目录不存在或不是目录：{Path(docs_dir)}")
    base = plan_archive(root, unversioned=unversioned, version_map=version_map)
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
    names = [item["name"] for item in moves]
    edits, payloads = _link_edits(docs, root.name, names)
    broken = _broken_after_archive(docs, root, names, payloads)
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
        "broken_links": broken,
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


def _archive_readme(root: Path, plan: dict[str, Any]) -> str:
    """`outbox/.archive/README.md`：按书列出最新版本/批次与已归档批次。"""
    records: dict[str, list[tuple[tuple[int, ...], str, str]]] = {}
    groups: list[dict[str, Any]] = [
        *(plan.get("keep") or []),
        *(plan.get("to_archive") or []),
    ]
    for entry in plan.get("already_archived") or []:
        batch = entry.get("batch")
        if isinstance(batch, dict):
            groups.append(batch)
    archive_dir = root / ARCHIVE_DIR
    if archive_dir.is_dir() and not archive_dir.is_symlink():
        for path in _subdirs(archive_dir, skip_archive=False):
            batch = _batch(path)
            if not batch.errors and not any(item.errors for item in batch.books):
                groups.append(batch.preview())
    for group in groups:
        name = str(group.get("name") or "")
        for item in group.get("books") or []:
            book = str(item.get("book") or "").strip()
            version = str(item.get("version") or "").strip()
            key = _version_key(version)
            if not name or not book or key is None:
                continue
            records.setdefault(book, []).append((key, version, name))
    lines = [
        "# 归档索引",
        "",
        "> 由 `auto-epublizer archive --apply` 生成；只列可核验的书名/版本/批次。",
        "",
        "| 书 | 最新版本 | 最新批次 | 已归档批次 |",
        "|---|---|---|---|",
    ]
    for book in sorted(records):
        entries = records[book]
        latest = max(entries)
        archived = sorted({name for _key, _version, name in entries if name != latest[2]})
        lines.append(f"| {book} | {latest[1]} | {latest[2]} | {', '.join(archived) or '—'} |")
    return "\n".join(lines) + "\n"


def apply_archive_transaction(
    outbox: str | Path,
    *,
    docs_dir: str | Path | None = None,
    gitignore: str | Path | None = None,
    unversioned: str = "hold",
    version_map: dict[str, str] | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """显式应用归档；先预检，失败按日志回滚，重跑幂等。"""
    root = Path(outbox)
    plan = plan_archive_transaction(
        root,
        docs_dir=docs_dir,
        gitignore=gitignore,
        unversioned=unversioned,
        version_map=version_map,
    )
    if not apply:
        return plan
    if plan["broken_links"]:
        raise ValueError(
            "归档会留下断链，已拒绝移动："
            + "；".join(f"{item['file']} → {item['link']}" for item in plan["broken_links"][:5])
        )
    if not plan["moves"] and not plan["link_edits"] and not plan["gitignore"]["changed"]:
        readme_path = root / ARCHIVE_DIR / "README.md"
        readme = _archive_readme(root, plan)
        changed = not readme_path.is_file() or readme_path.read_text(encoding="utf-8") != readme
        if changed:
            readme_path.parent.mkdir(parents=True, exist_ok=True)
            readme_path.write_text(readme, encoding="utf-8")
        return {
            "status": "up_to_date",
            "writes": changed,
            "archive_readme": readme_path.as_posix(),
            "archive_readme_changed": changed,
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
            text, _ = _rewrite_markdown_links(text, outbox_name=root.name, name=name)
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
        readme_path = root / ARCHIVE_DIR / "README.md"
        readme_path.parent.mkdir(parents=True, exist_ok=True)
        readme_path.write_text(_archive_readme(root, plan), encoding="utf-8")
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
        "link_occurrences": sum(item["occurrences"] for item in plan["link_edits"]),
        "gitignore_changed": plan["gitignore"]["changed"],
        "archive_readme": (root / ARCHIVE_DIR / "README.md").as_posix(),
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
