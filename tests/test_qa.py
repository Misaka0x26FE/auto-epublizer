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
    assert not result.findings


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
    assert "W_IMG_NO_ALT" in codes  # 空 alt 的 img 无 alt 属性？——空 alt 仍有 alt=
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
