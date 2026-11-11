# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""索引证据（#58/#57）：条目拆分、索引页识别、孤页/缺页与只读导出。

合成工作区只用于回归代码路径；真实书证据（页码/计数）记录在
``docs/plans/2026-11-11-open-issues-repair-plan.md``，不用合成样本冒充。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app
from auto_epublizer.preprocess.index_evidence import (
    _is_index_page,
    collect_index_evidence,
    parse_index_line,
)


def _ws(tmp_path: Path):
    source = tmp_path / "book.md"
    source.write_text(
        "# Chapter\n\nBody text.\n\n# Index\n\n- Alpha, 1, 3\n- Beta, 2\n",
        encoding="utf-8",
    )
    store = orch.init(str(source), workspace_dir=str(tmp_path / "ws"))
    (store.structured_dir / "raw").mkdir(exist_ok=True)
    return store


def _raw_page(store, page: int, blocks: list[dict]) -> None:
    path = store.structured_dir / "raw" / f"page-{page:03}.json"
    path.write_text(
        json.dumps({"page_idx": page, "blocks": blocks}, ensure_ascii=False), encoding="utf-8"
    )


def _text_block(text: str, *, column: int | None = None, bbox=None) -> dict:
    block = {"type": "text", "text": text}
    if column is not None:
        block["column"] = column
    if bbox is not None:
        block["bbox"] = bbox
    return block


# ── 行拆分：页码后缀、区间缩写、年份 ─────────────────────────────────────


@pytest.mark.parametrize(
    ("line", "label", "refs", "ranges"),
    [
        ("- abortion, 168, 173", "abortion", ["168", "173"], [[168], [173]]),
        ("  - in PLP leadership 1931-5, 79", "in PLP leadership 1931-5", ["79"], [[79]]),
        ("- Anomalies' Act 1931, 75", "Anomalies' Act 1931", ["75"], [[75]]),
        ("- air raids, 98-9, 105-6", "air raids", ["98-9", "105-6"], [[98, 99], [105, 106]]),
        (
            "- Alliance, SDP-Liberal, 212-13, 221-2",
            "Alliance, SDP-Liberal",
            ["212-13", "221-2"],
            [[212, 213], [221, 222]],
        ),
        (
            "- Ratkoš, Peter 265, 267, 268, 269 273–276",
            "Ratkoš, Peter",
            ["265", "267", "268", "269", "273–276"],
            None,
        ),
        ("- entry without page", "entry without page", [], []),
        ("# Index", None, None, None),
    ],
)
def test_parse_index_line_keeps_label_and_page_ranges(line, label, refs, ranges) -> None:
    parsed = parse_index_line(line)
    if label is None:
        assert parsed is None
        return
    assert parsed is not None
    assert parsed["label"] == label
    assert parsed["page_refs"] == refs
    if ranges is not None:
        assert parsed["page_ranges"] == ranges
    assert all(isinstance(value, int) for group in parsed["page_ranges"] for value in group)


def test_parse_long_index_line_does_not_backtrack_catastrophically() -> None:
    """真实索引行可达数千字符；整行后缀正则曾触发灾难性回溯。"""
    refs = ", ".join(str(100 + index) for index in range(400))
    parsed = parse_index_line(f"- very long entry, {refs}")
    assert parsed is not None
    assert parsed["label"] == "very long entry"
    assert len(parsed["page_refs"]) == 400


# ── 索引页识别：版头标题，不是正文里的“index” ────────────────────────────


def test_body_page_mentioning_index_is_not_an_index_page() -> None:
    body = (
        "48\nUNLIKELY ALLIES\n"
        "which served as a model for the card index on Jews. 105\n"
        "another index entry survives in the archive. 106\n"
    )
    assert _is_index_page(body, ["Index"]) is False


def test_index_page_requires_heading_line_at_page_top() -> None:
    assert _is_index_page("Index\n- Alpha, 1, 3\n- Beta, 2", ["Index"]) is True
    assert _is_index_page("390\nIndex\n- Alpha, 1, 3\n- Beta, 2", ["Index"]) is True
    # 标题出现在正文第 5 行之后不算版头
    assert _is_index_page("a\nb\nc\nd\nIndex\n- Alpha, 1\n- Beta, 2", ["Index"]) is False


# ── 孤页/缺页/重复/双栏证据 ────────────────────────────────────────────


def test_collect_reports_orphans_missing_pages_and_duplicates(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    index = store.structured_dir / "backmatter" / "index.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(
        "# Index\n\n- Alpha, 1, 99\n- Beta, 3\n- alpha, 5\n- NoPageEntry\n",
        encoding="utf-8",
    )
    _raw_page(store, 1, [_text_block("Index\n- Alpha, 1, 99")])
    _raw_page(store, 2, [_text_block("Body page.")])
    _raw_page(store, 5, [_text_block("Index\n- alpha, 5")])

    data = collect_index_evidence(store)
    assert data["source_kind"] == "raw"
    assert data["page_count"] == 5
    (unit,) = data["units"]
    assert unit["unit"] == "back-index"
    assert unit["entry_count"] == 4
    assert unit["unresolved_lines"] == [6]
    assert unit["orphan_page_refs"] == [{"line": 3, "label": "Alpha", "page": 99}]
    # 3 在页数范围内但 raw 缺页 → 缺页证据，不当作孤页
    assert unit["missing_page_evidence"] == [{"line": 4, "label": "Beta", "page": 3}]
    assert unit["duplicate_labels"] == [{"label": "Alpha", "lines": [3, 5]}]
    assert unit["index_pages"] == [1, 5]


def test_collect_marks_two_column_index_and_line_boxes(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    index = store.structured_dir / "backmatter" / "index.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text("# Index\n\n- Alpha, 1\n- Beta, 2\n", encoding="utf-8")
    _raw_page(
        store,
        1,
        [
            _text_block("Index\n- Alpha, 1", column=0, bbox=[10, 10, 90, 30]),
            _text_block("- Beta, 2", column=1, bbox=[110, 10, 190, 30]),
        ],
    )
    (unit,) = collect_index_evidence(store)["units"]
    assert unit["two_column_index"] is True
    by_label = {entry["label"]: entry for entry in unit["entries"]}
    assert by_label["Alpha"]["locations"][0]["side"] == "left"
    assert by_label["Beta"]["locations"][0]["side"] == "right"


def test_collect_is_read_only_for_structured_and_publication(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    index = store.structured_dir / "backmatter" / "index.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text("# Index\n\n- Alpha, 1\n", encoding="utf-8")
    _raw_page(store, 1, [_text_block("Index\n- Alpha, 1")])
    before = {path: path.read_bytes() for path in (store.publication_path, index) if path.is_file()}
    collect_index_evidence(store)
    assert all(path.read_bytes() == payload for path, payload in before.items())


# ── CLI：写 preprocessing/index-evidence.json，摘要可读 ───────────────────


def test_cli_writes_index_evidence_and_reports_orphans(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    index = store.structured_dir / "backmatter" / "index.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text("# Index\n\n- Alpha, 99\n", encoding="utf-8")
    _raw_page(store, 1, [_text_block("Index\n- Alpha, 99")])
    _raw_page(store, 2, [_text_block("Body.")])

    result = CliRunner().invoke(app, ["evidence", "index", "--workspace", str(store.dir), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["units"][0]["orphan_page_refs"] == [{"line": 3, "label": "Alpha", "page": 99}]
    assert "path" not in data  # CLI JSON 不输出落盘路径，摘要仍可复算

    out = store.preprocessing_dir / "index-evidence.json"
    assert out.is_file()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["units"][0]["entry_count"] == 1
    assert written["input_digest"]
