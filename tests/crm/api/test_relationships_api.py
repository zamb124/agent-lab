"""
API тесты для Relationships.
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
    """Тест создания связи"""
    source_id = unique_crm_id("source")
    target_id = unique_crm_id("target")
    
    payload = {
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "relationship_type": "works_for",
        "weight": 1.0,
        "attributes": {"role": "developer"},
    }
    
    response = await crm_client.post("/crm/api/v1/relationships", json=payload)
    
    if response.status_code == 200:
        data = response.json()
        assert data["source_entity_id"] == source_id
        assert data["target_entity_id"] == target_id
        assert data["relationship_type"] == "works_for"
        
        await crm_client.delete(f"/crm/api/v1/relationships/{data['relationship_id']}")
    else:
        assert response.status_code in [400, 404]


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

