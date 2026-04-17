"""
Интеграционные тесты доступности team API во всех сервисах.

core/api/team.py подключается в factory.py — эндпоинт GET /members
должен отвечать из любого сервиса с одним и тем же результатом.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytestmark = [pytest.mark.timeout(30)]


@pytest_asyncio.fixture
async def flows_team_client():
    from apps.flows.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def crm_team_client():
    from apps.crm.main import create_app
    crm_app = create_app()
    transport = ASGITransport(app=crm_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def rag_team_client():
    from apps.rag.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def sync_team_client():
    from apps.sync.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def office_team_client():
    from apps.office.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_team_members_endpoint_available_in_all_services(
    unique_id: str,
    frontend_client,
    flows_team_client,
    crm_team_client,
    rag_team_client,
    sync_team_client,
    office_team_client,
    auth_headers_system,
) -> None:
    _ = unique_id
    clients = [
        ("frontend", frontend_client, "/frontend/api/team/members"),
        ("flows", flows_team_client, "/flows/api/team/members"),
        ("crm", crm_team_client, "/crm/api/team/members"),
        ("rag", rag_team_client, "/rag/api/team/members"),
        ("sync", sync_team_client, "/sync/api/team/members"),
        ("office", office_team_client, "/documents/api/team/members"),
    ]

    for service_name, client, url in clients:
        response = await client.get(url, headers=auth_headers_system)
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
    frontend_client,
    flows_team_client,
    crm_team_client,
    rag_team_client,
    sync_team_client,
    office_team_client,
    auth_headers_system,
) -> None:
    _ = unique_id
    clients = [
        ("frontend", frontend_client, "/frontend/api/team/members"),
        ("flows", flows_team_client, "/flows/api/team/members"),
        ("crm", crm_team_client, "/crm/api/team/members"),
        ("rag", rag_team_client, "/rag/api/team/members"),
        ("sync", sync_team_client, "/sync/api/team/members"),
        ("office", office_team_client, "/documents/api/team/members"),
    ]

    member_sets: dict[str, set[str]] = {}
    for service_name, client, url in clients:
        response = await client.get(url, headers=auth_headers_system)
        assert response.status_code == 200
        response_data = response.json()
        members = response_data["items"]
        member_ids = {m["user_id"] for m in members}
        member_sets[service_name] = member_ids

    reference = member_sets["frontend"]
    for service_name, ids in member_sets.items():
        assert ids == reference, (
            f"{service_name} returned different members than frontend: "
            f"extra={ids - reference}, missing={reference - ids}"
        )


@pytest.mark.asyncio
async def test_team_members_response_schema(
    unique_id: str,
    frontend_client,
    auth_headers_system,
) -> None:
    _ = unique_id
    response = await frontend_client.get(
        "/frontend/api/team/members",
        headers=auth_headers_system,
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
    frontend_client,
    flows_team_client,
    crm_team_client,
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
