"""
Worktracker-специфичные фикстуры.

HTTP: worktracker_client (ASGI), worktracker_client_http (session HTTP).
Service/repository: worktracker_container, worktracker_service, worktracker_repository.
Helpers: worktracker_queue, worktracker_board, worktracker_item.
Realtime: worktracker_ui_events_listener (Redis platform:ui_events).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio
import redis.asyncio as redis_async
from httpx import ASGITransport, AsyncClient

from core.config import get_settings
from core.worktracker.models import Board, BoardColumn, WorkItem, WorkItemState, WorkQueue

API_PREFIX = "/worktracker/api/v1"

UiEventsReceive = Callable[[str, str | None, float], Awaitable[list[dict[str, Any]]]]


@pytest.fixture
def worktracker_container():
    from apps.worktracker.container import get_worktracker_container

    return get_worktracker_container()


@pytest.fixture
def worktracker_repository(worktracker_container):
    return worktracker_container.worktracker_repository


@pytest.fixture
def worktracker_service(worktracker_container):
    return worktracker_container.work_item_service


@pytest_asyncio.fixture
async def worktracker_app():
    from apps.worktracker.main import app

    yield app


@pytest_asyncio.fixture
async def worktracker_client(worktracker_app, auth_headers_system):
    transport = ASGITransport(app=worktracker_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers=auth_headers_system,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def worktracker_client_company2(worktracker_app, auth_headers_company2):
    transport = ASGITransport(app=worktracker_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers=auth_headers_company2,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def worktracker_queue(worktracker_service, unique_id: str) -> WorkQueue:
    return await worktracker_service.create_queue(
        company_id="system",
        name=f"Queue {unique_id}",
        slug=f"q-{unique_id}",
    )


@pytest_asyncio.fixture
async def worktracker_board(worktracker_service, unique_id: str) -> Board:
    return await worktracker_service.create_board(
        company_id="system",
        name=f"Board {unique_id}",
        columns=[
            BoardColumn(
                board_column_id="todo",
                label="To do",
                state=WorkItemState.OPEN,
                position=0,
            ),
            BoardColumn(
                board_column_id="done",
                label="Done",
                state=WorkItemState.DONE,
                position=1,
            ),
        ],
    )


@pytest_asyncio.fixture
async def worktracker_item(worktracker_service, unique_id: str) -> WorkItem:
    from core.worktracker.models import SystemActor

    return await worktracker_service.create_manual_task(
        company_id="system",
        title=f"Item {unique_id}",
        created_by=SystemActor(),
    )


@pytest_asyncio.fixture()
async def worktracker_ui_events_listener() -> AsyncIterator[UiEventsReceive]:
    settings = get_settings()
    if not settings.database.redis_url:
        raise RuntimeError("database.redis_url не задан для worktracker_ui_events_listener.")

    client = redis_async.from_url(settings.database.redis_url)
    pubsub = client.pubsub()
    await pubsub.subscribe("platform:ui_events")
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)

    async def _receive(
        filter_type: str,
        target_user_id: str | None,
        timeout: float,
    ) -> list[dict[str, Any]]:
        deadline = asyncio.get_event_loop().time() + timeout
        collected: list[dict[str, Any]] = []
        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=min(remaining, 0.5),
            )
            if msg is None:
                continue
            data = msg.get("data")
            if isinstance(data, (bytes, bytearray)):
                data = data.decode("utf-8")
            if not isinstance(data, str):
                continue
            try:
                envelope = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(envelope, dict):
                continue
            target = envelope.get("target")
            event = envelope.get("event")
            if not isinstance(target, dict) or not isinstance(event, dict):
                continue
            if event.get("type") != filter_type:
                continue
            if target_user_id is not None and target.get("user_id") != target_user_id:
                continue
            collected.append(event)
        return collected

    try:
        yield _receive
    finally:
        await pubsub.unsubscribe("platform:ui_events")
        await pubsub.aclose()
        await client.aclose()
