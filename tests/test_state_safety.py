"""A 组：状态、恢复与跨文件一致性（原子提交 / 并发写 / 中断恢复 / 幂等 / 源不可变）。

覆盖计划 §A 的验收：失败后旧状态可读、无错误完成态；重复运行产物与业务计数不
被错误累加；源文件与用户原件字节不变。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from auto_common.config import Config
from auto_common.workspace import RunStore, atomic_write_json, init_workspace, source_sha256
from auto_epublizer import orchestrator as orch

# ── 原子写：失败保全旧值 / 并发不共享临时文件 ────────────────────────────


def test_atomic_write_json_failure_keeps_old_target_and_cleans_tmp(tmp_path: Path) -> None:
    """写到一半失败：旧状态可读、不留半成品/临时文件（A 组故障注入）。"""
    target = tmp_path / "state.json"
    target.write_text('{"old": 1}\n', encoding="utf-8")

    class Boom:  # 不可 JSON 序列化 → 在写入途中抛 TypeError
        pass

    with pytest.raises(TypeError):
        atomic_write_json(target, {"x": Boom()})
    assert json.loads(target.read_text(encoding="utf-8")) == {"old": 1}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.json"]  # 临时文件已清理


def test_atomic_write_json_concurrent_writers_do_not_share_tmp(tmp_path: Path) -> None:
    """并发写同一目标：临时文件唯一 → 两个写入者都成功，目标始终是完整 JSON。

    修复前（固定 ``<name>.tmp``）：写者 B 会截断写者 A 正持有的临时文件，A 的
    ``os.replace`` 因临时文件已被 B 移走而抛 FileNotFoundError，且目标可能被就地
    交错写入——本用例即该竞态的确定性复现。
    """
    from auto_common.workspace import store as store_mod

    target = tmp_path / "state.json"
    target.write_text('{"initial": true}\n', encoding="utf-8")
    first_started = threading.Event()
    release_first = threading.Event()

    class SlowFirstDump:
        """只在第一次 dump 时：写一半后阻塞，模拟「另一个写入者还在写」。"""

        def __init__(self) -> None:
            self.calls = 0

        def dump(self, obj: object, f, **kw: object) -> None:  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                # 写者 A 持有自己的临时文件（尚未落盘），等 B 完成整轮后再继续
                first_started.set()
                assert release_first.wait(timeout=5)
            json.dump(obj, f, **kw)  # type: ignore[arg-type]

        def __getattr__(self, name: str):  # 其余属性透传给真实 json 模块
            return getattr(json, name)

    proxy = SlowFirstDump()
    original = store_mod.json
    store_mod.json = proxy  # type: ignore[assignment]
    errors: list[BaseException] = []

    def writer_a() -> None:
        try:
            atomic_write_json(target, {"thread_a": "finished"})
        except BaseException as e:  # noqa: BLE001 - 记录供断言
            errors.append(e)

    thread = threading.Thread(target=writer_a)
    try:
        thread.start()
        assert first_started.wait(timeout=5)
        # 主线程（写者 B）在 A 仍持有临时文件时完成一次写入
        atomic_write_json(target, {"thread_b": "finished"})
        release_first.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
    finally:
        store_mod.json = original  # type: ignore[assignment]

    assert errors == []
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data in ({"thread_a": "finished"}, {"thread_b": "finished"})


# ── 中断恢复 ────────────────────────────────────────────────────────────


def test_interrupted_init_before_publication_can_be_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """init 在提交 publication.json 前中断 → 无「半成功」状态，重跑 init 成功。"""
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.\n", encoding="utf-8")
    ws = tmp_path / "ws"
    ws_dir = ws / "book"

    def boom(self: RunStore, pub: object) -> None:
        raise RuntimeError("interrupted before commit")

    monkeypatch.setattr(RunStore, "save_publication", boom)
    with pytest.raises(RuntimeError):
        orch.init(str(src), workspace_dir=str(ws))
    assert not (ws_dir / "publication.json").is_file()  # 最终标记未落 => 未完成

    monkeypatch.undo()
    store = orch.init(str(src), workspace_dir=str(ws))
    pub = store.load_publication()
    assert pub.meta.source_sha256 == source_sha256(src)
    assert [u.id for u in pub.units] == ["ch01"]


def test_rebuild_recovers_interrupted_structure(tmp_path: Path) -> None:
    """init 完成但结构未写完（publication 有、units 空）→ preprocess --force 恢复。"""
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.\n", encoding="utf-8")
    store = init_workspace(str(src), workspace_dir=str(tmp_path / "ws"))
    pub = store.load_publication()
    assert pub.units == []  # 模拟结构阶段未跑/被中断

    result = orch.rebuild(store, config=Config())
    pub2 = store.load_publication()
    assert [u.id for u in pub2.units] == ["ch01"]
    assert {u.status for u in pub2.units} == {"split"}  # 重置为可安全续跑的状态
    assert (store.structured_dir / "body" / "ch01.md").is_file()
    assert result["facts"]["structure"]["totals"]["units"] == 1


# ── 源不可变 / 幂等 ─────────────────────────────────────────────────────


def _pipeline_ws(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.\n\nSecond sentence.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    orch.preprocess(store, config=Config())
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n第一句话。\n\n第二句话。\n", encoding="utf-8"
    )
    (store.translation_dir / "align").mkdir(parents=True, exist_ok=True)
    with open(store.unit_align_path("ch01"), "w", encoding="utf-8") as f:
        for row in [
            {"seq": 1, "src": "First sentence.", "tgt": "第一句话。", "note": None},
            {"seq": 2, "src": "Second sentence.", "tgt": "第二句话。", "note": None},
        ]:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return src, store


def test_full_pipeline_keeps_source_and_originals_byte_identical(tmp_path: Path) -> None:
    """全链路（init→preprocess→import→build→qa）后源文件与工作区源副本字节不变。"""
    src, store = _pipeline_ws(tmp_path)
    before = src.read_bytes()
    before_sha = source_sha256(src)
    copy_path = store.dir / store.load_publication().meta.source
    copy_before = copy_path.read_bytes()

    assert orch.import_translations(store)["imported"] == ["ch01"]
    assert orch.build(store).is_file()
    cfg = Config()
    cfg.qc.epubcheck.jar = str(tmp_path / "no-such-epubcheck.jar")  # 跳过外部工具
    report = orch.qa(store, config=cfg)
    assert report["epubcheck"]["ran"] is False

    assert src.read_bytes() == before
    assert source_sha256(src) == before_sha
    assert copy_path.read_bytes() == copy_before


def test_rerun_preprocess_import_qa_do_not_accumulate(tmp_path: Path) -> None:
    """重复运行不累加：单元数/词数/facts 统计与 qa 计数在重跑后保持一致。"""
    _src, store = _pipeline_ws(tmp_path)
    orch.preprocess(store, config=Config())
    facts1 = json.loads((store.preprocessing_dir / "facts.json").read_text(encoding="utf-8"))
    ids1 = [u.id for u in store.load_publication().units]

    orch.preprocess(store, config=Config())
    facts2 = json.loads((store.preprocessing_dir / "facts.json").read_text(encoding="utf-8"))
    assert [u.id for u in store.load_publication().units] == ids1
    assert facts1["structure"]["totals"] == facts2["structure"]["totals"]

    r1 = orch.import_translations(store)
    r2 = orch.import_translations(store)
    assert [len(r1["imported"]), len(r1["warnings"])] == [len(r2["imported"]), len(r2["warnings"])]
    assert store.load_publication().unit("ch01").status == "aligned"

    epub = orch.build(store)
    cfg = Config()
    cfg.qc.epubcheck.jar = str(tmp_path / "no-such-epubcheck.jar")
    q1 = orch.qa(store, epub_path=str(epub), config=cfg)
    q2 = orch.qa(store, epub_path=str(epub), config=cfg)
    assert len(q1["g0_flags"]) == len(q2["g0_flags"])
    assert q1["units_missing"] == q2["units_missing"] == 0
    assert q1["total_sentences"] == q2["total_sentences"] == 2


def test_source_identity_rejects_same_name_different_content(tmp_path: Path) -> None:
    """同名不同内容不得静默复用工作区状态（源哈希绑定）。"""
    from auto_common.workspace.store import SourceIdentityError

    src, store = _pipeline_ws(tmp_path)
    other = tmp_path / "book.md"
    other.write_text("# Chapter I\n\nCompletely different text.\n", encoding="utf-8")
    with pytest.raises(SourceIdentityError):
        store.ensure_source_identity(other)
