"""auto_translator：翻译引擎包（术语/文体/对齐/G0 校验/审校契约）。

依赖 auto_common（config/workspace），不依赖 auto_epublizer（EPUB 转制）。
唯一 LLM 原则：本包不做任何 LLM 调用——翻译/理解/审校判断由操作 CLI 的 agent
完成，这里只有确定性计算与 agent 产物的读写契约。
"""

from __future__ import annotations

from . import analysis, genre, glossary, review, translation

__all__ = ["analysis", "genre", "glossary", "review", "translation"]
