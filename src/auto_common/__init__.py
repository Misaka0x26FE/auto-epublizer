"""auto_common：基础设施包（翻译与 EPUB 两条路径的共同依赖）。

包含：配置（config）、LLM 抽象（llm）、工作区管理（workspace）。
本包不依赖 auto_translator / auto_epublizer，是依赖方向的底层。
"""

from __future__ import annotations

__all__ = ["config", "llm", "workspace"]
