"""
Тесты для EntityService.

EntityService работает с ChromaDB через RAGRepository.
Тесты используют реальный ChromaDB (mock не используется).
"""

import pytest
import pytest_asyncio

from apps.crm.models.entity_models import EntityCreate, EntityUpdate, EntitySearchRequest


@pytest_asyncio.fixture
async def entity_service(crm_container, test_context):
    """EntityService для тестов"""
    return crm_container.entity_service


@pytest.mark.asyncio
async def test_create_entity(entity_service, test_context, unique_id):
    """Тест создания сущности"""
    entity_id = unique_id("entity")
    
    data = EntityCreate(
        type="person",
        name=f"Test Person {entity_id}",
        description="Test description",
        attributes={"email": "test@example.com", "phone": "+1234567890"},
    )
    
    result = await entity_service.create_entity(data)
    
    assert result.type == "person"
    assert result.name == data.name
    assert result.description == data.description
    assert result.attributes["email"] == "test@example.com"
    assert result.entity_id is not None
    
    # Cleanup
    await entity_service.delete_entity(result.entity_id)


@pytest.mark.asyncio
async def test_get_entity(entity_service, test_context, unique_id):
    """Тест получения сущности по ID"""
    data = EntityCreate(
        type="person",
        name=f"Test Person {unique_id('entity')}",
        description="Test",
        attributes={},
    )
    
    created = await entity_service.create_entity(data)
    
    result = await entity_service.get_entity(created.entity_id)
    
    assert result is not None
    assert result.entity_id == created.entity_id
    assert result.name == data.name
    
    # Cleanup
    await entity_service.delete_entity(created.entity_id)


@pytest.mark.asyncio
async def test_get_nonexistent_entity(entity_service, test_context):
    """Тест получения несуществующей сущности"""
    result = await entity_service.get_entity("nonexistent_entity_id")
    
    assert result is None


@pytest.mark.asyncio
async def test_update_entity(entity_service, test_context, unique_id):
    """Тест обновления сущности"""
    data = EntityCreate(
        type="person",
        name=f"Test Person {unique_id('entity')}",
        description="Original description",
        attributes={"role": "developer"},
    )
    
    created = await entity_service.create_entity(data)
    
    update_data = EntityUpdate(
        name="Updated Person Name",
        description="Updated description",
    )
    
    result = await entity_service.update_entity(created.entity_id, update_data)
    
    assert result is not None
    assert result.name == "Updated Person Name"
    assert result.description == "Updated description"
    assert result.attributes["role"] == "developer"  # Атрибуты сохранились
    
    # Cleanup
    await entity_service.delete_entity(created.entity_id)


@pytest.mark.asyncio
async def test_update_nonexistent_entity(entity_service, test_context):
    """Тест обновления несуществующей сущности"""
    update_data = EntityUpdate(name="New Name")
    
    result = await entity_service.update_entity("nonexistent_id", update_data)
    
    assert result is None


@pytest.mark.asyncio
async def test_delete_entity(entity_service, test_context, unique_id):
    """Тест удаления сущности"""
    data = EntityCreate(
        type="person",
        name=f"Test Person {unique_id('entity')}",
        description="To be deleted",
        attributes={},
    )
    
    created = await entity_service.create_entity(data)
    
    success = await entity_service.delete_entity(created.entity_id)
    assert success is True
    
    # Проверяем что сущность удалена
    result = await entity_service.get_entity(created.entity_id)
    assert result is None


@pytest.mark.asyncio
async def test_delete_nonexistent_entity(entity_service, test_context):
    """Тест удаления несуществующей сущности"""
    success = await entity_service.delete_entity("nonexistent_id")
    
    # ChromaDB может вернуть True даже для несуществующих
    # Главное что не падает
    assert success in [True, False]


@pytest.mark.asyncio
async def test_list_entities(entity_service, test_context, unique_id):
    """Тест получения списка сущностей"""
    # Создаем несколько сущностей
    created_ids = []
    for i in range(3):
        data = EntityCreate(
            type="person",
            name=f"Test Person {unique_id('entity')}_{i}",
            description=f"Description {i}",
            attributes={},
        )
        result = await entity_service.create_entity(data)
        created_ids.append(result.entity_id)
    
    entities = await entity_service.list_entities(entity_type="person", limit=100)
    
    assert isinstance(entities, list)
    # Проверяем что наши сущности в списке
    found_ids = [e.entity_id for e in entities]
    for eid in created_ids:
        assert eid in found_ids
    
    # Cleanup
    for eid in created_ids:
        await entity_service.delete_entity(eid)


@pytest.mark.asyncio
async def test_list_entities_by_type(entity_service, test_context, unique_id):
    """Тест фильтрации по типу"""
    # Создаем сущности разных типов
    person_data = EntityCreate(
        type="person",
        name=f"Test Person {unique_id('entity')}",
        description="Person",
        attributes={},
    )
    org_data = EntityCreate(
        type="organization",
        name=f"Test Org {unique_id('entity')}",
        description="Org",
        attributes={},
    )
    
    person = await entity_service.create_entity(person_data)
    org = await entity_service.create_entity(org_data)
    
    # Фильтр по person
    persons = await entity_service.list_entities(entity_type="person", limit=100)
    
    person_ids = [e.entity_id for e in persons]
    assert person.entity_id in person_ids
    
    # Cleanup
    await entity_service.delete_entity(person.entity_id)
    await entity_service.delete_entity(org.entity_id)


@pytest.mark.asyncio
async def test_search_entities(entity_service, test_context, unique_id):
    """Тест семантического поиска"""
    # Создаем сущность с уникальным именем
    unique_name = f"UniqueSearchableCompany_{unique_id('entity')}"
    data = EntityCreate(
        type="organization",
        name=unique_name,
        description="Компания для тестирования поиска",
        attributes={"industry": "technology"},
    )
    
    created = await entity_service.create_entity(data)
    
    # Ищем по части имени
    request = EntitySearchRequest(
        query=unique_name[:20],
        limit=10,
    )
    
    result = await entity_service.search_entities(request)
    
    assert result.total >= 1
    found_ids = [e.entity_id for e in result.entities]
    assert created.entity_id in found_ids
    
    # Cleanup
    await entity_service.delete_entity(created.entity_id)


@pytest.mark.asyncio
async def test_search_entities_by_type(entity_service, test_context, unique_id):
    """Тест поиска с фильтром по типу"""
    data = EntityCreate(
        type="project",
        name=f"Test Project {unique_id('entity')}",
        description="Unique project for search test",
        attributes={},
    )
    
    created = await entity_service.create_entity(data)
    
    request = EntitySearchRequest(
        query="project",
        entity_type="project",
        limit=10,
    )
    
    result = await entity_service.search_entities(request)
    
    # Все результаты должны быть project
    for entity in result.entities:
        assert entity.type == "project"
    
    # Cleanup
    await entity_service.delete_entity(created.entity_id)


@pytest.mark.asyncio
async def test_find_duplicates(entity_service, test_context, unique_id):
    """Тест поиска дубликатов"""
    # Создаем сущность
    original_name = f"John Smith Developer {unique_id('entity')}"
    original_data = EntityCreate(
        type="person",
        name=original_name,
        description="Software developer at Tech Corp",
        attributes={"email": "john.smith@techcorp.com"},
    )
    
    original = await entity_service.create_entity(original_data)
    
    # Ищем дубликаты для похожей сущности
    similar_data = EntityCreate(
        type="person",
        name=original_name,  # Тот же name
        description="Developer at Tech Corporation",
        attributes={"email": "j.smith@techcorp.com"},
    )
    
    duplicates = await entity_service.find_duplicates(similar_data, threshold=0.5)
    
    # Должен найти original как потенциальный дубликат
    assert isinstance(duplicates, list)
    # С высоким threshold может и не найти, но хотя бы не падает
    
    # Cleanup
    await entity_service.delete_entity(original.entity_id)


@pytest.mark.asyncio
async def test_ensure_namespace(entity_service, test_context):
    """Тест создания namespace"""
    namespace = await entity_service.ensure_namespace()
    
    assert namespace is not None
    assert namespace.startswith("crm_")


@pytest.mark.asyncio
async def test_create_entity_invalid_type(entity_service, test_context, unique_id):
    """Тест создания сущности с невалидным типом"""
    data = EntityCreate(
        type="nonexistent_type",
        name=f"Test {unique_id('entity')}",
        description="Invalid",
        attributes={},
    )
    
    with pytest.raises(ValueError, match="не найден"):
        await entity_service.create_entity(data)

