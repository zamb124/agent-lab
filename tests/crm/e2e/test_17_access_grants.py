"""
E2E для OpenFGA grants (CRM sole authz).

Проверяем:
1. Public grant на entity (user:*) + public field projection
2. User grant cross-company + deny без гранта
"""

from typing import cast

import pytest
from httpx import AsyncClient, Response

from core.utils.tokens import get_token_service
from tests.crm.e2e._json_helpers import json_object, object_str


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


@pytest.mark.asyncio
async def test_01_entity_public_grant(
    crm_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_headers_company2: dict[str, str],
) -> None:
    """
    1. System user создает note
    2. Задаёт public_fields типа note
    3. Public grant через OpenFGA (user:* viewer)
    4. User из company2 видит только public projection
    """

    public_fields_response = await crm_client.put(
        "/crm/api/v1/entity-types/note/public-fields",
        json={
            "type_id": "note",
            "namespace": "default",
            "public_fields": ["name", "tags"],
        },
        headers=auth_headers_system,
    )
    assert public_fields_response.status_code == 200, public_fields_response.text

    entity_data = {
        "entity_type": "note",
        "name": "Secret Meeting Notes",
        "description": "Confidential information about project X",
        "attributes": {
            "location": "Office 42",
            "participants": ["Alice", "Bob"],
        },
        "tags": ["meeting", "confidential"],
    }

    create_response = await crm_client.post(
        "/crm/api/v1/entities",
        json=entity_data,
        headers=auth_headers_system,
    )
    assert create_response.status_code == 200, create_response.text
    entity = _http_json(create_response)
    entity_id = object_str(entity.get("entity_id"), field="entity_id")

    grant_response = await crm_client.post(
        "/crm/api/v1/grants",
        json={
            "resource_type": "entity",
            "resource_id": entity_id,
            "subject": "public",
        },
        headers=auth_headers_system,
    )
    assert grant_response.status_code == 200, grant_response.text
    grant = _http_json(grant_response)

    assert object_str(grant.get("grant_type"), field="grant_type") == "public"
    assert object_str(grant.get("resource_type"), field="resource_type") == "entity"
    assert object_str(grant.get("resource_id"), field="resource_id") == entity_id
    assert object_str(grant.get("role"), field="role") == "viewer"
    assert object_str(grant.get("grant_id"), field="grant_id")

    get_response = await crm_client.get(
        f"/crm/api/v1/entities/{entity_id}",
        headers=auth_headers_company2,
    )
    assert get_response.status_code == 200, get_response.text
    public_entity = _http_json(get_response)

    assert "entity_id" in public_entity
    assert "entity_type" in public_entity
    assert "name" in public_entity
    assert "tags" in public_entity

    description = public_entity.get("description")
    assert "description" not in public_entity or description is None
    assert "attributes" not in public_entity or public_entity.get("attributes") in (
        None,
        {},
    )


@pytest.mark.asyncio
async def test_02_entity_user_grant(
    crm_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_headers_company2: dict[str, str],
    auth_headers_company2_user2: dict[str, str],
) -> None:
    """
    1. System user создает task
    2. Шарит company2 user (editor) через OpenFGA user grant
    3. Company2 user — полный доступ
    4. Company2 user2 без гранта — 403
    """

    token_service = get_token_service()
    authorization = auth_headers_company2["Authorization"]
    token_company2 = authorization.removeprefix("Bearer ")
    payload_company2 = token_service.validate_token(token_company2)
    if payload_company2 is None:
        raise AssertionError("auth_headers_company2: невалидный JWT")
    user_b_id = payload_company2.user_id

    entity_data = {
        "entity_type": "task",
        "name": "Project Alpha",
        "description": "Top secret project",
        "attributes": {"priority": "high"},
    }

    create_response = await crm_client.post(
        "/crm/api/v1/entities",
        json=entity_data,
        headers=auth_headers_system,
    )
    assert create_response.status_code == 200, create_response.text
    entity_id = object_str(
        _http_json(create_response).get("entity_id"),
        field="entity_id",
    )

    grant_request = {
        "resource_type": "entity",
        "resource_id": entity_id,
        "subject": "user",
        "user_id": user_b_id,
        "role": "editor",
    }

    grant_response = await crm_client.post(
        "/crm/api/v1/grants",
        json=grant_request,
        headers=auth_headers_system,
    )
    assert grant_response.status_code == 200, grant_response.text
    grant = _http_json(grant_response)

    assert object_str(grant.get("grant_type"), field="grant_type") == "user"
    assert object_str(grant.get("target_user_id"), field="target_user_id") == user_b_id
    assert object_str(grant.get("role"), field="role") == "editor"
    assert object_str(grant.get("grant_id"), field="grant_id")

    get_b_response = await crm_client.get(
        f"/crm/api/v1/entities/{entity_id}",
        headers=auth_headers_company2,
    )
    assert get_b_response.status_code == 200, get_b_response.text
    entity_b = _http_json(get_b_response)

    assert object_str(entity_b.get("name"), field="name") == "Project Alpha"
    assert object_str(entity_b.get("description"), field="description") == "Top secret project"

    get_c_response = await crm_client.get(
        f"/crm/api/v1/entities/{entity_id}",
        headers=auth_headers_company2_user2,
    )
    assert get_c_response.status_code == 403
