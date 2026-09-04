"""doctor 能力自检测试：探测结构、降级语义、multimodal/search 留空（离线、确定）。"""

from __future__ import annotations

from typing import Any

import httpx

from auto_common.config import Config
from auto_epublizer.doctor import (
    Capability,
    capabilities_summary,
    collect_capabilities,
    probe_network,
)


def _find(caps: list[Capability], name: str) -> Capability:
    return next(c for c in caps if c.name == name)


def test_collect_capabilities_returns_all_probes() -> None:
    caps = collect_capabilities(Config(), ping=False)
    names = {c.name for c in caps}
    assert {
        "pandoc",
        "pdftotext",
        "tesseract",
        "ocrmypdf",
        "pymupdf",
        "rapidocr",
        "lxml",
        "epubcheck",
        "mineru",
        "llm_key",
        "llm_vision_model",
    } <= names
    # network 只在 --ping 时探测（离线默认不出现）
    assert "network" not in names


def test_summary_json_shape_and_self_report_slots() -> None:
    caps = collect_capabilities(Config(), ping=False)
    summary: dict[str, Any] = capabilities_summary(caps)
    assert summary["multimodal"] is None  # agent 自报，CLI 无法探测
    assert summary["search"] is None  # agent 自报，CLI 无法探测
    for item in summary["capabilities"].values():
        assert isinstance(item["available"], bool)
        assert "impact" in item and "hint" in item


def test_mineru_probe_follows_env(monkeypatch) -> None:
    from auto_epublizer.doctor import probe_mineru

    monkeypatch.delenv("MINERU_API_KEY", raising=False)
    assert probe_mineru().available is False
    assert "MINERU_API_KEY" in probe_mineru().hint
    monkeypatch.setenv("MINERU_API_KEY", "k-test")
    cap = probe_mineru()
    assert cap.available is True
    assert cap.hint == ""


def test_network_probe_unavailable_when_all_hosts_fail(monkeypatch) -> None:
    def _fail(url, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", _fail)
    cap = probe_network()
    assert cap.available is False
    assert "references/user" in cap.hint


def test_network_probe_available_on_first_host(monkeypatch) -> None:
    calls: list[str] = []

    def _ok(url, **kwargs):
        calls.append(url)
        return httpx.Response(200)

    monkeypatch.setattr(httpx, "get", _ok)
    cap = probe_network()
    assert cap.available is True
    assert calls == ["https://www.baidu.com"]


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
