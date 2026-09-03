"""analysis + genre 测试：语言/体裁检测、文体档案、语言指引、分析服务（FakeClient）。"""

from __future__ import annotations

from pathlib import Path

from auto_common.llm.providers.fake import FakeClient
from auto_common.workspace import init_workspace
from auto_translator.analysis import detect_genre, detect_language
from auto_translator.analysis.service import analyze, render_style_md
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


def _structured_workspace(tmp_path: Path):
    """init + 结构拆分（auto_translator 层无 auto_epublizer 依赖，手动拆）。"""
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nSome meaningful text here.\n", encoding="utf-8")
    store = init_workspace(src, workspace_dir=tmp_path / "ws")
    from auto_epublizer.ingest import load_document
    from auto_epublizer.structure import rebuild_structure, write_structured

    doc = load_document(store.dir / store.load_publication().meta.source, store=store)
    entries = rebuild_structure(doc, store.load_publication())
    write_structured(store, doc, entries)
    store.set_units(entries)
    return store


class _NoKeyClient(FakeClient):
    """凭证缺失的 client：validate_credentials 抛 ValueError（LLM 降级触发）。"""

    def validate_credentials(self) -> None:
        raise ValueError("缺少 API Key：请设置环境变量")


def test_analyze_degrades_without_llm_key(tmp_path: Path) -> None:
    """无 API Key 时 analyze 不报错：确定性 scaffold 完成，LLM 增强跳过（阶段 2）。"""
    store = _structured_workspace(tmp_path)
    client = _NoKeyClient()
    result = analyze(store, client)
    assert result["llm_enhanced"] is False
    assert result["language"] == "en"
    assert result["genre"] == "novel"
    assert result["terms_seeded"] == 0
    assert (store.analysis_dir / "style.md").is_file()
    # LLM 增强产物不应存在
    assert not (store.analysis_dir / "overview.md").exists()
    # 未发生任何 LLM 调用
    assert client._calls == []
    assert store.load_publication().units[0].status == "analyzed"
