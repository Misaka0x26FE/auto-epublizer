"""preprocess 预处理测试：嗅探（EPUB/PDF/DOCX/HTML）、facts 落盘、fallback、status 对账。"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from auto_common.config import Config
from auto_epublizer import orchestrator as orch
from auto_epublizer.preprocess import sniff
from auto_epublizer.preprocess.sniff import SniffError

# ── 测试夹具：手写最小 EPUB ─────────────────────────────────────────────

_CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
    <dc:creator>Some Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:date>2020-01-01</dc:date>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="nav"/><itemref idref="ch1"/></spine>
</package>
"""

_NAV = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<body><nav epub:type="toc"><ol>
<li><a href="ch1.xhtml">Chapter One</a></li>
</ol></nav></body></html>
"""


def _make_epub(tmp_path: Path, *, drm: bool = False) -> Path:
    p = tmp_path / "book.epub"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER)
        if drm:
            zf.writestr(
                "META-INF/encryption.xml",
                '<?xml version="1.0"?><encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"/>',
            )
        zf.writestr("OEBPS/content.opf", _OPF)
        zf.writestr("OEBPS/nav.xhtml", _NAV)
        zf.writestr("OEBPS/ch1.xhtml", "<html><body><p>hi</p></body></html>")
    return p


def _make_pdf(tmp_path: Path, *, with_text: bool = True, with_toc: bool = False) -> Path:
    import fitz

    p = tmp_path / "book.pdf"
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page()
        if with_text:
            page.insert_text((72, 72), f"Page {i + 1} sample text for analysis.")
    if with_toc:
        doc.set_toc([[1, "Chapter One", 1], [1, "Chapter Two", 2]])
    doc.save(str(p))
    doc.close()
    return p


# ── 嗅探 ────────────────────────────────────────────────────────────────


def test_sniff_epub_metadata_and_toc(tmp_path: Path) -> None:
    facts = sniff(_make_epub(tmp_path))
    assert facts["kind"] == "epub"
    assert facts["drm"] is False
    assert facts["metadata"]["title"] == "Test Book"
    assert facts["metadata"]["language"] == "en"
    assert facts["spine_count"] == 2
    assert facts["toc"] == [{"title": "Chapter One", "href": "ch1.xhtml"}]


def test_sniff_epub_drm_detected(tmp_path: Path) -> None:
    facts = sniff(_make_epub(tmp_path, drm=True))
    assert facts["drm"] is True


def test_sniff_pdf_text_layer_and_toc(tmp_path: Path) -> None:
    facts = sniff(_make_pdf(tmp_path, with_toc=True))
    assert facts["kind"] == "pdf"
    assert facts["has_text_layer"] is True
    assert facts["scanned"] is False
    assert facts["page_count"] == 3
    assert [t["title"] for t in facts["toc"]] == ["Chapter One", "Chapter Two"]


def test_sniff_pdf_scanned_detection(tmp_path: Path) -> None:
    facts = sniff(_make_pdf(tmp_path, with_text=False))
    assert facts["scanned"] is True
    assert facts["has_text_layer"] is False


def test_sniff_html_title(tmp_path: Path) -> None:
    p = tmp_path / "page.html"
    p.write_text(
        "<html lang='en'><head><title>My Page</title>"
        "<meta property='og:description' content='desc here'/></head><body>x</body></html>",
        encoding="utf-8",
    )
    facts = sniff(p)
    assert facts["metadata"]["title"] == "My Page"
    assert facts["metadata"]["language"] == "en"
    assert facts["metadata"]["description"] == "desc here"


def test_sniff_docx_core_props(tmp_path: Path) -> None:
    p = tmp_path / "doc.docx"
    core = (
        '<?xml version="1.0"?><cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Doc Title</dc:title><dc:creator>Doc Author</dc:creator></cp:coreProperties>"
    )
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("docProps/core.xml", core)
        zf.writestr("[Content_Types].xml", "<Types/>")
    facts = sniff(p)
    assert facts["metadata"]["title"] == "Doc Title"
    assert facts["metadata"]["creator"] == "Doc Author"


def test_sniff_unsupported_format(tmp_path: Path) -> None:
    p = tmp_path / "file.xyz"
    p.write_text("x", encoding="utf-8")
    try:
        sniff(p)
        raise AssertionError("应抛 SniffError")
    except SniffError:
        pass


# ── facts 收集与落盘 ────────────────────────────────────────────────────


def _caps_summary(**available: bool) -> dict:
    """构造 capabilities_summary 形状的假数据：只列出的名字 available=True。"""
    from auto_epublizer.doctor import Capability, capabilities_summary

    names = {
        "pandoc",
        "tesseract",
        "ocrmypdf",
        "rapidocr",
        "llm_vision_model",
        "mineru",
    }
    caps = [
        Capability(name=n, available=n in available, impact="", hint="", detail="")
        for n in sorted(names)
    ]
    return capabilities_summary(caps)


def _routing(caps: dict) -> str:
    from auto_epublizer.preprocess.facts import _ocr_routing

    return _ocr_routing(caps)[0]


def test_ocr_routing_prefers_traditional_ocr() -> None:
    assert "传统 OCR" in _routing(_caps_summary(tesseract=True, rapidocr=True))
    assert "传统 OCR" in _routing(_caps_summary(ocrmypdf=True))


def test_ocr_routing_falls_back_to_rapidocr() -> None:
    assert "RapidOCR" in _routing(_caps_summary(rapidocr=True, mineru=True))


def test_ocr_routing_vision_llm_before_mineru() -> None:
    assert "视觉 LLM" in _routing(_caps_summary(llm_vision_model=True, mineru=True))
    assert "MinerU" in _routing(_caps_summary(mineru=True))


def test_ocr_routing_no_backend_asks_user() -> None:
    assert "请用户提供" in _routing(_caps_summary())


def _workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text(
        "# Chapter I\n\nFirst paragraph of the book.\n\nSecond paragraph follows here.\n",
        encoding="utf-8",
    )
    return orch.init(str(src), workspace_dir=tmp_path / "ws")


def test_collect_facts_and_write(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    result = orch.preprocess(store, config=Config())
    facts = result["facts"]
    # 源事实
    assert facts["source"]["kind"] == "md"
    # 结构规模
    totals = facts["structure"]["totals"]
    assert totals["units"] == 1
    assert totals["words"] > 0
    assert totals["sentences"] > 0
    assert totals["estimated_tokens"] > 0
    # 体检与建议
    assert facts["checks"]["drm"] is False
    assert any("纯文本" in s for s in facts["suggestions"])
    # agent 待办（首位 capabilities 自报，共 7 项）
    assert len(facts["agent_todo"]) == 7
    assert "capabilities.md" in facts["agent_todo"][0]
    # 落盘
    json_path = Path(result["facts_json"])
    md_path = Path(result["facts_md"])
    assert json_path.is_file() and md_path.is_file()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["structure"]["totals"]["units"] == 1
    assert "agent 待办" in md_path.read_text(encoding="utf-8")
    # 工作区骨架含 preprocessing/
    assert (store.dir / "preprocessing").is_dir()


def test_preprocess_refresh_is_idempotent(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    orch.preprocess(store, config=Config())
    first = (store.preprocessing_dir / "facts.json").read_text(encoding="utf-8")
    orch.preprocess(store, config=Config())
    second = (store.preprocessing_dir / "facts.json").read_text(encoding="utf-8")
    assert first == second


def test_preprocess_requires_workspace(tmp_path: Path) -> None:
    from auto_common.workspace import RunStore

    store = RunStore(tmp_path / "empty-ws", create=False)
    try:
        orch.preprocess(store, config=Config())
        raise AssertionError("无 publication.json 应报错")
    except FileNotFoundError:
        pass


# ── 上下文 fallback 与 status 对账 ──────────────────────────────────────


def test_translate_context_falls_back_to_preprocessing(tmp_path: Path) -> None:
    from auto_translator.translation.service import _read_analysis

    store = _workspace(tmp_path)
    pre = store.preprocessing_dir
    (pre / "units").mkdir(parents=True, exist_ok=True)
    (pre / "global.md").write_text("# 全局理解\n\n主题：测试。", encoding="utf-8")
    (pre / "units" / "ch01.md").write_text("第一章梗概。", encoding="utf-8")

    ctx = _read_analysis(store, "ch01")
    assert "全局理解" in ctx
    assert "第一章梗概" in ctx


def test_review_context_falls_back_to_preprocessing(tmp_path: Path) -> None:
    from auto_common.llm.providers.fake import FakeClient
    from auto_translator.review.service import ReviewRun

    store = _workspace(tmp_path)
    (store.preprocessing_dir / "global.md").write_text("预处理全局理解。", encoding="utf-8")
    run = ReviewRun(store, FakeClient())
    assert "预处理全局理解" in run._load_book_context()


def test_status_reports_preprocessing_state(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    # 未预处理
    data = orch.status(store)
    assert data["has_preprocessing"] is False
    # facts 有、plan/global/capabilities 缺 → stale 提示
    orch.preprocess(store, config=Config())
    data = orch.status(store)
    assert data["has_preprocessing"] is True
    assert data["preprocessing_complete"] is False
    assert any(s["reason"] == "preprocessing_plan_missing" for s in data["stale"])
    # agent 补完 global.md 但 capabilities.md 仍缺 → 仍不 complete
    (store.preprocessing_dir / "global.md").write_text("理解完成。", encoding="utf-8")
    data = orch.status(store)
    assert data["preprocessing_complete"] is False
    # capabilities.md 也补完 → complete
    (store.preprocessing_dir / "capabilities.md").write_text(
        "# 能力自报\n\nmultimodal：否；search：无。", encoding="utf-8"
    )
    data = orch.status(store)
    assert data["preprocessing_complete"] is True
    assert not any(s["id"] == "preprocessing" for s in data["stale"])
