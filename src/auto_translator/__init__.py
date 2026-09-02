"""auto_translator：翻译引擎包（术语/文体/分层理解/翻译/审校）。

依赖 auto_common（config/llm/workspace），不依赖 auto_epublizer（EPUB 转制）。
对外暴露领域服务入口，供 auto_epublizer 编排层调用。
"""

from __future__ import annotations

from . import agents, analysis, genre, glossary, review, translation

__all__ = ["agents", "analysis", "genre", "glossary", "review", "translation"]
