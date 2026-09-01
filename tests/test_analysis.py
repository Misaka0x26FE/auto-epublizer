"""analysis + genre 测试：语言/体裁检测、文体档案、语言指引、分析服务（FakeClient）。"""

from __future__ import annotations

from pathlib import Path

from auto_epublizer.analysis import detect_genre, detect_language
from auto_epublizer.analysis.service import analyze, render_style_md
from auto_epublizer.genre.langprofile import get_langprofile
from auto_epublizer.genre.profiles import get_profile
from auto_epublizer.llm.providers.fake import FakeClient
from auto_epublizer.workspace import init_workspace


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


def test_analyze_writes_files(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter I\n\nIn my younger years my father gave me advice.\n\n# Chapter II\n\nMore text.\n",
        encoding="utf-8",
    )
    store = init_workspace(src, workspace_dir=tmp_path / "ws")

    # 先走一遍 convert 的结构落盘，使 units 带 rel_path
    from auto_epublizer.ingest import load_document
    from auto_epublizer.structure import rebuild_structure, write_structured

    doc = load_document(store.dir / store.load_publication().meta.source, store=store)
    entries = rebuild_structure(doc, store.load_publication())
    write_structured(store, doc, entries)
    store.set_units(entries)

    client = FakeClient()
    client.enqueue("全书概览内容。")
    client.enqueue("主题与语气。")
    client.enqueue("第一章梗概。")
    client.enqueue("第二章梗概。")
    client.enqueue_json(
        [
            {
                "source": "Jay Gatsby",
                "target": "杰伊·盖茨比",
                "type": "person",
                "aliases": [],
                "gender": "male",
                "note": "",
            }
        ]
    )
    client.enqueue_json(
        [
            {
                "source": "Jay Gatsby",
                "reading": "",
                "target": "杰伊·盖茨比",
                "gender": "男",
                "role": "主角",
                "note": "神秘富豪",
            }
        ]
    )

    result = analyze(store, client)
    assert result["language"] == "en"
    assert result["genre"] == "novel"
    assert result["units"] == 2

    analysis = store.analysis_dir
    assert (analysis / "overview.md").is_file()
    assert (analysis / "global.md").is_file()
    assert (analysis / "style.md").is_file()
    assert (analysis / "keypoints.md").is_file()
    assert (analysis / "glossary.csv").is_file()
    assert (analysis / "characters.csv").is_file()

    pub = store.load_publication()
    assert pub.meta.language == "en"
    assert pub.meta.genre == "novel"
    assert all(u.status == "analyzed" for u in pub.units)
