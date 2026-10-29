"""Access Explorer: поиск и гидрация объектов через репозитории владельцев (реальные БД)."""

from __future__ import annotations

import pytest
from httpx2 import AsyncClient

from core.authz.types import AuthzObjectType
from core.utils.tokens import get_token_service

pytestmark = pytest.mark.timeout(60, func_only=True)

_API = "/frontend/api/authz/explorer"


@pytest.mark.asyncio
async def test_explorer_objects_search_returns_hits_for_every_owner(
    frontend_client: AsyncClient,
    auth_headers_system,
) -> None:
    response = await frontend_client.get(f"{_API}/objects", headers=auth_headers_system, params={"q": ""})
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["items"], list)
    for item in body["items"]:
        assert item["object_key"]
        assert item["object_type"] in {kind.value for kind in AuthzObjectType}
        assert item["href"].startswith("/")


@pytest.mark.asyncio
async def test_explorer_by_object_hydrates_platform_namespace(
    frontend_client: AsyncClient,
    auth_headers_system,
) -> None:
    token_data = get_token_service().validate_token(auth_headers_system["Authorization"].replace("Bearer ", ""))
    assert token_data is not None
    response = await frontend_client.get(
        f"{_API}/by-object",
        headers=auth_headers_system,
        params={
            "object_type": AuthzObjectType.PLATFORM_NAMESPACE.value,
            "object_key": f"{token_data.company_id}/default",
        },
    )
    assert response.status_code == 200, response.text
    hydrated = response.json()
    assert hydrated["title"] == "default"
    assert hydrated["title_status"] == "loaded"
    assert hydrated["namespace"] == "default"


@pytest.mark.asyncio
async def test_explorer_by_object_missing_wiki_page(
    frontend_client: AsyncClient,
    auth_headers_system,
    unique_id: str,
) -> None:
    response = await frontend_client.get(
        f"{_API}/by-object",
        headers=auth_headers_system,
        params={"object_type": AuthzObjectType.WIKI_PAGE.value, "object_key": f"missing-{unique_id}"},
    )
    assert response.status_code == 404, response.text
