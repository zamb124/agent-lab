"""
Тесты для RelationshipRepository.
"""

import pytest
from datetime import datetime, timezone

from apps.crm.db.models import Relationship


@pytest.mark.asyncio
async def test_create_relationship(relationship_repo, test_context, unique_crm_id):
    """Тест создания связи"""
    rel_id = unique_crm_id("rel")
    
    relationship = Relationship(
        relationship_id=rel_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=unique_crm_id("src"),
        target_entity_id=unique_crm_id("tgt"),
        relationship_type="works_for",
        weight=0.8,
        attributes={"role": "developer"},
        created_at=datetime.now(timezone.utc),
    )
    
    created = await relationship_repo.create(relationship)
    
    assert created.relationship_id == rel_id
    assert created.relationship_type == "works_for"
    assert created.weight == 0.8
    
    await relationship_repo.delete(rel_id)


@pytest.mark.asyncio
async def test_get_relationship(relationship_repo, sample_relationship):
    """Тест получения связи по ID"""
    fetched = await relationship_repo.get(sample_relationship.relationship_id)
    
    assert fetched is not None
    assert fetched.relationship_id == sample_relationship.relationship_id
    assert fetched.relationship_type == sample_relationship.relationship_type


@pytest.mark.asyncio
async def test_update_relationship(relationship_repo, sample_relationship):
    """Тест обновления связи"""
    sample_relationship.weight = 0.5
    sample_relationship.attributes = {"updated": True}
    
    updated = await relationship_repo.update(sample_relationship)
    
    assert updated.weight == 0.5
    assert updated.attributes.get("updated") is True


@pytest.mark.asyncio
async def test_delete_relationship(relationship_repo, test_context, unique_crm_id):
    """Тест удаления связи"""
    rel_id = unique_crm_id("rel")
    
    relationship = Relationship(
        relationship_id=rel_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=unique_crm_id("src"),
        target_entity_id=unique_crm_id("tgt"),
        relationship_type="connected_to",
        weight=1.0,
        created_at=datetime.now(timezone.utc),
    )
    await relationship_repo.create(relationship)
    
    success = await relationship_repo.delete(rel_id)
    assert success is True
    
    fetched = await relationship_repo.get(rel_id)
    assert fetched is None


@pytest.mark.asyncio
async def test_get_by_source(relationship_repo, test_context, unique_crm_id):
    """Тест получения связей по source entity"""
    source_id = unique_crm_id("src")
    created_ids = []
    
    for i in range(3):
        rel_id = unique_crm_id(f"rel_{i}")
        relationship = Relationship(
            relationship_id=rel_id,
            company_id=test_context.active_company.company_id,
            source_entity_id=source_id,
            target_entity_id=unique_crm_id(f"tgt_{i}"),
            relationship_type="connected_to",
            weight=1.0,
            created_at=datetime.now(timezone.utc),
        )
        await relationship_repo.create(relationship)
        created_ids.append(rel_id)
    
    rels = await relationship_repo.get_by_source(
        test_context.active_company.company_id,
        source_id
    )
    
    assert len(rels) >= 3
    
    for rel_id in created_ids:
        await relationship_repo.delete(rel_id)


@pytest.mark.asyncio
async def test_get_by_target(relationship_repo, test_context, unique_crm_id):
    """Тест получения связей по target entity"""
    target_id = unique_crm_id("tgt")
    created_ids = []
    
    for i in range(3):
        rel_id = unique_crm_id(f"rel_{i}")
        relationship = Relationship(
            relationship_id=rel_id,
            company_id=test_context.active_company.company_id,
            source_entity_id=unique_crm_id(f"src_{i}"),
            target_entity_id=target_id,
            relationship_type="connected_to",
            weight=1.0,
            created_at=datetime.now(timezone.utc),
        )
        await relationship_repo.create(relationship)
        created_ids.append(rel_id)
    
    rels = await relationship_repo.get_by_target(
        test_context.active_company.company_id,
        target_id
    )
    
    assert len(rels) >= 3
    
    for rel_id in created_ids:
        await relationship_repo.delete(rel_id)


@pytest.mark.asyncio
async def test_get_by_entity(relationship_repo, test_context, unique_crm_id):
    """Тест получения всех связей сущности (входящих и исходящих)"""
    entity_id = unique_crm_id("entity")
    created_ids = []
    
    rel1_id = unique_crm_id("rel1")
    rel1 = Relationship(
        relationship_id=rel1_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=entity_id,
        target_entity_id=unique_crm_id("tgt"),
        relationship_type="connected_to",
        weight=1.0,
        created_at=datetime.now(timezone.utc),
    )
    await relationship_repo.create(rel1)
    created_ids.append(rel1_id)
    
    rel2_id = unique_crm_id("rel2")
    rel2 = Relationship(
        relationship_id=rel2_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=unique_crm_id("src"),
        target_entity_id=entity_id,
        relationship_type="works_for",
        weight=0.8,
        created_at=datetime.now(timezone.utc),
    )
    await relationship_repo.create(rel2)
    created_ids.append(rel2_id)
    
    rels = await relationship_repo.get_by_entity(
        test_context.active_company.company_id,
        entity_id
    )
    
    assert len(rels) >= 2
    
    for rel_id in created_ids:
        await relationship_repo.delete(rel_id)


@pytest.mark.asyncio
async def test_get_by_type(relationship_repo, test_context, unique_crm_id):
    """Тест получения связей по типу"""
    rel_id = unique_crm_id("rel")
    
    relationship = Relationship(
        relationship_id=rel_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=unique_crm_id("src"),
        target_entity_id=unique_crm_id("tgt"),
        relationship_type="mentors",
        weight=1.0,
        created_at=datetime.now(timezone.utc),
    )
    await relationship_repo.create(relationship)
    
    rels = await relationship_repo.get_by_type(
        test_context.active_company.company_id,
        "mentors"
    )
    
    rel_ids = [r.relationship_id for r in rels]
    assert rel_id in rel_ids
    
    await relationship_repo.delete(rel_id)


@pytest.mark.asyncio
async def test_get_between(relationship_repo, test_context, unique_crm_id):
    """Тест получения связей между двумя сущностями"""
    source_id = unique_crm_id("src")
    target_id = unique_crm_id("tgt")
    rel_id = unique_crm_id("rel")
    
    relationship = Relationship(
        relationship_id=rel_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=source_id,
        target_entity_id=target_id,
        relationship_type="partner_of",
        weight=1.0,
        created_at=datetime.now(timezone.utc),
    )
    await relationship_repo.create(relationship)
    
    rels = await relationship_repo.get_between(
        test_context.active_company.company_id,
        source_id,
        target_id
    )
    
    assert len(rels) >= 1
    rel_ids = [r.relationship_id for r in rels]
    assert rel_id in rel_ids
    
    await relationship_repo.delete(rel_id)


@pytest.mark.asyncio
async def test_delete_by_entity(relationship_repo, test_context, unique_crm_id):
    """Тест удаления всех связей сущности"""
    entity_id = unique_crm_id("entity")
    
    rel1_id = unique_crm_id("rel1")
    rel1 = Relationship(
        relationship_id=rel1_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=entity_id,
        target_entity_id=unique_crm_id("tgt"),
        relationship_type="connected_to",
        weight=1.0,
        created_at=datetime.now(timezone.utc),
    )
    await relationship_repo.create(rel1)
    
    rel2_id = unique_crm_id("rel2")
    rel2 = Relationship(
        relationship_id=rel2_id,
        company_id=test_context.active_company.company_id,
        source_entity_id=unique_crm_id("src"),
        target_entity_id=entity_id,
        relationship_type="works_for",
        weight=0.8,
        created_at=datetime.now(timezone.utc),
    )
    await relationship_repo.create(rel2)
    
    deleted_count = await relationship_repo.delete_by_entity(
        test_context.active_company.company_id,
        entity_id
    )
    
    assert deleted_count >= 2
    
    rels = await relationship_repo.get_by_entity(
        test_context.active_company.company_id,
        entity_id
    )
    assert len(rels) == 0

