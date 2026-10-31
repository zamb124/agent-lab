"""
Интеграционные тесты доступности team API во всех сервисах.

core/api/team.py подключается в factory.py — эндпоинт GET /members
должен отвечать из любого сервиса с одним и тем же результатом.

Не сканировать shared `company:system`: xdist копит roster, N сервисов × N+1 get
даёт timeout. Выделенная компания + OpenFGA tuples.
"""


from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx2 import ASGITransport, AsyncClient

from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service
from tests.fixtures.auth import set_test_company_member_roles

pytestmark = [pytest.mark.timeout(30)]

_PLATFORM_ASGI_BASE_URL = "http://linnex.io"
_PLATFORM_ASGI_HOST_HEADERS = {"Host": "linnex.io"}


async def _asgi_client(app: object) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url=_PLATFORM_ASGI_BASE_URL,
        headers=_PLATFORM_ASGI_HOST_HEADERS,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def flows_team_client(flows_client: AsyncClient) -> AsyncClient:
    return flows_client


@pytest_asyncio.fixture
async def crm_team_client(service_processes):
    async for client in _asgi_client(await service_processes.app("crm")):
        yield client


@pytest_asyncio.fixture
async def rag_team_client(rag_app: object):
    async for client in _asgi_client(rag_app):
        yield client


@pytest_asyncio.fixture
async def sync_team_client(sync_app: object):
    async for client in _asgi_client(sync_app):
        yield client


@pytest_asyncio.fixture
async def office_team_client(office_client: AsyncClient) -> AsyncClient:
    return office_client


async def _seed_team_company(
    frontend_di,
    unique_id: str,
    *,
    extra_member: bool = False,
) -> tuple[dict[str, str], set[str]]:
    company_id = f"team_xsvc_{unique_id}"
    owner_id = f"team_owner_{unique_id}"
    member_id = f"team_member_{unique_id}"
    await User.set(
        User(
            user_id=owner_id,
            name="Team Owner",
            companies={company_id: ["owner", "admin"]},
            active_company_id=company_id,
        )
    )
    await Company.set(
        Company(
            company_id=company_id,
            name=f"Team cross-service {unique_id}",
            owner_user_id=owner_id,
            members={owner_id: ["owner", "admin"]},
        )
    )
    await set_test_company_member_roles(
        frontend_di.authz_service,
        company_id=company_id,
        user_id=owner_id,
        roles=["owner", "admin"],
    )
    expected = {owner_id}
    if extra_member:
        await User.set(
            User(
                user_id=member_id,
                name="Team Member",
                companies={company_id: ["member"]},
                active_company_id=company_id,
            )
        )
        await set_test_company_member_roles(
            frontend_di.authz_service,
            company_id=company_id,
            user_id=member_id,
            roles=["member"],
        )
        expected.add(member_id)
    token = get_token_service().create_token(
        owner_id, company_id=company_id, roles=["owner", "admin"]
    )
    return {"Authorization": f"Bearer {token}"}, expected


def _team_clients(
    frontend_client: AsyncClient,
    flows_team_client: AsyncClient,
    crm_team_client: AsyncClient,
    rag_team_client: AsyncClient,
    sync_team_client: AsyncClient,
    office_team_client: AsyncClient,
) -> list[tuple[str, AsyncClient, str]]:
    return [
        ("frontend", frontend_client, "/frontend/api/team/members"),
        ("flows", flows_team_client, "/flows/api/team/members"),
        ("crm", crm_team_client, "/crm/api/team/members"),
        ("rag", rag_team_client, "/rag/api/team/members"),
        ("sync", sync_team_client, "/sync/api/team/members"),
        ("office", office_team_client, "/documents/api/team/members"),
    ]


@pytest.mark.asyncio
async def test_team_members_endpoint_available_in_all_services(
    unique_id: str,
    frontend_client: AsyncClient,
    frontend_di,
    flows_team_client: AsyncClient,
    crm_team_client: AsyncClient,
    rag_team_client: AsyncClient,
    sync_team_client: AsyncClient,
    office_team_client: AsyncClient,
) -> None:
    headers, _expected = await _seed_team_company(frontend_di, unique_id)
    clients = _team_clients(
        frontend_client,
        flows_team_client,
        crm_team_client,
        rag_team_client,
        sync_team_client,
        office_team_client,
    )

    for service_name, client, url in clients:
        response = await client.get(url, headers=headers)
        assert response.status_code == 200, (
            f"{service_name} must expose team members endpoint, got {response.status_code}"
        )
        response_data = response.json()
        assert isinstance(response_data, dict), f"{service_name} must return dict (ListResponse)"
        assert "items" in response_data, f"{service_name} must have 'items' key"
        members = response_data["items"]
        assert isinstance(members, list), f"{service_name}.items must be list"


@pytest.mark.asyncio
async def test_team_members_consistent_across_services(
    unique_id: str,
    frontend_client: AsyncClient,
    frontend_di,
    flows_team_client: AsyncClient,
    crm_team_client: AsyncClient,
    rag_team_client: AsyncClient,
    sync_team_client: AsyncClient,
    office_team_client: AsyncClient,
) -> None:
    """Состав команды одинаков во всех сервисах.

    Выделенная компания с фиксированным составом (не `system`): в system
    параллельные session-фикстуры других xdist-воркеров добавляют участников
    между запросами к разным сервисам, и сравнение множеств флейкает.
    """
    headers, expected = await _seed_team_company(
        frontend_di, unique_id, extra_member=True
    )
    clients = _team_clients(
        frontend_client,
        flows_team_client,
        crm_team_client,
        rag_team_client,
        sync_team_client,
        office_team_client,
    )

    for service_name, client, url in clients:
        response = await client.get(url, headers=headers)
        assert response.status_code == 200, service_name
        member_ids = {m["user_id"] for m in response.json()["items"]}
        assert member_ids == expected, (
            f"{service_name} returned unexpected members: "
            f"extra={member_ids - expected}, missing={expected - member_ids}"
        )


@pytest.mark.asyncio
async def test_team_members_response_schema(
    unique_id: str,
    frontend_client: AsyncClient,
    frontend_di,
) -> None:
    headers, _expected = await _seed_team_company(frontend_di, unique_id)
    response = await frontend_client.get(
        "/frontend/api/team/members",
        headers=headers,
    )
    assert response.status_code == 200
    response_data = response.json()
    assert isinstance(response_data, dict)
    assert "items" in response_data
    members = response_data["items"]
    assert isinstance(members, list)

    for member in members:
        assert "user_id" in member
        assert "name" in member
        assert "roles" in member
        assert isinstance(member["roles"], list)


@pytest.mark.asyncio
async def test_team_members_unauthorized(
    unique_id: str,
    frontend_client: AsyncClient,
    flows_team_client: AsyncClient,
    crm_team_client: AsyncClient,
) -> None:
    _ = unique_id
    clients = [
        ("frontend", frontend_client, "/frontend/api/team/members"),
        ("flows", flows_team_client, "/flows/api/team/members"),
        ("crm", crm_team_client, "/crm/api/team/members"),
    ]

    for service_name, client, url in clients:
        response = await client.get(url)
        assert response.status_code == 401, (
            f"{service_name} must require auth, got {response.status_code}"
        )
