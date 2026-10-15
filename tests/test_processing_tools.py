"""实际解析产物及工作区登记的工具快照；版本只在 ingest 时取得。"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import httpx
import pymupdf
import pytest

from auto_common.config import Config
from auto_common.workspace import init_workspace
from auto_epublizer import fingerprint
from auto_epublizer.ingest import load_document
from auto_epublizer.ingest.mineru import MineruClient
from auto_epublizer.ingest.ocr import FakeOcrBackend, RapidOcrBackend, rapidocr_available
from auto_epublizer.ingest.pandoc_reader import pandoc_available
from auto_epublizer.orchestrator import prepare_structure


def _pdf(path: Path, *, text: str = "", pages: int = 1) -> Path:
    with pymupdf.open() as doc:
        for _ in range(pages):
            page = doc.new_page()
            if text:
                page.insert_text((72, 100), text)
        doc.save(path)
    return path


def _local_pdf_config() -> Config:
    config = Config()
    config.pdf.backend = "pymupdf"
    config.pdf.ocr = "off"
    return config


@pytest.mark.parametrize("suffix", [".txt", ".md", ".markdown"])
def test_text_processing_tools_are_explicitly_empty(tmp_path: Path, suffix: str) -> None:
    source = tmp_path / f"book{suffix}"
    original = b"# Chapter One\n\nPlain text content.\n"
    source.write_bytes(original)
    doc = load_document(source)
    assert any("Plain text content." in s.source for u in doc.units for s in u.segments)
    assert doc.meta["processing_tools"] == []

    store = init_workspace(source, workspace_dir=tmp_path / "workspace")
    entries = prepare_structure(store)
    assert store.load_publication().meta.processing_tools == []
    assert "Plain text content." in (store.structured_dir / entries[0]["rel_path"]).read_text()
    assert store.read_events()[-1]["processing_tools"] == []
    assert source.read_bytes() == original
    assert (store.dir / store.load_publication().meta.source).read_bytes() == original


def test_text_pdf_does_not_record_unused_rapidocr(tmp_path: Path) -> None:
    source = _pdf(tmp_path / "text.pdf", text="Existing PDF text layer.")
    # 真正的后端类型已配置，但不初始化可选引擎；误走 OCR 会直接报错。
    backend = object.__new__(RapidOcrBackend)
    doc = load_document(source, ocr_backend=backend)
    assert any("Existing PDF text layer." in s.source for u in doc.units for s in u.segments)
    assert doc.meta["processing_tools"] == [fingerprint.used_tool("pymupdf")]


@pytest.mark.skipif(not rapidocr_available(), reason="需要真实 RapidOCR")
def test_scanned_pdf_records_rapidocr_only_after_real_page_processing(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    with pymupdf.open() as original:
        page = original.new_page()
        page.insert_text((72, 150), "HELLO OCR CONTENT", fontsize=32)
        image = page.get_pixmap(dpi=150).tobytes("png")
        with pymupdf.open() as scan:
            scanned_page = scan.new_page()
            scanned_page.insert_image(scanned_page.rect, stream=image)
            scan.save(source)
    doc = load_document(source, ocr_backend=RapidOcrBackend())
    assert any("OCR" in s.source for u in doc.units for s in u.segments)
    assert doc.meta["processing_tools"] == [
        fingerprint.used_tool("pymupdf"),
        fingerprint.used_tool("rapidocr"),
    ]


class _CustomOcrBackend(RapidOcrBackend):
    def __init__(self) -> None:
        self.calls = 0

    def ocr_image(self, image_path: str) -> str:
        assert Path(image_path).read_bytes().startswith(b"\x89PNG")
        self.calls += 1
        return "Custom OCR content."


@pytest.mark.parametrize("backend", [FakeOcrBackend("Custom OCR content."), _CustomOcrBackend()])
def test_fake_and_custom_ocr_do_not_claim_rapidocr(tmp_path: Path, backend) -> None:
    source = _pdf(tmp_path / "scan.pdf")
    doc = load_document(source, ocr_backend=backend)
    assert any("Custom OCR content." in s.source for u in doc.units for s in u.segments)
    assert doc.meta["processing_tools"] == [fingerprint.used_tool("pymupdf")]
    if isinstance(backend, _CustomOcrBackend):
        assert backend.calls == 1


@pytest.mark.skipif(not pandoc_available(), reason="需要真实 pandoc")
@pytest.mark.parametrize("suffix", [".html", ".docx", ".epub"])
def test_real_pandoc_input_registers_consumed_tool(tmp_path: Path, suffix: str) -> None:
    html = tmp_path / "input.html"
    html.write_text("<h1>Chapter One</h1><p>Actual Pandoc parsed content.</p>", encoding="utf-8")
    source = html
    if suffix != ".html":
        source = tmp_path / f"book{suffix}"
        subprocess.run(["pandoc", str(html), "-o", str(source)], check=True, timeout=30)
    original = source.read_bytes()
    store = init_workspace(source, workspace_dir=tmp_path / "workspace")
    entries = prepare_structure(store)
    text = "\n".join((store.structured_dir / e["rel_path"]).read_text() for e in entries)
    assert "Actual Pandoc parsed content." in text
    assert store.load_publication().meta.processing_tools == [fingerprint.used_tool("pandoc")]
    assert store.read_events()[-1]["processing_tools"] == [fingerprint.used_tool("pandoc")]
    assert source.read_bytes() == original
    assert (store.dir / store.load_publication().meta.source).read_bytes() == original


def test_registered_version_survives_environment_change_and_failed_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _pdf(tmp_path / "book.pdf", text="Persisted source content.")
    store = init_workspace(source, workspace_dir=tmp_path / "workspace")
    config = _local_pdf_config()
    entries = prepare_structure(store, config=config)
    assert (
        "Persisted source content." in (store.structured_dir / entries[0]["rel_path"]).read_text()
    )
    frozen = store.load_publication().meta.processing_tools
    assert frozen == [fingerprint.used_tool("pymupdf")]
    assert frozen[0]["version"] is not None
    original_source = (store.dir / store.load_publication().meta.source).read_bytes()

    monkeypatch.setattr(fingerprint.metadata, "version", lambda distribution: "999.888.777")
    monkeypatch.setattr(fingerprint, "_revision", lambda: (None, None))
    assert fingerprint.used_tool("pymupdf")["version"] == "999.888.777"
    current_build = fingerprint.build_fingerprint(store.load_publication())
    assert current_build["runtime"][1]["version"] == "999.888.777"
    assert current_build["processing_tools"] == frozen

    def interrupted(done: int, total: int) -> None:
        raise RuntimeError("Parsing interrupted")

    with pytest.raises(RuntimeError, match="Parsing interrupted"):
        prepare_structure(store, config=config, progress=interrupted)
    assert store.load_publication().meta.processing_tools == frozen
    assert store.read_events()[-1]["processing_tools"] == frozen
    assert (store.dir / store.load_publication().meta.source).read_bytes() == original_source


def test_mineru_records_actual_http_client_and_pdf_slicing(tmp_path: Path) -> None:
    source = _pdf(tmp_path / "remote.pdf", text="Local PDF content.", pages=2)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as result_zip:
        result_zip.writestr(
            "result_content_list.json",
            json.dumps([{"type": "text", "text": "Remote parsed content.", "page_idx": 0}]),
        )
        result_zip.writestr("full.md", "Remote parsed content.")
    uploads: list[bytes] = []
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/file-urls/batch"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "batch_id": "batch",
                        "file_urls": ["https://upload.invalid/pdf"],
                    },
                },
            )
        if request.method == "PUT":
            uploads.append(request.content)
            return httpx.Response(200)
        if "/extract-results/batch/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "extract_result": [
                            {
                                "state": "done",
                                "full_zip_url": "https://download.invalid/result.zip",
                            }
                        ]
                    },
                },
            )
        assert request.url.host == "download.invalid"
        return httpx.Response(200, content=archive.getvalue())

    client = MineruClient("test-token", transport=httpx.MockTransport(handler), poll_interval=0)
    doc = load_document(source, mineru_client=client, mineru_batch_pages=1)
    segments = [s for u in doc.units for s in u.segments]
    assert sum("Remote parsed content." in s.source for s in segments) == 2
    assert {s.meta["source_page"] for s in segments} == {1, 2}
    assert len(uploads) == 2
    for uploaded in uploads:
        with pymupdf.open(stream=uploaded, filetype="pdf") as part:
            assert part.page_count == 1
    assert len(requests) == 8
    assert doc.meta["processing_tools"] == [
        fingerprint.used_tool("pymupdf"),
        fingerprint.used_tool("mineru"),
        fingerprint.used_tool("httpx"),
    ]
    service = doc.meta["processing_tools"][1]
    assert service["kind"] == "service"
    assert service["version"] is None
    assert service["license"] is None


@pytest.mark.skipif(
    not pandoc_available() or shutil.which("ebook-convert") is None,
    reason="需要真实 pandoc 与 calibre",
)
def test_real_kindle_conversion_records_calibre_then_parser(tmp_path: Path) -> None:
    html = tmp_path / "source.html"
    html.write_text("<h1>Chapter One</h1><p>Actual Kindle parsed content.</p>", encoding="utf-8")
    source = tmp_path / "book.mobi"
    subprocess.run(["ebook-convert", str(html), str(source)], check=True, timeout=120)
    original = source.read_bytes()
    doc = load_document(source)
    assert any("Actual Kindle parsed content." in s.source for u in doc.units for s in u.segments)
    assert doc.meta["processing_tools"] == [
        fingerprint.used_tool("calibre"),
        fingerprint.used_tool("pandoc"),
    ]
    assert source.read_bytes() == original
