"""glossary 测试：CSV 往返、三态生命周期、提案/合并、冲突外置。"""

from __future__ import annotations

from pathlib import Path

from auto_translator.glossary import (
    STATUS_CONFIRMED,
    STATUS_CONFLICT,
    STATUS_SEED,
    Glossary,
    GlossaryEntry,
    load_glossary_csv,
    save_glossary_csv,
    terminology_hits,
    terms_in_text,
)


def _entry(source: str, target: str, **kw: object) -> GlossaryEntry:
    return GlossaryEntry(source=source, target=target, **kw)


def test_csv_roundtrip(tmp_path: Path) -> None:
    entries = [
        _entry("old sport", "老兄", type="fixed_expr", status=STATUS_CONFIRMED, note="口头禅"),
        _entry("Jay Gatsby", "杰伊·盖茨比", type="person", aliases=["James Gatz", "Jay"]),
    ]
    p = tmp_path / "glossary.csv"
    save_glossary_csv(p, entries)
    loaded = load_glossary_csv(p)
    assert len(loaded) == 2
    assert loaded[0].target == "老兄"
    assert loaded[0].status == STATUS_CONFIRMED
    assert loaded[1].aliases == ["James Gatz", "Jay"]


def test_row_to_entry_tolerates_none_cells() -> None:
    """None 单元格（非 csv.DictReader，如 JSON 反序列化行）不崩溃（豆包 GT2 实测回归）。"""
    from auto_translator.glossary.csv_io import row_to_entry

    entry = row_to_entry(
        {"source": "foo", "target": None, "type": "person", "aliases": None, "note": None}
    )
    assert entry.source == "foo"
    assert entry.target == "" and entry.note == "" and entry.aliases == []
    assert entry.type == "person"


def test_propose_new_term_becomes_seed() -> None:
    g = Glossary()
    g.propose("Sorge", "薛林根", type="person")
    assert g.lookup("Sorge")[0].status == STATUS_SEED


def test_propose_conflicting_with_confirmed() -> None:
    g = Glossary([_entry("Soviet area", "赤区", type="term", status=STATUS_CONFIRMED)])
    g.propose("Soviet area", "苏区", type="term")
    entries = g.lookup("Soviet area")
    assert any(e.status == STATUS_CONFLICT and e.target == "苏区" for e in entries)
    assert g.confirmed_target("Soviet area") == "赤区"


def test_confirmed_target_falls_back_to_first_nonempty() -> None:
    g = Glossary([_entry("infiltration", "渗透", type="term")])
    assert g.confirmed_target("infiltration") == "渗透"


def test_terms_in_text_filters_by_occurrence() -> None:
    g = Glossary(
        [
            _entry("old sport", "老兄", type="fixed_expr"),
            _entry("Jay Gatsby", "杰伊·盖茨比", type="person"),
        ]
    )
    text = "old sport is what Gatsby says."
    found = {e.source for e in terms_in_text(text, g)}
    assert "old sport" in found
    assert "Jay Gatsby" not in found


def test_terminology_hit_uses_alias() -> None:
    g = Glossary(
        [_entry("IDF", "以色列国防军", type="org", aliases=["IDG"], status=STATUS_CONFIRMED)]
    )
    # 源文排印讹误 IDG 命中别名，译文缺 target 报违例
    hits = terminology_hits("the IDG", "该组织", g)
    assert hits and hits[0].source == "IDF"
