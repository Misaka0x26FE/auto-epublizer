"""LLM provider 共用瞬时错误分类、退避等待与重试执行（自包含，不依赖 tenacity）。"""

from __future__ import annotations

import logging
import random
import ssl
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

_LOGGER = logging.getLogger(__name__)
_RETRYABLE_STATUS_CODES = {408, 409, 429}
_MAX_WAIT_SECONDS = 30.0

_PermanentErrors = (
    httpx.InvalidURL,
    httpx.LocalProtocolError,
    httpx.UnsupportedProtocol,
    ssl.SSLCertVerificationError,
)


def _exception_chain(error: Any) -> Iterator[Any]:
    current = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        cause = getattr(current, "__cause__", None)
        current = cause if cause is not None else getattr(current, "__context__", None)


def _status_code(error: Any) -> int | None:
    for item in _exception_chain(error):
        response = getattr(item, "response", None)
        candidates = (
            getattr(item, "status_code", None),
            getattr(response, "status_code", None),
            getattr(item, "code", None),
        )
        for value in candidates:
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                continue
            try:
                code = int(value)
            except (TypeError, ValueError):
                continue
            if 100 <= code <= 599:
                return code
    return None


def _header(error: Any, name: str) -> str | None:
    for item in _exception_chain(error):
        headers = getattr(getattr(item, "response", None), "headers", None)
        getter = getattr(headers, "get", None)
        if callable(getter):
            value = getter(name)
            if value is not None:
                return str(value).strip()
    return None


def retry_reason(error: Any) -> str | None:
    status_code = _status_code(error)
    if status_code is not None:
        if status_code in _RETRYABLE_STATUS_CODES or status_code >= 500:
            return f"http_{status_code}"
        return None

    chain = list(_exception_chain(error))
    if any(isinstance(item, _PermanentErrors) for item in chain):
        return None
    for item in chain:
        if isinstance(item, (TimeoutError, httpx.TimeoutException)):
            return "timeout"
        if isinstance(item, (ConnectionError, httpx.NetworkError, httpx.ProxyError)):
            return "connection"
    return None


def is_retryable_provider_error(error: Any) -> bool:
    return retry_reason(error) is not None


def _retry_after_seconds(error: Any) -> float | None:
    milliseconds = _header(error, "retry-after-ms")
    if milliseconds:
        try:
            return min(_MAX_WAIT_SECONDS, max(0.0, float(milliseconds) / 1000))
        except ValueError:
            pass
    value = _header(error, "retry-after")
    if not value:
        return None
    try:
        return min(_MAX_WAIT_SECONDS, max(0.0, float(value)))
    except ValueError:
        return None


def _wait_seconds(error: Any, attempt: int) -> float:
    server_wait = _retry_after_seconds(error)
    if server_wait is not None:
        return server_wait
    backoff = min(_MAX_WAIT_SECONDS, (2**attempt) + random.uniform(0, 0.5))
    return backoff


def with_retries[T](
    fn: Callable[[], T],
    *,
    max_retries: int,
    provider: str,
    tier: str,
    stage: str | None,
    emit: Callable[..., None],
) -> T:
    """执行远端调用并选择性重试瞬时错误；永久错误或耗尽时抛出原始异常。"""
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as error:  # noqa: BLE001
            if not is_retryable_provider_error(error):
                raise
            attempt += 1
            if attempt > max_retries:
                _LOGGER.error(
                    "LLM retries exhausted: provider=%s stage=%s tier=%s attempts=%s error=%s",
                    provider,
                    stage or "unknown",
                    tier,
                    attempt,
                    type(error).__name__,
                )
                emit(
                    "llm_retry_exhausted",
                    provider=provider,
                    tier=tier,
                    stage=stage,
                    attempts=attempt,
                    reason=retry_reason(error) or "unknown",
                )
                raise
            wait = _wait_seconds(error, attempt)
            _LOGGER.warning(
                "LLM request retrying: provider=%s stage=%s tier=%s attempt=%s/%s wait=%.3fs reason=%s",
                provider,
                stage or "unknown",
                tier,
                attempt,
                max_retries,
                wait,
                retry_reason(error),
            )
            emit(
                "llm_retry_wait",
                provider=provider,
                tier=tier,
                stage=stage,
                failed_attempt=attempt,
                wait_seconds=round(wait, 3),
            )
            time.sleep(wait)
