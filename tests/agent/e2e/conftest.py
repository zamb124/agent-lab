"""HumanitecAgent E2E через real HTTP (:9004) и WebSocket."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio

def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.timeout(120))


@pytest.fixture(autouse=True)
def agent_e2e_requires_frontend_service(frontend_service: None) -> None:
    _ = frontend_service


@pytest.fixture
def flows_worker(taskiq_worker):
    return taskiq_worker


@pytest.fixture
def flows_container(container):
    return container


@pytest_asyncio.fixture
async def mock_llm_with_queue(
    mock_llm_redis: Callable[[list[Any]], Awaitable[None]],
) -> Callable[[list[Any]], Awaitable[None]]:
    async def _factory(responses: list[Any]) -> None:
        await mock_llm_redis(responses)

    return _factory
