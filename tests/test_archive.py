# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""F1 真值表：旧批次归档身份识别与只读预览。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from auto_epublizer.archive import plan_archive
from auto_epublizer.cli import app

runner = CliRunner()


def _batch(
    root: Path, name: str, *, book: str = "book", version: str | None = "1.0", extra: str = ""
):
    path = root / name
    path.mkdir(parents=True)
    lines = ["# MANIFEST", "", "| 字段 | 值 |", "| --- | --- |", f"| 书名 | {book} |"]
    if version is not None:
        lines.append(f"| 版本 | {version} |")
    (path / "MANIFEST.md").write_text("\n".join(lines) + extra + "\n", encoding="utf-8")
    return path


def test_highest_version_is_kept_and_others_move(tmp_path: Path) -> None:
    _batch(tmp_path, "b-v1", version="1.0")
    _batch(tmp_path, "b-v3", version="1.2.1")
    _batch(tmp_path, "b-v2", version="1.1")
    plan = plan_archive(tmp_path)
    assert plan["writes"] is False
    assert [item["name"] for item in plan["keep"]] == ["b-v3"]
    assert {item["name"] for item in plan["to_archive"]} == {"b-v1", "b-v2"}
    assert plan["conflicts"] == [] and plan["unresolved"] == []


def test_missing_or_unparseable_version_is_unresolved(tmp_path: Path) -> None:
    _batch(tmp_path, "no-version", version=None)
    _batch(tmp_path, "final", version="终版")
    plan = plan_archive(tmp_path)
    assert plan["keep"] == [] and plan["to_archive"] == []
    assert {item["reason"] for item in plan["unresolved"]} == {
        "missing_version",
        "unparseable_version",
    }


def test_same_version_different_manifest_is_conflict(tmp_path: Path) -> None:
    _batch(tmp_path, "a", version="2.0", extra="extra-a")
    _batch(tmp_path, "b", version="2.0", extra="extra-b")
    plan = plan_archive(tmp_path)
    assert plan["keep"] == [] and plan["to_archive"] == []
    assert plan["conflicts"][0]["reason"] == "same_version_different_manifest"
    assert plan["conflicts"][0]["batches"] == ["a", "b"]


def test_archived_duplicate_is_recognized(tmp_path: Path) -> None:
    _batch(tmp_path, "current", version="1.0")
    _batch(tmp_path / ".archive", "old", version="1.0")
    plan = plan_archive(tmp_path)
    assert plan["archived_total"] == 1
    assert plan["already_archived"][0]["batch"]["name"] == "current"
    assert plan["already_archived"][0]["archived_path"].endswith(".archive/old")


def test_symlinked_directory_is_not_scanned(tmp_path: Path) -> None:
    _batch(tmp_path / "real", "one", version="1.0")
    (tmp_path / "link").symlink_to(tmp_path / "real" / "one", target_is_directory=True)
    plan = plan_archive(tmp_path)
    assert plan["current_total"] == 1


def test_preview_writes_nothing(tmp_path: Path) -> None:
    _batch(tmp_path, "v1", version="1.0")
    _batch(tmp_path, "v2", version="2.0")
    before = {path: path.stat().st_mtime_ns for path in tmp_path.rglob("*") if path.is_file()}
    plan_archive(tmp_path)
    after = {path: path.stat().st_mtime_ns for path in tmp_path.rglob("*") if path.is_file()}
    assert before == after


def test_cli_preview_is_read_only(tmp_path: Path) -> None:
    _batch(tmp_path, "v1", version="1.0")
    result = runner.invoke(app, ["archive", str(tmp_path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["writes"] is False
    assert [item["name"] for item in payload["keep"]] == ["v1"]


def _repo(tmp_path: Path):
    repo = tmp_path / "repo"
    outbox = repo / "outbox"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    _batch(outbox, "book-v1", version="1.0")
    _batch(outbox, "book-v2", version="2.0")
    (outbox / "book-v1" / "epub").mkdir()
    (outbox / "book-v1" / "epub" / "book.epub").write_bytes(b"epub-bytes")
    (docs / "a.md").write_text("链接：../outbox/book-v1/MANIFEST.md\n", encoding="utf-8")
    (repo / ".gitignore").write_text("outbox/*/epub/\n", encoding="utf-8")
    return repo, outbox, docs


def test_transaction_dry_run_and_apply(tmp_path: Path) -> None:
    from auto_epublizer.archive import apply_archive_transaction

    repo, outbox, docs = _repo(tmp_path)
    plan = apply_archive_transaction(outbox)
    assert plan["writes"] is False and len(plan["moves"]) == 1
    assert plan["link_edits"][0]["occurrences"] == 1
    assert set(plan["gitignore"]["missing"]) == {
        "outbox/.archive/*/epub/",
        "outbox/.archive/*/pdf/",
    }
    assert (outbox / "book-v1").is_dir()  # 预览零写入

    before_hash = hashlib.sha256(
        (outbox / "book-v1" / "epub" / "book.epub").read_bytes()
    ).hexdigest()
    result = apply_archive_transaction(outbox, apply=True)
    assert result["status"] == "applied"
    assert not (outbox / "book-v1").exists()
    assert (outbox / ".archive" / "book-v1" / "epub" / "book.epub").is_file()
    moved_hash = hashlib.sha256(
        (outbox / ".archive" / "book-v1" / "epub" / "book.epub").read_bytes()
    ).hexdigest()
    assert moved_hash == before_hash
    assert (outbox / "book-v2").is_dir()
    assert ".archive/book-v1" in (docs / "a.md").read_text(encoding="utf-8")
    ignore = (repo / ".gitignore").read_text(encoding="utf-8")
    assert "outbox/.archive/*/epub/" in ignore and "outbox/.archive/*/pdf/" in ignore
    again = apply_archive_transaction(outbox, apply=True)
    assert again["status"] == "up_to_date"


def test_existing_archive_target_is_skipped(tmp_path: Path) -> None:
    from auto_epublizer.archive import apply_archive_transaction

    _repo_path, outbox, _docs = _repo(tmp_path)
    (outbox / ".archive" / "book-v1").mkdir(parents=True)
    plan = apply_archive_transaction(outbox)
    assert plan["moves"] == []
    assert plan["skipped"][0]["reason"] == "archive_target_exists"
    assert (outbox / "book-v1").is_dir()


def test_failure_rolls_back_moves_links_and_gitignore(tmp_path: Path, monkeypatch) -> None:
    from auto_epublizer import archive as archive_mod

    repo, outbox, docs = _repo(tmp_path)
    (docs / "b.md").write_text("另一个链接：../outbox/book-v1/MANIFEST.md\n", encoding="utf-8")
    before_ignore = (repo / ".gitignore").read_bytes()
    before_docs = {path.name: path.read_bytes() for path in docs.iterdir()}
    real_write = Path.write_bytes
    failed = {"done": False}

    def failing(self, data):
        if self.name == "b.md" and not failed["done"]:
            failed["done"] = True
            raise OSError("disk full")
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing)
    try:
        archive_mod.apply_archive_transaction(outbox, apply=True)
    except ValueError as exc:
        assert "已回滚" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("应当失败并回滚")
    assert (outbox / "book-v1").is_dir() and not (outbox / ".archive" / "book-v1").exists()
    assert (repo / ".gitignore").read_bytes() == before_ignore
    for name, payload in before_docs.items():
        assert (docs / name).read_bytes() == payload


def test_recover_pending_transaction(tmp_path: Path, monkeypatch) -> None:
    from auto_epublizer import archive as archive_mod

    _repo_path, outbox, _docs = _repo(tmp_path)
    # 构造一个「已移动但日志仍 pending」的中断现场
    source = outbox / "book-v1"
    target = outbox / ".archive" / "book-v1"
    target.parent.mkdir(parents=True)
    import shutil

    shutil.move(str(source), str(target))
    journal = archive_mod._journal_dir(outbox) / "crashed.json"
    archive_mod._persist(
        journal,
        {
            "status": "pending",
            "moves": [
                {"source": source.as_posix(), "target": target.as_posix(), "name": "book-v1"}
            ],
            "link_edits": [],
            "gitignore": {},
        },
    )
    result = archive_mod.recover_archive(outbox)
    assert result["status"] == "recovered"
    assert source.is_dir() and not target.exists()


def test_gitignore_rules_cover_archived_binaries(tmp_path: Path) -> None:
    import shutil
    import subprocess

    from auto_epublizer.archive import apply_archive_transaction

    repo, outbox, _docs = _repo(tmp_path)
    apply_archive_transaction(outbox, apply=True)
    if shutil.which("git") is None:  # pragma: no cover
        return
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for path in (
        "outbox/.archive/book-v1/epub/book.epub",
        "outbox/.archive/book-v1/pdf/book.pdf",
        "outbox/book-v2/epub/book.epub",
    ):
        result = subprocess.run(
            ["git", "-C", str(repo), "check-ignore", "-q", "--", path],
            capture_output=True,
        )
        assert result.returncode == 0, (path, result.stderr)


def test_cli_apply_moves_and_is_idempotent(tmp_path: Path) -> None:
    _repo_path, outbox, _docs = _repo(tmp_path)
    result = runner.invoke(app, ["archive", str(outbox), "--apply", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "applied"
    assert (outbox / ".archive" / "book-v1").is_dir()
    again = runner.invoke(app, ["archive", str(outbox), "--apply", "--json"])
    assert json.loads(again.stdout)["status"] == "up_to_date"


def test_missing_outbox_is_an_error_not_an_empty_plan(tmp_path: Path) -> None:
    from auto_epublizer.archive import apply_archive_transaction

    with pytest.raises(ValueError, match="outbox"):
        apply_archive_transaction(tmp_path / "does-not-exist")

    result = runner.invoke(app, ["archive", str(tmp_path / "does-not-exist"), "--json"])
    assert result.exit_code != 0
    assert "归档失败" in result.output
    assert not (tmp_path / ".gitignore").exists()


def test_explicit_missing_docs_dir_is_an_error(tmp_path: Path) -> None:
    from auto_epublizer.archive import apply_archive_transaction

    _repo_path, outbox, docs = _repo(tmp_path)
    with pytest.raises(ValueError, match="docs"):
        apply_archive_transaction(outbox, docs_dir=tmp_path / "missing-docs")
    assert docs.is_dir()
    # 默认同级 docs 不存在时不算错误（工作根可能没有文档树）
    bare = tmp_path / "bare" / "outbox"
    _batch(bare, "book-v1", version="1.0")
    plan = apply_archive_transaction(bare)
    assert plan["link_edits"] == [] and plan["writes"] is False


def test_symlinked_archive_dir_is_rejected(tmp_path: Path) -> None:
    from auto_epublizer.archive import apply_archive_transaction

    _repo_path, outbox, _docs = _repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outbox / ".archive").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="符号链接"):
        apply_archive_transaction(outbox, apply=True)
    assert (outbox / "book-v1").is_dir()
    assert not (outside / "book-v1").exists()


def test_same_version_same_manifest_but_different_artifacts_conflicts(tmp_path: Path) -> None:
    from auto_epublizer.archive import plan_archive

    outbox = tmp_path / "outbox"
    for name, payload in (("book-a", b"epub-a"), ("book-b", b"epub-b")):
        _batch(outbox, name, version="1.0")
        (outbox / name / "epub").mkdir()
        (outbox / name / "epub" / "book.epub").write_bytes(payload)
    # 同一 MANIFEST 字节：先写一次再复制
    (outbox / "book-b" / "MANIFEST.md").write_bytes(
        (outbox / "book-a" / "MANIFEST.md").read_bytes()
    )
    plan = plan_archive(outbox)
    assert [c["reason"] for c in plan["conflicts"]] == ["same_version_different_artifacts"]
    assert plan["to_archive"] == []
