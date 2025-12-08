"""
API тесты для EntityTypes.
"""

import pytest


@pytest.mark.asyncio
async def test_list_entity_types(crm_client):
    """Тест получения списка типов сущностей"""
    response = await crm_client.get("/crm/api/v1/entity-types")
    
    if response.status_code != 200:
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_entity_type(crm_client, unique_id):
    """Тест создания типа сущности"""
    type_id = unique_id("api_type")
    
    payload = {
        "type_id": type_id,
        "name": "API Test Type",
        "description": "Created via API test",
        "prompt": "Extract API test entities",
        "required_attributes": ["name"],
        "optional_attributes": ["code"],
        "icon": "ti-api",
        "color": "#00FF00",
    }
    
    response = await crm_client.post("/crm/api/v1/entity-types", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["type_id"] == type_id
    assert data["name"] == "API Test Type"
    assert data["is_system"] is False
    
    await crm_client.delete(f"/crm/api/v1/entity-types/{type_id}")


@pytest.mark.asyncio
async def test_get_entity_type(crm_client, unique_id):
    """Тест получения типа по ID"""
    type_id = unique_id("api_type")
    
    payload = {
        "type_id": type_id,
        "name": "Get Test Type",
        "prompt": "Test",
    }
    
    await crm_client.post("/crm/api/v1/entity-types", json=payload)
    
    response = await crm_client.get(f"/crm/api/v1/entity-types/{type_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["type_id"] == type_id
    assert data["name"] == "Get Test Type"
    
    await crm_client.delete(f"/crm/api/v1/entity-types/{type_id}")


@pytest.mark.asyncio
async def test_get_nonexistent_entity_type(crm_client, unique_id):
    """Тест получения несуществующего типа"""
    fake_id = unique_id("fake")
    
    response = await crm_client.get(f"/crm/api/v1/entity-types/{fake_id}")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_entity_type(crm_client, unique_id):
    """Тест обновления типа"""
    type_id = unique_id("api_type")
    
    payload = {
        "type_id": type_id,
        "name": "Original Name",
        "prompt": "Test",
    }
    
    await crm_client.post("/crm/api/v1/entity-types", json=payload)
    
    update_payload = {"name": "Updated Name"}
    response = await crm_client.put(
        f"/crm/api/v1/entity-types/{type_id}",
        json=update_payload
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    
    await crm_client.delete(f"/crm/api/v1/entity-types/{type_id}")


@pytest.mark.asyncio
async def test_delete_entity_type(crm_client, unique_id):
    """Тест удаления типа"""
    type_id = unique_id("api_type")
    
    payload = {
        "type_id": type_id,
        "name": "To Delete",
        "prompt": "Test",
    }
    
    await crm_client.post("/crm/api/v1/entity-types", json=payload)
    
    response = await crm_client.delete(f"/crm/api/v1/entity-types/{type_id}")
    
    assert response.status_code == 200
    
    get_response = await crm_client.get(f"/crm/api/v1/entity-types/{type_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_delete_system_type(crm_client):
    """Тест запрета удаления системного типа"""
    response = await crm_client.delete("/crm/api/v1/entity-types/person")
    
    assert response.status_code in [400, 403, 500]

