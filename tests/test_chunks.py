"""D1/D2：分块导出、拼回预检、事务写入与恢复。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_epublizer import orchestrator as orch
from auto_epublizer.chunks import (
    assemble_unit,
    export_chunks,
    recover_chunks,
    split_blocks,
)
from auto_translator.translation.align import read_align


def _store(tmp_path: Path):
    src = tmp_path / "book.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        "# 第一章\n\n第一段。\n\n第二段。\n\n```\ncode\n\ninside\n```\n\n第三段。\n",
        encoding="utf-8",
    )
    return orch.init(str(src), workspace_dir=str(tmp_path / "ws"))


def _write_translation(store, unit: str = "ch01") -> None:
    chunk = store.preprocessing_dir / "chunks" / unit / "0001.zh.md"
    chunk.write_text(
        "# 第一章\n\n第一段译文。\n\n第二段译文。\n\n```\ncode\n\ninside\n```\n\n第三段译文。\n",
        encoding="utf-8",
    )


def test_split_blocks_keeps_fenced_code_intact() -> None:
    blocks = split_blocks("# T\n\na\n\n```\nx\n\ny\n```\n\nb\n")
    assert blocks == ["# T", "a", "```\nx\n\ny\n```", "b"]


def test_export_and_assemble_preflight(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = export_chunks(store)
    assert result["units"][0]["chunks"] == 1
    index = json.loads((store.preprocessing_dir / "chunks" / "ch01" / "index.json").read_text())
    assert index["source_sha256"]
    assert index["chunks"][0]["blocks"] == 5

    _write_translation(store)
    preview = assemble_unit(store, "ch01")
    assert preview["applied"] is False
    assert not (store.translation_dir / "body" / "ch01.md").exists()

    applied = assemble_unit(store, "ch01", apply=True)
    assert applied["applied"] is True
    md = (store.translation_dir / "body" / "ch01.md").read_text(encoding="utf-8")
    assert "第一段译文。" in md
    rows = read_align(store.translation_dir / "align" / "ch01.jsonl")
    assert [r["seq"] for r in rows] == list(range(1, len(rows) + 1))
    assert all(r["src"] and r["tgt"] for r in rows)
    assert not any(r["src"].startswith("#") for r in rows)


def test_assemble_rejects_stale_source_and_block_mismatch(tmp_path: Path) -> None:
    store = _store(tmp_path)
    export_chunks(store)
    _write_translation(store)
    source = store.structured_dir / "body" / "ch01.md"
    source.write_text(source.read_text(encoding="utf-8") + "\n新增。\n", encoding="utf-8")
    with pytest.raises(ValueError, match="源文已变更"):
        assemble_unit(store, "ch01")

    store2 = _store(tmp_path / "b")
    export_chunks(store2)
    (store2.preprocessing_dir / "chunks" / "ch01" / "0001.zh.md").write_text(
        "# 第一章\n\n只有一段。\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="块数不一致"):
        assemble_unit(store2, "ch01")


def test_recover_restores_pending_transaction(tmp_path: Path) -> None:
    store = _store(tmp_path)
    export_chunks(store)
    _write_translation(store)
    assemble_unit(store, "ch01", apply=True)
    journals = sorted((store.preprocessing_dir / "chunk-transactions").glob("*.json"))
    assert journals
    data = json.loads(journals[0].read_text(encoding="utf-8"))
    data["status"] = "pending"
    journals[0].write_text(json.dumps(data), encoding="utf-8")
    target = store.translation_dir / "body" / "ch01.md"
    target.write_text("broken", encoding="utf-8")

    restored = recover_chunks(store)
    assert restored["restored"] == ["ch01"]
    assert not target.exists()  # 事务写入前不存在 → 回滚为不存在


def test_reexport_after_source_change_requires_explicit_reset(tmp_path: Path) -> None:
    """P1：源文变更后重导出不得静默改写索引；reset 归档旧块后可重新导出。"""
    from auto_epublizer.chunks import reset_unit

    store = _store(tmp_path)
    export_chunks(store)
    source = store.structured_dir / "body" / "ch01.md"
    source.write_text(source.read_text(encoding="utf-8") + "\n新增段落。\n", encoding="utf-8")
    with pytest.raises(ValueError, match="源文已变更"):
        export_chunks(store)

    preview = reset_unit(store, "ch01")
    assert not Path(preview["target"]).exists()
    applied = reset_unit(store, "ch01", apply=True)
    assert Path(applied["target"]).is_dir()
    assert export_chunks(store)["units"][0]["chunks"] == 1


def test_import_tr_preview_apply_and_count_mismatch(tmp_path: Path) -> None:
    """D1：旧 .tr 导入默认只预览；数量不符拒绝。"""
    from auto_epublizer.chunks import import_tr

    store = _store(tmp_path)
    export_chunks(store)
    tr = tmp_path / "tr" / "ch01"
    tr.mkdir(parents=True)
    (tr / "0001.zh.md").write_text("# 第一章\n\n第一段。\n", encoding="utf-8")
    preview = import_tr(store, tmp_path / "tr")
    assert preview["files"] == 1
    assert not (store.preprocessing_dir / "chunks" / "ch01" / "0001.zh.md").exists()

    applied = import_tr(store, tmp_path / "tr", apply=True)
    assert applied["files"] == 1
    assert (store.preprocessing_dir / "chunks" / "ch01" / "0001.zh.md").is_file()

    (tr / "0002.zh.md").write_text("多余文件", encoding="utf-8")
    with pytest.raises(ValueError, match="不一致"):
        import_tr(store, tmp_path / "tr")


def test_assemble_refuses_to_overwrite_hand_edited_translation(tmp_path: Path) -> None:
    """D2：正式译文有新编辑时不得被旧分块静默覆盖。"""
    store = _store(tmp_path)
    export_chunks(store)
    _write_translation(store)
    assemble_unit(store, "ch01", apply=True)
    target = store.translation_dir / "body" / "ch01.md"
    target.write_text("手工修订", encoding="utf-8")
    with pytest.raises(ValueError, match="拒绝覆盖"):
        assemble_unit(store, "ch01", apply=True)
    assert target.read_text(encoding="utf-8") == "手工修订"
    assemble_unit(store, "ch01", apply=True, force=True)
    assert "第一段译文。" in target.read_text(encoding="utf-8")


def test_tampered_index_paths_are_rejected(tmp_path: Path) -> None:
    """D2：索引中的越界路径不得让 assemble 写出工作区。"""
    store = _store(tmp_path)
    export_chunks(store)
    _write_translation(store)
    index_path = store.preprocessing_dir / "chunks" / "ch01" / "index.json"
    data = json.loads(index_path.read_text(encoding="utf-8"))
    data["source_rel"] = "../../../etc/passwd"
    index_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="路径非法"):
        assemble_unit(store, "ch01")


def test_assemble_rolls_back_when_write_fails(tmp_path: Path, monkeypatch) -> None:
    """D2：写入边界失败时恢复旧版本，不留下半套 md。"""
    import auto_epublizer.chunks as chunks_mod

    store = _store(tmp_path)
    export_chunks(store)
    _write_translation(store)
    real = chunks_mod._atomic_write

    def boom(path, data):
        if path.name == "ch01.md":
            raise OSError("disk full")
        return real(path, data)

    monkeypatch.setattr(chunks_mod, "_atomic_write", boom)
    with pytest.raises(OSError):
        assemble_unit(store, "ch01", apply=True)
    assert not (store.translation_dir / "body" / "ch01.md").exists()
    journals = list((store.preprocessing_dir / "chunk-transactions").glob("*.json"))
    assert json.loads(journals[0].read_text(encoding="utf-8"))["status"] == "rolled_back"


def test_reexport_rejects_changed_max_chars(tmp_path: Path) -> None:
    """P2：分组参数变化也不得静默改写索引。"""
    store = _store(tmp_path)
    export_chunks(store)
    with pytest.raises(ValueError, match="参数/规则版本"):
        export_chunks(store, max_chars=200)


def test_recover_rejects_journal_paths_outside_translation(tmp_path: Path) -> None:
    """P1：伪造事务日志不得删除工作区外文件。"""
    store = _store(tmp_path)
    export_chunks(store)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep", encoding="utf-8")
    journal_dir = store.preprocessing_dir / "chunk-transactions"
    journal_dir.mkdir(parents=True)
    (journal_dir / "evil.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "unit": "ch01",
                "status": "pending",
                "files": [{"path": "../victim.txt", "existed": False, "old": ""}],
            }
        ),
        encoding="utf-8",
    )
    result = recover_chunks(store)
    assert result["errors"]
    assert victim.read_text(encoding="utf-8") == "keep"


def test_reset_rejects_non_unit_id(tmp_path: Path) -> None:
    from auto_epublizer.chunks import reset_unit

    store = _store(tmp_path)
    with pytest.raises(ValueError, match="文件名非法"):
        reset_unit(store, "..")


def test_assemble_refuses_to_overwrite_hand_edited_align(tmp_path: Path) -> None:
    """D2：单独编辑 align 也会触发冲突，不静默覆盖。"""
    store = _store(tmp_path)
    export_chunks(store)
    _write_translation(store)
    assemble_unit(store, "ch01", apply=True)
    align = store.translation_dir / "align" / "ch01.jsonl"
    align.write_text('{"seq": 1, "src": "x", "tgt": "y", "note": null}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="拒绝覆盖"):
        assemble_unit(store, "ch01", apply=True)
    assert '"seq": 1, "src": "x"' in align.read_text(encoding="utf-8")
