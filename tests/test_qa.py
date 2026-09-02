"""QA 测试：解包审计、epubcheck 跳过、报告汇总。"""

from __future__ import annotations

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
