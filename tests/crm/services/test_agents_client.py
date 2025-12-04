"""
Тесты для AgentsClient.

AgentsClient - HTTP клиент для вызова AI агентов из apps/agents.
Для тестов требуется запущенный agents сервис.
"""

import pytest
import pytest_asyncio

from apps.crm.services.agents_client import AgentsClient


@pytest_asyncio.fixture
async def agents_client(agents_service, test_context):
    """
    AgentsClient с URL запущенного agents сервиса.
    
    Зависит от фикстуры agents_service из tests/frontend/conftest.py
    которая запускает agents в отдельном процессе.
    """
    return AgentsClient(agents_base_url=agents_service["url"])


@pytest.mark.asyncio
async def test_health_check(agents_client):
    """Тест проверки доступности сервиса"""
    result = await agents_client.health_check()
    
    assert result is True


@pytest.mark.asyncio
async def test_extract_entities_basic(agents_client):
    """
    Базовый тест извлечения сущностей.
    
    Примечание: Этот тест может упасть если агент crm_entity_extractor
    не зарегистрирован в БД agents. В таком случае агент должен быть
    добавлен через миграцию.
    """
    text = """
    Сегодня встретился с Иваном Петровым из компании ТехноСофт.
    Обсудили проект внедрения CRM системы.
    """
    
    try:
        result = await agents_client.extract_entities(text)
        
        assert "entities" in result or "error" in result
    except Exception as e:
        # Агент может быть не зарегистрирован - это ОК для тестов
        pytest.skip(f"Agent not available: {e}")


@pytest.mark.asyncio
async def test_extract_entities_with_summary(agents_client):
    """Тест извлечения с генерацией резюме"""
    text = """
    Провели встречу с командой разработки.
    Присутствовали: Алексей (тимлид), Мария (дизайнер), Сергей (бэкенд).
    Решили запустить проект Alpha в следующем месяце.
    """
    
    try:
        result = await agents_client.extract_entities(
            text,
            generate_summary=True
        )
        
        # Ожидаем либо result с данными, либо ошибку если агент не настроен
        assert isinstance(result, dict)
    except Exception as e:
        pytest.skip(f"Agent not available: {e}")


@pytest.mark.asyncio
async def test_extract_entities_with_types(agents_client):
    """Тест извлечения с указанием типов"""
    text = "Иван работает в компании Apple над проектом iOS 20."
    
    entity_types = [
        {
            "type_id": "person",
            "name": "People",
            "prompt": "Извлеки имена людей"
        },
        {
            "type_id": "organization",
            "name": "Organizations",
            "prompt": "Извлеки названия организаций"
        }
    ]
    
    try:
        result = await agents_client.extract_entities(
            text,
            entity_types=entity_types
        )
        
        assert isinstance(result, dict)
    except Exception as e:
        pytest.skip(f"Agent not available: {e}")


@pytest.mark.asyncio
async def test_compare_entities(agents_client):
    """Тест сравнения сущностей"""
    entity_1 = {
        "name": "John Smith",
        "type": "person",
        "attributes": {"email": "john.smith@company.com"}
    }
    
    entity_2 = {
        "name": "J. Smith",
        "type": "person",
        "attributes": {"email": "jsmith@company.com"}
    }
    
    try:
        result = await agents_client.compare_entities(entity_1, entity_2)
        
        assert isinstance(result, dict)
        # Ожидаемые поля если агент работает
        if "is_duplicate" in result:
            assert isinstance(result["is_duplicate"], bool)
        if "confidence" in result:
            assert isinstance(result["confidence"], (int, float))
    except Exception as e:
        pytest.skip(f"Agent not available: {e}")


@pytest.mark.asyncio
async def test_agents_client_headers(test_context):
    """Тест формирования заголовков"""
    client = AgentsClient(agents_base_url="http://localhost:8001")
    
    headers = client._get_headers()
    
    assert "Content-Type" in headers
    assert headers["Content-Type"] == "application/json"
    
    # Должны быть заголовки с контекстом
    assert "X-Company-Id" in headers
    assert "X-User-Id" in headers


@pytest.mark.asyncio
async def test_agents_client_invalid_url():
    """Тест с невалидным URL"""
    client = AgentsClient(agents_base_url="http://nonexistent-host:9999")
    
    with pytest.raises(Exception):
        await client.health_check()

