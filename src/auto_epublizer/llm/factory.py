"""按配置创建 LLM provider 客户端。"""

from __future__ import annotations

from ..config import LLMConfig
from .base import LLMClient
from .providers.fake import FakeClient
from .providers.openai_compatible import OpenAICompatibleClient


def create_client(llm: LLMConfig) -> LLMClient:
    if llm.provider == "fake":
        return FakeClient()
    if llm.provider in {"openai-compatible", "openai", "deepseek", "ollama"}:
        return OpenAICompatibleClient(
            base_url=llm.base_url,
            api_key=llm.api_key(),
            timeout=llm.timeout,
            max_retries=llm.max_retries,
            tiers={name: cfg.model_dump(mode="json") for name, cfg in llm.tiers.items()},
        )
    raise ValueError(f"未知 provider：{llm.provider}")


__all__ = ["create_client", "FakeClient", "LLMClient"]
