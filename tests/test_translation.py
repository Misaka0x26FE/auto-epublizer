"""translation 测试：切片、句对齐、翻译服务（FakeClient）。"""

from __future__ import annotations

from pathlib import Path

from auto_common.llm.providers.fake import FakeClient
from auto_common.workspace import init_workspace
from auto_translator.translation import (
    align_rows,
    chunk_paragraphs,
    split_paragraph,
    split_sentences,
    translate,
)


def test_split_paragraph_short() -> None:
    out = split_paragraph("短段。", 1200)
    assert len(out) == 1
    assert out[0].cont is False


def test_split_paragraph_long_marks_cont() -> None:
    text = "。".join(["句" * 200] * 10)
    out = split_paragraph(text, 120)
    assert len(out) > 1
    assert out[0].cont is False
    assert all(s.cont for s in out[1:])


def test_chunk_paragraphs_batches() -> None:
    paras = ["短段一。", "短段二。", "短段三。"]
    batches = chunk_paragraphs(paras, max_chars_per_segment=1200, max_chars_per_batch=8)
    assert len(batches) >= 1
    total = sum(len(b) for b in batches)
    assert total == 3


def test_split_sentences() -> None:
    assert split_sentences("第一句。第二句！第三句？") == ["第一句。", "第二句！", "第三句？"]
    assert split_sentences("One. Two!") == ["One.", "Two!"]


def test_align_rows_1to1() -> None:
    rows = align_rows("甲。乙。", "A。B。")
    assert len(rows) == 2
    assert rows[0] == {"seq": 1, "src": "甲。", "tgt": "A。", "note": None}


def test_align_rows_split_declares_note() -> None:
    rows = align_rows("甲。乙。", "AB。")
    assert len(rows) == 2
    assert any(r["note"] for r in rows)


def _make_workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter I\n\nIn my younger years my father gave me advice.\n\nWhenever you feel like criticizing any one, remember that.\n",
        encoding="utf-8",
    )
    store = init_workspace(src, workspace_dir=tmp_path / "ws")

    from auto_epublizer.ingest import load_document
    from auto_epublizer.structure import rebuild_structure, write_structured

    doc = load_document(store.dir / store.load_publication().meta.source, store=store)
    entries = rebuild_structure(doc, store.load_publication())
    write_structured(store, doc, entries)
    store.set_units(entries)
    return store


def test_translate_writes_align(tmp_path: Path) -> None:
    store = _make_workspace(tmp_path)
    client = FakeClient()
    # 标题 + 2 段 = 3 blocks，一个批次返回 3 项句对
    client.enqueue_json(
        {
            "translations": [
                ["第一章"],
                ["在我年轻的时候，父亲给过我忠告。"],
                ["每当你想批评别人时，记住那一点。"],
            ]
        }
    )
    result = translate(store, client)
    assert result["units"] == 1

    pub = store.load_publication()
    assert pub.units[0].status == "aligned"

    align = store.unit_align_path("ch01")
    assert align.is_file()
    assert "父亲" in align.read_text(encoding="utf-8")

    tgt = store.translation_dir / "body" / "ch01.md"
    assert tgt.is_file()
