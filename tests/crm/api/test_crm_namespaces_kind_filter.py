"""E2E: CRM namespace list excludes personal/technical."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import NamespaceKind
from core.namespace import personal_namespace_name
from core.utils.tokens import get_token_service


@pytest.mark.asyncio
async def test_crm_list_namespaces_excludes_personal_and_technical(
    crm_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    frontend_container,
    unique_id: str,
) -> None:
    owner = get_token_service().validate_token(auth_token_system)
    assert owner is not None
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
        _ = await frontend_container.namespace_service.ensure_personal_namespace(
            owner.user_id, display_name=user.name
        )
        tech = f"office-catalog-crm-{unique_id}"
        _ = await frontend_container.namespace_service.get_or_create(
            tech,
            description="tech",
            kind=NamespaceKind.TECHNICAL,
        )
        ws = f"crm_ws_{unique_id}"
        _ = await frontend_container.namespace_service.create(
            name=ws,
            description="crm workspace",
            kind=NamespaceKind.COMPANY_WORKSPACE,
        )
    finally:
        clear_context()

    response = await crm_client.get(
        "/crm/api/v1/namespaces",
        headers=auth_headers_system,
        params={"limit": 500, "offset": 0},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    names = {item["name"] for item in items}
    assert ws in names
    assert personal_namespace_name(owner.user_id) not in names
    assert tech not in names
    for item in items:
        kind = item.get("kind")
        if kind is not None:
            assert kind == NamespaceKind.COMPANY_WORKSPACE.value
