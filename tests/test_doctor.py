"""doctor 能力自检测试：探测结构、降级语义、multimodal 留空（离线、确定）。"""

from __future__ import annotations

from typing import Any

from auto_common.config import Config
from auto_epublizer.doctor import Capability, capabilities_summary, collect_capabilities


def _find(caps: list[Capability], name: str) -> Capability:
    return next(c for c in caps if c.name == name)


def test_collect_capabilities_returns_all_probes() -> None:
    caps = collect_capabilities(Config(), ping=False)
    names = {c.name for c in caps}
    assert {
        "pandoc",
        "pdftotext",
        "tesseract",
        "pymupdf",
        "rapidocr",
        "lxml",
        "epubcheck",
        "llm_key",
        "llm_vision_model",
    } <= names


def test_summary_json_shape_and_multimodal_null() -> None:
    caps = collect_capabilities(Config(), ping=False)
    summary: dict[str, Any] = capabilities_summary(caps)
    assert summary["multimodal"] is None  # agent 自报，CLI 无法探测
    for item in summary["capabilities"].values():
        assert isinstance(item["available"], bool)
        assert "impact" in item and "hint" in item


def test_llm_key_absent_marks_unavailable(monkeypatch) -> None:

    cfg = Config()
    monkeypatch.delenv(cfg.llm.api_key_env, raising=False)
    caps = collect_capabilities(cfg, ping=False)
    llm = _find(caps, "llm_key")
    assert llm.available is False
    assert "export" in llm.hint


def test_epubcheck_missing_jar_has_download_hint(tmp_path) -> None:
    cfg = Config()
    cfg.qc.epubcheck.jar = str(tmp_path / "nope.jar")
    caps = collect_capabilities(cfg, ping=False)
    epub = _find(caps, "epubcheck")
    assert epub.available is False
    assert "epubcheck" in epub.hint.lower() or "下载" in epub.hint
