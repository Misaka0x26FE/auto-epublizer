"""工作区模型与 RunStore 测试：schema、原子写、sha256 绑定、账本、快照、init。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_epublizer.config import Config
from auto_epublizer.workspace import (
    UNIT_STATES,
    InitError,
    Publication,
    PublicationMeta,
    RunStore,
    atomic_write_json,
    init_workspace,
    read_json,
    slugify,
    source_sha256,
    update_meta,
)
from auto_epublizer.workspace.models import SCHEMA_VERSION, Unit
from auto_epublizer.workspace.store import SourceIdentityError


def test_slugify() -> None:
    assert slugify("The Great Gatsby.epub") == "the-great-gatsby"
    assert slugify("  Multiple   Spaces  .pdf") == "multiple-spaces"
    assert slugify("!!!").startswith("book")


def test_source_sha256_deterministic(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_bytes(b"hello")
    assert source_sha256(p) == source_sha256(p)
    assert len(source_sha256(p)) == 64


def test_atomic_write_and_read_json(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    atomic_write_json(p, {"a": 1})
    assert read_json(p) == {"a": 1}


def test_publication_model_roundtrip() -> None:
    pub = Publication(
        slug="book",
        meta=PublicationMeta(title="T", source_sha256="0" * 64),
        units=[Unit(id="ch01", kind="chapter", title="第一章")],
    )
    assert pub.schema_version == SCHEMA_VERSION
    assert pub.unit("ch01") is not None
    assert pub.unit("nope") is None
    pub.set_unit_status("ch01", "translated")
    assert pub.unit("ch01").status == "translated"
    with pytest.raises(KeyError):
        pub.set_unit_status("nope", "done")


def test_unit_states_are_linear() -> None:
    assert UNIT_STATES == (
        "pending",
        "split",
        "analyzed",
        "translated",
        "aligned",
        "reviewed",
        "built",
    )


def _make_store(tmp_path: Path) -> RunStore:
    store = RunStore(tmp_path / "ws")
    store.ensure_skeleton()
    pub = Publication(
        slug="ws",
        meta=PublicationMeta(title="T", source_sha256="a" * 64),
        units=[Unit(id="ch01", kind="chapter")],
    )
    store.save_publication(pub)
    return store


def test_runstore_load_save(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    assert store.exists()
    pub = store.load_publication()
    assert pub.slug == "ws"
    assert pub.meta.source_sha256 == "a" * 64


def test_runstore_set_unit_status(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.set_unit_status("ch01", "reviewed")
    assert store.load_publication().unit("ch01").status == "reviewed"
    with pytest.raises(KeyError):
        store.set_unit_status("nope", "built")


def test_runstore_require_initialized_raises(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "empty")
    with pytest.raises(FileNotFoundError):
        store.require_initialized()


def test_ensure_source_identity(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    src = tmp_path / "in.txt"
    src.write_text("data")
    actual = source_sha256(src)
    # 先把工作区记录的哈希更新为真实值 → 应通过
    pub = store.load_publication()
    pub.meta.source_sha256 = actual
    store.save_publication(pub)
    store.ensure_source_identity(src)
    # 内容变化 → 应拒绝
    src.write_text("changed")
    with pytest.raises(SourceIdentityError):
        store.ensure_source_identity(src)


def test_event_ledger_append(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.log_event("batch_translated", chapter=1, count=2)
    store.log_event("run_done", ok=True)
    events = store.read_events()
    assert [e["event"] for e in events] == ["batch_translated", "run_done"]
    assert events[0]["count"] == 2


def test_usage_ledger_merge(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    inc = {
        "by_tier": {
            "cheap": {
                "calls": 2,
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
                "cache_hit_tokens": 0,
                "cache_miss_tokens": 0,
            }
        },
        "by_stage": {
            "translate": {
                "calls": 2,
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
                "cache_hit_tokens": 0,
                "cache_miss_tokens": 0,
            }
        },
    }
    store.merge_usage(inc)
    merged = store.merge_usage(inc)
    assert merged["totals"]["calls"] == 4


def test_usage_merge_idempotent_by_run_id(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    inc = {
        "by_tier": {
            "cheap": {
                "calls": 1,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cache_hit_tokens": 0,
                "cache_miss_tokens": 0,
            }
        },
        "by_stage": {},
    }
    store.merge_usage(inc, run_id="run-1")
    # 同一 run_id 重复合并应被幂等跳过
    store.merge_usage(inc, run_id="run-1")
    merged = store.merge_usage(inc, run_id="run-2")
    assert merged["totals"]["calls"] == 2
    assert set(merged["merged_runs"]) == {"run-1", "run-2"}


def test_export_snapshot_frozen(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    pub = store.create_export_snapshot(actual_sha256="a" * 64)
    assert pub.slug == "ws"


def test_export_snapshot_rejects_bad_hash(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    with pytest.raises(SourceIdentityError):
        store.create_export_snapshot(actual_sha256="b" * 64)


def test_update_meta_does_not_deadlock(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    pub = update_meta(store, creator="作者", title="新标题")
    assert pub.meta.creator == "作者"
    assert pub.meta.title == "新标题"
    # 再读一次确认落盘
    assert store.load_publication().meta.creator == "作者"


def test_init_workspace(tmp_path: Path) -> None:
    src = tmp_path / "my book.pdf"
    src.write_bytes(b"%PDF-1.4 fake")
    ws_root = tmp_path / "workspaces"
    store = init_workspace(src, workspace_dir=ws_root)
    assert store.exists()
    assert store.publication_path.is_file()
    assert (store.source_dir / "my book.pdf").is_file()
    pub = store.load_publication()
    assert pub.slug == "my-book"
    assert len(pub.meta.source_sha256) == 64
    assert pub.config.target_language == "zh-CN"
    assert store.event_log_path.is_file()


def test_init_workspace_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InitError):
        init_workspace(tmp_path / "nope.pdf", workspace_dir=tmp_path / "w")


def test_init_workspace_already_exists(tmp_path: Path) -> None:
    src = tmp_path / "a.md"
    src.write_text("x")
    ws_root = tmp_path / "w"
    init_workspace(src, workspace_dir=ws_root)
    with pytest.raises(InitError):
        init_workspace(src, workspace_dir=ws_root)


def test_init_references_import(tmp_path: Path) -> None:
    src = tmp_path / "a.md"
    src.write_text("x")
    ref = tmp_path / "terms.csv"
    ref.write_text("a,b\n")
    store = init_workspace(src, workspace_dir=tmp_path / "w", references=[ref])
    assert (store.references_dir / "user" / "terms.csv").is_file()


def test_config_snapshot_from_target(tmp_path: Path) -> None:
    src = tmp_path / "a.md"
    src.write_text("x")
    cfg = Config()
    store = init_workspace(src, workspace_dir=tmp_path / "w", config=cfg, target_language="ja")
    assert store.load_publication().meta.target_language == "ja"


def test_publication_units_persisted(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    pub = store.load_publication()
    assert len(pub.units) == 1
    raw = json.loads(store.publication_path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == SCHEMA_VERSION
