"""C2/C3：注文语言候选、逐条处置、摘要失效与交付门计数。"""

from __future__ import annotations

import json
from pathlib import Path

from auto_epublizer import orchestrator as orch
from auto_epublizer.note_review import review_path, summarize, write_review


def _store(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# Chapter\n\nBody.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    (store.structured_dir / "notes.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "inventory": "present",
                "notes": [
                    {
                        "note_id": "n-1",
                        "source_markdown": "A source note.",
                        "source_locations": [{"page": 1}],
                    },
                    {
                        "note_id": "n-2",
                        "source_markdown": "Same text.",
                        "source_locations": [{"page": 1}],
                    },
                    {
                        "note_id": "n-3",
                        "source_markdown": "Good note.",
                        "source_locations": [{"page": 2}],
                    },
                ],
                "references": [],
            }
        ),
        encoding="utf-8",
    )
    (store.translation_dir / "notes.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "notes": [
                    {"note_id": "n-2", "target_markdown": "Same text."},
                    {"note_id": "n-3", "target_markdown": "好注。"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return store


def _dispose(store, dispositions: dict[str, str]) -> None:
    path = review_path(store)
    data = json.loads(path.read_text(encoding="utf-8"))
    for entry in data["entries"]:
        if entry["note_id"] in dispositions:
            entry["disposition"] = "retain_original"
            entry["reason"] = dispositions[entry["note_id"]]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_candidates_are_signals_not_verdicts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload, path = write_review(store)
    assert path.is_file()
    by_id = {e["note_id"]: e for e in payload["entries"]}
    assert by_id["n-1"]["signals"] == ["missing_target"]
    assert set(by_id["n-2"]["signals"]) == {"identical_to_source", "no_target_script"}
    assert by_id["n-3"]["signals"] == []
    assert summarize(store)["open"] == 2
    # 只写 review，不改 notes.json
    assert (
        json.loads((store.structured_dir / "notes.json").read_text())["notes"][0]["source_markdown"]
        == "A source note."
    )


def test_disposition_closes_candidates_and_reopens_on_change(tmp_path: Path) -> None:
    store = _store(tmp_path)
    write_review(store)
    _dispose(store, {"n-1": "纯著录条目", "n-2": "拉丁书名，按体例保留"})
    summary = summarize(store)
    assert summary["open"] == 0 and summary["status"] == "ok"

    target_path = store.translation_dir / "notes.json"
    data = json.loads(target_path.read_text(encoding="utf-8"))
    data["notes"][0]["target_markdown"] = "Same text changed."
    target_path.write_text(json.dumps(data), encoding="utf-8")
    summary = summarize(store)
    assert summary["open"] == 1
    assert summary["stale"] == 1
    assert "n-2" in summary["stale_note_ids"]


def test_missing_review_is_not_run_and_blocks(tmp_path: Path) -> None:
    store = _store(tmp_path)
    summary = summarize(store)
    assert summary["applicable"] is True
    assert summary["status"] == "not_run"
    assert summary["open"] == 3


def test_wrong_rule_version_requires_rerun(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _, path = write_review(store)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["rule_version"] = "notes-language-0"
    path.write_text(json.dumps(data), encoding="utf-8")
    summary = summarize(store)
    assert summary["status"] == "stale_rule"
    assert summary["open"] == 3


def test_unknown_note_ids_are_reported(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _, path = write_review(store)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["entries"].append(
        {
            "note_id": "n-999",
            "signals": [],
            "source_sha256": "0" * 64,
            "target_sha256": "0" * 64,
            "disposition": "translated",
            "reason": "x",
            "evidence": "",
            "stale": False,
        }
    )
    path.write_text(json.dumps(data), encoding="utf-8")
    assert summarize(store)["unknown_note_ids"] == ["n-999"]


def test_single_han_character_does_not_clear_candidate(tmp_path: Path) -> None:
    """P0：照搬原文后补一个汉字仍是未闭合候选（低目标文字占比）。"""
    store = _store(tmp_path)
    target_path = store.translation_dir / "notes.json"
    data = json.loads(target_path.read_text(encoding="utf-8"))
    data["notes"].append({"note_id": "n-1", "target_markdown": "A source note. （同上）"})
    target_path.write_text(json.dumps(data), encoding="utf-8")
    write_review(store)
    payload = json.loads(review_path(store).read_text(encoding="utf-8"))
    entry = next(e for e in payload["entries"] if e["note_id"] == "n-1")
    assert "low_target_script" in entry["signals"]
    assert summarize(store)["open"] >= 1


def test_normal_chinese_note_with_latin_name_is_not_flagged(tmp_path: Path) -> None:
    """正常学注提到人名/书名不应因拉丁字母被误报。"""
    store = _store(tmp_path)
    target_path = store.translation_dir / "notes.json"
    data = json.loads(target_path.read_text(encoding="utf-8"))
    data["notes"].append({"note_id": "n-1", "target_markdown": "参见 Smith 的论述，见前注。"})
    target_path.write_text(json.dumps(data), encoding="utf-8")
    write_review(store)
    payload = json.loads(review_path(store).read_text(encoding="utf-8"))
    entry = next(e for e in payload["entries"] if e["note_id"] == "n-1")
    assert entry["signals"] == []


def test_short_cross_reference_with_one_han_is_still_a_candidate(tmp_path: Path) -> None:
    """短交叉引用（See p. 5 / Ibid.）加一个汉字也不能清除候选。"""
    store = _store(tmp_path)
    target_path = store.translation_dir / "notes.json"
    data = json.loads(target_path.read_text(encoding="utf-8"))
    data["notes"].append({"note_id": "n-1", "target_markdown": "See p. 5 同"})
    target_path.write_text(json.dumps(data), encoding="utf-8")
    write_review(store)
    payload = json.loads(review_path(store).read_text(encoding="utf-8"))
    entry = next(e for e in payload["entries"] if e["note_id"] == "n-1")
    assert "low_target_script" in entry["signals"]


def test_same_language_skips_language_gate(tmp_path: Path) -> None:
    """同语种书不做翻译语言核验（校对仍由审校负责）。"""
    src = tmp_path / "zh.md"
    src.write_text("# 第一章\n\n这是中文正文，用于语言判定。\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "zws"), target_language="zh-CN")
    (store.structured_dir / "notes.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "inventory": "present",
                "notes": [
                    {"note_id": "n-1", "source_markdown": "中文注文。", "source_locations": []}
                ],
                "references": [],
            }
        ),
        encoding="utf-8",
    )
    summary = summarize(store)
    assert summary["applicable"] is False
    assert summary["status"] == "same_language"


def test_inventory_unverified_does_not_silently_pass(tmp_path: Path) -> None:
    store = _store(tmp_path)
    data = json.loads((store.structured_dir / "notes.json").read_text(encoding="utf-8"))
    data["inventory"] = "unverified"
    (store.structured_dir / "notes.json").write_text(json.dumps(data), encoding="utf-8")
    summary = summarize(store)
    assert summary["applicable"] is True
    assert summary["status"] == "inventory_unverified"
    assert summary["open"] == 3


def test_entry_rule_version_change_reopens_without_inheriting(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _, path = write_review(store)
    data = json.loads(path.read_text(encoding="utf-8"))
    for entry in data["entries"]:
        entry["rule_version"] = "notes-language-0"
        if entry["note_id"] == "n-1":
            entry["disposition"] = "retain_original"
            entry["reason"] = "旧规则结论"
    path.write_text(json.dumps(data), encoding="utf-8")
    write_review(store)
    payload = json.loads(path.read_text(encoding="utf-8"))
    entry = next(e for e in payload["entries"] if e["note_id"] == "n-1")
    assert entry["disposition"] is None and entry["stale"] is True
