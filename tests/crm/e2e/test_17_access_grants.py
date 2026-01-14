"""
E2E тесты для системы AccessGrants.

Проверяем:
1. Создание grants (entity/namespace, public/user/company)
2. Проверку доступа через grants
3. Фильтрацию публичных полей
4. Отзыв grants
"""

import pytest
from httpx import AsyncClient

from apps.crm.models.entity import ChromaDBEntity
from apps.crm.db.models import EntityType, AccessGrant


@pytest.mark.asyncio
async def test_01_entity_public_grant(crm_client: AsyncClient, auth_headers_system, auth_headers_company2):
    """
    Тест 1: Сделать entity публичной
    
    1. System user создает entity
    2. Делаем ее публичной через grant
    3. User из другой компании получает доступ с фильтрацией полей
    """
    
    # 1. System user создает entity
    entity_data = {
        "entity_type": "note",
        "name": "Secret Meeting Notes",
        "description": "Confidential information about project X",
        "attributes": {
            "location": "Office 42",
            "participants": ["Alice", "Bob"]
        },
        "tags": ["meeting", "confidential"]
    }
    
    create_response = await crm_client.post(
        "/crm/api/v1/entities/",
        json=entity_data,
        headers=auth_headers_system
    )
    assert create_response.status_code == 200
    entity = create_response.json()
    entity_id = entity["entity_id"]
    
    print(f"✅ Entity created by system user: {entity_id}")
    
    # 2. Делаем публичной
    grant_response = await crm_client.post(
        f"/crm/api/v1/entities/{entity_id}/grants/public",
        headers=auth_headers_system
    )
    assert grant_response.status_code == 200
    grant = grant_response.json()
    
    assert grant["grant_type"] == "public"
    assert grant["resource_type"] == "entity"
    assert grant["resource_id"] == entity_id
    assert grant["role"] == "viewer"
    
    print(f"✅ Public grant created: {grant['grant_id']}")
    
    # 3. User из другой компании получает доступ с фильтрацией полей
    get_response = await crm_client.get(
        f"/crm/api/v1/entities/{entity_id}",
        headers=auth_headers_company2  # User из company2
    )
    assert get_response.status_code == 200
    public_entity = get_response.json()
    
    # Проверяем что получили только публичные поля
    assert "entity_id" in public_entity
    assert "entity_type" in public_entity
    assert "name" in public_entity
    assert "tags" in public_entity
    
    # Конфиденциальные поля должны быть скрыты
    # (description не в public_fields для note по умолчанию)
    assert "description" not in public_entity or public_entity["description"] is None
    
    print(f"✅ Company2 user access works with filtered fields")
    print(f"   Public fields: {list(public_entity.keys())}")


@pytest.mark.asyncio
async def test_02_entity_user_grant(crm_client: AsyncClient, auth_headers_system, auth_headers_company2, auth_headers_company2_user2):
    """
    Тест 2: Пошерить entity конкретному user
    
    1. System user создает entity
    2. System user шарит entity company2 user (другая компания) с правами editor
    3. Company2 user получает полный доступ
    4. Company2 user2 НЕ получает доступ (не шарили ему)
    """
    
    # Получаем user_id из токена company2 user
    from core.utils.tokens import get_token_service
    token_service = get_token_service()
    token_company2 = auth_headers_company2["Authorization"].replace("Bearer ", "")
    payload_company2 = token_service.validate_token(token_company2)
    user_b_id = payload_company2.user_id
    
    # 1. System user создает entity
    entity_data = {
        "entity_type": "task",
        "name": "Project Alpha",
        "description": "Top secret project",
        "attributes": {"priority": "high"}
    }
    
    create_response = await crm_client.post(
        "/crm/api/v1/entities/",
        json=entity_data,
        headers=auth_headers_system
    )
    assert create_response.status_code == 200
    entity_id = create_response.json()["entity_id"]
    
    print(f"✅ Entity created by system user: {entity_id}")
    
    # 2. System user шарит company2 user с правами editor
    grant_request = {
        "user_id": user_b_id,
        "role": "editor"
    }
    
    grant_response = await crm_client.post(
        f"/crm/api/v1/entities/{entity_id}/grants/user",
        json=grant_request,
        headers=auth_headers_system
    )
    assert grant_response.status_code == 200
    grant = grant_response.json()
    
    assert grant["grant_type"] == "user"
    assert grant["target_user_id"] == user_b_id
    assert grant["role"] == "editor"
    
    print(f"✅ Grant created for company2 user: {grant['grant_id']}")
    
    # 3. Company2 user получает полный доступ
    get_b_response = await crm_client.get(
        f"/crm/api/v1/entities/{entity_id}",
        headers=auth_headers_company2
    )
    assert get_b_response.status_code == 200
    entity_b = get_b_response.json()
    
    # Company2 user видит все поля (т.к. есть user grant)
    assert entity_b["name"] == "Project Alpha"
    assert entity_b["description"] == "Top secret project"
    
    print(f"✅ Company2 user has full access")
    
    # 4. Company2 user2 НЕ получает доступ (grant только для user1)
    get_c_response = await crm_client.get(
        f"/crm/api/v1/entities/{entity_id}",
        headers=auth_headers_company2_user2
    )
    assert get_c_response.status_code == 403
    
    print(f"✅ Company2 user2 denied access (as expected)")

