"""auto-epublizer：翻译 + 转 EPUB 的 Python CLI（转 EPUB + 编排层）。

三包结构（monorepo）：``auto_common``（基础设施）← ``auto_translator``（翻译引擎）
← ``auto_epublizer``（本包：EPUB 转制 + 编排）。本包负责 ingest/structure/build/qa
与 CLI 编排，翻译能力由 auto_translator 提供。
"""

__version__ = "0.1.0"
