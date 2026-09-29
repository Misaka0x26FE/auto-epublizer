"""RTL 抽取支持测试：检测 / 归一化 / 逻辑序还原（纯函数、离线确定）。"""

from __future__ import annotations

from auto_epublizer.ingest.rtl import (
    detect_book_rtl,
    is_rtl_text,
    normalize_and_reorder,
    normalize_rtl,
    reorder_line,
    rtl_ratio,
    strip_bidi_controls,
)

# 呈现形字符（Unicode Presentation Forms）
_MEEM_INITIAL = "\ufee3"  # ARABIC LETTER MEEM INITIAL FORM
_MEEM_MEDIAL = "\ufee4"  # ARABIC LETTER MEEM MEDIAL FORM
_ZWNJ = "\u200c"


def test_rtl_ratio_persian_high_latin_zero() -> None:
    assert rtl_ratio("سلام دنیا") > 0.9
    assert rtl_ratio("hello world") == 0.0
    assert rtl_ratio("12345 !!!") == 0.0  # 无强方向性字符
    assert rtl_ratio("") == 0.0


def test_is_rtl_text_threshold() -> None:
    assert is_rtl_text("کتاب تاریخ") is True
    assert is_rtl_text("Chapter One") is False
    # 拉丁为主的行：不判为 RTL（保护 RTL 书中的英文引文）
    assert is_rtl_text("a b c د") is False


def test_detect_book_rtl_aggregates_counts() -> None:
    assert detect_book_rtl(["hello world", "این یک کتاب است"]) is True
    assert detect_book_rtl(["hello", "world"]) is False
    assert detect_book_rtl([]) is False


def test_strip_bidi_controls_removes_marks_keeps_zwnj() -> None:
    assert strip_bidi_controls("a\u202bb\u202cc\u200ed\u200fe") == "abcde"
    assert strip_bidi_controls("\u2066x\u2069") == "x"
    # ZWNJ/ZWJ 是波斯语构词字符，必须保留
    assert strip_bidi_controls(f"می{_ZWNJ}شود") == f"می{_ZWNJ}شود"


def test_normalize_rtl_presentation_forms_and_controls() -> None:
    assert normalize_rtl(f"{_MEEM_INITIAL}{_MEEM_MEDIAL}") == "\u0645\u0645"
    assert normalize_rtl("a\u202bb") == "ab"
    # NFKC：全角 → 半角（RTL 书内统一归一化）
    assert normalize_rtl("ＡＢ１２") == "AB12"


def test_reorder_line_reverses_tokens() -> None:
    assert reorder_line("a b c") == "c b a"
    assert reorder_line("solo") == "solo"
    assert reorder_line("") == ""
    assert reorder_line("   ") == "   "


def test_normalize_and_reorder_rtl_line() -> None:
    # 视觉序（词倒序）→ 逻辑序
    assert normalize_and_reorder("شهزاده آوردند قتل") == "قتل آوردند شهزاده"


def test_normalize_and_reorder_ltr_line_not_reversed() -> None:
    # RTL 书内夹杂的英文行：只归一化，不逆序
    assert normalize_and_reorder("hello world") == "hello world"
    assert normalize_and_reorder("ＡＢ ＣＤ") == "AB CD"
