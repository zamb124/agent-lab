"""
Тесты для API сущностей CRM.

Тестируются endpoints:
- GET /crm/api/v1/entities
- GET /crm/api/v1/entities/{entity_id}
- POST /crm/api/v1/entities
- PUT /crm/api/v1/entities/{entity_id}
- DELETE /crm/api/v1/entities/{entity_id}
- POST /crm/api/v1/entities/search
- POST /crm/api/v1/entities/find-duplicates
"""

import pytest


@pytest.mark.asyncio
async def test_list_entities(crm_client):
    """Тест получения списка сущностей"""
    response = await crm_client.get("/crm/api/v1/entities")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_entity(crm_client, unique_id):
    """Тест создания сущности"""
    entity_name = f"API Test Person {unique_id('api')}"
    payload = {
        "type": "person",
        "name": entity_name,
        "description": "Created via API test",
        "attributes": {"email": "api.test@example.com"},
    }
    
    response = await crm_client.post("/crm/api/v1/entities", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "person"
    assert data["name"] == entity_name
    assert data["entity_id"] is not None
    
    # Cleanup
    await crm_client.delete(f"/crm/api/v1/entities/{data['entity_id']}")


@pytest.mark.asyncio
async def test_get_entity(crm_client, unique_id):
    """Тест получения сущности по ID"""
    # Создаем сущность
    payload = {
        "type": "person",
        "name": f"Get Test Person {unique_id('api')}",
        "description": "Test",
        "attributes": {},
    }
    create_response = await crm_client.post("/crm/api/v1/entities", json=payload)
    assert create_response.status_code == 200
    created = create_response.json()
    
    # Получаем её
    response = await crm_client.get(f"/crm/api/v1/entities/{created['entity_id']}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["entity_id"] == created["entity_id"]
    assert data["name"] == payload["name"]
    
    # Cleanup
    await crm_client.delete(f"/crm/api/v1/entities/{created['entity_id']}")
    data = response.json()
    assert data["entity_id"] == created["entity_id"]
    assert data["name"] == payload["name"]
    
    # Cleanup
    await crm_client.delete(f"/crm/api/v1/entities/{created['entity_id']}")


@pytest.mark.asyncio
async def test_get_nonexistent_entity(crm_client):
    """Тест получения несуществующей сущности"""
    response = await crm_client.get("/crm/api/v1/entities/nonexistent_entity_id")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_entity(crm_client, unique_id):
    """Тест обновления сущности"""
    # Создаем
    payload = {
        "type": "person",
        "name": f"Update Test {unique_id('api')}",
        "description": "Original",
        "attributes": {"role": "dev"},
    }
    create_response = await crm_client.post("/crm/api/v1/entities", json=payload)
    created = create_response.json()
    
    # Обновляем
    update_payload = {
        "name": "Updated Name",
        "description": "Updated description",
    }
    response = await crm_client.put(
        f"/crm/api/v1/entities/{created['entity_id']}", 
        json=update_payload
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "Updated description"
    
    # Cleanup
    await crm_client.delete(f"/crm/api/v1/entities/{created['entity_id']}")


@pytest.mark.asyncio
async def test_update_nonexistent_entity(crm_client):
    """Тест обновления несуществующей сущности"""
    response = await crm_client.put(
        "/crm/api/v1/entities/nonexistent_id",
        json={"name": "New Name"}
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_entity(crm_client, unique_id):
    """Тест удаления сущности"""
    # Создаем
    payload = {
        "type": "person",
        "name": f"Delete Test {unique_id('api')}",
        "description": "To be deleted",
        "attributes": {},
    }
    create_response = await crm_client.post("/crm/api/v1/entities", json=payload)
    created = create_response.json()
    
    # Удаляем
    response = await crm_client.delete(f"/crm/api/v1/entities/{created['entity_id']}")
    
    assert response.status_code == 200
    
    # Проверяем что удалена
    get_response = await crm_client.get(f"/crm/api/v1/entities/{created['entity_id']}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_entity(crm_client):
    """Тест удаления несуществующей сущности"""
    response = await crm_client.delete("/crm/api/v1/entities/nonexistent_id")
    
    # Может вернуть 200 или 404 в зависимости от ChromaDB
    assert response.status_code in [200, 404]


@pytest.mark.asyncio
async def test_list_entities_by_type(crm_client, unique_id):
    """Тест фильтрации по типу"""
    # Создаем сущность
    payload = {
        "type": "organization",
        "name": f"Filter Test Org {unique_id('api')}",
        "description": "Test",
        "attributes": {},
    }
    create_response = await crm_client.post("/crm/api/v1/entities", json=payload)
    created = create_response.json()
    
    # Фильтруем
    response = await crm_client.get("/crm/api/v1/entities?entity_type=organization")
    
    assert response.status_code == 200
    data = response.json()
    
    # Все должны быть organization
    for entity in data:
        assert entity["type"] == "organization"
    
    # Cleanup
    await crm_client.delete(f"/crm/api/v1/entities/{created['entity_id']}")


@pytest.mark.asyncio
async def test_search_entities(crm_client, unique_id):
    """Тест семантического поиска"""
    # Создаем сущность
    unique_name = f"UniqueSearchTerm_{unique_id('api')}"
    payload = {
        "type": "project",
        "name": unique_name,
        "description": "Project for search test",
        "attributes": {},
    }
    create_response = await crm_client.post("/crm/api/v1/entities", json=payload)
    created = create_response.json()
    
    # Ищем
    search_payload = {
        "query": unique_name[:15],
        "limit": 10,
    }
    response = await crm_client.post("/crm/api/v1/entities/search", json=search_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "entities" in data
    assert "total" in data
    
    # Cleanup
    await crm_client.delete(f"/crm/api/v1/entities/{created['entity_id']}")


@pytest.mark.asyncio
async def test_search_entities_by_type(crm_client, unique_id):
    """Тест поиска с фильтром по типу"""
    search_payload = {
        "query": "test",
        "entity_type": "person",
        "limit": 10,
    }
    response = await crm_client.post("/crm/api/v1/entities/search", json=search_payload)
    
    assert response.status_code == 200
    data = response.json()
    
    # Все результаты должны быть person
    for entity in data["entities"]:
        assert entity["type"] == "person"


@pytest.mark.asyncio
async def test_find_duplicates(crm_client, unique_id):
    """Тест поиска дубликатов"""
    # Создаем сущность
    original_name = f"Duplicate Test Person {unique_id('api')}"
    payload = {
        "type": "person",
        "name": original_name,
        "description": "Original person",
        "attributes": {"email": "original@test.com"},
    }
    create_response = await crm_client.post("/crm/api/v1/entities", json=payload)
    created = create_response.json()
    
    # Ищем дубликаты для похожей сущности
    duplicate_payload = {
        "type": "person",
        "name": original_name,  # Тот же name
        "description": "Similar person",
        "attributes": {"email": "similar@test.com"},
    }
    response = await crm_client.post(
        "/crm/api/v1/entities/find-duplicates?threshold=0.5",
        json=duplicate_payload
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    # Cleanup
    await crm_client.delete(f"/crm/api/v1/entities/{created['entity_id']}")


@pytest.mark.asyncio
async def test_create_entity_invalid_type(crm_client, unique_id):
    """Тест создания сущности с невалидным типом"""
    payload = {
        "type": "invalid_type_xxx",
        "name": f"Invalid {unique_id('api')}",
        "description": "Should fail",
        "attributes": {},
    }
    
    response = await crm_client.post("/crm/api/v1/entities", json=payload)
    
    # Должен вернуть ошибку
    assert response.status_code in [400, 404, 422, 500]


@pytest.mark.asyncio
async def test_list_entities_pagination(crm_client):
    """Тест пагинации"""
    response = await crm_client.get("/crm/api/v1/entities?limit=5")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 5


@pytest.mark.asyncio
async def test_update_entity_status_to_approved(crm_client, unique_id):
    """Тест обновления статуса сущности на approved"""
    # Создаем сущность со статусом pending
    payload = {
        "type": "person",
        "name": f"Status Test {unique_id('status')}",
        "description": "Entity for status test",
        "attributes": {},
        "status": "pending",
    }
    create_response = await crm_client.post("/crm/api/v1/entities", json=payload)
    assert create_response.status_code == 200
    created = create_response.json()
    entity_id = created["entity_id"]
    
    # Обновляем статус на approved
    response = await crm_client.put(
        f"/crm/api/v1/entities/{entity_id}/status?status=approved"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    
    # Cleanup
    await crm_client.delete(f"/crm/api/v1/entities/{entity_id}")


@pytest.mark.asyncio
async def test_update_entity_status_to_rejected(crm_client, unique_id):
    """Тест обновления статуса сущности на rejected"""
    # Создаем сущность
    payload = {
        "type": "person",
        "name": f"Reject Test {unique_id('reject')}",
        "description": "Entity to reject",
        "attributes": {},
        "status": "pending",
    }
    create_response = await crm_client.post("/crm/api/v1/entities", json=payload)
    created = create_response.json()
    entity_id = created["entity_id"]
    
    # Обновляем статус на rejected
    response = await crm_client.put(
        f"/crm/api/v1/entities/{entity_id}/status?status=rejected"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    
    # Cleanup
    await crm_client.delete(f"/crm/api/v1/entities/{entity_id}")


@pytest.mark.asyncio
async def test_update_entity_status_nonexistent(crm_client, unique_id):
    """Тест обновления статуса несуществующей сущности"""
    fake_id = unique_id("fake")
    
    response = await crm_client.put(
        f"/crm/api/v1/entities/{fake_id}/status?status=approved"
    )
    
    assert response.status_code == 404
