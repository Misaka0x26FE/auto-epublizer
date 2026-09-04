"""阅读顺序重排测试：单栏/双栏/通栏标题/中部切块/无坐标（纯函数、离线确定）。"""

from __future__ import annotations

from auto_epublizer.ingest.reading_order import sort_reading_order


def b(x0: float, y0: float, x1: float, y1: float, text: str) -> dict:
    return {"bbox": [x0, y0, x1, y1], "text": text, "type": "text"}


def test_single_column_sorted_by_y() -> None:
    blocks = [b(50, 300, 550, 350, "B"), b(50, 100, 550, 150, "A")]
    assert [x["text"] for x in sort_reading_order(blocks)] == ["A", "B"]


def test_two_columns_whole_left_column_first() -> None:
    blocks = [
        b(50, 100, 290, 150, "L1"),
        b(310, 100, 550, 150, "R1"),
        b(50, 200, 290, 250, "L2"),
        b(310, 200, 550, 250, "R2"),
    ]
    assert [x["text"] for x in sort_reading_order(blocks)] == ["L1", "L2", "R1", "R2"]


def test_wide_heading_and_footer_interleave_by_y() -> None:
    blocks = [
        b(50, 600, 550, 630, "F"),
        b(310, 100, 550, 150, "R1"),
        b(50, 30, 550, 60, "H"),
        b(50, 100, 290, 150, "L1"),
    ]
    assert [x["text"] for x in sort_reading_order(blocks)] == ["H", "L1", "R1", "F"]


def test_middle_full_width_block_splits_zones() -> None:
    blocks = [
        b(50, 30, 550, 60, "H"),
        b(50, 100, 290, 150, "L1"),
        b(310, 100, 550, 150, "R1"),
        b(50, 270, 550, 290, "M"),
        b(50, 320, 290, 350, "L2"),
        b(310, 320, 550, 350, "R2"),
    ]
    assert [x["text"] for x in sort_reading_order(blocks)] == ["H", "L1", "R1", "M", "L2", "R2"]


def test_missing_bbox_keeps_original_order() -> None:
    blocks = [{"text": "x", "bbox": None}, b(50, 100, 550, 150, "y")]
    assert [x["text"] for x in sort_reading_order(blocks)] == ["x", "y"]


def test_input_not_mutated() -> None:
    blocks = [b(310, 100, 550, 150, "R1"), b(50, 100, 290, 150, "L1")]
    snapshot = [dict(x) for x in blocks]
    sort_reading_order(blocks)
    assert blocks == snapshot
