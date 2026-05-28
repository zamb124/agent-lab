"""
E2E тесты для системы AccessGrants.

Проверяем:
1. Создание grants (entity/namespace, public/user/company)
2. Проверку доступа через grants
3. Фильтрацию публичных полей
4. Отзыв grants
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
    Тест 1: Сделать entity публичной

    1. System user создает entity
    2. Делаем ее публичной через grant
    3. User из другой компании получает доступ с фильтрацией полей
    """

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
        "/crm/api/v1/entities/",
        json=entity_data,
        headers=auth_headers_system,
    )
    assert create_response.status_code == 200
    entity = _http_json(create_response)
    entity_id = object_str(entity.get("entity_id"), field="entity_id")

    print(f"✅ Entity created by system user: {entity_id}")

    grant_response = await crm_client.post(
        f"/crm/api/v1/entities/{entity_id}/grants/public",
        headers=auth_headers_system,
    )
    assert grant_response.status_code == 200
    grant = _http_json(grant_response)

    assert object_str(grant.get("grant_type"), field="grant_type") == "public"
    assert object_str(grant.get("resource_type"), field="resource_type") == "entity"
    assert object_str(grant.get("resource_id"), field="resource_id") == entity_id
    assert object_str(grant.get("role"), field="role") == "viewer"

    print(f"✅ Public grant created: {object_str(grant.get('grant_id'), field='grant_id')}")

    get_response = await crm_client.get(
        f"/crm/api/v1/entities/{entity_id}",
        headers=auth_headers_company2,
    )
    assert get_response.status_code == 200
    public_entity = _http_json(get_response)

    assert "entity_id" in public_entity
    assert "entity_type" in public_entity
    assert "name" in public_entity
    assert "tags" in public_entity

    description = public_entity.get("description")
    assert "description" not in public_entity or description is None

    print("✅ Company2 user access works with filtered fields")
    print(f"   Public fields: {list(public_entity.keys())}")


@pytest.mark.asyncio
async def test_02_entity_user_grant(
    crm_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_headers_company2: dict[str, str],
    auth_headers_company2_user2: dict[str, str],
) -> None:
    """
    Тест 2: Пошерить entity конкретному user

    1. System user создает entity
    2. System user шарит entity company2 user (другая компания) с правами editor
    3. Company2 user получает полный доступ
    4. Company2 user2 НЕ получает доступ (не шарили ему)
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
        "/crm/api/v1/entities/",
        json=entity_data,
        headers=auth_headers_system,
    )
    assert create_response.status_code == 200
    entity_id = object_str(
        _http_json(create_response).get("entity_id"),
        field="entity_id",
    )

    print(f"✅ Entity created by system user: {entity_id}")

    grant_request = {
        "user_id": user_b_id,
        "role": "editor",
    }

    grant_response = await crm_client.post(
        f"/crm/api/v1/entities/{entity_id}/grants/user",
        json=grant_request,
        headers=auth_headers_system,
    )
    assert grant_response.status_code == 200
    grant = _http_json(grant_response)

    assert object_str(grant.get("grant_type"), field="grant_type") == "user"
    assert object_str(grant.get("target_user_id"), field="target_user_id") == user_b_id
    assert object_str(grant.get("role"), field="role") == "editor"

    print(f"✅ Grant created for company2 user: {object_str(grant.get('grant_id'), field='grant_id')}")

    get_b_response = await crm_client.get(
        f"/crm/api/v1/entities/{entity_id}",
        headers=auth_headers_company2,
    )
    assert get_b_response.status_code == 200
    entity_b = _http_json(get_b_response)

    assert object_str(entity_b.get("name"), field="name") == "Project Alpha"
    assert object_str(entity_b.get("description"), field="description") == "Top secret project"

    print("✅ Company2 user has full access")

    get_c_response = await crm_client.get(
        f"/crm/api/v1/entities/{entity_id}",
        headers=auth_headers_company2_user2,
    )
    assert get_c_response.status_code == 403

    print("✅ Company2 user2 denied access (as expected)")
