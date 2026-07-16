"""REST API каталога и CRUD AgentToolkit."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from apps.flows.src.models.agent_toolkit import AgentToolkit
from apps.frontend.config import get_frontend_public_base_url
from tests.agent._helpers import AGENT_API_PREFIX


@pytest.mark.asyncio
async def test_catalog_shape_and_mcp_url(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    from tests.agent.test_platform_mcp_exposure import _repository_context_for_auth

    toolkit_id = f"tk_cat_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name="Catalog toolkit",
                description="For catalog shape test",
                default_enabled=False,
                position=5,
                source="custom",
            )
        )
        try:
            response = await flows_client.get(
                "/flows/api/v1/agent/toolkits",
                headers=auth_headers,
            )
            assert response.status_code == 200, response.text
            items = response.json()
            assert isinstance(items, list)
            matched = next(
                (item for item in items if item.get("toolkit_id") == toolkit_id),
                None,
            )
            assert matched is not None
            frontend_base = get_frontend_public_base_url("humanitec.ru").rstrip("/")
            assert matched["mcp_url"] == (
                f"{frontend_base}/flows/api/v1/agent/platform-mcp/{toolkit_id}"
            )
            assert matched["name"] == "Catalog toolkit"
            positions = [item["position"] for item in items if isinstance(item, dict)]
            assert positions == sorted(positions)
        finally:
            await container.agent_toolkit_repository.delete(toolkit_id)


@pytest.mark.asyncio
async def test_catalog_mcp_url_linnex_host(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    from tests.agent.test_platform_mcp_exposure import _repository_context_for_auth

    toolkit_id = f"tk_linnex_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name="Linnex host toolkit",
                description="MCP URL must use linnex.io apex",
                default_enabled=False,
                position=6,
                source="custom",
            )
        )
        try:
            response = await flows_client.get(
                "/flows/api/v1/agent/toolkits",
                headers={**auth_headers, "Host": "linnex.io"},
            )
            assert response.status_code == 200, response.text
            matched = next(
                (item for item in response.json() if item.get("toolkit_id") == toolkit_id),
                None,
            )
            assert matched is not None
            assert matched["mcp_url"] == (
                f"https://linnex.io/flows/api/v1/agent/platform-mcp/{toolkit_id}"
            )
        finally:
            await container.agent_toolkit_repository.delete(toolkit_id)


@pytest.mark.asyncio
async def test_catalog_device_jwt(
    flows_client: AsyncClient,
    frontend_client_with_auth: AsyncClient,
    unique_id: str,
) -> None:
    pairing = await frontend_client_with_auth.post(f"{AGENT_API_PREFIX}/pairing")
    assert pairing.status_code == 200, pairing.text
    pairing_code = pairing.json()["pairing_code"]
    register = await frontend_client_with_auth.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": pairing_code,
            "device_id": f"device_cat_{unique_id}",
            "device_name": f"Device {unique_id}",
            "os": "darwin",
            "hostname": f"host-{unique_id}",
        },
    )
    assert register.status_code == 200, register.text
    device_token = register.json()["token"]
    response = await flows_client.get(
        "/flows/api/v1/agent/toolkits",
        headers={"Authorization": f"Bearer {device_token}"},
    )
    assert response.status_code == 200, response.text
    items = response.json()
    assert isinstance(items, list)
    toolkit_ids = {item["toolkit_id"] for item in items if isinstance(item, dict)}
    assert toolkit_ids == {"lara"}
    assert items[0]["default_enabled"] is True


@pytest.mark.asyncio
async def test_catalog_revoked_device_returns_401(
    flows_client: AsyncClient,
    frontend_client_with_auth: AsyncClient,
    unique_id: str,
) -> None:
    pairing = await frontend_client_with_auth.post(f"{AGENT_API_PREFIX}/pairing")
    assert pairing.status_code == 200, pairing.text
    pairing_code = pairing.json()["pairing_code"]
    device_id = f"device_revoked_{unique_id}"
    register = await frontend_client_with_auth.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": pairing_code,
            "device_id": device_id,
            "device_name": f"Device {unique_id}",
            "os": "darwin",
            "hostname": f"host-{unique_id}",
        },
    )
    assert register.status_code == 200, register.text
    device_token = register.json()["token"]
    revoke = await frontend_client_with_auth.delete(f"{AGENT_API_PREFIX}/devices/{device_id}")
    assert revoke.status_code == 204
    response = await flows_client.get(
        "/flows/api/v1/agent/toolkits",
        headers={"Authorization": f"Bearer {device_token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_catalog_lazy_backfill_empty_company(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    from core.context import Context, clear_context, get_context, set_context
    from core.models.identity_models import Company
    from tests.agent._helpers import user_id_from_auth_token
    auth_token = auth_headers["Authorization"].removeprefix("Bearer ").strip()
    user_id = user_id_from_auth_token(auth_token)
    user = await frontend_container.user_repository.get(user_id)
    assert user is not None
    company_id = f"empty_tk_company_{unique_id}"
    company = Company(
        company_id=company_id,
        name=f"Empty TK {unique_id}",
        subdomain=f"empty-tk-{unique_id}",
    )
    previous = None

    previous = get_context()
    set_context(
        Context(
            user=user,
            active_company=company,
            session_id="test_session",
            channel="test",
            metadata={},
        )
    )
    try:
        existing = await container.agent_toolkit_repository.list(limit=10)
        for toolkit in existing:
            if toolkit.toolkit_id.startswith("tk_"):
                continue
        response = await flows_client.get(
            "/flows/api/v1/agent/toolkits",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        items = response.json()
        toolkit_ids = {item["toolkit_id"] for item in items if isinstance(item, dict)}
        assert "humanitec_core" in toolkit_ids
    finally:
        clear_context()
        if previous is not None:
            set_context(previous)


@pytest.mark.asyncio
async def test_manage_crud_lifecycle(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> None:
    toolkit_id = f"tk_crud_{unique_id}"
    create = await flows_client.post(
        "/flows/api/v1/agent/toolkits/manage",
        headers=auth_headers,
        json={
            "toolkit_id": toolkit_id,
            "name": "CRUD toolkit",
            "description": "Create test",
            "default_enabled": False,
            "position": 100,
            "flow_ids": [],
            "tool_ids": ["calculator"],
        },
    )
    assert create.status_code == 200, create.text
    assert create.json()["source"] == "custom"

    duplicate = await flows_client.post(
        "/flows/api/v1/agent/toolkits/manage",
        headers=auth_headers,
        json={
            "toolkit_id": toolkit_id,
            "name": "Duplicate",
            "description": "Duplicate",
        },
    )
    assert duplicate.status_code == 409

    get_one = await flows_client.get(
        f"/flows/api/v1/agent/toolkits/manage/{toolkit_id}",
        headers=auth_headers,
    )
    assert get_one.status_code == 200
    assert get_one.json()["toolkit_id"] == toolkit_id

    update = await flows_client.put(
        f"/flows/api/v1/agent/toolkits/manage/{toolkit_id}",
        headers=auth_headers,
        json={
            "name": "CRUD updated",
            "description": "Updated",
            "default_enabled": True,
            "position": 101,
            "flow_ids": [],
            "tool_ids": ["calculator", "rag_search"],
        },
    )
    assert update.status_code == 200
    assert update.json()["name"] == "CRUD updated"

    missing = await flows_client.get(
        f"/flows/api/v1/agent/toolkits/manage/missing_{unique_id}",
        headers=auth_headers,
    )
    assert missing.status_code == 404

    delete = await flows_client.delete(
        f"/flows/api/v1/agent/toolkits/manage/{toolkit_id}",
        headers=auth_headers,
    )
    assert delete.status_code == 200
    assert delete.json()["removed"] is True


@pytest.mark.asyncio
async def test_manage_delete_platform_toolkit_forbidden(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    from tests.agent.test_platform_mcp_exposure import _repository_context_for_auth

    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id="humanitec_core",
                name="Humanitec",
                description="Platform core",
                default_enabled=True,
                position=0,
                flow_ids=["humanitec_agent"],
                tool_ids=["calculator"],
                source="platform",
            )
        )
    response = await flows_client.delete(
        "/flows/api/v1/agent/toolkits/manage/humanitec_core",
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_manage_company_isolation(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    auth_headers_company2: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    from tests.agent.test_platform_mcp_exposure import _repository_context_for_auth

    toolkit_id = f"tk_iso_{unique_id}"

    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name="Isolated",
                description="Company A only",
                source="custom",
            )
        )
    try:
        own_response = await flows_client.get(
            f"/flows/api/v1/agent/toolkits/manage/{toolkit_id}",
            headers=auth_headers,
        )
        assert own_response.status_code == 200, own_response.text

        other_response = await flows_client.get(
            f"/flows/api/v1/agent/toolkits/manage/{toolkit_id}",
            headers=auth_headers_company2,
        )
        assert other_response.status_code == 404
    finally:
        async with _repository_context_for_auth(auth_headers, frontend_container):
            await container.agent_toolkit_repository.delete(toolkit_id)
