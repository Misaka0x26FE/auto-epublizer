"""领域服务并发原语：固定 worker 线程池 + 稳定原文序合并。

并发属于具体领域服务（AGENTS.md 架构契约）；结果必须按输入顺序返回，
不得让线程完成顺序改变输出。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor


def map_parallel[T, R](fn: Callable[[T], R], items: Iterable[T], *, workers: int = 4) -> list[R]:
    """以固定 worker 数并发执行 ``fn``，结果按输入顺序返回。

    单元素/workers<=1 时退化为串行（测试与短路场景保持确定性）。
    线程内异常在对应输入位置原样抛出。
    """
    seq = list(items)
    if workers <= 1 or len(seq) <= 1:
        return [fn(x) for x in seq]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(fn, x) for x in seq]
        return [f.result() for f in futures]
