# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""按书样式（E2）：工作区内的受限 CSS，只允许排版间距，不改字体/颜色/字号。

约束与 ``epub-template-spec`` 的呈现层一致：书籍样式只能微调缩进、段距、行距、对齐、
字重/字形等排版属性；具体字体名、字号、颜色、背景、外部资源和 ``@`` 规则一律拒绝。
路径必须是工作区内相对文件，解析符号链接后仍在工作区内；内容上限 64 KiB。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from auto_common.workspace import RunStore

MAX_CSS_BYTES = 64 * 1024

_ALLOWED = {
    "text-indent",
    "margin",
    "margin-top",
    "margin-right",
    "margin-bottom",
    "margin-left",
    "padding",
    "padding-top",
    "padding-right",
    "padding-bottom",
    "padding-left",
    "line-height",
    "text-align",
    "letter-spacing",
    "word-spacing",
    "font-weight",
    "font-style",
    "hyphens",
    "text-transform",
    "white-space",
    "orphans",
    "widows",
    "page-break-before",
    "page-break-after",
    "page-break-inside",
    "break-before",
    "break-after",
    "break-inside",
}
_DENY = ("url(", "expression(", "javascript:", "<", ">")
_BLOCK = re.compile(r"([^{}]+)\{([^{}]*)\}")


def validate_book_css(css: str) -> None:
    """校验按书 CSS；不合法抛中文 ``ValueError``。"""
    if not isinstance(css, str):
        raise ValueError("按书样式必须是文本")
    if css.count("{") != css.count("}"):
        raise ValueError("按书样式的花括号不配对")
    if "@" in re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL):
        raise ValueError("按书样式不允许 @ 规则（@import/@media/@font-face 等）")
    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    matched = 0
    for match in _BLOCK.finditer(stripped):
        matched += 1
        selector, declarations = match.group(1).strip(), match.group(2)
        if not selector:
            raise ValueError("按书样式存在空选择器")
        for declaration in declarations.split(";"):
            if not declaration.strip():
                continue
            if ":" not in declaration:
                raise ValueError(f"按书样式声明缺冒号：{declaration.strip()[:40]}")
            prop = declaration.split(":", 1)[0].strip().lower()
            if prop not in _ALLOWED:
                raise ValueError(
                    f"按书样式属性不在允许范围：{prop}（只允许缩进/间距/行距/对齐/字重等排版属性）"
                )
            if any(token in declaration.lower() for token in _DENY):
                raise ValueError(f"按书样式含禁用值：{declaration.strip()[:60]}")
    if stripped.strip() and matched == 0:
        raise ValueError("按书样式没有可解析的规则块")
    if stripped.count("{") != matched:
        raise ValueError("按书样式存在无法解析的规则块")


def read_book_css(store: RunStore, rel: str | None) -> tuple[str, str | None]:
    """读取并校验工作区按书样式；返回 ``(css, sha256)``（未配置时为空）。"""
    if not rel:
        return "", None
    raw = Path(str(rel))
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("按书样式必须是工作区内相对路径")
    path = store.dir / raw
    resolved = path.resolve()
    if not resolved.is_relative_to(store.dir.resolve()):
        raise ValueError("按书样式越出工作区")
    if not path.is_file():
        raise ValueError(f"按书样式文件不存在：{rel}")
    data = path.read_bytes()
    if len(data) > MAX_CSS_BYTES:
        raise ValueError(f"按书样式超过 {MAX_CSS_BYTES} 字节上限")
    try:
        css = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"按书样式不是 UTF-8：{exc}") from None
    validate_book_css(css)
    return css, hashlib.sha256(data).hexdigest()


def book_css_meta(path: str, digest: str | None) -> dict[str, Any]:
    """构建事件/摘要用的样式身份。"""
    return {"path": path, "sha256": digest}
