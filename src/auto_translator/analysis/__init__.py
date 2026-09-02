"""analysis：分层理解（LLM）+ 术语播种 + 语言/体裁检测。"""

from __future__ import annotations

from .detect import detect_genre, detect_language
from .service import analyze, render_style_md

__all__ = ["analyze", "detect_genre", "detect_language", "render_style_md"]
