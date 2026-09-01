"""auto-epublizer：翻译 + 转 EPUB 的 Python CLI。

架构分层：CLI → Orchestrator（薄 façade）→ 领域服务 → agents / llm / glossary / workspace。
"""

__version__ = "0.1.0"
