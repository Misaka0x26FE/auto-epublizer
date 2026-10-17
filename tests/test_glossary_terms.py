from __future__ import annotations

from auto_translator.glossary import STATUS_SEED, Glossary, GlossaryEntry
from auto_translator.glossary.terms import terminology_hits


def _entry(source: str, target: str) -> GlossaryEntry:
    return GlossaryEntry(source=source, target=target, type="org", status=STATUS_SEED)


def test_em_dash_does_not_block_boundary() -> None:
    """中文破折号 ``——`` 之后仍应命中术语（2026-10-07 回归）。

    ``_HYPHENS`` 早先把 em dash(U+2014) 当作**词内**连接符，于是
    ``DAP——NSDAP 的前身`` 里的 ``NSDAP`` 匹配不上译文，报出
    「术语 NSDAP 译文缺失 NSDAP」这种**自相矛盾**的告警——
    译文里明明就有 ``NSDAP``，而且改译文也放行不了（换别的标点只会制造新的不一致）。

    en dash ``–`` 仍须挡住，否则短词条 ``Brest`` 会命中到 ``Brest–Litovsk`` 内部，
    那正是 2026-10-06 把连字符族收进边界集合要解决的问题。
    """
    g = Glossary([_entry("NSDAP", "NSDAP")])
    # 中文破折号后命中，且译文含该术语 → 不报
    assert (
        terminology_hits("DAP ist eine Vorläuferin der NSDAP", "DAP\u2014\u2014NSDAP 的前身", g)
        == []
    )
    # 普通位置命中 → 不报
    assert terminology_hits("Vorläuferin der NSDAP", "NSDAP 的前身", g) == []
    # en dash 仍按词内连接符处理：短词条 `Brest` 不得命中 `Brest–Litovsk` 内部，
    # 故 src 不命中 → 译文缺不缺都无从谈起 → 0 条告警。
    # （这正是 2026-10-06 把连字符族收进边界集合要保住的行为。）
    hit = terminology_hits(
        "Stadt Brest–Litovsk", "布列斯特-立陶宛", Glossary([_entry("Brest", "布雷斯特")])
    )
    assert hit == [], "en dash 必须继续阻断边界"
    # 独立出现时仍须强制确认译法
    assert (
        len(terminology_hits("der Hafen Brest", "该港口", Glossary([_entry("Brest", "布雷斯特")])))
        == 1
    )
