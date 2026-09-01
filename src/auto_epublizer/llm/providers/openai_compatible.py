"""基于 httpx 的 OpenAI 兼容端点 provider（deepseek/openai/ollama 等统一接入）。"""

from __future__ import annotations

from typing import Any

import httpx

from ..base import LLMClient
from ..retrying import with_retries
from ..tiers import resolve_tier
from ..usage import make_usage_sample


class OpenAICompatibleClient(LLMClient):
    """直连 OpenAI 兼容 ``/chat/completions``，关闭 SDK 内置重试、由统一模块重试。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 600.0,
        max_retries: int = 4,
        tiers: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._tiers = tiers or {}
        self._client = httpx.Client(timeout=timeout)

    def validate_credentials(self) -> None:
        if not self._api_key:
            raise ValueError("缺少 API Key：请设置环境变量（见配置 llm.api_key_env）")

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        tier: str = "strong",
        json_mode: bool = False,
        max_tokens: int | None = None,
        stage: str | None = None,
    ) -> str:
        tier_cfg = resolve_tier(self._tiers, tier)
        payload: dict[str, Any] = {
            "model": tier_cfg["model"],
            "messages": messages,
            "stream": False,
        }
        for key, value in (tier_cfg.get("options") or {}).items():
            payload[key] = value
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        def _call() -> httpx.Response:
            return self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            )

        response = with_retries(
            _call,
            max_retries=self._max_retries,
            provider="openai-compatible",
            tier=tier,
            stage=stage,
            emit=self._emit_event,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            self._emit_event(
                "llm_http_error",
                provider="openai-compatible",
                tier=tier,
                stage=stage,
                status_code=error.response.status_code,
            )
            raise RuntimeError(
                f"LLM 请求失败（HTTP {error.response.status_code}）：{error.response.text[:200]}"
            ) from error

        data = response.json()
        self.usage.record(tier, make_usage_sample(data.get("usage")), stage)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("LLM 响应缺少 choices")
        content = choices[0].get("message", {}).get("content")
        if content is None:
            raise RuntimeError("LLM 响应缺少 message.content")
        return str(content)

    def close(self) -> None:
        self._client.close()
