"""analysis：语言/体裁确定性检测 + 文体档案渲染（零 token）。

分层理解（overview/global/units/keypoints/glossary）是 agent 任务——agent 用自身
能力撰写 analysis/*.md；本模块只提供确定性助手（detect_language/detect_genre/
render_style_md），供 convert 路径与 agent 参考。
"""

from __future__ import annotations

from typing import Any

from ..genre.langprofile import get_langprofile
from ..genre.profiles import get_profile
from .detect import detect_genre, detect_language


def render_style_md(
    genre: str,
    *,
    detect: str,
    lang: str,
    style: dict[str, Any] | None = None,
) -> str:
    """按文体档案 + 语言指引生成 analysis/style.md。"""
    profile = get_profile(genre)
    langprofile = get_langprofile(lang)
    lines = [
        "# 文体档案（style.md）",
        "",
        "```yaml",
        f"genre: {genre}",
        f"detect: {detect}",
    ]
    style_vals = style or {}
    if style_vals:
        lines.append("style:")
        for k, v in style_vals.items():
            lines.append(f"  {k}: {v}")
    lines.append("term_types: [" + ", ".join(profile.term_types) + "]")
    lines.append("review_focus: [" + ", ".join(profile.review_focus) + "]")
    lines.append("source_only_types: [" + ", ".join(profile.source_only_types) + "]")
    lines.append("```")
    lines.append("")
    lines.append("## 翻译指引（文体）")
    for rule in profile.translation_rules:
        lines.append(f"- {rule}")
    lines.append("")
    lines.append(f"## 语言指引（源语言 {lang}）")
    for g in langprofile.guidance:
        lines.append(f"- {g}")
    lines.append("")
    return "\n".join(lines)


__all__ = ["detect_genre", "detect_language", "render_style_md"]
