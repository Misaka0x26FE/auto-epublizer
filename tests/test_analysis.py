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


def test_chunk_helpers() -> None:
    """分块与采样纯函数：短文不分块、段落边界优先、首尾必选且保序（C6）。"""
    from auto_translator.analysis.service import _sample_chunks, _split_chunks

    # 短文不分块
    assert _split_chunks("ab", 6000) == ["ab"]

    # 长文分块且段落边界优先（边界位于窗口后段时优先断开）
    parts = _split_chunks("x" * 4000 + "\n\n" + "y" * 8000, 6000)
    assert parts[0] == "x" * 4000
    assert all(len(c) <= 6000 for c in parts)

    # 单段长文按 size 均切
    assert all(len(c) <= 6000 for c in _split_chunks("x" * 25000, 6000))

    # 采样：首尾必选、数量上限、保序
    chunks = [str(i) for i in range(10)]
    s = _sample_chunks(chunks, 5)
    assert s[0] == "0" and s[-1] == "9"
    assert len(s) <= 5
    assert s == sorted(s)

    # 不超上限时原样返回
    assert _sample_chunks(["a", "b"], 5) == ["a", "b"]


def test_analyze_long_text_chunked(tmp_path: Path) -> None:
    """长书（>6000 字）analyze：overview/global 分块采样 + merge，覆盖全书而非只看开头（C6）。"""
    from auto_translator.analysis.service import _sample_chunks, _split_chunks, analyze

    # 单章超长文本（无段落分隔，确保切成多个 6000 字块）
    unit_text = "In my younger years my father gave me some advice. " * 400
    store = _structured_workspace_long(tmp_path, unit_text)

    # 精确计算分块数，按调用顺序入队：overview(n+merge) → global(n+merge) → unit → seed → characters
    chunks = _sample_chunks(_split_chunks(unit_text, 6000), max_chunks=5)
    n = len(chunks)
    client = FakeClient()
    for _ in range(n + 1):
        client.enqueue("overview 回复。")
    for _ in range(n + 1):
        client.enqueue("global 回复。")
    client.enqueue("单元理解回复。")
    client.enqueue_json([])  # seed_terms
    client.enqueue_json([])  # characters

    analyze(store, client)

    stages = [c["stage"] for c in client._calls]
    assert stages.count("analysis_overview") == n, "overview 分块调用数应与采样块数一致"
    assert stages.count("analysis_global") == n
    assert stages.count("analysis_overview_merge") == 1
    assert stages.count("analysis_global_merge") == 1
    assert n > 1, "长书必须分块（此前只看前 6000 字）"

    # 每个分块调用都收到原文而非空串（FakeClient 记录 messages）
    for c in client._calls:
        if c["stage"] in ("analysis_overview", "analysis_global"):
            user_msg = c["messages"][-1]["content"]
            assert user_msg.strip(), f"{c['stage']} 分块输入为空"


def _structured_workspace_long(tmp_path: Path, unit_text: str):
    """建含单超长单元的结构化工作区（复用 _structured_workspace 的拆分流程）。"""
    src = tmp_path / "book.md"
    src.write_text(f"# Chapter I\n\n{unit_text}\n", encoding="utf-8")
    store = init_workspace(src, workspace_dir=tmp_path / "ws")
    from auto_epublizer.ingest import load_document
    from auto_epublizer.structure import rebuild_structure, write_structured

    doc = load_document(store.dir / store.load_publication().meta.source, store=store)
    entries = rebuild_structure(doc, store.load_publication())
    write_structured(store, doc, entries)
    store.set_units(entries)
    return store
