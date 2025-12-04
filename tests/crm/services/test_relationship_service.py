"""
Тесты для RelationshipService.

Примечание: RelationshipService зависит от EntityService,
который работает с ChromaDB. Тесты ограничены операциями
с репозиторием связей без создания реальных сущностей в ChromaDB.
"""

import pytest
from datetime import datetime, timezone

from apps.crm.db.models import Relationship


@pytest.mark.asyncio
async def test_get_relationship(relationship_service, relationship_repo, test_context, unique_crm_id):
    """Тест получения связи по ID"""
    rel_id = unique_crm_id("rel")
    
    relationship = Relationship(
        relationship_id=rel_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=unique_crm_id("src"),
        target_entity_id=unique_crm_id("tgt"),
        relationship_type="works_for",
        weight=0.8,
        attributes={"role": "engineer"},
        created_at=datetime.now(timezone.utc),
    )
    
    await relationship_repo.create(relationship)
    
    result = await relationship_service.get_relationship(rel_id)
    
    assert result is not None
    assert result.relationship_id == rel_id
    assert result.relationship_type == "works_for"
    assert result.weight == 0.8
    
    await relationship_repo.delete(rel_id)


@pytest.mark.asyncio
async def test_delete_relationship(relationship_service, relationship_repo, test_context, unique_crm_id):
    """Тест удаления связи"""
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
    
    result = await relationship_service.delete_relationship(rel_id)
    
    assert result is True
    
    deleted = await relationship_service.get_relationship(rel_id)
    assert deleted is None


@pytest.mark.asyncio
async def test_get_entity_relationships(
    relationship_service,
    relationship_repo,
    test_context,
    unique_crm_id
):
    """Тест получения связей для сущности"""
    entity_id = unique_crm_id("entity")
    rel1_id = unique_crm_id("rel1")
    rel2_id = unique_crm_id("rel2")
    
    rel1 = Relationship(
        relationship_id=rel1_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=entity_id,
        target_entity_id=unique_crm_id("tgt1"),
        relationship_type="knows",
        weight=1.0,
        attributes={},
        created_at=datetime.now(timezone.utc),
    )
    
    rel2 = Relationship(
        relationship_id=rel2_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=unique_crm_id("src2"),
        target_entity_id=entity_id,
        relationship_type="knows",
        weight=1.0,
        attributes={},
        created_at=datetime.now(timezone.utc),
    )
    
    await relationship_repo.create(rel1)
    await relationship_repo.create(rel2)
    
    results = await relationship_service.get_entity_relationships(
        entity_id,
        company_id=test_context.active_company.company_id
    )
    
    rel_ids = [r.relationship_id for r in results]
    assert rel1_id in rel_ids
    assert rel2_id in rel_ids
    
    await relationship_repo.delete(rel1_id)
    await relationship_repo.delete(rel2_id)


@pytest.mark.asyncio
async def test_get_relationships_between(
    relationship_service,
    relationship_repo,
    test_context,
    unique_crm_id
):
    """Тест получения связей между двумя сущностями"""
    entity1_id = unique_crm_id("entity1")
    entity2_id = unique_crm_id("entity2")
    rel_id = unique_crm_id("rel")
    
    relationship = Relationship(
        relationship_id=rel_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=entity1_id,
        target_entity_id=entity2_id,
        relationship_type="partner_of",
        weight=1.0,
        attributes={},
        created_at=datetime.now(timezone.utc),
    )
    
    await relationship_repo.create(relationship)
    
    results = await relationship_service.get_relationships_between(
        entity1_id,
        entity2_id,
        company_id=test_context.active_company.company_id
    )
    
    assert len(results) >= 1
    rel_ids = [r.relationship_id for r in results]
    assert rel_id in rel_ids
    
    await relationship_repo.delete(rel_id)


@pytest.mark.asyncio
async def test_list_relationships(
    relationship_service,
    relationship_repo,
    test_context,
    unique_crm_id
):
    """Тест получения списка связей"""
    rel_id = unique_crm_id("rel")
    
    relationship = Relationship(
        relationship_id=rel_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=unique_crm_id("src"),
        target_entity_id=unique_crm_id("tgt"),
        relationship_type="works_at",
        weight=1.0,
        attributes={},
        created_at=datetime.now(timezone.utc),
    )
    
    await relationship_repo.create(relationship)
    
    results = await relationship_service.list_relationships(
        company_id=test_context.active_company.company_id
    )
    
    assert len(results) >= 1
    rel_ids = [r.relationship_id for r in results]
    assert rel_id in rel_ids
    
    await relationship_repo.delete(rel_id)


@pytest.mark.asyncio
async def test_list_relationships_by_type(
    relationship_service,
    relationship_repo,
    test_context,
    unique_crm_id
):
    """Тест фильтрации связей по типу"""
    rel_id = unique_crm_id("rel")
    rel_type = f"custom_type_{unique_crm_id('type')}"
    
    relationship = Relationship(
        relationship_id=rel_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=unique_crm_id("src"),
        target_entity_id=unique_crm_id("tgt"),
        relationship_type=rel_type,
        weight=1.0,
        attributes={},
        created_at=datetime.now(timezone.utc),
    )
    
    await relationship_repo.create(relationship)
    
    results = await relationship_service.list_relationships(
        relationship_type=rel_type,
        company_id=test_context.active_company.company_id
    )
    
    assert len(results) >= 1
    for r in results:
        assert r.relationship_type == rel_type
    
    await relationship_repo.delete(rel_id)


@pytest.mark.asyncio
async def test_get_nonexistent_relationship(relationship_service, unique_crm_id):
    """Тест получения несуществующей связи"""
    fake_id = unique_crm_id("fake")
    
    result = await relationship_service.get_relationship(fake_id)
    
    assert result is None

