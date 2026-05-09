"""
Контракт TaskIQ: retry_on_error/max_retries без SimpleRetryMiddleware не дают повторов.

InMemoryBroker допустим только в этом модуле как минимальная проверка контракта библиотеки;
прод — только RedisStreamBroker (taskiq.mdc).
"""

from __future__ import annotations

import pytest
from taskiq.brokers.inmemory_broker import InMemoryBroker
from taskiq.middlewares.simple_retry_middleware import SimpleRetryMiddleware


@pytest.mark.asyncio
async def test_retry_on_error_without_middleware_runs_once() -> None:
    broker = InMemoryBroker(await_inplace=True)
    calls = {"n": 0}

    @broker.task(retry_on_error=True, max_retries=5)
    async def flaky() -> str:
        calls["n"] += 1
        raise RuntimeError("fail")

    await broker.startup()
    task = await flaky.kiq()
    result = await task.wait_result(timeout=10)
    await broker.shutdown()

    assert calls["n"] == 1
    assert result.is_err


@pytest.mark.asyncio
async def test_retry_on_error_with_simple_retry_middleware_retries() -> None:
    broker = InMemoryBroker(await_inplace=True).with_middlewares(SimpleRetryMiddleware())
    calls = {"n": 0}

    @broker.task(retry_on_error=True, max_retries=5)
    async def flaky_ok_third() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("fail")
        return "ok"

    await broker.startup()
    task = await flaky_ok_third.kiq()
    result = await task.wait_result(timeout=10)
    await broker.shutdown()

    assert calls["n"] == 3
    assert not result.is_err
    assert result.return_value == "ok"
