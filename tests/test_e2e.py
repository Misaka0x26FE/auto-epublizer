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

    # 1. init：建工作区 + 四层结构拆分（P0 回归：init 后即有单元与 structured 文件）
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    pub = store.load_publication()
    assert pub.units, "init 后必须有内容单元（四层结构拆分）"
    assert (store.structured_dir / "body" / "ch01.md").is_file()
    assert pub.units[0].status == "split"

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
                ["在我年轻还稚嫩的时候，我父亲给过我一番忠告。"],
                [
                    "每当你想要批评任何人的时候，都要记住，这世上并不是所有人都有你拥有的那些优越条件。"
                ],
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

    # 5b. build 的目录与页面标题取译文标题（豆包实测 P8 回归）
    import zipfile

    with zipfile.ZipFile(epub) as zf:
        nav = zf.read("OEBPS/nav.xhtml").decode("utf-8")
        ch = zf.read("OEBPS/ch01.xhtml").decode("utf-8")
    assert "第一章" in nav and "Chapter I" not in nav
    assert "<title>第一章</title>" in ch

    # 6. report.json 聚合 G0–G5（epubcheck jar 缺失时 released=False 属预期）
    import json

    report_json = json.loads((store.dir / "report.json").read_text(encoding="utf-8"))
    assert report_json["g3_termination"] == "clean_confirmed"
    assert report_json["g2_confirmed"] == 0
    assert report_json["g1_candidates"] == 0
    assert report_json["g0_flags"] == []
    assert report_json["total_sentences"] == 3
    assert report_json["released"] is False  # epubcheck 未运行，不放行
    assert report_json["error_rate"] == 0.0

    # 7. usage.json 覆盖 analyze/translate/review 三个阶段（各自 run_id 幂等合并）
    usage = json.loads((store.dir / "usage.json").read_text(encoding="utf-8"))
    assert "analyze" in "".join(usage.get("merged_runs", []))
    assert "translate" in "".join(usage.get("merged_runs", []))
    assert "review" in "".join(usage.get("merged_runs", []))
    assert usage["totals"]["calls"] > 0

    # 译文确实写入了 EPUB（含中文标题）
    import zipfile

    with zipfile.ZipFile(epub) as zf:
        body = zf.read("OEBPS/ch01.xhtml").decode("utf-8")
    assert "第一章" in body
    assert "忠告" in body


def test_orchestrator_unit_heading_and_skip_empty() -> None:
    """_unit_heading 提取译文标题；_skip_empty_unit 只剔除空壳单元（豆包 P8/P9 回归）。"""
    from auto_epublizer.orchestrator import _skip_empty_unit, _unit_heading

    assert _unit_heading("# 第一章 交织的百合\n\n正文") == "第一章 交织的百合"
    assert _unit_heading("无标题正文") is None

    # 空壳单元：标题为「正文」占位、内容仅容器标记
    assert _skip_empty_unit("# 正文\n\n:::\n:::\n", "正文") is True
    # 有正文段落：不跳过
    assert _skip_empty_unit("# 正文\n\n实际段落。\n", "正文") is False
    # 真实章节标题页（仅标题、无正文）：保留作目录锚点
    assert _skip_empty_unit("# 第一章\n", "第一章") is False
