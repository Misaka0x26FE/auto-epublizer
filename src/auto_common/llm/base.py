"""LLM provider 的稳定抽象接口。

所有 provider 实现 ``LLMClient``；重试由统一模块负责，SDK 内置重试应关闭避免嵌套。
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from .json_parser import parse_json_loose
from .usage import UsageTracker

Messages = list[dict[str, str]]
EventSink = Callable[..., None]


class LLMClient(ABC):
    """所有 provider 实现此接口。"""

    def __init__(self) -> None:
        self.usage = UsageTracker()
        self._event_sink: EventSink | None = None
        self._event_sink_lock = threading.Lock()

    def set_event_sink(self, sink: EventSink | None) -> None:
        with self._event_sink_lock:
            self._event_sink = sink

    def _emit_event(self, event: str, **data: Any) -> None:
        with self._event_sink_lock:
            sink = self._event_sink
            if sink is None:
                return
            with suppress(Exception):
                sink(event, **data)

    def usage_summary(self) -> dict[str, Any]:
        return self.usage.summary()

    def validate_credentials(self) -> None:
        """校验凭证可用性；不可用时应抛 ValueError（无 Key 等用户可预期错误）。"""
        return None

    @abstractmethod
    def complete(
        self,
        messages: Messages,
        *,
        tier: str = "strong",
        json_mode: bool = False,
        max_tokens: int | None = None,
        stage: str | None = None,
    ) -> str:
        raise NotImplementedError

    def complete_json(
        self,
        messages: Messages,
        *,
        tier: str = "strong",
        max_tokens: int | None = None,
        stage: str | None = None,
    ) -> Any:
        text = self.complete(
            messages, tier=tier, json_mode=True, max_tokens=max_tokens, stage=stage
        )
        return parse_json_loose(text)
