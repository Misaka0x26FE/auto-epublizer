"""离线测试用 FakeClient：不调用真实 LLM 或网络。"""

from __future__ import annotations

import json
import threading
from typing import Any

from ..base import LLMClient
from ..usage import make_usage_sample


class FakeClient(LLMClient):
    """按脚本返回预设回复；用于测试与演示，不触发任何网络请求。

    线程安全：``complete`` 对脚本弹出与调用记录加锁，供并发路径（C7）测试使用。
    """

    def __init__(self, script: list[dict[str, Any]] | None = None) -> None:
        super().__init__()
        self._script = list(script or [])
        self._calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def enqueue(self, text: str) -> None:
        self._script.append({"text": text})

    def enqueue_json(self, value: Any) -> None:
        self._script.append({"text": json.dumps(value, ensure_ascii=False)})

    def validate_credentials(self) -> None:
        pass

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        tier: str = "strong",
        json_mode: bool = False,
        max_tokens: int | None = None,
        stage: str | None = None,
    ) -> str:
        with self._lock:
            self._calls.append(
                {"messages": messages, "tier": tier, "json_mode": json_mode, "stage": stage}
            )
            if not self._script:
                raise RuntimeError("FakeClient 脚本已耗尽")
            entry = self._script.pop(0)
        usage = entry.get("usage")
        if usage is None:
            usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        self.usage.record(tier, make_usage_sample(usage), stage)
        return entry["text"]
