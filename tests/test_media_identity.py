"""媒体身份：精确解析、basename 兼容与显式迁移映射的边界。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from auto_epublizer.media_paths import (
    MediaMapError,
    load_media_map,
    resolve_audit_media,
    resolve_media,
    resolve_media_path,
)


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "ws" / "structured" / "raw" / "media"
    (root / "chapter-a").mkdir(parents=True)
    (root / "chapter-a" / "figure.png").write_bytes(b"a")
    (root / "cover.png").write_bytes(b"cover")
    return root


def test_exact_resolution_preserves_subdirectory(tmp_path: Path) -> None:
    root = _root(tmp_path)
    found = resolve_media("chapter-a/figure.png", root)
    assert found is not None
    assert found.strategy == "exact"
    assert found.path == (root / "chapter-a" / "figure.png").resolve()


def test_strict_resolution_rejects_wrong_directory(tmp_path: Path) -> None:
    """同名不同目录不得在交付对账中被 basename 静默替代。"""
    root = _root(tmp_path)
    (root / "figure.png").write_bytes(b"wrong")
    assert resolve_media("chapter-b/figure.png", root, allow_basename=False) is None
    assert resolve_media_path("chapter-b/figure.png", root, allow_basename=False) is None
    legacy = resolve_media("chapter-b/figure.png", root, allow_basename=True)
    assert legacy is not None and legacy.strategy == "basename"
    assert legacy.path.read_bytes() == b"wrong"


def test_root_prefix_is_exact_identity(tmp_path: Path) -> None:
    root = _root(tmp_path)
    found = resolve_media("structured/raw/media/cover.png", root, allow_basename=False)
    assert found is not None
    assert found.strategy in {"root-prefix", "exact"}


def _write_map(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "ws" / "preprocessing" / "media-map.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": 1, "entries": entries}), encoding="utf-8")
    return path


def test_explicit_mapping_resolves_legacy_absolute_path(tmp_path: Path) -> None:
    root = _root(tmp_path)
    digest = hashlib.sha256(b"a").hexdigest()
    _write_map(
        tmp_path,
        [
            {
                "ref": "/home/agent/book/media/chapter-a/figure.png",
                "member": "chapter-a/figure.png",
                "reason": "旧工作区绝对路径迁移",
                "sha256": digest,
            }
        ],
    )
    mapping = load_media_map(tmp_path / "ws")
    assert mapping.findings == []
    found = resolve_audit_media("/home/agent/book/media/chapter-a/figure.png", root, mapping)
    assert found is not None and found.strategy == "mapped"
    assert found.path == (root / "chapter-a" / "figure.png").resolve()


def test_mapping_sha_mismatch_is_rejected_with_finding(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _write_map(
        tmp_path,
        [
            {
                "ref": "old/x.png",
                "member": "chapter-a/figure.png",
                "reason": "迁移",
                "sha256": "0" * 64,
            }
        ],
    )
    mapping = load_media_map(tmp_path / "ws")
    assert any("摘要不匹配" in f for f in mapping.findings)
    assert mapping.entries == {}
    assert resolve_audit_media("old/x.png", root, mapping) is None


def test_mapping_rejects_traversal_and_duplicates(tmp_path: Path) -> None:
    _root(tmp_path)
    _write_map(
        tmp_path,
        [
            {"ref": "a", "member": "../secret.png", "reason": "越界"},
            {"ref": "b", "member": "cover.png", "reason": "ok"},
            {"ref": "b", "member": "cover.png", "reason": "dup"},
        ],
    )
    mapping = load_media_map(tmp_path / "ws")
    assert any("越界" in f for f in mapping.findings)
    assert any("重复" in f for f in mapping.findings)
    assert list(mapping.entries) == ["b"]


def test_mapping_requires_reason_and_schema(tmp_path: Path) -> None:
    _root(tmp_path)
    _write_map(tmp_path, [{"ref": "a", "member": "cover.png", "reason": ""}])
    assert any("缺 reason" in f for f in load_media_map(tmp_path / "ws").findings)

    path = tmp_path / "ws" / "preprocessing" / "media-map.json"
    path.write_text(json.dumps({"entries": []}), encoding="utf-8")
    with pytest.raises(MediaMapError, match="schema"):
        load_media_map(tmp_path / "ws")


def test_member_accepts_relative_media_root(tmp_path: Path, monkeypatch) -> None:
    """P1：相对 --workspace 时 media_root 未 resolve 也不得崩溃。"""
    _root(tmp_path)
    monkeypatch.chdir(tmp_path)
    found = resolve_media("chapter-a/figure.png", Path("ws/structured/raw/media"))
    assert found is not None
    assert found.member(Path("ws/structured/raw/media")) == "media/chapter-a/figure.png"
