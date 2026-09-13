"""语义整备信号层测试：repair_signals 纯函数（六类信号 + 误报防护）。"""

from __future__ import annotations

from auto_epublizer.preprocess.signals import repair_signals


def test_signals_clean_text_all_zero() -> None:
    md = "# 第一章\n\n这是完整的一句话。\n\n第二段文字，标点规范。\n"
    s = repair_signals(md)
    assert all(v == 0 for v in s.values()), s


def test_signals_hard_wrap_and_hyphen() -> None:
    md = "# 一\n\nThis sentence is hard\nwrapped in the middle.\n\ninter-\nnational word.\n"
    s = repair_signals(md)
    assert s["hard_wrap_lines"] == 2
    assert s["hyphen_eol"] == 1


def test_signals_duplicate_garbled_punct_latin() -> None:
    md = (
        "# 一\n\n重复的段落。\n\n重复的段落。\n\nÃ© 乱码。\n\n"
        "中文,用了半角逗号。\n\nabcdefghijklmnopqrstuvwx\n"
    )
    s = repair_signals(md)
    assert s["duplicate_paras"] == 1
    assert s["garbled_marks"] >= 1
    assert s["ascii_punct_cjk"] >= 1
    assert s["long_latin_run"] == 1


def test_signals_structural_blocks_exempt() -> None:
    """列表/引文/诗行的换行是刻意的，不计 hard_wrap。"""
    md = "# 一\n\n- 列表项一\n- 列表项二\n\n> 引文第一行\n> 引文第二行\n\n| 诗行一\n| 诗行二\n"
    s = repair_signals(md)
    assert s["hard_wrap_lines"] == 0
