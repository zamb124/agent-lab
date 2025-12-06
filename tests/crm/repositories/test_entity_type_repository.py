"""
Тесты для EntityTypeRepository.
"""

import pytest
from datetime import datetime, timezone

from apps.crm.db.models import EntityType


@pytest.mark.asyncio
async def test_create_entity_type(entity_type_repo, test_context, unique_crm_id):
    """Тест создания типа сущности"""
    type_id = unique_crm_id("type")
    
    entity_type = EntityType(
        type_id=type_id,
        company_id=test_context.active_company.company_id,
        name="Test Person",
        description="A person entity",
        prompt="Extract person entities",
        required_fields={"name": {"label": "Name", "type": "text"}},
        optional_fields={"email": {"label": "Email", "type": "email"}, "phone": {"label": "Phone", "type": "phone"}},
        icon="ti-user",
        color="#4A90E2",
        is_system=False,
        check_duplicates=True,
        is_filtered=False,
    )
    
    created = await entity_type_repo.create(entity_type)
    
    assert created.type_id == type_id
    assert created.name == "Test Person"
    assert created.company_id == test_context.active_company.company_id
    
    await entity_type_repo.delete(type_id)


@pytest.mark.asyncio
async def test_get_entity_type(entity_type_repo, sample_entity_type):
    """Тест получения типа сущности по ID"""
    fetched = await entity_type_repo.get(sample_entity_type.type_id)
    
    assert fetched is not None
    assert fetched.type_id == sample_entity_type.type_id
    assert fetched.name == sample_entity_type.name


@pytest.mark.asyncio
async def test_get_entity_type_not_found(entity_type_repo):
    """Тест получения несуществующего типа"""
    fetched = await entity_type_repo.get("nonexistent_type")
    assert fetched is None


@pytest.mark.asyncio
async def test_update_entity_type(entity_type_repo, sample_entity_type):
    """Тест обновления типа сущности"""
    sample_entity_type.name = "Updated Name"
    sample_entity_type.description = "Updated description"
    
    updated = await entity_type_repo.update(sample_entity_type)
    
    assert updated.name == "Updated Name"
    assert updated.description == "Updated description"
    
    fetched = await entity_type_repo.get(sample_entity_type.type_id)
    assert fetched.name == "Updated Name"


@pytest.mark.asyncio
async def test_delete_entity_type(entity_type_repo, test_context, unique_crm_id):
    """Тест удаления типа сущности"""
    type_id = unique_crm_id("type")
    
    entity_type = EntityType(
        type_id=type_id,
        company_id=test_context.active_company.company_id,
        name="To Delete",
        is_system=False,
    )
    await entity_type_repo.create(entity_type)
    
    success = await entity_type_repo.delete(type_id)
    assert success is True
    
    fetched = await entity_type_repo.get(type_id)
    assert fetched is None


@pytest.mark.asyncio
async def test_list_entity_types(entity_type_repo, test_context, unique_crm_id):
    """Тест получения списка типов с пагинацией"""
    created_ids = []
    for i in range(5):
        type_id = unique_crm_id(f"type_{i}")
        entity_type = EntityType(
            type_id=type_id,
            company_id=test_context.active_company.company_id,
            name=f"Test Type {i}",
            is_system=False,
        )
        await entity_type_repo.create(entity_type)
        created_ids.append(type_id)
    
    all_types = await entity_type_repo.list_all(limit=100)
    assert len(all_types) >= 5
    
    limited = await entity_type_repo.list_all(limit=3)
    assert len(limited) == 3
    
    for type_id in created_ids:
        await entity_type_repo.delete(type_id)


@pytest.mark.asyncio
async def test_get_custom_types(entity_type_repo, test_context, unique_crm_id):
    """Тест получения кастомных типов компании"""
    type_id = unique_crm_id("type")
    
    entity_type = EntityType(
        type_id=type_id,
        company_id=test_context.active_company.company_id,
        name="Company Type",
        is_system=False,
    )
    await entity_type_repo.create(entity_type)
    
    custom_types = await entity_type_repo.get_custom_types(
        test_context.active_company.company_id
    )
    
    type_ids = [t.type_id for t in custom_types]
    assert type_id in type_ids
    
    await entity_type_repo.delete(type_id)


@pytest.mark.asyncio
async def test_get_system_types(entity_type_repo, test_context, unique_crm_id):
    """Тест получения системных типов"""
    type_id = unique_crm_id("sys_type")
    
    system_type = EntityType(
        type_id=type_id,
        company_id=None,
        name="System Type",
        is_system=True,
    )
    await entity_type_repo.create(system_type)
    
    system_types = await entity_type_repo.get_system_types()
    
    type_ids = [t.type_id for t in system_types]
    assert type_id in type_ids
    
    await entity_type_repo.delete(type_id)


@pytest.mark.asyncio
async def test_get_many_entity_types(entity_type_repo, test_context, unique_crm_id):
    """Тест получения нескольких типов по ID"""
    created_ids = []
    for i in range(3):
        type_id = unique_crm_id(f"type_{i}")
        entity_type = EntityType(
            type_id=type_id,
            company_id=test_context.active_company.company_id,
            name=f"Test Type {i}",
            is_system=False,
        )
        await entity_type_repo.create(entity_type)
        created_ids.append(type_id)
    
    fetched = await entity_type_repo.get_many(created_ids)
    
    assert len(fetched) == 3
    fetched_ids = [t.type_id for t in fetched]
    for type_id in created_ids:
        assert type_id in fetched_ids
    
    for type_id in created_ids:
        await entity_type_repo.delete(type_id)


@pytest.mark.asyncio
async def test_count_entity_types(entity_type_repo, test_context, unique_crm_id):
    """Тест подсчета типов"""
    initial_count = await entity_type_repo.count()
    
    type_id = unique_crm_id("type")
    entity_type = EntityType(
        type_id=type_id,
        company_id=test_context.active_company.company_id,
        name="Count Test",
        is_system=False,
    )
    await entity_type_repo.create(entity_type)
    
    new_count = await entity_type_repo.count()
    assert new_count == initial_count + 1
    
    await entity_type_repo.delete(type_id)

