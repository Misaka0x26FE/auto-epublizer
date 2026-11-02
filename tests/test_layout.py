# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""C2 真值表：版面段落候选（栏/缩进/列表/字符范围/unknown）与合成 PDF。"""

from __future__ import annotations

import json
from pathlib import Path

from auto_common.workspace import RunStore
from auto_epublizer.preprocess.layout import collect_layout_candidates


def _store(tmp_path: Path) -> RunStore:
    store = RunStore(tmp_path / "ws")
    (store.structured_dir / "raw").mkdir(parents=True, exist_ok=True)
    return store


def _page(store: RunStore, payload: dict, name: str = "page-001.json") -> None:
    (store.structured_dir / "raw" / name).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _block(text: str, bbox: list[float], size: float = 10.0) -> dict:
    return {"type": "text", "text": text, "bbox": bbox, "font_size": size}


def test_two_columns_and_character_ranges(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _page(
        store,
        {
            "page_idx": 1,
            "blocks": [
                _block("左栏第一段。\n续行。", [50, 100, 250, 140]),
                _block("左栏第二段。", [50, 160, 250, 195]),
                _block("右栏第一段。", [320, 100, 520, 140]),
                _block("右栏第二段。", [320, 160, 520, 195]),
            ],
        },
    )
    page = collect_layout_candidates(store)["pages"][0]
    assert page["status"] == "ok"
    assert page["columns"] == 2
    assert [block["column"] for block in page["blocks"]] == [0, 0, 1, 1]
    ranges = [block["chars"] for block in page["blocks"]]
    assert ranges[0][0] == 0
    assert all(ranges[i][1] < ranges[i + 1][0] for i in range(len(ranges) - 1))


def test_missing_bbox_is_unknown_not_guessed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _page(store, {"page_idx": 1, "blocks": [{"type": "text", "text": "无坐标。", "bbox": None}]})
    result = collect_layout_candidates(store)
    assert result["unknown_pages"] == [1]
    assert result["pages"][0]["status"] == "unknown"
    assert result["pages"][0]["blocks"][0]["kind"] == "unknown"


def test_indent_and_list_candidates(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _page(
        store,
        {
            "page_idx": 1,
            "blocks": [
                _block("正文第一行。", [50, 100, 300, 120]),
                _block("缩进引文。", [74, 140, 300, 160]),
                _block("1. 列表项。", [50, 180, 300, 200]),
            ],
        },
    )
    blocks = collect_layout_candidates(store)["pages"][0]["blocks"]
    assert blocks[1]["kind"] == "indent"
    assert blocks[1]["indent"] > 0
    assert blocks[2]["kind"] == "list"


def test_merged_paragraph_candidate_is_flagged(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _page(
        store,
        {
            "page_idx": 1,
            "blocks": [_block("第一段。\n第二段。\n第三段。\n第四段。", [50, 100, 300, 200])],
        },
    )
    block = collect_layout_candidates(store)["pages"][0]["blocks"][0]
    assert "possible merged paragraphs" in block["reasons"]


def test_hanging_indent_and_in_block_split(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _page(
        store,
        {
            "page_idx": 1,
            "blocks": [
                {
                    "type": "text",
                    "text": "第一段结束。\n第二段开始。",
                    "bbox": [50, 100, 300, 190],
                    "font_size": 10,
                    "lines": [
                        {"text": "第一段结束。", "bbox": [50, 100, 300, 115]},
                        {"text": "第二段开始。", "bbox": [70, 175, 300, 190]},
                    ],
                }
            ],
        },
    )
    block = collect_layout_candidates(store)["pages"][0]["blocks"][0]
    assert "hanging indent" in block["reasons"]
    assert any(item["kind"] == "new_paragraph_in_block" for item in block["boundaries"])


def test_cross_page_continuation_is_flagged(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _page(store, {"page_idx": 1, "blocks": [_block("跨页未完的句子", [50, 700, 300, 720])]})
    _page(
        store,
        {"page_idx": 2, "blocks": [_block("接着写完。", [50, 80, 300, 100])]},
        "page-002.json",
    )
    result = collect_layout_candidates(store)
    assert result["cross_page_candidates"] == 1
    last = result["pages"][0]["blocks"][0]
    assert any(item["kind"] == "continue_across_pages" for item in last["boundaries"])


def test_rtl_column_numbering_follows_reading_direction(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _page(
        store,
        {
            "page_idx": 1,
            "rtl": True,
            "blocks": [
                _block("右栏。", [320, 100, 520, 140]),
                _block("左栏。", [50, 100, 250, 140]),
            ],
        },
    )
    blocks = collect_layout_candidates(store)["pages"][0]["blocks"]
    assert [block["column"] for block in blocks] == [0, 1]


def test_synthetic_pdf_preserves_order_and_chars(tmp_path: Path) -> None:
    import fitz

    from auto_epublizer.ingest.pdf_reader import read_pdf

    store = _store(tmp_path)
    pdf = tmp_path / "two-column.pdf"
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((50, 100), "Left column first.")
    page.insert_text((50, 130), "Left column second.")
    page.insert_text((330, 100), "Right column first.")
    page.insert_text((330, 130), "Right column second.")
    document.save(str(pdf))
    document.close()
    read_pdf(pdf, raw_dir=store.structured_dir / "raw")
    result = collect_layout_candidates(store)
    page = result["pages"][0]
    assert page["status"] == "ok"
    assert page["columns"] == 2
    text = "".join(block["text_head"] for block in page["blocks"])
    assert text.index("Left") < text.index("Right")
    assert page["page_chars"] > 0
