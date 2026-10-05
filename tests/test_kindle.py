"""#30 §4.1：Kindle 容器（.azw3/.azw/.mobi）经 ebook-convert 转 EPUB。

离线测试只覆盖「缺转换器 → 明确报错」路径；无 calibre 环境下保持一致行为。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from auto_epublizer.ingest import load as load_mod
from auto_epublizer.ingest.kindle import KindleError, as_epub
from auto_epublizer.preprocess.sniff import SniffError as _SniffError
from auto_epublizer.preprocess.sniff import sniff as _sniff


def _no_converter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)


def test_as_epub_missing_converter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_converter(monkeypatch)
    f = tmp_path / "book.azw3"
    f.write_bytes(b"junk")
    with pytest.raises(KindleError) as e, as_epub(f):
        pass
    assert "ebook-convert" in str(e.value)


def test_sniff_azw3_missing_converter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_converter(monkeypatch)
    f = tmp_path / "book.azw3"
    f.write_bytes(b"junk")
    with pytest.raises(_SniffError) as e:
        _sniff(f)
    assert "ebook-convert" in str(e.value)


def test_load_document_mobi_missing_converter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _no_converter(monkeypatch)
    f = tmp_path / "book.mobi"
    f.write_bytes(b"junk")
    with pytest.raises(load_mod.IngestError) as e:
        load_mod.load_document(f)
    assert "ebook-convert" in str(e.value)
