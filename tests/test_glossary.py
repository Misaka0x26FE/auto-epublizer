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


def test_row_to_entry_tolerates_none_cells(tmp_path: Path) -> None:
    """None 单元格（非 csv.DictReader，如 JSON 反序列化行）不崩溃（豆包 GT2 实测回归）。"""
    from auto_translator.glossary.csv_io import row_to_entry

    entry = row_to_entry(
        {"source": "foo", "target": None, "type": "person", "aliases": None, "note": None}
    )
    assert entry.source == "foo"
    assert entry.target == "" and entry.note == "" and entry.aliases == []
    assert entry.type == "person"


def test_source_only_types_survive_csv_roundtrip(tmp_path: Path) -> None:
    """文体档案 source-only 类型（appellation/honorific/speech）不做静默降级。

    回归：此前 TERM_TYPES 白名单不含这三类，CSV 往返会静默降级为 term，
    与 genre/profiles.py 的 novel source_only_types 契约矛盾。
    """
    entries = [
        _entry("anie", "小安", type="appellation"),
        _entry("dono", "大人", type="honorific"),
        _entry("desu wa", "的说", type="speech"),
    ]
    p = tmp_path / "glossary.csv"
    save_glossary_csv(p, entries)
    loaded = load_glossary_csv(p)
    assert [e.type for e in loaded] == ["appellation", "honorific", "speech"]


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


def test_terminology_hit_word_boundary_cyrillic() -> None:
    """回归：俄文术语不得命中更长词的内部（СС ⊄ СССР/АССР/КФССР）。

    旧实现以 ``[A-Za-z0-9]`` 为词边界，西里尔字母不算边界字符 → 短术语（СС/СД 等）
    在全书中产生成批误报（实测一卷 2,440 处）。
    """
    g = Glossary([_entry("СС", "党卫队", type="org", status=STATUS_CONFIRMED)])
    assert terminology_hits("АССР и СССР", "自治共和国与苏联", g) == []
    hits = terminology_hits("подразделения СС вели бой", "党卫队部队在战斗", g)
    assert hits == []
    hits = terminology_hits("подразделения СС вели бой", "部队在战斗", g)
    assert len(hits) == 1 and hits[0].expected == "党卫队"


def test_terminology_hit_accepts_attributive_stem_form() -> None:
    """回归 #8：target 以结构助词「的」结尾时，定语用法（去「的」）也应命中。

    现场案例：术语表写「犹太-共济会的」（定语形式），而正文作定语时不带「的」
    （「犹太-共济会三角形」）——译文正确却报硬缺陷，只能去改术语表。缺失仍要报。
    """
    g = Glossary([_entry("иудо-масонский", "犹太-共济会的"), _entry("антисионистский", "反锡安主义的")])
    assert terminology_hits("иудо-масонский треугольник", "犹太-共济会三角形", g) == []
    assert terminology_hits("антисионистский фронт", "反锡安主义反共济会阵线", g) == []
    # 原形（带「的」）仍命中
    assert terminology_hits("иудо-масонский треугольник", "犹太-共济会的三角形", g) == []
    # 完全没译到该术语仍报违例
    hits = terminology_hits("иудо-масонский треугольник", "某个三角形", g)
    assert len(hits) == 1 and hits[0].expected == "犹太-共济会的"
    # 不以助词结尾的 target 不做形态容错
    g2 = Glossary([_entry("сионизм", "锡安主义")])
    assert terminology_hits("сионизм опасен", "锡安主义是危险的", g2) == []
    assert len(terminology_hits("сионизм опасен", "复国主义是危险的", g2)) == 1


def test_terminology_hit_word_boundary_latin_adjacent_cjk() -> None:
    """回归：非 CJK 术语紧邻中文仍是合法词边界（``\\w`` 含 CJK 的例外）。

    ``\\w`` 包含 CJK，纯 ``\\w`` 边界会把「NATO成员国」判为无边界 → 假报「译文缺失」
    （G0 硬缺陷）且 ``terms_in_text`` 漏命中；CJK 侧须单独放行。
    """
    g = Glossary(
        [
            _entry("NATO", "NATO", type="org", status=STATUS_CONFIRMED),
            _entry("DNA", "DNA", type="term", status=STATUS_CONFIRMED),
        ]
    )
    assert terminology_hits("NATO members", "NATO成员国", g) == []
    assert terminology_hits("DNA sequence", "使用DNA序列", g) == []
    assert terminology_hits("NATO members", "北约成员国", g)  # 真缺失仍须报
    assert {e.source for e in terms_in_text("中文NATO中文", g)} == {"NATO"}


def test_terminology_hit_uses_alias() -> None:
    g = Glossary(
        [_entry("IDF", "以色列国防军", type="org", aliases=["IDG"], status=STATUS_CONFIRMED)]
    )
    # 源文排印讹误 IDG 命中别名，译文缺 target 报违例
    hits = terminology_hits("the IDG", "该组织", g)
    assert hits and hits[0].source == "IDF"


def test_terminology_hit_normalizes_fullwidth_target() -> None:
    """回归（issue #4）：target 含全角括号，译文用 NFKC 半角形式 → 不误报。"""
    g = Glossary([_entry("交通部", "交通（道路）部", type="org", status=STATUS_CONFIRMED)])
    hits = terminology_hits("交通部负责修建", "交通(道路)部负责修建", g)
    assert hits == []


def test_terminology_hit_missing_fullwidth_target_still_reported() -> None:
    """target 归一化后仍缺失 → 真实违例照报（不得因归一化漏报）。"""
    g = Glossary([_entry("交通部", "交通（道路）部", type="org", status=STATUS_CONFIRMED)])
    hits = terminology_hits("交通部负责修建", "该部门负责修建", g)
    assert len(hits) == 1
    assert hits[0].expected == "交通（道路）部"


def test_terms_in_text_normalizes_fullwidth_candidates() -> None:
    """回归（issue #4）：术语 source/alias 含全角括号，正文 NFKC 形式应命中。"""
    g = Glossary(
        [
            _entry("交通（道路）部", "铁道部", type="org"),
            _entry("Railway Board", "铁路局", type="org", aliases=["（军事）动员"]),
        ]
    )
    assert {e.source for e in terms_in_text("交通(道路)部发布命令", g)} == {"交通（道路）部"}
    assert {e.source for e in terms_in_text("负责(军事)动员工作", g)} == {"Railway Board"}


def test_terminology_hit_normalizes_fullwidth_alias() -> None:
    """别名含全角形式时，源侧（NFKC 后）也须命中。"""
    g = Glossary(
        [
            _entry(
                "Railway Board",
                "铁路局",
                type="org",
                aliases=["交通（道路）部"],
                status=STATUS_CONFIRMED,
            )
        ]
    )
    hits = terminology_hits("交通(道路)部发布命令", "未用确认译法", g)
    assert len(hits) == 1
    assert hits[0].source == "Railway Board"
