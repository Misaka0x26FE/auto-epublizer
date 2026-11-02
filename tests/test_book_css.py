# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""E2 真值表：按书样式（受限 CSS、路径约束、构建摘要）。"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from auto_common.config import Config, OutputConfig
from auto_epublizer import orchestrator as orch
from auto_epublizer.build.bookcss import MAX_CSS_BYTES, read_book_css, validate_book_css


def _workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# Chapter I\n\nBody.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=tmp_path / "ws")
    (store.preprocessing_dir / "book.css").parent.mkdir(parents=True, exist_ok=True)
    return store


def test_valid_style_is_appended_and_digested(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    css = "p { text-indent: 2em; margin: 0; }\nblockquote p { margin-left: 1em; }\n"
    (store.preprocessing_dir / "book.css").write_text(css, encoding="utf-8")
    out = orch.build(store, config=Config(output=OutputConfig(css="preprocessing/book.css")))
    with zipfile.ZipFile(out) as zf:
        style = zf.read("OEBPS/style.css").decode("utf-8")
    assert "blockquote p" in style and "margin-left: 1em" in style
    events = (store.dir / "events.jsonl").read_text(encoding="utf-8")
    assert "book_css_used" in events and "preprocessing/book.css" in events


@pytest.mark.parametrize(
    "css",
    [
        "p { font-size: 12pt; }",
        'p { font-family: "Georgia"; }',
        "p { color: red; }",
        "p { background: url(https://example.com/x.png); }",
        "@import url(https://example.com/x.css);",
        "p { margin: 0; } @media print { p { margin: 1em; } }",
        "p { position: absolute; }",
    ],
)
def test_forbidden_style_is_rejected(css: str) -> None:
    with pytest.raises(ValueError):
        validate_book_css(css)


@pytest.mark.parametrize("rel", ["../outside.css", "/etc/passwd", "missing.css"])
def test_path_escape_and_missing_are_rejected(tmp_path: Path, rel: str) -> None:
    store = _workspace(tmp_path)
    with pytest.raises(ValueError):
        read_book_css(store, rel)


def test_oversize_style_is_rejected(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    path = store.preprocessing_dir / "huge.css"
    path.write_text("p { margin: 0; }\n" * (MAX_CSS_BYTES // 10), encoding="utf-8")
    with pytest.raises(ValueError, match="上限"):
        read_book_css(store, "preprocessing/huge.css")


def test_build_rejects_invalid_style_before_writing(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    (store.preprocessing_dir / "book.css").write_text("p { font-size: 20pt; }", encoding="utf-8")
    with pytest.raises(ValueError, match="允许范围"):
        orch.build(store, config=Config(output=OutputConfig(css="preprocessing/book.css")))
