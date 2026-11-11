"""structure 测试：四层归类、清洗、落盘。"""

from __future__ import annotations

import json
from pathlib import Path

from auto_common.workspace import Publication, PublicationMeta, RunStore, init_workspace
from auto_epublizer.ingest.models import SourceDocument, SourceSegment, SourceUnit
from auto_epublizer.structure import (
    classify_units,
    clean_header_footer,
    clean_unit,
    clean_unit_with_report,
    rebuild_structure,
    strip_page_numbers,
    write_structured,
)


def _unit(title: str, segments: list[SourceSegment], kind: str = "chapter") -> SourceUnit:
    return SourceUnit(id="x", kind=kind, title=title, segments=segments)


def _seg(text: str, page: int | None = None, kind: str = "text") -> SourceSegment:
    meta = {}
    if page is not None:
        meta["source_page"] = page
    return SourceSegment(index=0, source=text, kind=kind, meta=meta)


def test_classify_units_front_body_back() -> None:
    doc = SourceDocument(
        title="B",
        units=[
            _unit("前言", [_seg("前言内容")], "preface"),
            _unit("第一章", [_seg("正文")], "chapter"),
            _unit("第二章", [_seg("更多正文")], "chapter"),
            _unit("索引", [_seg("索引内容")], "index"),
        ],
    )
    entries = classify_units(doc)
    assert entries[0].region == "frontmatter"
    assert entries[0].unit_id == "front-preface"
    assert entries[1].region == "body"
    assert entries[1].unit_id == "ch01"
    assert entries[2].unit_id == "ch02"
    assert entries[3].region == "backmatter"
    assert entries[3].unit_id == "back-index"


def test_classify_first_aggregated_unit_looks_like_front_matter() -> None:
    """回归 #31 ③：无书签 PDF 首个聚合单元含版权/标题页标记 → frontmatter。"""
    u = SourceUnit(
        id="ch01",
        kind="chapter",
        title="Some Book Title",
        segments=[_seg("title page"), _seg("copyright page")],
        meta={"aggregated": True},
    )
    doc = SourceDocument(title="B", units=[u, _unit("Chapter 1", [_seg("body")], "chapter")])
    entries = classify_units(doc)
    assert entries[0].region == "frontmatter"
    assert entries[0].unit_id == "front-titlepage"
    assert entries[1].unit_id == "ch01"  # 正文章序号不受影响


def test_classify_cover() -> None:
    doc = SourceDocument(title="B", units=[_unit("封面", [_seg("书名")], "cover")])
    entries = classify_units(doc)
    assert entries[0].unit_id == "cover"


def test_classify_toc() -> None:
    doc = SourceDocument(title="B", units=[_unit("目录", [_seg("...")], "toc")])
    entries = classify_units(doc)
    assert entries[0].rel_path == "frontmatter/toc.md"


def test_classify_duplicate_aux_unit_ids_get_suffix() -> None:
    """同类辅文出现多个时（如 Appendix A/B），unit_id 与 rel_path 不得冲突（P2 回归）。"""
    doc = SourceDocument(
        title="B",
        units=[
            _unit("附录 A", [_seg("附录 A 内容")], "appendix"),
            _unit("附录 B", [_seg("附录 B 内容")], "appendix"),
            _unit("附录 C", [_seg("附录 C 内容")], "appendix"),
        ],
    )
    entries = classify_units(doc)
    ids = [e.unit_id for e in entries]
    paths = [e.rel_path for e in entries]
    assert len(set(ids)) == 3, ids
    assert len(set(paths)) == 3, paths
    assert ids[0] == "back-appendix"
    assert ids[1] == "back-appendix-2"
    assert ids[2] == "back-appendix-3"


def test_classify_cover_keyword_uses_word_boundary() -> None:
    """``cover`` 不得命中 ``Covert``（真实事故：Pentagon Papers 的
    "Chapter 5 The Covert War…" 被误判为封面，与真封面同 id 互相覆盖）。"""
    doc = SourceDocument(
        title="B",
        units=[_unit("Chapter 5 The Covert War and Tonkin Gulf", [_seg("正文")])],
    )
    entries = classify_units(doc)
    assert entries[0].region == "body"
    assert entries[0].unit_id == "ch01"
    assert entries[0].rel_path == "body/ch01.md"


def test_classify_multiple_covers_get_unique_ids() -> None:
    """多个封面（front/back cover）必须分配唯一 id/rel_path，否则互相覆盖丢内容。"""
    doc = SourceDocument(
        title="B",
        units=[
            _unit("Cover", [_seg("front")]),
            _unit("Back Cover", [_seg("back")]),
        ],
    )
    entries = classify_units(doc)
    ids = [e.unit_id for e in entries]
    paths = [e.rel_path for e in entries]
    assert ids == ["cover", "cover-2"], ids
    assert paths == ["cover.md", "cover-2.md"], paths


def test_strip_page_numbers_requires_evidence() -> None:
    """裸数字证据不足时保留；显式/装饰页码才删除。"""
    segs = [_seg("正文1"), _seg("  12  "), _seg("正文2"), _seg("- 8 -"), _seg("第 9 页")]
    out = strip_page_numbers(segs)
    assert [s.source for s in out] == ["正文1", "  12  ", "正文2"]
    assert [s.index for s in out] == [0, 1, 2]


def test_strip_page_numbers_keeps_body_number_without_page_evidence() -> None:
    """年份/编号是正文，不能按数字形态删除。"""
    segs = [_seg("出版于"), _seg("1968"), _seg("。")]
    out = strip_page_numbers(segs)
    assert [s.source for s in out] == ["出版于", "1968", "。"]


def test_strip_page_numbers_uses_page_sequence_evidence() -> None:
    """有 source_page、与页序接近且跨 >=5 页递增的裸数字是页码。"""
    segs = []
    for page in range(1, 6):
        segs.append(_seg(f"正文{page}", page))
        segs.append(_seg(str(page), page))
    out = strip_page_numbers(segs)
    assert [s.source for s in out] == [f"正文{i}" for i in range(1, 6)]


def test_strip_page_numbers_keeps_year_sequence() -> None:
    """P1：页末 1968/1969/1970 是年份不是页码，远离页序时必须保留。"""
    segs = []
    for page, year in ((1, "1968"), (2, "1969"), (3, "1970"), (4, "1971"), (5, "1972")):
        segs.append(_seg(f"正文{page}", page))
        segs.append(_seg(year, page))
    out = strip_page_numbers(segs)
    assert [s.source for s in out if s.source.isdigit()] == ["1968", "1969", "1970", "1971", "1972"]


def test_clean_unit_reports_unverified_number_candidate() -> None:
    """页首/页末孤立裸数字保留并作为候选上报，不静默删除。"""
    unit = SourceUnit(
        id="ch01",
        kind="chapter",
        title="第一章",
        segments=[_seg("1968", 1), _seg("正文", 1)],
    )
    cleaned, report = clean_unit_with_report(unit)
    assert [s.source for s in cleaned.segments] == ["1968", "正文"]
    assert [c.source for c in report.candidates] == ["1968"]
    assert report.removed == ()


def test_clean_unit_uses_classified_kind_for_title_page() -> None:
    """聚合单元按内容判为书名页时，必须按归类结果豁免，不能按标题重判。"""
    unit = SourceUnit(
        id="ch01",
        kind="chapter",
        title="Some Book Title",
        segments=[_seg("1968", 1), _seg("- 12 -", 1), _seg("书名", 1)],
    )
    cleaned, report = clean_unit_with_report(unit, kind="titlepage")
    assert [s.source for s in cleaned.segments] == ["1968", "- 12 -", "书名"]
    assert report.removed == () and report.candidates == ()


def test_clean_header_footer_removes_repeat() -> None:
    segs = []
    # 3 页，每页首行都是同一页眉"书名"
    for pg in (1, 2, 3):
        segs.append(_seg("书名", pg))
        segs.append(_seg(f"第{pg}页正文", pg))
    out = clean_header_footer(segs, min_pages=3)
    assert all(s.source != "书名" for s in out)
    assert len(out) == 3


def test_clean_header_footer_keeps_distinct() -> None:
    segs = [_seg("A", 1), _seg("B", 2), _seg("C", 3)]
    out = clean_header_footer(segs, min_pages=3)
    assert len(out) == 3


def test_clean_header_footer_only_drops_page_boundary_occurrences() -> None:
    """页首跨页重复的是页眉；页中同文是正文，不能连带删除（issue #97 同类）。"""
    segs = []
    for pg in (1, 2, 3):
        segs.append(_seg("书名", pg))
        segs.append(_seg(f"第{pg}页正文", pg))
        segs.append(_seg("书名", pg))
        segs.append(_seg(f"第{pg}页末", pg))
    out = clean_header_footer(segs, min_pages=3)
    assert [s.source for s in out].count("书名") == 3


def test_clean_header_footer_keeps_heading_segments() -> None:
    """标题段与页眉同文时仍是结构标题，不能按页眉删除。"""
    segs = []
    for pg in (1, 2, 3):
        segs.append(_seg("第一章 导论", pg))
        segs.append(_seg(f"正文{pg}", pg))
        segs.append(_seg("第一章 导论", pg, kind="heading"))
    out = clean_header_footer(segs, min_pages=3)
    assert [s.source for s in out].count("第一章 导论") == 3
    assert [s.kind for s in out if s.source == "第一章 导论"] == ["heading"] * 3


def test_rebuild_structure_entries() -> None:
    doc = SourceDocument(
        title="B",
        units=[_unit("第一章", [_seg("正文")], "chapter")],
    )
    pub = Publication(slug="b", meta=PublicationMeta(title="B"))
    entries = rebuild_structure(doc, pub)
    assert entries[0]["id"] == "ch01"
    assert entries[0]["region"] == "body"


def test_clean_unit_keeps_title_page_content() -> None:
    """书名页的出版年/页码同形行是内容，不按家具剔除（#97 建议的 kind 排除）。"""
    unit = SourceUnit(
        id="front-titlepage",
        title="Title Page",
        segments=[
            _seg("Marxism and Medieval Studies", 4),
            _seg("2024", 4),
            _seg("5", 4),
        ],
    )
    out = clean_unit(unit)
    assert [s.source for s in out.segments] == ["Marxism and Medieval Studies", "2024", "5"]


def test_write_structured(tmp_path: Path) -> None:
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n\n# 第二章\n\n更多。\n", encoding="utf-8")
    store = init_workspace(src, workspace_dir=tmp_path / "ws")
    from auto_epublizer.ingest import load_document

    doc = load_document(src, store=store)
    entries = rebuild_structure(doc, store.load_publication())
    write_structured(store, doc, entries)
    assert (store.structured_dir / "body/ch01.md").is_file()
    assert (store.structured_dir / "body/ch02.md").is_file()


def test_title_page_title_and_subtitle_survive_structure_rebuild(tmp_path: Path) -> None:
    """#97：书名页的书名/副题/编者必须原字节进入 structured/（不得当页眉回声删除）。"""
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    store = init_workspace(src, workspace_dir=tmp_path / "ws")
    doc = SourceDocument(
        title="Marxism and Medieval Studies",
        units=[
            SourceUnit(
                id="spine001",
                title="Title Page",
                segments=[
                    _seg("Marxism and Medieval Studies", 4, kind="heading"),
                    _seg("Marxist Historiography in East Central Europe", 4),
                    _seg("Edited by", 4),
                    _seg("Martin Nodl / Piotr Węcowski / Dušan Zupka", 4),
                    _seg("LEIDEN | BOSTON", 4),
                ],
                meta={"heading_level": 1},
            )
        ],
    )
    entries = rebuild_structure(doc, store.load_publication())
    write_structured(store, doc, entries)
    md = (store.structured_dir / entries[0]["rel_path"]).read_text(encoding="utf-8")
    for line in (
        "Marxism and Medieval Studies",
        "Marxist Historiography in East Central Europe",
        "Edited by",
        "Martin Nodl / Piotr Węcowski / Dušan Zupka",
        "LEIDEN | BOSTON",
    ):
        assert line in md, md


def test_write_structured_cleans_furniture_and_reports_evidence(tmp_path: Path) -> None:
    """页眉/页码不流入 structured；删除项留证据，正文年份保留。"""
    store = RunStore(tmp_path / "ws")
    store.ensure_skeleton()
    segments = []
    for page in range(1, 6):
        segments.append(_seg("BOOK TITLE", page))
        segments.append(_seg(f"Body paragraph {page}.", page))
        if page == 2:
            segments.append(_seg("1968", page))
        segments.append(_seg(str(page), page))
    doc = SourceDocument(
        title="B",
        units=[SourceUnit(id="u1", kind="chapter", title="Chapter 1", segments=segments)],
    )
    entries = rebuild_structure(doc, Publication(slug="b"))
    write_structured(store, doc, entries)
    md = (store.structured_dir / "body/ch01.md").read_text(encoding="utf-8")
    assert "BOOK TITLE" not in md
    assert "1968" in md
    for page in range(1, 6):
        assert f"Body paragraph {page}." in md
    report = json.loads(
        (store.structured_dir / "raw/structure-clean.json").read_text(encoding="utf-8")
    )
    reasons = {r["reason"] for r in report["units"][0]["removed"]}
    assert "repeated_header" in reasons
    assert "page_number" in reasons


def test_write_structured_removes_stale_clean_report(tmp_path: Path) -> None:
    """第二次写入没有清洗项时，旧台账必须被空清单替换。"""
    store = RunStore(tmp_path / "ws")
    store.ensure_skeleton()
    dirty = SourceDocument(
        title="B",
        units=[
            SourceUnit(
                id="u1",
                kind="chapter",
                title="C",
                segments=[_seg("- 1 -", 1), _seg("正文", 1)],
            )
        ],
    )
    entries = rebuild_structure(dirty, Publication(slug="b"))
    write_structured(store, dirty, entries)
    report_path = store.structured_dir / "raw/structure-clean.json"
    assert json.loads(report_path.read_text(encoding="utf-8"))["units"]

    clean = SourceDocument(
        title="B",
        units=[SourceUnit(id="u1", kind="chapter", title="C", segments=[_seg("正文")])],
    )
    write_structured(store, clean, rebuild_structure(clean, Publication(slug="b")))
    assert json.loads(report_path.read_text(encoding="utf-8"))["units"] == []


def test_write_structured_writes_front_and_back(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "ws")
    store.ensure_skeleton()
    doc = SourceDocument(
        title="B",
        units=[
            _unit("前言", [_seg("前言")], "preface"),
            _unit("第一章", [_seg("正文")], "chapter"),
            _unit("后记", [_seg("后记")], "afterword"),
        ],
    )
    entries = rebuild_structure(
        doc, store.load_publication() if store.exists() else Publication(slug="b")
    )
    write_structured(store, doc, entries)
    assert (store.structured_dir / "frontmatter/preface.md").is_file()
    assert (store.structured_dir / "body/ch01.md").is_file()
    assert (store.structured_dir / "backmatter/afterword.md").is_file()


def test_render_markdown_heading_levels() -> None:
    """结构重建按段原层级写标题（不再一律 ##）；h1 夹取为 h2；单元题去重。"""
    from auto_epublizer.ingest.models import KIND_HEADING, KIND_TEXT, SourceSegment, SourceUnit
    from auto_epublizer.structure.rebuild import _render_markdown

    unit = SourceUnit(
        id="ch01",
        title="第一章",
        segments=[
            SourceSegment(index=0, source="第一章", kind=KIND_HEADING),  # 与单元题同文 → 去重
            SourceSegment(index=1, source="第一节", kind=KIND_HEADING, meta={"heading_level": 2}),
            SourceSegment(index=2, source="正文。", kind=KIND_TEXT),
            SourceSegment(index=3, source="小节", kind=KIND_HEADING, meta={"heading_level": 3}),
            SourceSegment(index=4, source="高层级", kind=KIND_HEADING, meta={"heading_level": 1}),
            SourceSegment(
                index=5, source="MinerU 节", kind=KIND_HEADING, meta={"mineru_text_level": 3}
            ),
        ],
    )
    md = _render_markdown(unit.title, unit.segments)
    assert md.startswith("# 第一章\n")
    assert "## 第一节\n" in md
    assert "### 小节\n" in md
    assert "## 高层级\n" in md  # h1 夹取为 h2（每文档恰好一个 h1）
    assert "### MinerU 节\n" in md  # mineru_text_level 兜底
    assert "\n## 第一章" not in md  # 单元题不重复写入


def test_preview_rebuild_does_not_write_raw(tmp_path: Path, monkeypatch) -> None:
    """P1：预览不得把 raw/ 中间产物写回工作区，也不走 MinerU 网络解析。"""
    from auto_epublizer import orchestrator as orch

    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    store = init_workspace(src, workspace_dir=tmp_path / "ws2")
    captured: dict = {}

    def fake(path, **kw):
        captured.update(kw)
        return SourceDocument(
            title="B",
            units=[SourceUnit(id="u1", kind="chapter", title="第一章", segments=[_seg("正文。")])],
        )

    monkeypatch.setattr(orch, "load_document", fake)
    preview = orch.preview_rebuild(store)
    assert captured["store"] is None
    assert captured["mineru_client"] is None
    assert preview["counts"]["new"] == 1


def _seg_font(text: str, page: int, size: float) -> SourceSegment:
    return SourceSegment(
        index=0,
        source=text,
        kind="text",
        meta={"source_page": page, "source_font_size": size},
    )


def test_half_title_is_page_furniture_kind() -> None:
    """#97：半书名页必须识别为 frontmatter/half-title 并整页保留。"""
    doc = SourceDocument(
        title="B",
        units=[_unit("Half Title", [_seg("HALF TITLE", 1), _seg("B", 2)], "chapter")],
    )
    entry = classify_units(doc)[0]
    assert (entry.region, entry.kind) == ("frontmatter", "half-title")
    cleaned, report = clean_unit_with_report(doc.units[0], kind=entry.kind)
    assert [s.source for s in cleaned.segments] == ["HALF TITLE", "B"]
    assert report.removed == ()


def test_aggregated_unit_titled_as_book_is_titlepage_even_when_not_first() -> None:
    """#97：非首单元的书名页（标题=书名）不得被判成正文后删标题。"""
    doc = SourceDocument(
        title="Marxism and Medieval Studies",
        units=[
            _unit("Chapter", [_seg("Body.", 1)], "chapter"),
            SourceUnit(
                id="u2",
                kind="chapter",
                title="Marxism and Medieval Studies",
                segments=[
                    _seg_font("Marxism and Medieval Studies", 1, 28),
                    _seg_font("Half title other text.", 1, 12),
                    _seg_font("Marxism and Medieval Studies", 2, 28),
                    _seg_font("Preface body text.", 2, 12),
                    _seg_font("Marxism and Medieval Studies", 3, 28),
                    _seg_font("Copyright page text here.", 3, 12),
                ],
                meta={"aggregated": True},
            ),
        ],
    )
    entry = classify_units(doc)[1]
    assert (entry.region, entry.kind) == ("frontmatter", "titlepage")
    cleaned, report = clean_unit_with_report(doc.units[1], kind=entry.kind)
    assert len(cleaned.segments) == 6
    assert report.removed == () and report.candidates == ()


def test_repeated_large_font_title_is_kept_as_candidate() -> None:
    """#97：整页最大字号的书名即使跨页重复也只记候选，不按页眉删除。"""
    segments = []
    for page in range(1, 4):
        segments.append(_seg_font("Marxism and Medieval Studies", page, 28))
        segments.append(_seg_font(f"Body paragraph {page}.", page, 10))
    unit = SourceUnit(
        id="u1", kind="chapter", title="Marxism and Medieval Studies", segments=segments
    )
    cleaned, report = clean_unit_with_report(unit)
    assert [s.source for s in cleaned.segments if "Marxism" in s.source] == [
        "Marxism and Medieval Studies"
    ] * 3
    assert report.removed == ()
    assert any("large_font" in item.reason for item in report.candidates)


def test_same_size_repeated_header_is_still_removed() -> None:
    segments = []
    for page in range(1, 4):
        segments.append(_seg_font("BOOK TITLE", page, 10))
        segments.append(_seg_font(f"Body paragraph {page}.", page, 10))
    unit = SourceUnit(id="u1", kind="chapter", title="Chapter", segments=segments)
    cleaned, report = clean_unit_with_report(unit)
    assert not any(s.source == "BOOK TITLE" for s in cleaned.segments)
    assert len(report.removed) == 3


def test_facts_report_clean_ledger(tmp_path: Path) -> None:
    """#97：facts 必须显示清洗删除/候选数，而不是只藏在 raw JSON。"""
    import json

    from auto_common.config import Config
    from auto_epublizer.preprocess.facts import collect_facts

    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    store = init_workspace(src, workspace_dir=tmp_path / "ws-clean")
    raw = store.structured_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "structure-clean.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "units": [
                    {
                        "unit_id": "ch01",
                        "removed": [{"index": 0, "source": "BOOK", "reason": "repeated_header"}],
                        "candidates": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    facts = collect_facts(store, Config())
    assert facts["clean"]["removed"] == 1
    assert facts["clean"]["units"] == 1


def test_sources_and_literature_is_bibliography_but_review_is_not() -> None:
    """#58e：'Sources and Literature' 归参考文献；'Literature Review' 仍是正文。"""
    doc = SourceDocument(
        title="B",
        units=[
            _unit("Sources and Literature", [_seg("Smith 2000.")], "chapter"),
            _unit("Literature Review", [_seg("Body.")], "chapter"),
        ],
    )
    entries = classify_units(doc)
    assert (entries[0].region, entries[0].kind) == ("backmatter", "bibliography")
    assert (entries[1].region, entries[1].kind) == ("body", "chapter")


def test_half_title_page_forms_win_over_titlepage_keyword() -> None:
    """#97：'半书名页' / 'Half Title Page' 必须先命中 half-title。"""
    for title in ("半书名页", "Half Title Page"):
        doc = SourceDocument(title="B", units=[_unit(title, [_seg("T", 1)], "chapter")])
        entry = classify_units(doc)[0]
        assert entry.kind == "half-title", title


def test_large_but_unrelated_running_head_is_still_removed() -> None:
    """#97：12–14pt 的页眉若与书名无关，不因字号大就保留。"""
    segments = []
    for page in range(1, 4):
        segments.append(_seg_font("Running Head", page, 13))
        segments.append(_seg_font(f"Body paragraph {page}.", page, 10))
    unit = SourceUnit(id="u1", kind="chapter", title="Real Chapter Title", segments=segments)
    cleaned, report = clean_unit_with_report(unit)
    assert not any(s.source == "Running Head" for s in cleaned.segments)
    assert len(report.removed) == 3


def test_rebuild_preserves_source_notes_json(tmp_path: Path) -> None:
    """#71/#72：preprocess --force 不得删除已核证的 structured/notes.json。"""
    from auto_epublizer import orchestrator as orch

    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    store = init_workspace(src, workspace_dir=tmp_path / "ws-notes-rebuild")
    payload = '{"schema_version":"1","inventory":"none","notes":[],"references":[]}'
    (store.structured_dir / "notes.json").write_text(payload, encoding="utf-8")
    orch.rebuild(store)
    assert (store.structured_dir / "notes.json").read_text(encoding="utf-8") == payload


def test_long_chapter_titled_as_book_is_not_titlepage() -> None:
    """#97 反向：同名但长、且不在前几页的章节不能判成书名页。"""
    body = "正文内容。" * 500
    doc = SourceDocument(
        title="Essays",
        units=[
            _unit("Chapter", [_seg("Body.", 1)], "chapter"),
            SourceUnit(
                id="u2",
                kind="chapter",
                title="Essays",
                segments=[_seg(body, 50)],
                meta={"aggregated": True},
            ),
        ],
    )
    entry = classify_units(doc)[1]
    assert (entry.region, entry.kind) == ("body", "chapter")


def test_rebuild_does_not_copy_cover_path_outside_workspace(tmp_path: Path) -> None:
    """#71：cover 记录里的 `../` 路径不能被 rebuild 读出/写回工作区。"""
    import json

    from auto_epublizer import orchestrator as orch

    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=tmp_path / "ws-escape")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"OUTSIDE")
    (store.preprocessing_dir / "cover-generated.json").write_text(
        json.dumps({"file": "../../outside.png"}), encoding="utf-8"
    )
    orch.rebuild(store)
    assert outside.read_bytes() == b"OUTSIDE"
    assert "rebuild_skip_outside_workspace" in (store.dir / "events.jsonl").read_text(
        encoding="utf-8"
    )


def test_split_book_title_segments_are_kept_as_candidates() -> None:
    """#97：书名被拆成多段（每段只是完整标题的子串）时也不能当页眉删除。"""
    segments = []
    for page in range(1, 4):
        segments.append(_seg_font("Marxism", page, 28))
        segments.append(_seg_font("and Medieval Studies", page, 28))
        for index in range(5):
            segments.append(_seg_font(f"Body paragraph {page}-{index}.", page, 10))
    unit = SourceUnit(
        id="u1",
        kind="chapter",
        title="Marxism and Medieval Studies",
        segments=segments,
    )
    cleaned, report = clean_unit_with_report(unit)
    assert [s.source for s in cleaned.segments].count("Marxism") == 3
    assert [s.source for s in cleaned.segments].count("and Medieval Studies") == 3
    assert report.removed == ()
    assert all("large_font" in item.reason for item in report.candidates)
