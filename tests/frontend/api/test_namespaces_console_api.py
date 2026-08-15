"""E2E: console namespaces API (admin list/create/filter, ACL)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import NamespaceKind, User
from core.namespace import personal_namespace_name
from core.utils.tokens import get_token_service


async def _viewer_headers(frontend_container, *, unique_id: str, company_id: str) -> dict[str, str]:
    from tests.fixtures.auth import set_test_company_member_roles

    viewer_id = f"ns_viewer_{unique_id}"
    await set_test_company_member_roles(
        frontend_container.company_repository,
        frontend_container.authz_service,
        company_id=company_id,
        user_id=viewer_id,
        roles=["viewer"],
    )
    user = User(
        user_id=viewer_id,
        name=f"Viewer {unique_id}",
        emails=[f"{viewer_id}@t.local"],
        companies={company_id: ["viewer"]},
        active_company_id=company_id,
    )
    await frontend_container.user_repository.set(user)
    token = get_token_service().create_token(
        viewer_id, company_id=company_id, roles=["viewer"]
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_console_list_includes_workspace_and_personal_excludes_technical(
    frontend_client: AsyncClient,
    auth_headers: dict[str, str],
    auth_token: str,
    frontend_container,
    unique_id: str,
) -> None:
    token_service = get_token_service()
    owner = token_service.validate_token(auth_token)
    assert owner is not None

    _ = await frontend_client.get(
        "/frontend/api/namespaces/me/personal",
        headers=auth_headers,
    )

    company = await frontend_container.company_repository.get(owner.company_id)
    user = await frontend_container.user_repository.get(owner.user_id)
    assert company is not None and user is not None
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )
    try:
        tech_name = f"office-catalog-{unique_id}"
        _ = await frontend_container.namespace_service.get_or_create(
            tech_name,
            description="tech",
            kind=NamespaceKind.TECHNICAL,
        )
        ws_name = f"ws_{unique_id}"
        _ = await frontend_container.namespace_service.create(
            name=ws_name,
            description="workspace",
            kind=NamespaceKind.COMPANY_WORKSPACE,
        )
    finally:
        clear_context()

    listed = await frontend_client.get(
        "/frontend/api/namespaces",
        headers=auth_headers,
        params={"limit": 500, "offset": 0},
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    kinds = {item["kind"] for item in items}
    names = {item["name"] for item in items}
    assert NamespaceKind.TECHNICAL.value not in kinds
    assert tech_name not in names
    assert ws_name in names
    assert personal_namespace_name(owner.user_id) in names
    assert NamespaceKind.PERSONAL.value in kinds
    assert NamespaceKind.COMPANY_WORKSPACE.value in kinds

    personal_only = await frontend_client.get(
        "/frontend/api/namespaces",
        headers=auth_headers,
        params={"kind": "personal", "limit": 500},
    )
    assert personal_only.status_code == 200, personal_only.text
    personal_items = personal_only.json()["items"]
    assert personal_items
    assert all(item["kind"] == NamespaceKind.PERSONAL.value for item in personal_items)


@pytest.mark.asyncio
async def test_console_create_lightweight_workspace(
    frontend_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> None:
    name = f"light_{unique_id}"
    created = await frontend_client.post(
        "/frontend/api/namespaces",
        headers=auth_headers,
        json={"name": name, "description": "Lightweight workspace"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == name
    assert body["kind"] == NamespaceKind.COMPANY_WORKSPACE.value
    assert body["owner_user_id"] is None

    listed = await frontend_client.get(
        "/frontend/api/namespaces",
        headers=auth_headers,
        params={"kind": "company_workspace", "limit": 500},
    )
    assert listed.status_code == 200
    names = {item["name"] for item in listed.json()["items"]}
    assert name in names


@pytest.mark.asyncio
async def test_console_create_rejects_reserved_prefixes(
    frontend_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> None:
    for name in (f"user-{unique_id}", f"office-catalog-{unique_id}", f"llm-memory-{unique_id}"):
        response = await frontend_client.post(
            "/frontend/api/namespaces",
            headers=auth_headers,
            json={"name": name, "description": "nope"},
        )
        assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_console_namespaces_forbidden_for_viewer(
    frontend_client: AsyncClient,
    auth_token: str,
    frontend_container,
    unique_id: str,
) -> None:
    owner = get_token_service().validate_token(auth_token)
    assert owner is not None
    viewer_headers = await _viewer_headers(
        frontend_container, unique_id=unique_id, company_id=owner.company_id
    )
    listed = await frontend_client.get(
        "/frontend/api/namespaces",
        headers=viewer_headers,
    )
    assert listed.status_code == 403
    created = await frontend_client.post(
        "/frontend/api/namespaces",
        headers=viewer_headers,
        json={"name": f"vws_{unique_id}", "description": "x"},
    )
    assert created.status_code == 403
