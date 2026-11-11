# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""源注独立清点与跨页注尾配对（#58）：只报排版候选，不冒充漏注结论。"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app
from auto_epublizer.preprocess.note_inventory import collect_note_inventory


def _ws(tmp_path: Path):
    source = tmp_path / "book.md"
    source.write_text("# Chapter\n\nText.\n", encoding="utf-8")
    store = orch.init(str(source), workspace_dir=str(tmp_path / "ws"))
    (store.structured_dir / "raw").mkdir(exist_ok=True)
    return store


def _page(store, page: int, blocks: list[dict]) -> None:
    (store.structured_dir / "raw" / f"page-{page:03}.json").write_text(
        json.dumps({"page_idx": page, "blocks": blocks}, ensure_ascii=False), encoding="utf-8"
    )


def _text(text: str, *, size: float = 10.0, box: list[float] | None = None) -> dict:
    return {"type": "text", "text": text, "font_size": size, "bbox": box or [10, 10, 200, 30]}


# ── 独立清点：整页注文、正文脚注、页脚剔除 ───────────────────────────


def test_endnote_page_counts_all_note_numbers_even_when_block_starts_mid_note(
    tmp_path: Path,
) -> None:
    store = _ws(tmp_path)
    _page(
        store,
        1,
        [
            _text("232\nNOTES TO CHAPTER 1", size=7.0),
            _text(
                "as Ukraine’s Piedmont, 22–24; Markovits, Nationbuilding, 51–57.\n"
                " 50. Stephen Seegel, Map Men, 12.\n 51. Volodymyr Kubiiovych, Meni 85.",
                size=9.5,
            ),
        ],
    )
    data = collect_note_inventory(store)
    (row,) = [page for page in data["pages"] if page["note_blocks"]]
    assert row["note_labels"] == ["50", "51"]
    assert data["counts"]["labeled_notes"] == 2
    assert data["registered"]["registered"] is False


def test_body_page_footnote_uses_small_font_and_bottom_position(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    _page(
        store,
        1,
        [
            _text("Body paragraph " * 20, size=14.0, box=[10, 10, 500, 400]),
            _text("1The final chapter surveys the scene.", size=11.5, box=[10, 720, 500, 760]),
        ],
    )
    data = collect_note_inventory(store)
    assert data["counts"]["labeled_notes"] == 1
    assert data["counts"]["note_like_blocks"] == 1


def test_repeated_footer_is_not_a_note_block(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    footer = "Cambridge Histories Online © Cambridge University Press, 2011"
    for page in range(1, 7):
        _page(
            store,
            page,
            [
                _text("Body paragraph " * 20, size=14.0, box=[10, 10, 500, 700]),
                _text(footer, size=9.7, box=[10, 795, 500, 805]),
            ],
        )
    data = collect_note_inventory(store)
    assert data["counts"]["note_like_blocks"] == 0


# ── 跨页注尾：只在连续页且两端都像注文时配对 ─────────────────────────


def test_continuation_tail_pairs_only_consecutive_note_blocks(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    body = _text("Body paragraph " * 20, size=14.0, box=[10, 10, 500, 400])
    _page(
        store,
        1,
        [body, _text("1The note breaks at a hyphen-", size=9.5, box=[10, 700, 500, 760])],
    )
    _page(store, 2, [_text("ated word continues here.", size=9.5, box=[10, 10, 500, 60]), body])
    data = collect_note_inventory(store)
    (tail,) = data["continued_tails"]
    assert tail["prev_page"] == 1 and tail["next_page"] == 2
    assert tail["reason"] == "hyphenated"
    assert tail["prev_tail"].endswith("hyphen-")


def test_page_without_notes_breaks_tail_pairing(tmp_path: Path) -> None:
    body = _text("Body paragraph " * 20, size=14.0, box=[10, 10, 500, 400])
    store = _ws(tmp_path)
    _page(
        store,
        1,
        [body, _text("1The note breaks at a hyphen-", size=9.5, box=[10, 700, 500, 760])],
    )
    _page(store, 2, [body])
    _page(store, 3, [_text("ated word continues later.", size=9.5, box=[10, 10, 500, 60]), body])
    assert collect_note_inventory(store)["continued_tails"] == []


def test_non_consecutive_pages_are_not_paired(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    _page(
        store, 1, [_text("1A note without terminal punctuation", size=9.5, box=[10, 700, 500, 760])]
    )
    _page(store, 3, [_text("2Another note starts here.", size=9.5, box=[10, 10, 500, 60])])
    data = collect_note_inventory(store)
    assert data["continued_tails"] == []


# ── 与 evidence source 集成 ─────────────────────────────────────────


def test_evidence_source_includes_inventory_and_is_read_only(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    _page(
        store,
        1,
        [
            _text("Body paragraph " * 20, size=14.0, box=[10, 10, 500, 400]),
            _text("1A longer note sentence for evidence.", size=9.5, box=[10, 700, 500, 760]),
        ],
    )
    before = {path: path.read_bytes() for path in store.dir.rglob("*") if path.is_file()}
    data = orch.source_evidence(store)
    assert data["note_inventory"]["counts"]["note_like_blocks"] == 1
    assert data["note_tail_pairs"] == []
    assert all(path.read_bytes() == value for path, value in before.items())


def test_cli_source_mentions_inventory_and_tail_counts(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    _page(
        store,
        1,
        [
            _text("Body paragraph " * 20, size=14.0, box=[10, 10, 500, 400]),
            _text("1A longer note sentence for evidence.", size=9.5, box=[10, 700, 500, 760]),
        ],
    )
    result = CliRunner().invoke(app, ["evidence", "source", "--workspace", str(store.dir)])
    assert result.exit_code == 0, result.output
    assert "源注候选块 1" in result.output
    assert "跨页注尾候选 0" in result.output
