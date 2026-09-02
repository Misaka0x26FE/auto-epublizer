"""LLM 抽象测试：FakeClient、宽松 JSON、档位、重试、用量账本。"""

from __future__ import annotations

from typing import Any

import pytest

from auto_common.config import LLMConfig
from auto_common.llm import JsonParseError, create_client, parse_json_loose
from auto_common.llm.base import LLMClient
from auto_common.llm.providers.fake import FakeClient
from auto_common.llm.retrying import retry_reason, with_retries
from auto_common.llm.tiers import resolve_tier
from auto_common.llm.usage import merge_usage_summaries, usage_delta


def test_fake_client_complete() -> None:
    client = FakeClient()
    client.enqueue("hello")
    assert client.complete([{"role": "user", "content": "hi"}], tier="fast") == "hello"


def test_fake_client_json() -> None:
    client = FakeClient()
    client.enqueue_json({"ok": True, "items": [1, 2]})
    assert client.complete_json([{"role": "user", "content": "x"}]) == {
        "ok": True,
        "items": [1, 2],
    }


def test_fake_client_exhausted_raises() -> None:
    client = FakeClient()
    with pytest.raises(RuntimeError, match="脚本已耗尽"):
        client.complete([{"role": "user", "content": "x"}])


def test_fake_client_records_usage() -> None:
    client = FakeClient()
    client.enqueue("a")
    client.enqueue("b")
    client.complete([{"role": "user", "content": "1"}], tier="cheap", stage="translate")
    client.complete([{"role": "user", "content": "2"}], tier="cheap", stage="translate")
    summary = client.usage_summary()
    assert summary["totals"]["calls"] == 2
    assert summary["by_tier"]["cheap"]["calls"] == 2
    assert summary["by_stage"]["translate"]["calls"] == 2


def test_parse_json_loose_strict() -> None:
    assert parse_json_loose('{"a": 1}') == {"a": 1}


def test_parse_json_loose_repaired() -> None:
    assert parse_json_loose('{"a": 1,}') == {"a": 1}


def test_parse_json_loose_fenced() -> None:
    assert parse_json_loose('```json\n{"a": 2}\n```') == {"a": 2}


def test_parse_json_loose_invalid() -> None:
    with pytest.raises(JsonParseError):
        parse_json_loose("不是 JSON")


def test_resolve_tier_direct() -> None:
    tiers = {"strong": "s", "cheap": "c", "fast": "f"}
    assert resolve_tier(tiers, "fast") == "f"


def test_resolve_tier_fallback() -> None:
    tiers = {"strong": "s", "cheap": "c"}
    assert resolve_tier(tiers, "fast") == "c"
    tiers2 = {"strong": "s"}
    assert resolve_tier(tiers2, "cheap") == "s"


def test_retry_reason_classification() -> None:
    class FakeStatus:
        status_code = 429

    class FakeError(Exception):
        def __init__(self, status_code: int) -> None:
            super().__init__("boom")
            self.status_code = status_code

    assert retry_reason(FakeError(429)) == "http_429"
    assert retry_reason(FakeError(503)) == "http_503"
    assert retry_reason(FakeError(400)) is None


def test_with_retries_success_first_try() -> None:
    events: list[dict[str, Any]] = []

    def emit(event: str, **data: Any) -> None:
        events.append({"event": event, **data})

    result = with_retries(
        lambda: "ok", max_retries=2, provider="p", tier="t", stage=None, emit=emit
    )
    assert result == "ok"
    assert events == []


def test_with_retries_recovers() -> None:
    calls = {"n": 0}
    events: list[dict[str, Any]] = []

    class FakeError(Exception):
        status_code = 429

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise FakeError("rate")
        return "ok"

    result = with_retries(
        fn, max_retries=3, provider="p", tier="t", stage=None, emit=lambda e, **d: events.append(d)
    )
    assert result == "ok"
    assert calls["n"] == 3
    assert any(e.get("wait_seconds") is not None for e in events)


def test_with_retries_exhausted() -> None:
    calls = {"n": 0}
    events: list[dict[str, Any]] = []

    class FakeError(Exception):
        status_code = 429

    def fn() -> str:
        calls["n"] += 1
        raise FakeError("rate")

    with pytest.raises(FakeError):
        with_retries(
            fn,
            max_retries=2,
            provider="p",
            tier="t",
            stage=None,
            emit=lambda e, **d: events.append({"event": e, **d}),
        )
    assert calls["n"] == 3
    assert any(e["event"] == "llm_retry_exhausted" for e in events)


def test_usage_delta_and_merge() -> None:
    base: dict[str, Any] = {
        "by_tier": {
            "cheap": {
                "calls": 1,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cache_hit_tokens": 0,
                "cache_miss_tokens": 0,
            }
        },
        "by_stage": {},
    }
    cur: dict[str, Any] = {
        "by_tier": {
            "cheap": {
                "calls": 3,
                "prompt_tokens": 30,
                "completion_tokens": 15,
                "total_tokens": 45,
                "cache_hit_tokens": 0,
                "cache_miss_tokens": 0,
            }
        },
        "by_stage": {
            "translate": {
                "calls": 2,
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
                "cache_hit_tokens": 0,
                "cache_miss_tokens": 0,
            }
        },
    }
    delta = usage_delta(cur, base)
    assert delta["by_tier"]["cheap"]["calls"] == 2
    merged = merge_usage_summaries(base, delta)
    assert merged["totals"]["calls"] == 3


def test_create_fake_client() -> None:
    client = create_client(LLMConfig(provider="fake"))
    assert isinstance(client, LLMClient)


def test_openai_compatible_options_passthrough() -> None:
    import json

    import httpx

    from auto_common.llm.providers.openai_compatible import OpenAICompatibleClient

    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    client = OpenAICompatibleClient(
        base_url="https://example.com",
        api_key="k",
        tiers={"strong": {"model": "m", "options": {"thinking": True, "temperature": 0.1}}},
    )
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    assert client.complete([{"role": "user", "content": "hi"}], tier="strong") == "ok"
    assert captured["payload"]["model"] == "m"
    assert captured["payload"]["thinking"] is True
    assert captured["payload"]["temperature"] == 0.1


def test_fake_validate_credentials() -> None:
    FakeClient().validate_credentials()


def test_event_sink() -> None:
    client = FakeClient()
    events: list[str] = []
    client.set_event_sink(lambda event, **data: events.append(event))
    client.enqueue("x")
    client.complete([{"role": "user", "content": "x"}])
    assert events == []
