"""auto_common：基础设施包（EPUB 工作流的共同依赖）。

包含：配置（config）、工作区管理（workspace）。
唯一 LLM 原则：本包不含任何 LLM 抽象/provider——CLI 只做确定性计算。
本包不依赖 auto_translator / auto_epublizer，是依赖方向的底层。
"""

from __future__ import annotations

__all__ = ["config", "workspace"]
