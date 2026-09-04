"""analysis + genre 测试：语言/体裁检测、文体档案、语言指引（纯确定性）。

分层理解（overview/global/units）是 agent 任务，CLI 不做。
"""

from __future__ import annotations

from auto_translator.analysis import detect_genre, detect_language
from auto_translator.analysis.service import render_style_md
from auto_translator.genre.langprofile import get_langprofile
from auto_translator.genre.profiles import get_profile


def test_detect_language() -> None:
    assert detect_language("Hello world") == "en"
    assert detect_language("你好，世界") == "zh"
    assert detect_language("こんにちは世界、これは日本語です") == "ja"
    assert detect_language("Привет мир") == "ru"
    assert detect_language("안녕하세요") == "ko"


def test_detect_genre() -> None:
    assert detect_genre("Once upon a time...") == "novel"
    assert detect_genre("See references and bibliography. The appendix.") == "academic"


def test_genre_profile() -> None:
    novel = get_profile("novel")
    assert novel.needs_characters is True
    assert "person" in novel.term_types
    assert "pronoun" in novel.review_focus
    assert get_profile("nonsense").genre == "novel"


def test_langprofile() -> None:
    ja = get_langprofile("ja")
    assert any("敬称" in g for g in ja.guidance)
    assert get_langprofile("fr").guidance  # 默认兜底非空


def test_render_style_md() -> None:
    md = render_style_md("novel", detect="auto", lang="ja")
    assert "genre: novel" in md
    assert "term_types:" in md
    assert "敬称" in md
