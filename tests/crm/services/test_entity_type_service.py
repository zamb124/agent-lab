"""
Тесты для EntityTypeService.
"""

import pytest

from apps.crm.models.entity_type_models import EntityTypeCreate, EntityTypeUpdate


@pytest.mark.asyncio
async def test_init_system_types(entity_type_service, test_context):
    """Тест инициализации системных типов"""
    await entity_type_service.init_system_types()
    
    all_types = await entity_type_service.get_all_types(
        company_id=test_context.active_company.company_id
    )
    
    type_ids = [t.type_id for t in all_types]
    
    assert "person" in type_ids
    assert "organization" in type_ids
    assert "project" in type_ids
    assert "task" in type_ids


@pytest.mark.asyncio
async def test_create_custom_type(entity_type_service, test_context, unique_crm_id):
    """Тест создания кастомного типа"""
    data = EntityTypeCreate(
        type_id=unique_crm_id("custom"),
        name="Custom Entity",
        description="Custom entity type for testing",
        prompt="Extract custom entities",
        required_attributes=["name"],
        optional_attributes=["code", "description"],
        icon="ti-custom",
        color="#FF6600",
    )
    
    created = await entity_type_service.create_type(
        data=data,
        company_id=test_context.active_company.company_id
    )
    
    assert created.type_id == data.type_id
    assert created.name == "Custom Entity"
    assert created.is_system is False
    assert created.company_id == test_context.active_company.company_id
    
    await entity_type_service.delete_type(
        data.type_id,
        company_id=test_context.active_company.company_id
    )


@pytest.mark.asyncio
async def test_get_type(entity_type_service, test_context, unique_crm_id):
    """Тест получения типа по ID"""
    type_id = unique_crm_id("type")
    data = EntityTypeCreate(
        type_id=type_id,
        name="Test Type",
        prompt="Test prompt",
    )
    
    await entity_type_service.create_type(
        data=data,
        company_id=test_context.active_company.company_id
    )
    
    fetched = await entity_type_service.get_type(
        type_id,
        company_id=test_context.active_company.company_id
    )
    
    assert fetched is not None
    assert fetched.type_id == type_id
    assert fetched.name == "Test Type"
    
    await entity_type_service.delete_type(
        type_id,
        company_id=test_context.active_company.company_id
    )


@pytest.mark.asyncio
async def test_update_type(entity_type_service, test_context, unique_crm_id):
    """Тест обновления типа"""
    type_id = unique_crm_id("type")
    data = EntityTypeCreate(
        type_id=type_id,
        name="Original Name",
        prompt="Original prompt",
    )
    
    await entity_type_service.create_type(
        data=data,
        company_id=test_context.active_company.company_id
    )
    
    update_data = EntityTypeUpdate(name="Updated Name")
    updated = await entity_type_service.update_type(
        type_id,
        update_data,
        company_id=test_context.active_company.company_id
    )
    
    assert updated.name == "Updated Name"
    
    await entity_type_service.delete_type(
        type_id,
        company_id=test_context.active_company.company_id
    )


@pytest.mark.asyncio
async def test_delete_type(entity_type_service, test_context, unique_crm_id):
    """Тест удаления типа"""
    type_id = unique_crm_id("type")
    data = EntityTypeCreate(
        type_id=type_id,
        name="To Delete",
        prompt="Test",
    )
    
    await entity_type_service.create_type(
        data=data,
        company_id=test_context.active_company.company_id
    )
    
    result = await entity_type_service.delete_type(
        type_id,
        company_id=test_context.active_company.company_id
    )
    
    assert result is True
    
    deleted = await entity_type_service.get_type(
        type_id,
        company_id=test_context.active_company.company_id
    )
    assert deleted is None


@pytest.mark.asyncio
async def test_cannot_delete_system_type(entity_type_service, test_context):
    """Тест запрета удаления системного типа"""
    await entity_type_service.init_system_types()
    
    with pytest.raises(ValueError, match="Системные типы нельзя удалять"):
        await entity_type_service.delete_type("person")


@pytest.mark.asyncio
async def test_get_all_types(entity_type_service, test_context, unique_crm_id):
    """Тест получения всех типов (системные + кастомные)"""
    await entity_type_service.init_system_types()
    
    type_id = unique_crm_id("custom")
    data = EntityTypeCreate(
        type_id=type_id,
        name="Custom Type",
        prompt="Test",
    )
    
    await entity_type_service.create_type(
        data=data,
        company_id=test_context.active_company.company_id
    )
    
    all_types = await entity_type_service.get_all_types(
        company_id=test_context.active_company.company_id
    )
    
    type_ids = [t.type_id for t in all_types]
    
    assert "person" in type_ids
    assert type_id in type_ids
    
    await entity_type_service.delete_type(
        type_id,
        company_id=test_context.active_company.company_id
    )
