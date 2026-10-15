"""D 组：输入边界与可信边界（媒体引用包含性 / 越界读取 / 失败路由）。

先证后修的 P0：``collect_media`` 原实现用 ``media_root / cand`` 词法拼接后直接
``read_bytes()``——`../../…` 链可读取**工作区之外**（乃至 ``/etc/*``）的文件，并把
``media/../../…`` 作为成员名写进成品（越界读 → 成品外泄 + 非法成员名）。
修复：候选解析（含符号链接）后必须落在 ``media_root`` 之内，越界一律记入 dropped。
"""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from auto_common.workspace import RunStore
from auto_epublizer import orchestrator as orch
from auto_epublizer.build import collect_media
from auto_epublizer.cli import app
from auto_epublizer.ingest.pandoc_reader import pandoc_available

runner = CliRunner()


# ── ① 纯函数：包含性 ──────────────────────────────────────────────────────


def _media_root(tmp_path: Path) -> Path:
    root = tmp_path / "ws" / "structured" / "raw" / "media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_collect_media_rejects_escaping_relative_ref(tmp_path: Path) -> None:
    """真实存在的越界目标：`../../` 链不得被读取（修复前会把内容收进 files）。"""
    media_root = _media_root(tmp_path)
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("OUTSIDE-SECRET", encoding="utf-8")
    ref = os.path.relpath(secret, media_root)  # 攻击者构造的形态
    rewritten, files, dropped = collect_media(f"![x]({ref})", media_root)
    assert files == [] and dropped == [ref]
    assert "OUTSIDE-SECRET" not in rewritten
    assert ".." not in rewritten


def test_collect_media_rejects_absolute_path_ref(tmp_path: Path) -> None:
    media_root = _media_root(tmp_path)
    absolute = tmp_path / "abs-secret.txt"
    absolute.write_text("ABS-SECRET", encoding="utf-8")
    _rewritten, files, dropped = collect_media(f"![x]({absolute})", media_root)
    assert files == []
    assert len(dropped) == 1 and dropped[0].lstrip("/") == str(absolute).lstrip("/")


def test_collect_media_rejects_symlink_escape(tmp_path: Path) -> None:
    """符号链接指向 media_root 之外：解析后仍越界 → 拒绝（不跟随读出）。"""
    media_root = _media_root(tmp_path)
    outside = tmp_path / "link-target.txt"
    outside.write_text("LINK-SECRET", encoding="utf-8")
    link = media_root / "link.txt"
    link.symlink_to(outside)
    _rewritten, files, dropped = collect_media("![x](link.txt)", media_root)
    assert files == [] and dropped == ["link.txt"]


def test_collect_media_keeps_legit_nested_and_basename_fallback(tmp_path: Path) -> None:
    """相邻合法用例不受影响：嵌套保留子目录、raw/media 前缀可去、basename 兜底。"""
    media_root = _media_root(tmp_path)
    (media_root / "sub").mkdir()
    (media_root / "sub" / "ok.png").write_bytes(b"NESTED")
    (media_root / "flat.png").write_bytes(b"FLAT")
    rw1, files1, dropped1 = collect_media("![a](sub/ok.png)", media_root)
    assert files1 == [("media/sub/ok.png", b"NESTED")] and dropped1 == []
    assert "media/sub/ok.png" in rw1
    rw2, files2, _ = collect_media("![b](raw/media/flat.png)", media_root)
    assert files2 == [("media/flat.png", b"FLAT")]
    assert "media/flat.png" in rw2
    rw3, files3, _ = collect_media("![c](deep/dir/flat.png)", media_root)
    assert files3 == [("media/flat.png", b"FLAT")] and "media/flat.png" in rw3


# ── ② 端到端：越界引用不进成品，且拒绝放行（不静默成功） ───────────────────


def test_escaping_media_ref_never_reaches_product_and_blocks_release(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    secret = work / "outside-secret.txt"
    secret.write_text("OUTSIDE-WORKSPACE-SECRET", encoding="utf-8")

    src = work / "book.md"
    src.write_text("# Chapter I\n\nFirst paragraph.\n", encoding="utf-8")
    ws = work / "ws"
    result = runner.invoke(app, ["init", str(src), "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    store = RunStore(ws / "book")

    media_root = store.structured_dir / "raw" / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    ref = os.path.relpath(secret, media_root)  # 工作区之外的越界引用
    md = store.structured_dir / "body" / "ch01.md"
    md.write_text(f"# Chapter I\n\nFirst paragraph.\n\n![outside]({ref})\n", encoding="utf-8")

    epub = orch.build(store)
    with zipfile.ZipFile(epub) as zf:
        names = zf.namelist()
        assert not [n for n in names if ".." in n], names  # 非法成员名不得出现
        assert not [n for n in names if n.startswith("OEBPS/media/")]
    # 构建留痕：越界引用被显式记录，不是静默跳过
    events = [
        json.loads(ln) for ln in store.event_log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert any(e.get("event") == "media_dropped" for e in events)

    # qa：译文引用的图片不在成品 → provenance 硬门阻断（不静默成功）
    from auto_common.config import Config

    cfg = Config()
    cfg.qc.epubcheck.jar = str(tmp_path / "no-such-epubcheck.jar")
    report = orch.qa(store, epub_path=str(epub), config=cfg)
    assert report["released"] is False
    assert report["epub_media_missing"] >= 1
    assert any(f["code"] == "E_MEDIA_EPUB_LOST" for f in report["provenance_findings"])


def test_inserts_file_escape_counted_missing_not_stat(tmp_path: Path) -> None:
    """inserts 的 source.file 越界（../）计为缺失，不去 stat 工作区外的路径。"""
    from auto_epublizer.qa.provenance import audit_provenance

    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nFirst paragraph.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    raw = store.structured_dir / "raw"
    (raw / "inserts").mkdir(parents=True, exist_ok=True)
    (raw / "inserts" / "img-0001.json").write_text(
        json.dumps(
            {
                "id": "img-0001",
                "type": "image",
                "source": {"page": 1, "bbox": [0, 0, 1, 1], "xref": None, "method": "embedded"},
                "file": "../../../../../etc/hostname",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    entries = orch.structure_entries(store)
    epub = orch.build(store)
    result = audit_provenance(store, entries, epub)
    assert result.inserts_missing_files == 1
    assert any(f["code"] == "E_INSERT_MISSING_FILE" for f in result.findings)


# ── ③ 守恒：EPUB 源（嵌套媒体）的引用相对化与成品保留 ─────────────────────


_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000100ffff03000006000557bfabd4"
    "0000000049454e44ae426082"
)


def _make_epub_with_nested_image(tmp_path: Path) -> Path:
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>T</dc:title><dc:language>en</dc:language></metadata>"
        "<manifest>"
        '<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="i1" href="img/pic.png" media-type="image/png"/>'
        '</manifest><spine><itemref idref="c1"/></spine></package>'
    )
    c1 = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
        "<head><title>C1</title></head><body>"
        "<h1>Chapter One</h1><h2>Section A</h2>"
        '<p>Text with a note<a epub:type="noteref" href="#fn1">1</a>.</p>'
        '<aside epub:type="footnote" id="fn1"><p>Note body text.</p></aside>'
        '<p><img src="img/pic.png" alt="pic"/></p>'
        "</body></html>"
    )
    container = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    path = tmp_path / "synth.epub"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/c1.xhtml", c1)
        z.writestr("OEBPS/img/pic.png", _PNG)
    return path


@pytest.mark.skipif(not pandoc_available(), reason="需要 pandoc")
def test_epub_source_conserves_headings_footnote_and_nested_media(tmp_path: Path) -> None:
    """守恒：EPUB 源的标题层级/脚注/嵌套插图在 structured 与成品中保留（引用相对化）。"""
    epub_src = _make_epub_with_nested_image(tmp_path)
    store = orch.init(str(epub_src), workspace_dir=str(tmp_path / "ws"))
    md_path = store.structured_dir / "body" / "ch01.md"
    md = md_path.read_text(encoding="utf-8")
    assert "# Chapter One" in md and "## Section A" in md  # 标题层级守恒
    assert "[^1]" in md and "[^1]: Note body text." in md  # 脚注引用与定义守恒
    assert "raw/media/img/pic.png" in md  # 引用被相对化（工作区相对）
    assert str(store.dir) not in md  # 机器绝对路径不得进产物
    assert (store.structured_dir / "raw" / "media" / "img" / "pic.png").is_file()

    out = orch.build(store)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert "OEBPS/media/img/pic.png" in names  # 嵌套子目录保留
        body = zf.read("OEBPS/ch01.xhtml").decode("utf-8")
        assert 'src="media/img/pic.png"' in body  # 插图未丢
        assert "Note body text." in body  # 脚注内容进成品


def test_corrupt_epub_and_missing_pandoc_give_clear_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """坏文件/缺工具：给出明确错误，不静默产出空章节或假成功。"""
    from auto_epublizer.ingest import pandoc_reader
    from auto_epublizer.ingest.epub_reader import EpubError, read_epub
    from auto_epublizer.ingest.load import IngestError, load_document

    bad = tmp_path / "bad.epub"
    bad.write_bytes(b"this is not a zip")
    with pytest.raises(EpubError) as ei:
        read_epub(bad, media_dir=tmp_path / "media")
    assert "zip" in str(ei.value)
    if pandoc_available():
        with pytest.raises(IngestError) as ei2:  # 回退 pandoc 也失败 → 明确报错
            load_document(bad)
        assert "pandoc" in str(ei2.value)

    monkeypatch.setattr(pandoc_reader, "pandoc_available", lambda: False)
    with pytest.raises(pandoc_reader.PandocError) as ei3:
        pandoc_reader.run_pandoc(tmp_path / "x.docx")
    assert "pandoc" in str(ei3.value)
