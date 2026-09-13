"""QA 测试：解包审计、epubcheck 跳过、报告汇总。"""

from __future__ import annotations

import zipfile
from pathlib import Path

from auto_common.workspace import Publication, PublicationMeta
from auto_epublizer.build import build_epub
from auto_epublizer.build.html import render_document
from auto_epublizer.qa import (
    AuditResult,
    audit_epub,
    generate_report,
    run_epubcheck,
)


def _pub() -> Publication:
    return Publication(
        slug="book",
        meta=PublicationMeta(title="测试书", creator="作者", target_language="zh-CN"),
    )


def _make_epub(tmp_path: Path, *, with_content: bool = True) -> Path:
    pub = _pub()
    entries = [
        {"id": "front-preface", "region": "frontmatter", "title": "前言"},
        {"id": "ch01", "region": "body", "title": "第一章"},
        {"id": "back-index", "region": "backmatter", "title": "索引"},
    ]
    content = []
    if with_content:
        for e in entries:
            content.append(
                (
                    f"{e['id']}.xhtml",
                    render_document(e["title"], f"# {e['title']}\n\n正文。\n", lang="zh-CN"),
                )
            )
    return build_epub(
        pub,
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "book.epub",
    )


def test_audit_valid_epub(tmp_path: Path) -> None:
    epub = _make_epub(tmp_path)
    result = audit_epub(epub)
    assert result.ok, [f.message for f in result.findings]
    # 零 error；warning（如元数据补全提示 W_META_INCOMPLETE）不阻断
    assert not [f for f in result.findings if f.level == "error"]


def test_audit_mimetype_first(tmp_path: Path) -> None:
    import zipfile

    # 构造 mimetype 不在首位的坏书
    bad = tmp_path / "bad.epub"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("x.txt", "x")
        zf.writestr("mimetype", "application/epub+zip")
    result = audit_epub(bad)
    assert not result.ok
    assert any(f.code == "E_MIMETYPE_FIRST" for f in result.findings)


def test_audit_not_epub(tmp_path: Path) -> None:
    p = tmp_path / "not.epub"
    p.write_bytes(b"not a zip")
    result = audit_epub(p)
    assert not result.ok
    assert any(f.code == "E_NOT_EPUB" for f in result.findings)


def test_epubcheck_missing_jar_skips(tmp_path: Path) -> None:
    epub = _make_epub(tmp_path)
    result = run_epubcheck(epub, jar_path=tmp_path / "nope.jar")
    assert result.available is False
    assert result.ran is False


def test_generate_report_pass() -> None:
    audit = AuditResult(ok=True)
    from auto_epublizer.qa import EpubcheckResult

    result = generate_report(
        "book",
        audit,
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0),
        epub_path="book.epub",
    )
    assert result.g4_audit == "pass"
    assert result.passed is True


def test_generate_report_epubcheck_missing_not_pass() -> None:
    audit = AuditResult(ok=True)
    from auto_epublizer.qa import EpubcheckResult

    result = generate_report(
        "book",
        audit,
        EpubcheckResult(available=False, ran=False, errors=-1, warnings=-1),
        epub_path="book.epub",
    )
    assert result.g4_audit == "pass"
    assert result.passed is False


def test_generate_report_fail_on_audit_error() -> None:
    audit = AuditResult(ok=True)
    audit.add("error", "E_TEST", "测试错误")
    from auto_epublizer.qa import EpubcheckResult

    result = generate_report(
        "book",
        audit,
        EpubcheckResult(available=False, ran=False, errors=-1, warnings=-1),
    )
    assert result.g4_audit == "fail"
    assert result.passed is False


def test_generate_report_epubcheck_error() -> None:
    audit = AuditResult(ok=True)
    from auto_epublizer.qa import EpubcheckResult

    result = generate_report(
        "book",
        audit,
        EpubcheckResult(available=True, ran=True, errors=2, warnings=0),
    )
    assert result.passed is False
    assert result.g4_epubcheck_errors == 2


def test_generate_report_g5_release_fields() -> None:
    """G5 聚合：g0_flags/g1_candidates/g2_confirmed/error_rate/released 字段齐全。"""
    from auto_epublizer.qa import EpubcheckResult

    audit = AuditResult(ok=True)
    review = {
        "issue_count": 1,
        "g1_candidates": 3,
        "g2_confirmed": 1,
        "g3_patched": 1,
        "termination": "clean_confirmed",
        "rounds": 3,
    }
    result = generate_report(
        "book",
        audit,
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0),
        review=review,
        g0_flags=[{"unit": "ch01", "check": "length", "message": "译文为空", "data": {}}],
        total_sentences=100,
    )
    assert result.g1_candidates == 3
    assert result.g2_confirmed == 1
    assert result.g3_patched == 1
    assert result.g3_termination == "clean_confirmed"
    assert result.total_sentences == 100
    assert result.error_rate == 0.01
    # G0 告警是 advisory 线索，不阻断放行（豆包实测 P12：英→中长度比误报 994 条）
    assert result.released is True


def test_generate_report_released_when_clean() -> None:
    from auto_epublizer.qa import EpubcheckResult

    audit = AuditResult(ok=True)
    review = {
        "g1_candidates": 0,
        "g2_confirmed": 0,
        "g3_patched": 0,
        "termination": "clean_confirmed",
        "rounds": 2,
    }
    result = generate_report(
        "book",
        audit,
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0),
        review=review,
        g0_flags=[],
        total_sentences=50,
    )
    assert result.released is True


def test_generate_report_unconfirmed_blocks_release() -> None:
    """G2 确认未修订（patched < confirmed）→ 不放行。"""
    from auto_epublizer.qa import EpubcheckResult

    audit = AuditResult(ok=True)
    review = {
        "g1_candidates": 2,
        "g2_confirmed": 2,
        "g3_patched": 1,
        "termination": "unresolved_fixes",
        "rounds": 3,
    }
    result = generate_report(
        "book",
        audit,
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0),
        review=review,
        g0_flags=[],
        total_sentences=50,
    )
    assert result.released is False


def test_generate_report_glossary_conflict_blocks_release() -> None:
    """未决术语冲突阻断放行（S1.1）：同一术语两种译法并存=真实缺陷。"""
    from auto_epublizer.qa import EpubcheckResult

    audit = AuditResult(ok=True)
    review = {
        "g1_candidates": 0,
        "g2_confirmed": 0,
        "g3_patched": 0,
        "termination": "clean_confirmed",
        "rounds": 2,
    }
    result = generate_report(
        "book",
        audit,
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0),
        review=review,
        g0_flags=[],
        total_sentences=50,
        glossary_conflicts_open=2,
    )
    assert result.glossary_conflicts_open == 2
    assert result.released is False
    assert result.released_reason == "glossary_conflict_open"


def test_generate_report_structure_blocks_release() -> None:
    """G0 结构违例（marker/footnote/table/fidelity）阻断放行（S1.2）。"""
    from auto_epublizer.qa import EpubcheckResult

    audit = AuditResult(ok=True)
    review = {
        "g1_candidates": 0,
        "g2_confirmed": 0,
        "g3_patched": 0,
        "termination": "clean_confirmed",
        "rounds": 2,
    }
    result = generate_report(
        "book",
        audit,
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0),
        review=review,
        g0_flags=[
            {"unit": "ch01", "check": "marker", "message": "插入标记数量不守恒", "data": {}},
        ],
        total_sentences=50,
    )
    assert result.g0_structure_open == 1
    assert result.released is False
    assert result.released_reason == "structure_open"


def test_generate_report_provenance_error_finding_blocks_release() -> None:
    """溯源 error 级发现（E_UNIT_ORDER/E_MEDIA_ORDER/E_INSERT_BAD_SOURCE 等）阻断放行。

    回归：此前 prov_ok 只查标量字段，error 级 findings 不进放行门
    （units_unexpected/media_order_violations/E_INSERT_BAD_SOURCE 出现时仍 released=True）。
    """
    from auto_epublizer.qa import EpubcheckResult

    audit = AuditResult(ok=True)
    review = {
        "g1_candidates": 0,
        "g2_confirmed": 0,
        "g3_patched": 0,
        "termination": "clean_confirmed",
        "rounds": 2,
    }
    provenance = {
        "coverage": 1.0,
        "units_missing": [],
        "units_order_ok": True,
        "media_lost": [],
        "toc_flat": False,
        "inserts_missing_files": 0,
        "findings": [
            {"level": "error", "code": "E_UNIT_ORDER", "message": "spine 含未知内容文档：extra"},
            {"level": "warning", "code": "W_TOC_MISSING", "message": "源 TOC 缺失条目：附录"},
        ],
    }
    result = generate_report(
        "book",
        audit,
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0),
        review=review,
        g0_flags=[],
        total_sentences=50,
        provenance=provenance,
    )
    assert result.released is False
    assert result.released_reason == "provenance_incomplete"


def test_generate_report_terminology_blocks_release() -> None:
    """G0 术语命中是真实缺陷：存在即不放行（QC 落实；豆包曾把术语漏检混为 advisory）。"""
    from auto_epublizer.qa import EpubcheckResult

    audit = AuditResult(ok=True)
    review = {
        "g1_candidates": 0,
        "g2_confirmed": 0,
        "g3_patched": 0,
        "termination": "clean_confirmed",
        "rounds": 1,
    }
    result = generate_report(
        "book",
        audit,
        EpubcheckResult(available=True, ran=True, errors=0, warnings=0),
        review=review,
        g0_flags=[
            {"unit": "ch01", "check": "length", "message": "长度比过低（疑漏译）", "data": {}},
            {
                "unit": "ch01",
                "check": "terminology",
                "message": "术语 Academy City 译文缺失 学园都市",
                "data": {},
            },
        ],
        total_sentences=50,
    )
    assert result.g0_terminology_open == 1
    assert result.released is False
    assert result.released_reason == "terminology_open"


def test_audit_zip_duplicate(tmp_path: Path) -> None:
    """S1.3：zip 条目名重复 → E_ZIP_DUPLICATE（zip 允许同名后者遮蔽前者，内容不可信）。"""
    import warnings

    bad = tmp_path / "dupe.epub"
    with warnings.catch_warnings():
        # zipfile 对重复条目名发 UserWarning——这正是本测试要制造的情形
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr("OEBPS/ch01.xhtml", "<html><body><p>x</p></body></html>")
            zf.writestr("OEBPS/ch01.xhtml", "<html><body><p>y</p></body></html>")
    result = audit_epub(bad)
    assert not result.ok
    assert any(f.code == "E_ZIP_DUPLICATE" for f in result.findings)


def test_audit_remote_img_blocks(tmp_path: Path) -> None:
    """S1.3：img src 外链（http）→ E_IMG_REMOTE error（媒体必须打包，阅读器离线丢图）。"""
    pub = _pub()
    entries = [{"id": "ch01", "region": "body", "title": "第一章"}]
    content = [
        (
            "ch01.xhtml",
            render_document(
                "第一章",
                "# 第一章\n\n正文 ![外链图](https://example.com/x.png) 结束。\n",
                lang="zh-CN",
            ),
        )
    ]
    epub = build_epub(
        pub,
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "remote.epub",
    )
    result = audit_epub(epub)
    assert not result.ok
    assert any(f.code == "E_IMG_REMOTE" for f in result.findings)


def test_audit_toc_coverage_bidirectional(tmp_path: Path) -> None:
    """S1.3：spine↔nav 双向覆盖。正常书双向齐；从 nav 移除一章 / nav 塞非 spine 条目均报。"""
    import shutil

    epub = _make_epub(tmp_path)
    result = audit_epub(epub)
    assert not [f for f in result.findings if f.code == "E_TOC_COVERAGE"]

    # 坏书 1：nav toc 区移除一章的 <li> → spine 文档未进目录
    bad1 = tmp_path / "bad1.epub"
    shutil.copy(epub, bad1)
    with zipfile.ZipFile(bad1) as zf:
        items = {n: zf.read(n) for n in zf.namelist()}
    nav = items["OEBPS/nav.xhtml"].decode("utf-8")
    nav = nav.replace('<li><a href="ch01.xhtml">第一章</a></li>', "")
    items["OEBPS/nav.xhtml"] = nav.encode("utf-8")
    with zipfile.ZipFile(bad1, "w") as zf:
        for n, data in items.items():
            zf.writestr(n, data)
    result = audit_epub(bad1)
    assert any(
        "spine 文档未进目录" in f.message for f in result.findings if f.code == "E_TOC_COVERAGE"
    )

    # 坏书 2：nav toc 区塞一条指向非 spine 文档的链接
    bad2 = tmp_path / "bad2.epub"
    shutil.copy(epub, bad2)
    with zipfile.ZipFile(bad2) as zf:
        items = {n: zf.read(n) for n in zf.namelist()}
    nav = items["OEBPS/nav.xhtml"].decode("utf-8")
    nav = nav.replace("</ol>", '<li><a href="ghost.xhtml">幽灵章</a></li></ol>', 1)
    items["OEBPS/nav.xhtml"] = nav.encode("utf-8")
    with zipfile.ZipFile(bad2, "w") as zf:
        for n, data in items.items():
            zf.writestr(n, data)
    result = audit_epub(bad2)
    cov = [f for f in result.findings if f.code == "E_TOC_COVERAGE"]
    assert any("nav 条目不在 spine" in f.message for f in cov)


def test_audit_toc_projection_exempt(tmp_path: Path) -> None:
    """目录投影：nav_depth 剔除的 spine 文档经 nav_exempt 豁免；非 spine 豁免名报错。"""
    pub = _pub()
    entries = [
        {"id": "ch01", "region": "body", "kind": "chapter", "title": "一", "level": 1},
        {"id": "ch02", "region": "body", "kind": "chapter", "title": "二", "level": 2},
        {"id": "ch03", "region": "body", "kind": "chapter", "title": "三", "level": 3},
        {"id": "ch04", "region": "body", "kind": "chapter", "title": "四", "level": 4},
    ]
    content = [
        (f"{e['id']}.xhtml", render_document(e["title"], "正文。", lang="zh-CN")) for e in entries
    ]
    epub = build_epub(
        pub,
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "p.epub",
        nav_depth=2,
    )
    # 未声明投影：ch03/ch04 未进目录 → 两条 E_TOC_COVERAGE
    result = audit_epub(epub)
    cov = [f for f in result.findings if f.code == "E_TOC_COVERAGE"]
    assert len(cov) == 2 and all("未进目录" in f.message for f in cov)
    # 声明投影豁免：通过；nav 幽灵条目检查不受影响
    result2 = audit_epub(epub, nav_exempt={"ch03.xhtml", "ch04.xhtml"})
    assert not [f for f in result2.findings if f.code == "E_TOC_COVERAGE"]
    # 豁免集含非 spine 文档 → 报错（防止豁免集写错）
    result3 = audit_epub(epub, nav_exempt={"ghost.xhtml"})
    assert any("非 spine 文档" in f.message for f in result3.findings if f.code == "E_TOC_COVERAGE")


def test_audit_meta_creator_with_attributes(tmp_path: Path) -> None:
    """S2 回归：build 输出的 <dc:creator id="creator-aut">（带属性）不得被误报缺失。"""
    epub = _make_epub(tmp_path)
    with zipfile.ZipFile(epub) as zf:
        opf = next(zf.read(n).decode("utf-8") for n in zf.namelist() if n.endswith(".opf"))
    assert 'id="creator-aut"' in opf  # build 实际写法（带属性）
    result = audit_epub(epub)
    warnings = [f for f in result.findings if f.code == "W_META_INCOMPLETE"]
    assert not any("dc:creator" in f.message for f in warnings)


def test_audit_meta_empty_value(tmp_path: Path) -> None:
    """S1.3：DC 元数据标签存在但内容空白 → W_META_INCOMPLETE 仍告警。"""
    epub = _make_epub(tmp_path)
    # 原书无 publisher/rights（build 按需输出）；再验证空 date 标签也报
    with zipfile.ZipFile(epub) as zf:
        items = {n: zf.read(n) for n in zf.namelist()}
    opf_name = next(n for n in items if n.endswith(".opf"))
    opf = items[opf_name].decode("utf-8")
    opf = opf.replace("<dc:language>", "<dc:date></dc:date><dc:language>", 1)
    items[opf_name] = opf.encode("utf-8")
    with zipfile.ZipFile(epub, "w") as zf:
        for n, data in items.items():
            zf.writestr(n, data)
    result = audit_epub(epub)
    warnings = [f for f in result.findings if f.code == "W_META_INCOMPLETE"]
    assert any("dc:date" in f.message for f in warnings)


def test_audit_media_warnings(tmp_path: Path) -> None:
    """媒体审计：缺 alt / 超宽图 / webp 兼容性告警（P1）；audit 不含主题违规。"""
    import struct
    import zlib

    def make_png(w: int, h: int) -> bytes:
        def chunk(t: bytes, d: bytes) -> bytes:
            c = t + d
            return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        raw = b"".join(b"\x00" + b"\x80\x80\x80" * w for _ in range(h))
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b"")
        )

    pub = _pub()
    entries = [{"id": "ch01", "region": "body", "title": "第一章"}]
    md = (
        "# 第一章\n\n![宽图](media/wide.png)\n\n"
        "![](media/noalt.png)\n\n"
        "![兼容](media/pic.webp)\n\n"
        "![正常](media/ok.png)\n"
    )
    content = [("ch01.xhtml", render_document("第一章", md, lang="zh-CN"))]
    out = build_epub(
        pub,
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "m.epub",
        media_files=[
            ("media/wide.png", make_png(5001, 100)),
            ("media/noalt.png", make_png(20, 20)),
            ("media/pic.webp", b"WEBPDATA"),
            ("media/ok.png", make_png(20, 20)),
        ],
    )
    result = audit_epub(out)
    codes = {f.code for f in result.findings}
    assert "W_IMG_LARGE" in codes  # 5001px 宽
    # 空 alt 已被 build 兜底为文件名（test_build 回归），正常管道不再产生 W_IMG_NO_ALT
    assert "W_IMG_NO_ALT" not in codes
    assert "W_IMG_FORMAT" in codes  # webp
    assert result.ok


def test_audit_theme_violations(tmp_path: Path) -> None:
    """主题校验：style.css 含具体字体名/字号/颜色 → E_THEME_*（自定义 zip 注入）。"""
    out = _make_epub(tmp_path)
    bad_css = b"body { font-family: Georgia; font-size: 12pt; color: red; }"
    out2 = out.with_name("bad.epub")
    with zipfile.ZipFile(out) as zin, zipfile.ZipFile(out2, "w") as zout:
        for item in zin.infolist():
            data = bad_css if item.filename == "OEBPS/style.css" else zin.read(item.filename)
            zout.writestr(item, data)
    result = audit_epub(out2)
    codes = {f.code for f in result.findings}
    assert "E_THEME_FONT" in codes  # 具体字体名 + 字号
    assert "E_THEME_COLOR" in codes
    assert not result.ok


def test_audit_heading_skip_residue_anchor_pairs(tmp_path: Path) -> None:
    """P2 audit：标题跳级 / 残留 / 内部锚点 / 双语成对（zip 注入模拟）。"""
    out = _make_epub(tmp_path)
    # 注入：h1→h3 跳级、HTML 注释、不可解析锚点、双语不成对
    bad = (
        '<h1>标题</h1><h3>跳级</h3><!-- 注释 --><p class="tgt">只有译文</p>'
        '<p><a href="#missing">断锚</a></p>'
    )
    out2 = out.with_name("bad2.epub")
    with zipfile.ZipFile(out) as zin, zipfile.ZipFile(out2, "w") as zout:
        for item in zin.infolist():
            data = (
                zin.read(item.filename).replace(b"<h1>", bad.encode("utf-8"), 1)
                if item.filename.endswith("front-preface.xhtml")
                else zin.read(item.filename)
            )
            zout.writestr(item, data)
    result = audit_epub(out2)
    codes = {f.code for f in result.findings}
    assert "E_HEADING_SKIP" in codes
    assert "E_RESIDUE" in codes  # HTML 注释
    assert "E_ANCHOR" in codes
    assert "E_BI_PAIRS" in codes
    assert not result.ok


def test_audit_footnote_backlink_ok_and_missing(tmp_path: Path) -> None:
    """P2 audit：脚注回链——正常 noteref/footnote 无告警；删回链 → E_FN_BACKLINK。"""
    from auto_epublizer.build.html import FootnoteState

    pub = _pub()
    entries = [{"id": "ch01", "region": "body", "title": "第一章"}]
    state = FootnoteState()
    content = [
        (
            "ch01.xhtml",
            render_document(
                "第一章",
                "正文[^1]。\n\n[^1]: 注释。",
                lang="zh-CN",
                unit_id="ch01",
                fn_state=state,
            ),
        )
    ]
    out = build_epub(
        pub,
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "fn.epub",
    )
    assert not [f for f in audit_epub(out).findings if f.level == "error"]

    # 注入：footnote aside 去掉回链
    out2 = out.with_name("fn_bad.epub")
    with zipfile.ZipFile(out) as zin, zipfile.ZipFile(out2, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith("ch01.xhtml"):
                data = data.replace(b'<a epub:type="backlink" href="#ref-1">', b"<span>")
            zout.writestr(item, data)
    codes = {f.code for f in audit_epub(out2).findings}
    assert "E_FN_BACKLINK" in codes


def test_audit_volume_warnings(tmp_path: Path, monkeypatch) -> None:
    """P2 体积审计：模块阈值可注入；超大图 → W_IMG_UNCOMPRESSED；总体积 → W_EPUB_SIZE。"""
    from auto_epublizer.qa import audit as audit_mod

    monkeypatch.setattr(audit_mod, "_MAX_IMG_BYTES", 1024)
    monkeypatch.setattr(audit_mod, "_MAX_EPUB_BYTES", 2048)
    pub = _pub()
    entries = [{"id": "ch01", "region": "body", "title": "第一章"}]
    content = [("ch01.xhtml", render_document("第一章", "![图](media/big.png)\n", lang="zh-CN"))]
    out = build_epub(
        pub,
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "big.epub",
        media_files=[("media/big.png", b"X" * 4096)],
    )
    codes = {f.code for f in audit_epub(out).findings}
    assert "W_IMG_UNCOMPRESSED" in codes
    assert "W_EPUB_SIZE" in codes
