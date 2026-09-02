"""端到端一条龙：init → 结构 → analyze → translate → review → build → qa（FakeClient）。

验证完整翻译路径在 orchestrator/领域服务层面可跑通，且状态机正确推进：
split → analyzed → translated → aligned → reviewed → built。
"""

from __future__ import annotations

from pathlib import Path

from auto_common.llm.providers.fake import FakeClient
from auto_epublizer import orchestrator as orch


def test_full_pipeline(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter I\n\nIn my younger years my father gave me some advice.\n\n"
        "Whenever you feel like criticizing any one, remember that.\n",
        encoding="utf-8",
    )

    # 1. init + 结构落盘（convert 会顺便 build 源文 EPUB）
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    orch.convert(store)

    # 2. analyze：overview / global / unit / seed_terms / characters（novel）
    client = FakeClient()
    client.enqueue("全书概览：一个关于成长与批评的故事。")
    client.enqueue("主题：成长；人称：第一人称；语气：克制。")
    client.enqueue("本章梗概：父亲忠告与处世准则。")
    client.enqueue_json(
        [
            {
                "source": "advice",
                "target": "忠告",
                "type": "term",
                "aliases": [],
                "gender": "",
                "note": "",
            }
        ]
    )
    client.enqueue_json(
        [
            {
                "source": "father",
                "reading": "",
                "target": "父亲",
                "gender": "男",
                "role": "",
                "note": "叙述者父亲",
            }
        ]
    )
    result = orch.analyze(store, client)
    assert result["language"] == "en"
    assert result["genre"] == "novel"
    assert store.load_publication().meta.language == "en"

    # 3. translate：标题 + 2 段 = 3 blocks，一个批次
    client = FakeClient()
    client.enqueue_json(
        {
            "translations": [
                ["第一章"],
                ["在我年轻的时候，父亲给过我一些忠告。"],
                ["每当你想批评别人时，记住那一点。"],
            ]
        }
    )
    orch.translate(store, client)
    assert store.load_publication().units[0].status == "aligned"

    # 4. review：两轮 clean → clean_confirmed
    client = FakeClient()
    client.enqueue_json({"issues": [], "reviewed_segments": 3, "complete": True})
    client.enqueue_json({"issues": [], "reviewed_segments": 3, "complete": True})
    r = orch.review(store, client)
    assert r["termination"] == "clean_confirmed"
    assert store.load_publication().units[0].status == "reviewed"

    # 5. build（从译文）+ qa
    epub = orch.build(store)
    assert epub.is_file()
    report = orch.qa(store, epub_path=str(epub))
    assert report["g4_audit"] == "pass"
    assert store.load_publication().units[0].status == "built"

    # 译文确实写入了 EPUB（含中文标题）
    import zipfile

    with zipfile.ZipFile(epub) as zf:
        body = zf.read("OEBPS/ch01.xhtml").decode("utf-8")
    assert "第一章" in body
    assert "忠告" in body
