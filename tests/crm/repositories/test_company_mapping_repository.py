"""
Тесты для CompanyMappingRepository.
"""

import pytest
from datetime import datetime, timezone

from apps.crm.db.models import CompanyMapping


@pytest.mark.asyncio
async def test_create_company_mapping(company_mapping_repo, test_context, unique_id):
    """Тест создания связи company-entity"""
    entity_id = unique_id("entity")
    
    mapping = CompanyMapping(
        company_id=test_context.active_company.company_id,
        entity_id=entity_id,
        is_owner=True,
        created_at=datetime.now(timezone.utc),
    )
    
    await company_mapping_repo.create(mapping)
    
    loaded = await company_mapping_repo.get(test_context.active_company.company_id)
    
    assert loaded is not None
    assert loaded.entity_id == entity_id
    assert loaded.is_owner is True
    
    await company_mapping_repo.delete(test_context.active_company.company_id)


@pytest.mark.asyncio
async def test_get_company_mapping(company_mapping_repo, test_context, unique_id):
    """Тест получения mapping по company_id"""
    entity_id = unique_id("entity")
    
    mapping = CompanyMapping(
        company_id=test_context.active_company.company_id,
        entity_id=entity_id,
        is_owner=True,
        created_at=datetime.now(timezone.utc),
    )
    
    await company_mapping_repo.create(mapping)
    
    loaded = await company_mapping_repo.get(test_context.active_company.company_id)
    
    assert loaded is not None
    assert loaded.company_id == test_context.active_company.company_id
    
    await company_mapping_repo.delete(test_context.active_company.company_id)


@pytest.mark.asyncio
async def test_get_by_entity(company_mapping_repo, test_context, unique_id):
    """Тест получения mapping по entity_id"""
    entity_id = unique_id("entity")
    
    mapping = CompanyMapping(
        company_id=test_context.active_company.company_id,
        entity_id=entity_id,
        is_owner=True,
        created_at=datetime.now(timezone.utc),
    )
    
    await company_mapping_repo.create(mapping)
    
    loaded = await company_mapping_repo.get_by_entity(entity_id)
    
    assert loaded is not None
    assert loaded.company_id == test_context.active_company.company_id
    assert loaded.entity_id == entity_id
    
    await company_mapping_repo.delete(test_context.active_company.company_id)


@pytest.mark.asyncio
async def test_delete_company_mapping(company_mapping_repo, test_context, unique_id):
    """Тест удаления mapping"""
    entity_id = unique_id("entity")
    
    mapping = CompanyMapping(
        company_id=test_context.active_company.company_id,
        entity_id=entity_id,
        is_owner=False,
        created_at=datetime.now(timezone.utc),
    )
    
    await company_mapping_repo.create(mapping)
    
    success = await company_mapping_repo.delete(test_context.active_company.company_id)
    assert success is True
    
    deleted = await company_mapping_repo.get(test_context.active_company.company_id)
    assert deleted is None


@pytest.mark.asyncio
async def test_update_company_mapping(company_mapping_repo, test_context, unique_id):
    """Тест обновления mapping"""
    entity_id = unique_id("entity")
    new_entity_id = unique_id("new_entity")
    
    mapping = CompanyMapping(
        company_id=test_context.active_company.company_id,
        entity_id=entity_id,
        is_owner=True,
        created_at=datetime.now(timezone.utc),
    )
    
    await company_mapping_repo.create(mapping)
    
    mapping.entity_id = new_entity_id
    mapping.is_owner = False
    await company_mapping_repo.update(mapping)
    
    loaded = await company_mapping_repo.get(test_context.active_company.company_id)
    
    assert loaded is not None
    assert loaded.entity_id == new_entity_id
    assert loaded.is_owner is False
    
    await company_mapping_repo.delete(test_context.active_company.company_id)


@pytest.mark.asyncio
async def test_get_nonexistent_mapping(company_mapping_repo, unique_id):
    """Тест получения несуществующего mapping"""
    fake_company_id = unique_id("fake_company")
    
    mapping = await company_mapping_repo.get(fake_company_id)
    
    assert mapping is None


@pytest.mark.asyncio
async def test_get_by_nonexistent_entity(company_mapping_repo, unique_id):
    """Тест получения mapping по несуществующему entity_id"""
    fake_entity_id = unique_id("fake_entity")
    
    mapping = await company_mapping_repo.get_by_entity(fake_entity_id)
    
    assert mapping is None

