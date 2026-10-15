# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""analysis：语言/体裁确定性检测 + 文体档案渲染（零 token；理解是 agent 任务）。"""

from __future__ import annotations

from .detect import detect_genre, detect_language
from .service import render_style_md

__all__ = ["detect_genre", "detect_language", "render_style_md"]
