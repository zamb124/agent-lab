"""
Worktracker-специфичные фикстуры.

HTTP: worktracker_client (ASGI), worktracker_client_http (session HTTP).
Service: worktracker_di, worktracker_service.
Helpers: worktracker_queue, worktracker_board, worktracker_item.
Realtime: platform_events_listener (шина Redis platform:events).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx2 import ASGITransport, AsyncClient

from apps.worktracker.di import WorktrackerDi
from core.di import require_di
from core.worktracker.models import (
    Board,
    BoardColumn,
    UserActor,
    WorkItem,
    WorkItemState,
    WorkQueue,
)
from core.worktracker.service import WorkItemService
from tests.fixtures.platform_events import (
    PlatformEventsReceive,
)
from tests.fixtures.platform_events import (
    platform_events_listener as open_platform_events_stream,
)
from tests.fixtures.service_processes import ServiceProcesses

API_PREFIX = "/worktracker/api/v1"

UiEventsReceive = PlatformEventsReceive


@pytest_asyncio.fixture
async def worktracker_di(worktracker_app) -> WorktrackerDi:
    """Тот же ``WorktrackerDi``, что собрал lifespan ``worktracker_app``."""
    return require_di(worktracker_app, WorktrackerDi)


@pytest.fixture
def worktracker_service(request: pytest.FixtureRequest) -> WorkItemService:
    opened = request.getfixturevalue("worktracker_di")
    if not isinstance(opened, WorktrackerDi):
        raise TypeError("worktracker DI is not open")
    return opened.work_item_service


@pytest_asyncio.fixture
async def worktracker_app(service_processes: ServiceProcesses):
    return await service_processes.app("worktracker")


@pytest_asyncio.fixture
async def worktracker_client(worktracker_app, setup_database_before_tests, auth_headers_system):
    _ = setup_database_before_tests
    transport = ASGITransport(app=worktracker_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers=auth_headers_system,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def worktracker_client_company2(worktracker_app, setup_database_before_tests, auth_headers_company2):
    _ = setup_database_before_tests
    transport = ASGITransport(app=worktracker_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers=auth_headers_company2,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def worktracker_queue(
    worktracker_service, unique_id: str, system_user_id: str
) -> WorkQueue:
    return await worktracker_service.create_queue(
        company_id="system",
        name=f"Queue {unique_id}",
        slug=f"q-{unique_id}",
        creator=UserActor(user_id=system_user_id),
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
async def platform_events_listener() -> AsyncIterator[UiEventsReceive]:
    async with open_platform_events_stream() as receive:
        yield receive
