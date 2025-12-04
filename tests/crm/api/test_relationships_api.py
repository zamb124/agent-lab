"""
API тесты для Relationships.

Тесты самодостаточные - сами создают необходимые сущности.
"""

import pytest


@pytest.mark.asyncio
async def test_list_relationships(crm_client):
    """Тест получения списка связей"""
    response = await crm_client.get("/crm/api/v1/relationships")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_relationship(crm_client, unique_crm_id):
    """
    Тест создания связи.
    
    Самодостаточный тест:
    1. Создаёт две сущности через API
    2. Создаёт связь между ними
    3. Проверяет связь
    4. Удаляет всё
    """
    # 1. Создаем source сущность
    source_payload = {
        "type": "person",
        "name": f"Source Person {unique_crm_id('src')}",
        "description": "Source entity for relationship test",
        "attributes": {},
    }
    source_response = await crm_client.post("/crm/api/v1/entities", json=source_payload)
    assert source_response.status_code == 200, f"Failed to create source: {source_response.text}"
    source_entity = source_response.json()
    
    # 2. Создаем target сущность
    target_payload = {
        "type": "organization",
        "name": f"Target Org {unique_crm_id('tgt')}",
        "description": "Target entity for relationship test",
        "attributes": {},
    }
    target_response = await crm_client.post("/crm/api/v1/entities", json=target_payload)
    assert target_response.status_code == 200, f"Failed to create target: {target_response.text}"
    target_entity = target_response.json()
    
    try:
        # 3. Создаем связь
        relationship_payload = {
            "source_entity_id": source_entity["entity_id"],
            "target_entity_id": target_entity["entity_id"],
            "relationship_type": "works_for",
            "weight": 1.0,
            "attributes": {"role": "developer"},
        }
        
        rel_response = await crm_client.post("/crm/api/v1/relationships", json=relationship_payload)
        assert rel_response.status_code == 200, f"Failed to create relationship: {rel_response.text}"
        
        relationship = rel_response.json()
        assert relationship["source_entity_id"] == source_entity["entity_id"]
        assert relationship["target_entity_id"] == target_entity["entity_id"]
        assert relationship["relationship_type"] == "works_for"
        assert relationship["weight"] == 1.0
        
        # Cleanup relationship
        await crm_client.delete(f"/crm/api/v1/relationships/{relationship['relationship_id']}")
        
    finally:
        # Cleanup entities
        await crm_client.delete(f"/crm/api/v1/entities/{source_entity['entity_id']}")
        await crm_client.delete(f"/crm/api/v1/entities/{target_entity['entity_id']}")


@pytest.mark.asyncio
async def test_get_relationship(crm_client, sample_relationship):
    """Тест получения связи по ID"""
    response = await crm_client.get(
        f"/crm/api/v1/relationships/{sample_relationship.relationship_id}"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["relationship_id"] == sample_relationship.relationship_id


@pytest.mark.asyncio
async def test_get_nonexistent_relationship(crm_client, unique_crm_id):
    """Тест получения несуществующей связи"""
    fake_id = unique_crm_id("fake")
    
    response = await crm_client.get(f"/crm/api/v1/relationships/{fake_id}")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_relationship(crm_client, relationship_repo, test_context, unique_crm_id):
    """Тест удаления связи"""
    from datetime import datetime, timezone
    from apps.crm.db.models import Relationship
    
    rel_id = unique_crm_id("rel")
    relationship = Relationship(
        relationship_id=rel_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=unique_crm_id("src"),
        target_entity_id=unique_crm_id("tgt"),
        relationship_type="connected_to",
        weight=1.0,
        attributes={},
        created_at=datetime.now(timezone.utc),
    )
    
    await relationship_repo.create(relationship)
    
    response = await crm_client.delete(f"/crm/api/v1/relationships/{rel_id}")
    
    assert response.status_code == 200
    
    get_response = await crm_client.get(f"/crm/api/v1/relationships/{rel_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_get_entity_relationships(crm_client, sample_relationship):
    """Тест получения связей для сущности"""
    response = await crm_client.get(
        f"/crm/api/v1/relationships/entity/{sample_relationship.source_entity_id}"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_relationships_by_type(crm_client, sample_relationship):
    """Тест фильтрации связей по типу"""
    response = await crm_client.get(
        f"/crm/api/v1/relationships?relationship_type={sample_relationship.relationship_type}"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    for rel in data:
        assert rel["relationship_type"] == sample_relationship.relationship_type
