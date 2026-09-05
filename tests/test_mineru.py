"""MinerU 后端回归（全离线：httpx.MockTransport 注入，不依赖网络与真实 key）。

fixture 形状来自 2026-09 真实 API 探测（/tmp/opencode/mineru-probe），含关键坑：
紧随插图的正文行会被归为 image_footnote——解析器必须吐回正文，否则丢内容。
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator
from itertools import repeat
from pathlib import Path

import httpx
import pytest

from auto_epublizer.ingest.mineru import (
    MineruClient,
    MineruError,
    aggregate_mineru_chapters,
    read_mineru,
)
from auto_epublizer.ingest.models import KIND_HEADING, KIND_TEXT


def _result_zip(
    content_list: list[dict], markdown: str = "", images: dict[str, bytes] | None = None
) -> bytes:
    """构造 MinerU 结果 zip（v1 content_list + full.md + images/）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("abc123_content_list_v2.json", "[]")  # v2 应被忽略
        zf.writestr("abc123_content_list.json", json.dumps(content_list, ensure_ascii=False))
        zf.writestr("full.md", markdown)
        for name, data in (images or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def _mock_transport(
    *,
    zip_bytes: bytes,
    requests_log: list | None = None,
    poll_states: list[str] | Iterator[str] | None = None,
) -> httpx.MockTransport:
    """模拟完整 API 流程：batch → PUT → 轮询（状态序列）→ 下载 zip。"""
    states: Iterator[str] = iter(poll_states) if poll_states is not None else repeat("done")
    it = iter(states)

    def handler(request: httpx.Request) -> httpx.Response:
        if requests_log is not None:
            requests_log.append(request)
        url = str(request.url)
        if url.endswith("/file-urls/batch"):
            return httpx.Response(
                200,
                json={"code": 0, "data": {"batch_id": "b-1", "file_urls": ["https://oss/upload"]}},
            )
        if url.startswith("https://oss/upload"):
            return httpx.Response(200)
        if "/extract-results/batch/" in url:
            state = next(it, "done")
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "extract_result": [
                            {"state": state, "full_zip_url": "https://cdn/z.zip", "err_msg": ""}
                        ]
                    },
                },
            )
        if url == "https://cdn/z.zip":
            return httpx.Response(200, content=zip_bytes)
        return httpx.Response(404, json={"code": 1, "msg": "unknown"})

    return httpx.MockTransport(handler)


def _client(transport: httpx.MockTransport) -> MineruClient:
    return MineruClient(
        "test-token",
        poll_interval=0.0,
        poll_timeout=1.0,
        transport=transport,
    )


def _pdf(tmp_path: Path) -> Path:
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "hello", fontsize=12)
    p = tmp_path / "book.pdf"
    doc.save(str(p))
    doc.close()
    return p


# ── 客户端流程 ───────────────────────────────────────────────────────────


def test_client_full_flow(tmp_path: Path) -> None:
    """batch → PUT → 轮询 → 下载：四段流程 + 请求形状（Bearer/无 Content-Type 上传）。"""
    zip_bytes = _result_zip([{"type": "text", "text": "hi", "page_idx": 0}], "## hi")
    log: list = []
    client = _client(_mock_transport(zip_bytes=zip_bytes, requests_log=log))
    result = client.parse_file(_pdf(tmp_path))
    assert result.content_list == [{"type": "text", "text": "hi", "page_idx": 0}]
    assert result.markdown == "## hi"
    assert not result.images

    batch = log[0]
    assert batch.headers["Authorization"] == "Bearer test-token"
    body = json.loads(batch.content)
    assert body["model_version"] == "pipeline"
    assert body["files"][0]["is_ocr"] is True
    upload = log[1]
    assert upload.method == "PUT"
    assert "Content-Type" not in upload.headers


def test_client_failed_state_raises(tmp_path: Path) -> None:
    transport = _mock_transport(zip_bytes=b"", poll_states=["failed"])
    with pytest.raises(MineruError, match="解析失败"):
        _client(transport).parse_file(_pdf(tmp_path))


def test_client_poll_timeout(tmp_path: Path) -> None:
    transport = _mock_transport(zip_bytes=b"", poll_states=repeat("running"))
    with pytest.raises(MineruError, match="超时"):
        _client(transport).parse_file(_pdf(tmp_path))


def test_client_api_error_msg(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": -1, "msg": "配额不足"})

    with pytest.raises(MineruError, match="配额不足"):
        _client(httpx.MockTransport(handler)).parse_file(_pdf(tmp_path))


# ── content_list → SourceDocument ────────────────────────────────────────


def _sample_content_list() -> tuple[list[dict], dict[str, bytes]]:
    return (
        [
            {"type": "text", "text": "Book Title", "text_level": 1, "page_idx": 0},
            {"type": "text", "text": "preface text", "page_idx": 0},
            {"type": "text", "text": "Chapter One", "text_level": 2, "page_idx": 1},
            {"type": "text", "text": "First paragraph.", "page_idx": 1},
            {
                "type": "image",
                "img_path": "images/img1.jpg",
                "image_caption": ["Figure 1"],
                "image_footnote": ["Text swallowed as footnote."],
                "page_idx": 1,
            },
            {"type": "text", "text": "Chapter Two", "text_level": 2, "page_idx": 5},
            {"type": "chart", "img_path": "images/img2.jpg", "page_idx": 6},
            {"type": "equation", "text": "E=mc^2", "page_idx": 6},
            {"type": "header", "text": "running head", "page_idx": 6},
        ],
        {"images/img1.jpg": b"JPG1", "images/img2.jpg": b"JPG2"},
    )


def test_read_mineru_maps_content_list(tmp_path: Path) -> None:
    """文本/标题/图/表/公式映射 + image_footnote 吐回正文 + header 剔除。"""
    items, images = _sample_content_list()
    zip_bytes = _result_zip(items, markdown="# full", images=images)
    client = _client(_mock_transport(zip_bytes=zip_bytes))
    raw_dir = tmp_path / "raw"

    doc = read_mineru(_pdf(tmp_path), raw_dir=raw_dir, client=client)

    assert doc.fmt == "pdf"
    assert doc.meta["parser"] == "mineru"
    assert doc.meta["pages"] == 7  # max(page_idx)+1

    # 切章：text_level=2 为最小章级 → Book Title 前无内容级（level1 首块），
    # chapter_level=1？不——levels={1,2}，min=1：Book Title 自成 fm+首章边界
    titles = [u.title for u in doc.units]
    assert "Chapter One" in titles and "Chapter Two" in titles

    ch1 = next(u for u in doc.units if u.title == "Chapter One")
    texts = [s.source for s in ch1.segments]
    # image_footnote 的文本必须吐回正文（GT2 实测坑）
    assert "Text swallowed as footnote." in texts
    assert "Figure 1" in texts
    # 图片引用存在且指向 raw/media
    img_refs = [t for t in texts if t.startswith("![")]
    assert len(img_refs) == 1 and "(raw/media/p002-img01.jpg)" in img_refs[0]

    # 媒体落盘 + inserts 记录
    assert (raw_dir / "media" / "p002-img01.jpg").read_bytes() == b"JPG1"
    inserts = json.loads((raw_dir / "inserts" / "p002-img01.json").read_text())
    assert inserts["source"]["method"] == "mineru"
    assert inserts["source"]["page"] == 2
    # raw/mineru 审计产物
    assert (raw_dir / "mineru" / "full.md").read_text() == "# full"

    ch2 = next(u for u in doc.units if u.title == "Chapter Two")
    texts2 = [s.source for s in ch2.segments]
    assert any(t.startswith("![") and "p007" in t for t in texts2)  # chart 也走图片路由
    assert "$$E=mc^2$$" in texts2  # 公式 latex 包 $$
    assert "running head" not in texts2  # header 剔除

    # 公式 insert 记录带 latex
    fml = json.loads((raw_dir / "inserts" / "p007-fml01.json").read_text())
    assert fml["latex"] == "E=mc^2"


def test_read_mineru_table_with_html_body(tmp_path: Path) -> None:
    """表格：img_path 走图路由 + table_body html 存 extra 供 agent 参考。"""
    items = [
        {"type": "text", "text": "Chapter", "text_level": 1, "page_idx": 0},
        {
            "type": "table",
            "img_path": "images/tbl.jpg",
            "table_caption": ["Table 1"],
            "table_body": "<table><tr><td>1</td></tr></table>",
            "page_idx": 0,
        },
    ]
    zip_bytes = _result_zip(items, images={"images/tbl.jpg": b"TBL"})
    client = _client(_mock_transport(zip_bytes=zip_bytes))
    doc = read_mineru(_pdf(tmp_path), raw_dir=tmp_path / "raw", client=client)
    ch = next(u for u in doc.units if u.title == "Chapter")
    texts = [s.source for s in ch.segments]
    assert "Table 1" in texts
    rec = json.loads((tmp_path / "raw" / "inserts" / "p001-tbl01.json").read_text())
    assert rec["type"] == "table"
    assert rec["extra"]["table_body_html"].startswith("<table>")


def test_read_mineru_missing_image_bytes_no_dangling_ref(tmp_path: Path) -> None:
    """图片字节缺失：不产生悬空引用（宁缺毋滥），caption 文本保留。"""
    items = [
        {"type": "text", "text": "Chapter", "text_level": 1, "page_idx": 0},
        {
            "type": "image",
            "img_path": "images/gone.jpg",
            "image_caption": ["Caption kept"],
            "page_idx": 0,
        },
    ]
    zip_bytes = _result_zip(items)
    client = _client(_mock_transport(zip_bytes=zip_bytes))
    doc = read_mineru(_pdf(tmp_path), raw_dir=tmp_path / "raw", client=client)
    texts = [s.source for u in doc.units for s in u.segments]
    assert "Caption kept" in texts
    assert not [t for t in texts if t.startswith("![")]


def test_read_mineru_requires_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINERU_API_KEY", raising=False)
    with pytest.raises(MineruError, match="MINERU_API_KEY"):
        read_mineru(_pdf(tmp_path))


def test_aggregate_mineru_chapters_no_headings() -> None:
    """无标题信号 → 单单元（与 aggregate_pdf_chapters 回退一致）。"""
    from auto_epublizer.ingest.models import SourceSegment

    segs = [
        SourceSegment(index=0, source="a", kind=KIND_TEXT, meta={}),
        SourceSegment(index=1, source="b", kind=KIND_TEXT, meta={}),
    ]
    units = aggregate_mineru_chapters(segs, book_title="T")
    assert len(units) == 1 and units[0].title == "T"


def test_aggregate_mineru_chapters_pre_content_frontmatter() -> None:
    """每个标题（任意层级）都是单元边界；源文层级写入 heading_level。"""
    from auto_epublizer.ingest.models import SourceSegment

    segs = [
        SourceSegment(index=0, source="Intro", kind=KIND_TEXT, meta={}),
        SourceSegment(index=1, source="Ch 1", kind=KIND_HEADING, meta={"mineru_text_level": 1}),
        SourceSegment(index=2, source="body", kind=KIND_TEXT, meta={}),
        SourceSegment(index=3, source="Sub", kind=KIND_HEADING, meta={"mineru_text_level": 2}),
        SourceSegment(index=4, source="more", kind=KIND_TEXT, meta={}),
        SourceSegment(index=5, source="Ch 2", kind=KIND_HEADING, meta={"mineru_text_level": 1}),
        SourceSegment(index=6, source="tail", kind=KIND_TEXT, meta={}),
    ]
    units = aggregate_mineru_chapters(segs, book_title="T")
    assert [u.id for u in units] == ["fm01", "ch01", "ch02", "ch03"]
    assert units[0].kind == "frontmatter"
    # 源文标题层级原样保留（目录据此嵌套，E_TOC_FLAT 才能真实校验）
    assert units[1].title == "Ch 1" and units[1].meta["heading_level"] == 1
    assert units[2].title == "Sub" and units[2].meta["heading_level"] == 2
    assert units[3].title == "Ch 2" and units[3].meta["heading_level"] == 1
    assert [s.source for s in units[1].segments] == ["Ch 1", "body"]
    assert [s.source for s in units[2].segments] == ["Sub", "more"]


# ── 编排路由决策 + 全链路 ────────────────────────────────────────────────


def _pdf_store(tmp_path: Path):
    """已 init 的工作区（文字层 PDF + pymupdf 后端，离线不触发 MinerU/OCR）。"""
    from auto_common.config import Config, PDFConfig
    from auto_epublizer import orchestrator as orch

    store = orch.init(
        str(_pdf(tmp_path)),
        workspace_dir=tmp_path / "ws",
        config=Config(pdf=PDFConfig(backend="pymupdf", ocr="off")),
    )
    return store


def test_mineru_decision_forced_missing_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """backend=mineru 且无 key → 明确报错（要求向用户询问 key）。"""
    from auto_common.config import Config, PDFConfig
    from auto_epublizer import orchestrator as orch

    store = _pdf_store(tmp_path)
    monkeypatch.delenv("MINERU_API_KEY", raising=False)
    with pytest.raises(orch.OrchestrationError, match="MINERU_API_KEY"):
        orch._mineru_client_if_preferred(store, Config(pdf=PDFConfig(backend="mineru")))


def _patch_sniff_scanned(monkeypatch: pytest.MonkeyPatch) -> None:
    """让嗅探判定扫描件（经 importlib 取真子模块，规避 preprocess 包对函数的遮蔽）。"""
    import importlib

    sniff_module = importlib.import_module("auto_epublizer.preprocess.sniff")
    monkeypatch.setattr(sniff_module, "sniff", lambda p: {"scanned": True})


def test_mineru_decision_matrix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """强制/禁用/auto×扫描 的路由矩阵（auto：文字层 PDF 不走 MinerU）。"""
    from auto_common.config import Config, PDFConfig
    from auto_epublizer import orchestrator as orch
    from auto_epublizer.ingest.mineru import MineruClient

    store = _pdf_store(tmp_path)
    monkeypatch.setenv("MINERU_API_KEY", "k")

    forced = orch._mineru_client_if_preferred(store, Config(pdf=PDFConfig(backend="mineru")))
    assert isinstance(forced, MineruClient)

    disabled = orch._mineru_client_if_preferred(store, Config(pdf=PDFConfig(backend="pymupdf")))
    assert disabled is None

    # auto + 文字层 PDF（真实嗅探，非扫描）→ 不走 MinerU
    auto_text = orch._mineru_client_if_preferred(store, Config())
    assert auto_text is None

    # auto + 扫描件（嗅探 monkeypatch 为 scanned）→ MinerU
    _patch_sniff_scanned(monkeypatch)
    auto_scanned = orch._mineru_client_if_preferred(store, Config())
    assert isinstance(auto_scanned, MineruClient)


class _FakeClient:
    """e2e 用假 MinerU 客户端：返回固定解析产物，全程离线。"""

    def __init__(self, token: str, **kwargs: object) -> None:
        pass

    def parse_file(self, path, *, model_version="pipeline", language="ch", is_ocr=True):
        from auto_epublizer.ingest.mineru import MineruParseResult

        items, images = _sample_content_list()
        return MineruParseResult(content_list=items, markdown="# full", images=images)


def test_mineru_e2e_init_scanned_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """扫描件 + auto + key → init 全链路走 MinerU：structured/units/raw 落盘正确。"""
    from auto_common.config import Config
    from auto_epublizer import orchestrator as orch

    monkeypatch.setenv("MINERU_API_KEY", "k")
    _patch_sniff_scanned(monkeypatch)
    monkeypatch.setattr("auto_epublizer.ingest.mineru.MineruClient", _FakeClient)

    store = orch.init(str(_pdf(tmp_path)), workspace_dir=tmp_path / "ws", config=Config())
    pub = store.load_publication()
    assert len(pub.units) == 3  # 书名+序言 / Chapter One / Chapter Two

    structured = store.structured_dir
    # 首单元：书名 + 序言（标题关键词未命中辅文 → 归正文首章）
    ch1_md = (structured / "body" / "ch01.md").read_text(encoding="utf-8")
    assert "preface text" in ch1_md
    # Chapter One：正文 + 插图引用（caption/footnote 吐回）
    body_md = (structured / "body" / "ch02.md").read_text(encoding="utf-8")
    assert "First paragraph." in body_md
    assert "![p002-img01](raw/media/p002-img01.jpg)" in body_md
    assert "Text swallowed as footnote." in body_md
    # 媒体与审计产物落盘
    assert (structured / "raw" / "media" / "p002-img01.jpg").read_bytes() == b"JPG1"
    assert (structured / "raw" / "mineru" / "full.md").read_text() == "# full"
    ins = json.loads((structured / "raw" / "inserts" / "p002-img01.json").read_text())
    assert ins["source"]["method"] == "mineru"
