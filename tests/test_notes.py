"""N 阶段：注释候选盘点 / notes.json 登记门 / 翻译导入门 / next_tasks（离线合成样本）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_common.config import Config
from auto_epublizer import notes as notes_mod
from auto_epublizer import orchestrator as orch


def _unit_md(store, unit_id: str = "ch01") -> Path:
    pub = store.load_publication()
    rel = (pub.unit(unit_id).meta or {})["rel_path"]
    return store.structured_dir / rel


def _src_notes(store, *, text: str = "Source note text.", marker_in_body: bool = True):
    pub = store.load_publication()
    if marker_in_body:
        md = _unit_md(store).read_text(encoding="utf-8")
        _unit_md(store).write_text(
            md.replace("First sentence.", "First sentence.[^ref-000001]"), encoding="utf-8"
        )
    return {
        "schema_version": "1",
        "source_sha256": pub.meta.source_sha256,
        "inventory": "present",
        "notes": [
            {
                "note_id": "n-000001",
                "scope_id": "ch01",
                "source_label": "1",
                "note_type": "footnote",
                "source_markdown": text,
                "source_locations": [{"kind": "page", "page": 3, "text_block": "First sentence."}],
                "status": "verified",
            }
        ],
        "references": [
            {
                "ref_id": "ref-000001",
                "note_id": "n-000001",
                "unit": "ch01",
                "scope_id": "ch01",
                "label_text": "1",
                "context": "First sentence.",
                "status": "verified",
            }
        ],
    }


def _notes_ws(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.1\n\n[^1]: Source note text.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    return store


def _register(store, data=None):
    data = data if data is not None else _src_notes(store)
    (store.structured_dir / "notes.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    return orch.register_notes(store)


def _write_translation(store, *, md: str, rows: list[dict], target_notes: dict | None = None):
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(md, encoding="utf-8")
    (store.translation_dir / "align").mkdir(parents=True, exist_ok=True)
    with open(store.unit_align_path("ch01"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if target_notes is not None:
        (store.translation_dir / "notes.json").write_text(
            json.dumps(target_notes, ensure_ascii=False), encoding="utf-8"
        )


def _tgt_notes(store, *, text: str = "注释文本。"):
    digest = notes_mod.file_digest(notes_mod.source_notes_path(store))
    return {
        "schema_version": "1",
        "source_notes_sha256": digest,
        "notes": [{"note_id": "n-000001", "target_markdown": text}],
    }


# ── N1 候选盘点 ──────────────────────────────────────────────────────────


def test_candidates_export_and_disposition_preserved(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text(
        "# 第一章\n\n他说了话。1 又补充道。\n\n(机关)14 随后发言。\n\n241 库贝茨基，Drütte-Prozeß。\n",
        encoding="utf-8",
    )
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    result = orch.notes_candidates(store)
    assert result["candidates"] >= 3
    assert {"marker", "numbered_paragraph"} <= set(result["by_kind"])
    path = Path(result["path"])
    rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()]
    # 逐条核证：给第一条标处置；重跑导出必须保留（候选身份不含行号）
    rows[0]["disposition"] = "not_note"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    result2 = orch.notes_candidates(store)
    assert result2["dispositions_kept"] == 1
    rows2 = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()]
    assert rows2[0]["candidate_id"] == rows[0]["candidate_id"]
    assert rows2[0]["disposition"] == "not_note"


# ── N2/N3 登记门 ────────────────────────────────────────────────────────


def test_register_notes_validates_and_writes_summary(tmp_path: Path) -> None:
    store = _notes_ws(tmp_path)
    result = _register(store)
    assert result["summary"]["notes"] == 1
    assert result["summary"]["references"] == 1
    reloaded = store.load_publication()
    assert reloaded.notes is not None
    assert reloaded.notes["source_notes_sha256"] == notes_mod.file_digest(
        notes_mod.source_notes_path(store)
    )
    # 幂等：重复登记摘要不变
    again = orch.register_notes(store)
    assert again["summary"] == result["summary"]


def test_register_notes_blocks_unresolved_or_unbound(tmp_path: Path) -> None:
    store = _notes_ws(tmp_path)
    data = _src_notes(store)
    data["notes"][0]["status"] = "unresolved"
    with pytest.raises(orch.OrchestrationError) as ei:
        _register(store, data)
    assert "unresolved" in str(ei.value)

    store2 = _notes_ws(tmp_path / "b")
    data2 = _src_notes(store2, marker_in_body=False)  # 正文缺原位标记
    with pytest.raises(orch.OrchestrationError) as ei2:
        _register(store2, data2)
    assert "缺原位标记" in str(ei2.value)


def test_register_notes_blocks_unregistered_marker(tmp_path: Path) -> None:
    store = _notes_ws(tmp_path)
    data = _src_notes(store)
    md = _unit_md(store).read_text(encoding="utf-8")
    _unit_md(store).write_text(md + "\n[^ref-000099] 额外标记\n", encoding="utf-8")
    with pytest.raises(orch.OrchestrationError) as ei:
        _register(store, data)
    assert "未登记的标记" in str(ei.value)


def test_register_notes_none_inventory_zero_to_zero(tmp_path: Path) -> None:
    store = _notes_ws(tmp_path)
    pub = store.load_publication()
    data = {
        "schema_version": "1",
        "source_sha256": pub.meta.source_sha256,
        "inventory": "none",
        "notes": [],
        "references": [],
    }
    result = _register(store, data)
    assert result["summary"]["inventory"] == "none"
    assert result["summary"]["notes"] == 0


def test_register_notes_blocks_unverified_inventory(tmp_path: Path) -> None:
    store = _notes_ws(tmp_path)
    data = _src_notes(store)
    data["inventory"] = "unverified"
    data["notes"] = []
    data["references"] = []
    with pytest.raises(orch.OrchestrationError) as ei:
        _register(store, data)
    assert "unverified" in str(ei.value)


def test_register_notes_blocks_undisposed_candidates(tmp_path: Path) -> None:
    store = _notes_ws(tmp_path)
    orch.notes_candidates(store)  # 生成候选（全部未决）
    with pytest.raises(orch.OrchestrationError) as ei:
        _register(store)
    assert "候选未全部处置" in str(ei.value)


# ── 翻译导入门 ──────────────────────────────────────────────────────────


def test_import_gate_requires_marker_and_translation_notes(tmp_path: Path) -> None:
    store = _notes_ws(tmp_path)
    _register(store)
    rows = [
        {
            "seq": 1,
            "src": "First sentence.[^ref-000001]",
            "tgt": "第一句话[^ref-000001]。",
            "note": None,
        }
    ]
    # 1) 译文缺标记 → 阻断
    _write_translation(store, md="# 第一章\n\n第一句话。\n", rows=rows)
    r1 = orch.import_translations(store)
    assert r1["imported"] == []
    assert any("注释标记" in e for e in r1["failed"][0]["errors"])

    # 2) 标记齐全但缺译注 → 阻断
    _write_translation(
        store, md="# 第一章\n\n第一句话[^ref-000001]。\n", rows=rows, target_notes=None
    )
    r2 = orch.import_translations(store)
    assert any("缺 translation/notes.json" in e for e in r2["failed"][0]["errors"])

    # 3) 译注齐全 → 通过
    _write_translation(
        store,
        md="# 第一章\n\n第一句话[^ref-000001]。\n",
        rows=rows,
        target_notes=_tgt_notes(store),
    )
    r3 = orch.import_translations(store)
    assert r3["imported"] == ["ch01"], r3["failed"]


def test_import_gate_blocks_stale_translation_notes_digest(tmp_path: Path) -> None:
    store = _notes_ws(tmp_path)
    _register(store)
    stale = _tgt_notes(store)
    stale["source_notes_sha256"] = "0" * 64
    _write_translation(
        store,
        md="# 第一章\n\n第一句话[^ref-000001]。\n",
        rows=[
            {
                "seq": 1,
                "src": "First sentence.[^ref-000001]",
                "tgt": "第一句话[^ref-000001]。",
                "note": None,
            }
        ],
        target_notes=stale,
    )
    # F3：导入路径的译注要求由**逐单元门**承担（按被导入单元的实际使用判定），
    # 共享加载入口不重复要求——过期绑定仍在导入门逐条阻断（含「摘要不符」）。
    result = orch.import_translations(store)
    assert result["failed"], result
    assert any("摘要不符" in e for e in result["failed"][0]["errors"])


def test_import_blocks_when_source_notes_changed_after_register(tmp_path: Path) -> None:
    store = _notes_ws(tmp_path)
    _register(store)
    # 源注文被改动但未重登记 → import 明确失败（失效链，不静默沿用旧绑定）
    (store.structured_dir / "notes.json").write_text(
        json.dumps(
            {
                **json.loads((store.structured_dir / "notes.json").read_text(encoding="utf-8")),
                "x": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(orch.OrchestrationError) as ei:
        orch.import_translations(store)
    assert "与登记摘要不一致" in str(ei.value)


# ── N3 status / next_tasks ──────────────────────────────────────────────


def test_next_tasks_drive_notes_verify_register_then_translate(tmp_path: Path) -> None:
    store = _notes_ws(tmp_path)
    orch.preprocess(store, config=Config())
    for name in ("capabilities.md", "global.md", "todo.md"):
        (store.preprocessing_dir / name).write_text("x", encoding="utf-8")
    orch.notes_candidates(store)
    head = orch.status(store)["next_tasks"][0]
    assert head["kind"] == "notes_verify"
    # 处置全部候选 → 下一个任务是 notes register
    path = notes_mod.candidates_path(store)
    rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()]
    for r in rows:
        r["disposition"] = "not_note"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    head2 = orch.status(store)["next_tasks"][0]
    assert head2["kind"] == "notes_register"
    # 登记后不再有注释前置任务
    _register(store)
    kinds = [t["kind"] for t in orch.status(store)["next_tasks"]]
    assert "notes_verify" not in kinds and "notes_register" not in kinds


def test_notes_status_reports_stale_after_change(tmp_path: Path) -> None:
    store = _notes_ws(tmp_path)
    _register(store)
    st = orch.notes_status(store)
    assert st["stale"] is False and st["registered"]["notes"] == 1
    path = notes_mod.source_notes_path(store)
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    st2 = orch.notes_status(store)
    assert st2["stale"] is True
    assert any(s["id"] == "notes" for s in orch.status(store)["stale"])


def test_notes_candidates_readonly_does_not_touch_structured(tmp_path: Path) -> None:
    store = _notes_ws(tmp_path)
    before = _unit_md(store).read_bytes()
    orch.notes_candidates(store)
    assert _unit_md(store).read_bytes() == before


def test_status_metadata_cache_mentions_notes_field(tmp_path: Path) -> None:
    """publication.json 的 notes 字段默认 None（旧工作区照常解析）。"""
    store = _notes_ws(tmp_path)
    assert store.load_publication().notes is None
    assert orch.status(store)["notes"]["registered"] is None


def test_config_unused_but_importable() -> None:
    """哨兵：Config 默认值未被本阶段改动（防误改配置契约）。"""
    cfg = Config()
    assert cfg.qc.length_ratio["min_src_chars"] == 20


# ── N4 全书级语义构建 ───────────────────────────────────────────────────


def _two_chapter_ws(tmp_path: Path):
    """两章 + 三条引用（一条跨章复引、一条章内重号）。"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter I\n\nFirst sentence.1\n\n# Chapter II\n\nSecond sentence.2\n\nThird sentence.3\n",
        encoding="utf-8",
    )
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    pub = store.load_publication()
    sha = pub.meta.source_sha256

    def _md(unit: str) -> Path:
        rel = (pub.unit(unit).meta or {})["rel_path"]
        return store.structured_dir / rel

    md1 = (
        _md("ch01")
        .read_text(encoding="utf-8")
        .replace("First sentence.", "First sentence.[^ref-000001]")
    )
    _md("ch01").write_text(md1, encoding="utf-8")
    md2 = (
        _md("ch02")
        .read_text(encoding="utf-8")
        .replace("Second sentence.", "Second sentence.[^ref-000002]")
        .replace("Third sentence.", "Third sentence.[^ref-000003]")
    )
    _md("ch02").write_text(md2, encoding="utf-8")
    data = {
        "schema_version": "1",
        "source_sha256": sha,
        "inventory": "present",
        "notes": [
            {
                "note_id": "n-000001",
                "scope_id": "ch01",
                "source_label": "1",
                "note_type": "footnote",
                "source_markdown": "First note.",
                "source_locations": [{"kind": "page", "page": 1}],
                "status": "verified",
            },
            {
                "note_id": "n-000002",
                "scope_id": "ch02",
                "source_label": "1",
                "note_type": "footnote",
                "source_markdown": "Second note.",
                "source_locations": [{"kind": "page", "page": 2}],
                "status": "verified",
            },
        ],
        "references": [
            {
                "ref_id": "ref-000001",
                "note_id": "n-000001",
                "unit": "ch01",
                "scope_id": "ch01",
                "label_text": "1",
                "context": "First sentence.",
                "status": "verified",
            },
            {
                "ref_id": "ref-000002",
                "note_id": "n-000001",
                "unit": "ch02",
                "scope_id": "ch02",
                "label_text": "2",
                "context": "Second sentence.",
                "status": "verified",
            },
            {
                "ref_id": "ref-000003",
                "note_id": "n-000002",
                "unit": "ch02",
                "scope_id": "ch02",
                "label_text": "3",
                "context": "Third sentence.",
                "status": "verified",
            },
        ],
    }
    (store.structured_dir / "notes.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    orch.register_notes(store)
    digest = notes_mod.file_digest(notes_mod.source_notes_path(store))
    return store, digest


def _write_two_chapter_translation(store, digest: str, *, tgt_texts: dict[str, str] | None = None):
    texts = tgt_texts or {"n-000001": "第一条注。", "n-000002": "第二条注。"}
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "align").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n第一句话。[^ref-000001]\n", encoding="utf-8"
    )
    (store.translation_dir / "body" / "ch02.md").write_text(
        "# 第二章\n\n第二句话。[^ref-000002]\n\n第三句话。[^ref-000003]\n", encoding="utf-8"
    )
    align = {
        "ch01": [
            {
                "seq": 1,
                "src": "First sentence.[^ref-000001]",
                "tgt": "第一句话。[^ref-000001]",
                "note": None,
            }
        ],
        "ch02": [
            {
                "seq": 1,
                "src": "Second sentence.[^ref-000002]",
                "tgt": "第二句话。[^ref-000002]",
                "note": None,
            },
            {
                "seq": 2,
                "src": "Third sentence.[^ref-000003]",
                "tgt": "第三句话。[^ref-000003]",
                "note": None,
            },
        ],
    }
    for unit, rows in align.items():
        with open(store.unit_align_path(unit), "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (store.translation_dir / "notes.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "source_notes_sha256": digest,
                "notes": [
                    {"note_id": "n-000001", "target_markdown": texts["n-000001"]},
                    {"note_id": "n-000002", "target_markdown": texts["n-000002"]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _read_epub(epub: Path, name: str) -> str:
    import zipfile

    with zipfile.ZipFile(epub) as zf:
        return zf.read(f"OEBPS/{name}").decode("utf-8")


def test_build_renders_semantic_notes_with_cross_file_backlinks(tmp_path: Path) -> None:
    store, digest = _two_chapter_ws(tmp_path)
    _write_two_chapter_translation(store, digest)
    result = orch.import_translations(store)
    assert result["imported"] == ["ch01", "ch02"], result["failed"]
    epub = orch.build(store)
    ch01 = _read_epub(epub, "ch01.xhtml")
    ch02 = _read_epub(epub, "ch02.xhtml")
    # noteref 语义锚点 + 跨文件 href（ch02 的复引指向 ch01 的宿主注文）
    assert 'epub:type="noteref"' in ch01 and 'id="ref-000001"' in ch01
    assert 'href="ch01.xhtml#fn-n-000001"' in ch02
    # 宿主注文（aside）在 ch01，含译文与回链
    assert 'epub:type="footnote"' in ch01 and 'id="fn-n-000001"' in ch01
    assert "第一条注。" in ch01
    assert 'href="ch01.xhtml#ref-000001"' in ch01
    # 一注多引：ch01 的宿主注文带 ch02 回链
    assert 'href="ch02.xhtml#ref-000002"' in ch01
    # 章内重号：两个作用域的注文都从 [1] 起
    assert ch01.count(">[1]<") >= 1
    assert "第二条注。" in ch02 and 'id="fn-n-000002"' in ch02
    assert 'href="ch02.xhtml#fn-n-000002"' in ch02


def test_build_blocks_missing_translation_note(tmp_path: Path) -> None:
    store, digest = _two_chapter_ws(tmp_path)
    _write_two_chapter_translation(
        store, digest, tgt_texts={"n-000001": "第一条注。", "n-000002": ""}
    )
    # 绕过 import 门（直接 build）也要阻断：译文构建缺译注不得静默降级
    with pytest.raises(orch.OrchestrationError):
        orch.build(store)


def test_build_blocks_unregistered_marker(tmp_path: Path) -> None:
    store, digest = _two_chapter_ws(tmp_path)
    _write_two_chapter_translation(store, digest)
    md_path = store.translation_dir / "body" / "ch01.md"
    md_path.write_text(
        md_path.read_text(encoding="utf-8") + "\n[^ref-000099] 未登记的标记\n", encoding="utf-8"
    )
    with pytest.raises(orch.OrchestrationError) as ei:
        orch.build(store)
    assert "未登记标记" in str(ei.value)


def test_build_keeps_legacy_footnotes_when_no_notes_registered(tmp_path: Path) -> None:
    """未登记注释的工作区照常走旧 [^label] 路径（向后兼容）。"""
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence[^1].\n\n[^1]: Legacy note.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n第一句话[^1]。\n\n[^1]: 旧注。\n", encoding="utf-8"
    )
    (store.translation_dir / "align").mkdir(parents=True, exist_ok=True)
    with open(store.unit_align_path("ch01"), "w", encoding="utf-8") as f:
        for row in [
            {"seq": 1, "src": "First sentence[^1].", "tgt": "第一句话[^1]。", "note": None},
            {"seq": 2, "src": "[^1]: Legacy note.", "tgt": "[^1]: 旧注。", "note": None},
        ]:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    orch.import_translations(store)
    epub = orch.build(store)
    ch01 = _read_epub(epub, "ch01.xhtml")
    assert 'epub:type="noteref"' in ch01 and "旧注。" in ch01


# ── N5 成品门（独立解析最终 XHTML）──────────────────────────────────────


def _tamper(src: Path, dst: Path, name: str, old: str, new: str) -> Path:
    import zipfile

    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == f"OEBPS/{name}":
                text = data.decode("utf-8").replace(old, new)
                data = text.encode("utf-8")
            zout.writestr(item, data)
    return dst


def test_notes_product_gate_clean_build_passes(tmp_path: Path) -> None:
    from auto_epublizer.qa import audit_epub, audit_notes_epub

    store, digest = _two_chapter_ws(tmp_path)
    _write_two_chapter_translation(store, digest)
    orch.import_translations(store)
    epub = orch.build(store)
    ctx = notes_mod.read_notes_json(notes_mod.source_notes_path(store))
    tgt = notes_mod.read_notes_json(notes_mod.translation_notes_path(store))
    result = audit_notes_epub(
        epub, source_notes=ctx, target_notes=tgt, media_root=store.structured_dir / "raw" / "media"
    )
    assert result.ok, result.findings
    assert audit_epub(epub, notes_registered=True).ok


def test_notes_product_gate_detects_missing_anchor_and_content(tmp_path: Path) -> None:
    from auto_epublizer.qa import audit_notes_epub

    store, digest = _two_chapter_ws(tmp_path)
    _write_two_chapter_translation(store, digest)
    orch.import_translations(store)
    epub = orch.build(store)
    ctx = notes_mod.read_notes_json(notes_mod.source_notes_path(store))
    tgt = notes_mod.read_notes_json(notes_mod.translation_notes_path(store))

    # ① 锚点 id 被改 → 已登记引用缺锚点 + 出现孤儿锚点
    bad1 = _tamper(epub, tmp_path / "bad1.epub", "ch01.xhtml", 'id="ref-000001"', 'id="ref-999999"')
    r1 = audit_notes_epub(
        bad1, source_notes=ctx, target_notes=tgt, media_root=store.structured_dir / "raw" / "media"
    )
    codes1 = {f["code"] for f in r1.findings}
    assert "E_NOTES_ANCHOR_MISSING" in codes1
    assert "E_NOTES_ORPHAN_ANCHOR" in codes1
    assert not r1.ok

    # ② 注文内容被改 → 内容核对失败
    bad2 = _tamper(epub, tmp_path / "bad2.epub", "ch01.xhtml", "第一条注。", "被替换的注文。")
    r2 = audit_notes_epub(
        bad2, source_notes=ctx, target_notes=tgt, media_root=store.structured_dir / "raw" / "media"
    )
    assert "E_NOTES_CONTENT_MISMATCH" in {f["code"] for f in r2.findings}

    # ③ 回链被删 → 缺回链
    bad3 = _tamper(
        epub,
        tmp_path / "bad3.epub",
        "ch01.xhtml",
        'href="ch01.xhtml#ref-000001"',
        'href="#ref-000001"',
    )
    r3 = audit_notes_epub(
        bad3, source_notes=ctx, target_notes=tgt, media_root=store.structured_dir / "raw" / "media"
    )
    assert "E_NOTES_BACKLINK_MISSING" in {f["code"] for f in r3.findings}


def test_notes_product_gate_none_inventory_zero_to_zero(tmp_path: Path) -> None:
    from auto_epublizer.qa import audit_notes_epub

    store = _notes_ws(tmp_path)
    pub = store.load_publication()
    data = {
        "schema_version": "1",
        "source_sha256": pub.meta.source_sha256,
        "inventory": "none",
        "notes": [],
        "references": [],
    }
    _register(store, data)
    rows = [
        {"seq": 1, "src": "First sentence.1", "tgt": "第一句话。", "note": None},
    ]
    _write_translation(store, md="# 第一章\n\n第一句话。\n", rows=rows)
    assert orch.import_translations(store)["imported"] == ["ch01"]
    epub = orch.build(store)
    result = audit_notes_epub(
        epub,
        source_notes=data,
        target_notes=None,
        media_root=store.structured_dir / "raw" / "media",
    )
    assert result.ok, result.findings
    # 注入一个未登记的 noteref → 无注书不得有语义注释
    bad = _tamper(
        epub,
        tmp_path / "none-bad.epub",
        "ch01.xhtml",
        "第一句话。",
        '第一句话。<a epub:type="noteref" id="ref-000001" href="#fn-x">[1]</a>',
    )
    r2 = audit_notes_epub(
        bad, source_notes=data, target_notes=None, media_root=store.structured_dir / "raw" / "media"
    )
    assert "E_NOTES_NONE_UNEXPECTED" in {f["code"] for f in r2.findings}


def test_report_blocks_release_on_notes_findings() -> None:
    from auto_epublizer.qa import AuditResult, EpubcheckResult, generate_report

    result = generate_report(
        "book",
        AuditResult(ok=True),
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0, returncode=0),
        notes_audit={
            "findings": [{"level": "error", "code": "E_NOTES_ANCHOR_MISSING", "message": "缺锚点"}],
            "missing": ["ref-000001"],
        },
    )
    assert result.released is False
    assert result.released_reason == "notes_open"
    assert result.notes_missing == ["ref-000001"]


def test_notes_gate_partial_omission_locates_remaining_ref(tmp_path: Path) -> None:
    """部分遗漏：只丢一条引用时，门必须精确定位**那一条**（不是整本书报错）。"""
    from auto_epublizer.qa import audit_notes_epub

    store, digest = _two_chapter_ws(tmp_path)
    _write_two_chapter_translation(store, digest)
    orch.import_translations(store)
    epub = orch.build(store)
    ctx = notes_mod.read_notes_json(notes_mod.source_notes_path(store))
    tgt = notes_mod.read_notes_json(notes_mod.translation_notes_path(store))
    bad = _tamper(epub, tmp_path / "partial.epub", "ch02.xhtml", 'id="ref-000003"', 'id="ref-x"')
    r = audit_notes_epub(
        bad, source_notes=ctx, target_notes=tgt, media_root=store.structured_dir / "raw" / "media"
    )
    assert r.missing == ["ref-000003"]
    assert "E_NOTES_ANCHOR_MISSING" in {f["code"] for f in r.findings}


def test_notes_gate_detects_equal_count_swap(tmp_path: Path) -> None:
    """等量错配：两条注文互换内容（总数不变）也必须被内容核对抓住。"""
    from auto_epublizer.qa import audit_notes_epub

    store, digest = _two_chapter_ws(tmp_path)
    _write_two_chapter_translation(store, digest)
    orch.import_translations(store)
    epub = orch.build(store)
    ctx = notes_mod.read_notes_json(notes_mod.source_notes_path(store))
    tgt = notes_mod.read_notes_json(notes_mod.translation_notes_path(store))
    bad = _tamper(epub, tmp_path / "swap.epub", "ch01.xhtml", "第一条注。", "第二条注。")
    r = audit_notes_epub(
        bad, source_notes=ctx, target_notes=tgt, media_root=store.structured_dir / "raw" / "media"
    )
    assert "E_NOTES_CONTENT_MISMATCH" in {f["code"] for f in r.findings}
    assert r.missing == ["n-000001"]


def test_notes_gate_supports_multi_paragraph_note(tmp_path: Path) -> None:
    """多段注文：完整块级 Markdown 渲染且内容核对通过（不压平、不截断）。"""
    from auto_epublizer.qa import audit_notes_epub

    store, digest = _two_chapter_ws(tmp_path)
    multi = "第一段注文。\n\n第二段：**强调**与列表。\n\n- 甲\n- 乙"
    _write_two_chapter_translation(
        store, digest, tgt_texts={"n-000001": multi, "n-000002": "第二条注。"}
    )
    orch.import_translations(store)
    epub = orch.build(store)
    ch01 = _read_epub(epub, "ch01.xhtml")
    assert "第二段" in ch01 and "强调" in ch01 and "<li>甲</li>" in ch01
    ctx = notes_mod.read_notes_json(notes_mod.source_notes_path(store))
    tgt = notes_mod.read_notes_json(notes_mod.translation_notes_path(store))
    assert audit_notes_epub(
        epub, source_notes=ctx, target_notes=tgt, media_root=store.structured_dir / "raw" / "media"
    ).ok


def test_notes_stale_after_source_change_blocks_qa(tmp_path: Path) -> None:
    """正文/源注文 JSON 变更后，旧登记与旧报告失效：qa 明确阻断（E_NOTES_STALE）。"""
    store, digest = _two_chapter_ws(tmp_path)
    _write_two_chapter_translation(store, digest)
    orch.import_translations(store)
    epub = orch.build(store)
    path = notes_mod.source_notes_path(store)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["notes"][0]["source_markdown"] = "First note（修订）。"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    cfg = Config()
    cfg.qc.epubcheck.jar = str(tmp_path / "no-such-epubcheck.jar")  # 跳过外部工具，专注注释门
    report = orch.qa(store, epub_path=str(epub), config=cfg)
    assert report["released"] is False
    assert "E_NOTES_STALE" in {f["code"] for f in report["notes_findings"]}
    # 过期登记不能移交旧数量门：无定义正文中的成品 aside 仍应被旧门发现。
    assert report["epub_footnotes_missing"] > 0


def test_notes_with_media_are_collected_and_rendered(tmp_path: Path) -> None:
    """带媒体注文：注文内图片经 collect_media 收进 EPUB 并正常渲染（N6）。"""
    import zipfile

    from auto_epublizer.qa import audit_notes_epub

    store, digest = _two_chapter_ws(tmp_path)
    media_root = store.structured_dir / "raw" / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    (media_root / "n1.png").write_bytes(b"PNGDATA")
    text = "注文见下图。\n\n![插图](raw/media/n1.png)"
    _write_two_chapter_translation(
        store, digest, tgt_texts={"n-000001": text, "n-000002": "第二条注。"}
    )
    orch.import_translations(store)
    epub = orch.build(store)
    with zipfile.ZipFile(epub) as zf:
        assert "OEBPS/media/n1.png" in zf.namelist()
    ch01 = _read_epub(epub, "ch01.xhtml")
    assert '<img src="media/n1.png"' in ch01
    ctx = notes_mod.read_notes_json(notes_mod.source_notes_path(store))
    tgt = notes_mod.read_notes_json(notes_mod.translation_notes_path(store))
    assert audit_notes_epub(
        epub, source_notes=ctx, target_notes=tgt, media_root=store.structured_dir / "raw" / "media"
    ).ok
    bad = _tamper(
        epub,
        tmp_path / "missing-note-media.epub",
        "ch01.xhtml",
        '<img src="media/n1.png"',
        '<img src="media/missing.png"',
    )
    assert not audit_notes_epub(
        bad,
        source_notes=ctx,
        target_notes=tgt,
        media_root=media_root,
    ).ok


# ── P1 漏门回归（2026-10-15 审查回流）────────────────────────────────────────


def test_register_rejects_note_candidates_with_none_inventory(tmp_path: Path) -> None:
    """P1：已核证 note 候选与 inventory=none 矛盾 → 拒绝登记（此前可登记且门全绿）。"""
    store = _notes_ws(tmp_path)
    data = _src_notes(store)
    data["inventory"] = "none"
    data["notes"] = []
    data["references"] = []
    (store.preprocessing_dir).mkdir(parents=True, exist_ok=True)
    (store.preprocessing_dir / "note_candidates.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "candidate_id": f"c-{i}",
                    "unit": "ch01",
                    "kind": "numbered_paragraph",
                    "label": str(i),
                    "line": i,
                    "text": f"{i} Source note text.",
                    "disposition": "note",
                },
                ensure_ascii=False,
            )
            for i in (1, 2)
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(orch.OrchestrationError) as ei:
        _register(store, data)
    assert "inventory=none" in str(ei.value)


def _candidate(**kw) -> dict:
    row = {
        "candidate_id": "c-1",
        "unit": "ch01",
        "kind": "marker",
        "label": "1",
        "line": 3,
        "text": "First sentence.1",
        "disposition": "note",
    }
    row.update(kw)
    return row


def _write_candidates(store, rows: list[dict]) -> None:
    store.preprocessing_dir.mkdir(parents=True, exist_ok=True)
    (store.preprocessing_dir / "note_candidates.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def test_register_requires_bound_note_candidates(tmp_path: Path) -> None:
    """F1：判 note 的候选必须绑定稳定身份（引用型→ref_id，注文型→note_id）。"""
    store = _notes_ws(tmp_path)
    data = _src_notes(store)  # 只插一次原位标记，后续复用同一份登记数据
    # 无绑定 → 拒绝
    _write_candidates(store, [_candidate()])
    with pytest.raises(orch.OrchestrationError) as ei:
        _register(store, data)
    assert "缺少 ref_id 绑定" in str(ei.value)
    # 绑定到不存在的 ref → 拒绝
    _write_candidates(store, [_candidate(ref_id="ref-999999")])
    with pytest.raises(orch.OrchestrationError) as ei:
        _register(store, data)
    assert "不在登记图中" in str(ei.value)
    # 正例：同单元、同注号绑定 → 通过
    _write_candidates(store, [_candidate(ref_id="ref-000001")])
    assert _register(store, data)["summary"]["inventory"] == "present"
    # 重复绑定同一引用 → 拒绝
    _write_candidates(
        store,
        [
            _candidate(candidate_id="c-1", ref_id="ref-000001"),
            _candidate(candidate_id="c-2", ref_id="ref-000001", text="另一处 .1"),
        ],
    )
    with pytest.raises(orch.OrchestrationError) as ei:
        _register(store, data)
    assert "重复绑定同一引用" in str(ei.value)


def test_register_rejects_cross_unit_note_binding(tmp_path: Path) -> None:
    """F1（增量审查复现）：跨章同号候选不得用全局同号/前缀冒充第一章的注文。"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter I\n\nFirst sentence.1\n\n# Chapter II\n\nSecond sentence.\n",
        encoding="utf-8",
    )
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    # ch01 正文写原位标记；ch02 是另一章的注文（编号段落），不写标记
    md1 = store.structured_dir / "body" / "ch01.md"
    md1.write_text("# Chapter I\n\nFirst sentence.[^ref-000001]\n", encoding="utf-8")
    md2 = store.structured_dir / "body" / "ch02.md"
    md2.write_text(
        "# Chapter II\n\nSecond sentence.\n\n1 Zweiter Hinweis mit Text.\n", encoding="utf-8"
    )
    data = {
        "schema_version": "1",
        "source_sha256": store.load_publication().meta.source_sha256,
        "inventory": "present",
        "notes": [
            {
                "note_id": "n-000001",
                "scope_id": "ch01",
                "source_label": "1",
                "note_type": "footnote",
                "source_markdown": "Erste Anmerkung.",
                "source_locations": [{"kind": "page", "page": 1}],
                "status": "verified",
            }
        ],
        "references": [
            {
                "ref_id": "ref-000001",
                "note_id": "n-000001",
                "unit": "ch01",
                "scope_id": "ch01",
                "label_text": "1",
                "status": "verified",
            }
        ],
    }
    _write_candidates(
        store,
        [
            _candidate(
                candidate_id="c-c1-m",
                unit="ch01",
                kind="marker",
                label="1",
                text="First sentence.1",
                ref_id="ref-000001",
            ),
            _candidate(
                candidate_id="c-c1-d",
                unit="ch01",
                kind="numbered_paragraph",
                label="1",
                text="1 Erste Anmerkung mit Text.",
                note_id="n-000001",
            ),
            _candidate(
                candidate_id="c-c2-m",
                unit="ch02",
                kind="marker",
                label="1",
                text="Second sentence.1",
                ref_id="ref-000001",
            ),
            _candidate(
                candidate_id="c-c2-d",
                unit="ch02",
                kind="numbered_paragraph",
                label="1",
                text="1 Zweiter Hinweis mit Text.",
                note_id="n-000001",
            ),
        ],
    )
    with pytest.raises(orch.OrchestrationError) as ei:
        _register(store, data)
    msg = str(ei.value)
    assert "跨章同号" in msg or "其它单元" in msg, msg
    assert "candidate_id" in msg
    assert "c-c2-m" in msg and "c-c2-d" in msg, msg


def test_build_blocks_when_translation_notes_binding_stale(tmp_path: Path) -> None:
    """P1：源注文变更并重登记后，译注摘要不符必须在 build（共享入口）阻断。"""
    store = _notes_ws(tmp_path)
    _register(store)
    _write_translation(
        store,
        md="# 第一章\n\n第一句话[^ref-000001]。\n",
        rows=[
            {
                "seq": 1,
                "src": "First sentence.[^ref-000001]",
                "tgt": "第一句话[^ref-000001]。",
                "note": None,
            }
        ],
        target_notes={
            "schema_version": "1",
            "source_notes_sha256": notes_mod.file_digest(notes_mod.source_notes_path(store)),
            "notes": [{"note_id": "n-000001", "target_markdown": "译文注文。"}],
        },
    )
    # 源注文变更 → 旧摘要失效（重新登记后译注仍是旧绑定）
    data = _src_notes(store, text="Source note text CHANGED.", marker_in_body=False)
    _register(store, data)
    with pytest.raises(orch.OrchestrationError) as ei:
        orch.build(store)
    assert "摘要不符" in str(ei.value)


def test_notes_product_gate_flags_note_media_missing(tmp_path: Path) -> None:
    """P1：注文图片缺失不得被去图文本规范化掩盖——成品门单独核对注文媒体。"""
    store = _notes_ws(tmp_path)
    data = _src_notes(store, text="Note with image ![x](media/nope.png) here.")
    _register(store, data)
    _write_translation(
        store,
        md="# 第一章\n\n第一句话[^ref-000001]。\n",
        rows=[
            {
                "seq": 1,
                "src": "First sentence.[^ref-000001]",
                "tgt": "第一句话[^ref-000001]。",
                "note": None,
            }
        ],
        target_notes={
            "schema_version": "1",
            "source_notes_sha256": notes_mod.file_digest(notes_mod.source_notes_path(store)),
            "notes": [
                {"note_id": "n-000001", "target_markdown": "带图注文 ![x](media/nope.png)。"}
            ],
        },
    )
    orch.import_translations(store)
    epub = orch.build(store)
    result = None
    from auto_epublizer.qa.notes_audit import audit_notes_epub

    tgt = notes_mod.read_notes_json(notes_mod.translation_notes_path(store))
    result = audit_notes_epub(
        epub, source_notes=data, target_notes=tgt, media_root=store.structured_dir / "raw" / "media"
    )
    codes = [f["code"] for f in result.findings]
    assert "E_NOTES_MEDIA_MISSING" in codes, codes


def test_report_goes_stale_when_catalog_unresolved_added_after_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1：放行后新增 catalog unresolved → 报告必须过期（摘要覆盖全部放行输入）。"""
    from auto_epublizer.qa.artifacts import report_state
    from auto_epublizer.qa.epubcheck import EpubcheckResult

    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "root"))
    assert store.dir.name == "book"
    (store.translation_dir / "body").mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "body" / "ch01.md").write_text(
        "# 第一章\n\n第一句话。\n", encoding="utf-8"
    )
    (store.translation_dir / "align").mkdir(parents=True, exist_ok=True)
    (store.unit_align_path("ch01")).write_text(
        json.dumps(
            {"seq": 1, "src": "First sentence.", "tgt": "第一句话。", "note": None},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    review_dir = store.reviews_dir / "review-20261015T000000"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "result.json").write_text(
        json.dumps({"issue_count": 0, "g2_confirmed": 0, "termination": "clean_confirmed"}),
        encoding="utf-8",
    )
    orch.import_translations(store)
    for u in store.load_publication().units:
        store.set_unit_status(u.id, "reviewed")
    epub = orch.build(store)
    monkeypatch.setattr(
        orch, "run_epubcheck", lambda *a, **k: EpubcheckResult(True, True, 0, 0, returncode=0)
    )
    report = orch.qa(store, epub_path=str(epub))
    assert report["released"] is True, report.get("released_reason")
    assert report_state(store)["stale"] is False
    # 放行后新增未决源盘点 → 摘要输入变化 → 过期
    (store.preprocessing_dir / "catalog.csv").write_text(
        "item,kind,status,locator,unit_id,note\nX,figure,unresolved,page 9,,\n",
        encoding="utf-8",
    )
    state = report_state(store)
    assert state["stale"] is True, state


def test_build_allows_source_fallback_without_any_translation(tmp_path: Path) -> None:
    """F3：全源文回退构建（工作区无任何译文/译注）不得被「译注缺失」阻断。"""
    store = _notes_ws(tmp_path)
    _register(store)
    epub = orch.build(store)  # 无 translation/ 完全合法：源文回退
    assert epub.is_file()


def test_build_ignores_stale_translation_notes_when_not_used(tmp_path: Path) -> None:
    """F3：存在但**未被使用**的旧译注（源文回退路径）不得阻断构建。"""
    store = _notes_ws(tmp_path)
    _register(store)
    (store.translation_dir).mkdir(parents=True, exist_ok=True)
    (store.translation_dir / "notes.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "source_notes_sha256": "0" * 64,  # 过期绑定
                "notes": [{"note_id": "n-000001", "target_markdown": "旧译文。"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    epub = orch.build(store)  # 该译注不参与渲染 → 不校验、不阻断
    assert epub.is_file()


def test_build_blocks_when_used_translation_notes_stale(tmp_path: Path) -> None:
    """F3 对照：注文宿主单元**实际以译文渲染**时，过期译注仍必须阻断。"""
    store = _notes_ws(tmp_path)
    _register(store)
    _write_translation(
        store,
        md="# 第一章\n\n第一句话[^ref-000001]。\n",
        rows=[
            {
                "seq": 1,
                "src": "First sentence.[^ref-000001]",
                "tgt": "第一句话[^ref-000001]。",
                "note": None,
            }
        ],
        target_notes={
            "schema_version": "1",
            "source_notes_sha256": "0" * 64,  # 过期绑定，但该单元确实用译文渲染
            "notes": [{"note_id": "n-000001", "target_markdown": "译文注文。"}],
        },
    )
    import pytest as _pytest

    with _pytest.raises(orch.OrchestrationError) as ei:
        orch.build(store)
    assert "摘要不符" in str(ei.value)


@pytest.mark.parametrize("binding", ["note_id", "ref_id"])
def test_candidates_rerun_preserves_identity_bindings(tmp_path: Path, binding: str) -> None:
    """候选重跑保留处置及注文或引用身份。"""
    store = _notes_ws(tmp_path)
    first = orch.notes_candidates(store)
    rows = [
        json.loads(ln)
        for ln in (store.preprocessing_dir / "note_candidates.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    ]
    assert rows, first
    rows[0]["disposition"] = "note"
    identity = "n-000001" if binding == "note_id" else "ref-000001"
    rows[0][binding] = identity
    (store.preprocessing_dir / "note_candidates.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    orch.notes_candidates(store)  # 重跑
    again = [
        json.loads(ln)
        for ln in (store.preprocessing_dir / "note_candidates.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    ]
    kept = [r for r in again if r.get("candidate_id") == rows[0]["candidate_id"]]
    assert kept and kept[0].get(binding) == identity
    assert kept[0].get("disposition") == "note"


@pytest.mark.parametrize("orphan", [False, True])
def test_register_multilocation_endnote_candidates(tmp_path: Path, orphan: bool) -> None:
    """混合附录的跨页注文可合并，合法孤儿无需伪造引用。"""
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter I\n\nFirst sentence.\n\n# Appendix\n\nMixed appendix.\n", encoding="utf-8"
    )
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    data = _src_notes(store, text="Complete note with continuation.", marker_in_body=not orphan)
    appendix_unit = next(u.id for u in store.load_publication().units if u.kind == "appendix")
    if orphan:
        data["references"] = []
        data["notes"][0].update(orphan_ok=True, orphan_reason="原书无引用")
    rows = [
        _candidate(
            candidate_id="c-page-1",
            unit=appendix_unit,
            kind="numbered_paragraph",
            note_id="n-000001",
            line=5,
        ),
        _candidate(
            candidate_id="c-page-2",
            unit=appendix_unit,
            kind="numbered_paragraph",
            note_id="n-000001",
            line=9,
        ),
    ]
    data["notes"][0]["source_locations"] = [
        {
            "kind": "page",
            "page": 12,
            "bbox": [1, 2, 30, 40],
            "candidate_id": "c-page-1",
            "unit": appendix_unit,
            "line": 5,
        },
        {"kind": "page", "page": 13, "candidate_id": "c-page-2"},
    ]
    _write_candidates(store, rows)
    before = _unit_md(store, appendix_unit).read_text(encoding="utf-8")
    assert _register(store, data)["summary"]["inventory"] == "present"
    assert _unit_md(store, appendix_unit).read_text(encoding="utf-8") == before
    assert notes_mod.read_candidates(store.preprocessing_dir / "note_candidates.jsonl") == rows
    for bad_locations in (
        [{"kind": "page", "page": 12}],
        [{"candidate_id": "wrong-note-candidate"}],
        [{"candidate_id": "c-page-1", "unit": "ch01"}, {"candidate_id": "c-page-2"}],
        [{"candidate_id": "c-page-1", "line": 99}, {"candidate_id": "c-page-2"}],
    ):
        data["notes"][0]["source_locations"] = bad_locations
        with pytest.raises(orch.OrchestrationError) as exc:
            _register(store, data)
        assert "c-page-1" in str(exc.value)


def test_registered_orphan_passes_offline_notes_and_structure_gates(tmp_path: Path) -> None:
    """干净正文中的合法无引用注文通过独立注释门与 G4，不伪造引用。"""
    from auto_epublizer.qa import audit_epub, audit_notes_epub

    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst sentence.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    data = _src_notes(store, marker_in_body=False)
    data["references"] = []
    data["notes"][0].update(orphan_ok=True, orphan_reason="原书无引用")
    _register(store, data)
    _write_translation(
        store,
        md="# 第一章\n\n第一句话。\n",
        rows=[{"seq": 1, "src": "First sentence.", "tgt": "第一句话。", "note": None}],
        target_notes=_tgt_notes(store),
    )
    assert orch.import_translations(store)["imported"] == ["ch01"]
    epub = orch.build(store)
    target = notes_mod.read_notes_json(notes_mod.translation_notes_path(store))
    independent = audit_notes_epub(
        epub,
        source_notes=data,
        target_notes=target,
        media_root=store.structured_dir / "raw" / "media",
    )
    assert independent.ok, independent.findings
    legacy = audit_epub(epub)
    assert "E_FN_BACKLINK" in {f.code for f in legacy.findings}
    assert audit_epub(epub, notes_registered=True).ok
    cfg = Config()
    # 不运行外部检查器；此处只验证离线结构门，不宣称 EPUBCheck 或阅读器兼容。
    cfg.qc.epubcheck.jar = str(tmp_path / "missing-epubcheck.jar")
    report = orch.qa(store, epub_path=str(epub), config=cfg)
    assert report["g4_audit"] == "pass"
    assert not report["notes_findings"]
    assert report["epub_footnotes_missing"] == 0

    # 移交不掩盖独立门的内容缺失与额外未登记 aside。
    for filename, old, new in [
        ("missing.epub", "注释文本。", ""),
        (
            "extra.epub",
            "</body>",
            '<aside epub:type="footnote" id="fn-extra"><p>额外注文。</p></aside></body>',
        ),
    ]:
        bad = _tamper(epub, tmp_path / filename, "ch01.xhtml", old, new)
        result = audit_notes_epub(
            bad,
            source_notes=data,
            target_notes=target,
            media_root=store.structured_dir / "raw" / "media",
        )
        assert not result.ok
        report = orch.qa(store, epub_path=str(bad), config=cfg)
        assert report["released"] is False
        assert report["notes_findings"]
