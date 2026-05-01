"""
Unit тесты для репозиториев встраиваемых виджетов.

Тесты БЕЗ моков - проверяем реальную работу с БД.
Проверяем is_global=False/True изоляцию.
"""

import pytest
from datetime import datetime, timezone

from core.models.embed_models import EmbedConfig, EmbedMapping, EmbedStatus
from core.db.repositories.embed_config_repository import EmbedConfigRepository
from core.db.repositories.embed_mapping_repository import EmbedMappingRepository
from core.models.context_models import Context
from core.models.identity_models import User, Company
from core.context import set_context, clear_context


@pytest.mark.asyncio
async def test_embed_config_repository_basic(storage):
    """Тест базовых операций с EmbedConfigRepository"""
    repo = EmbedConfigRepository(storage=storage)
    
    # Создаем конфигурацию
    config = EmbedConfig(
        embed_id="embed_test123",
        name="Test Widget",
        flow_id="embed_flow_fixture",
        allowed_origins=["https://example.com"],
        status=EmbedStatus.ACTIVE,
        theme="dark",
        position="bottom-right",
        show_reasoning=True,
        show_tool_calls=False,
        primary_color="#6366f1",
        greeting_message="Hello!",
        placeholder="Type here...",
        branding=True,
        created_by="test_user",
    )
    
    # Сохраняем
    await repo.set(config)
    
    # Получаем обратно
    loaded_config = await repo.get("embed_test123")
    
    assert loaded_config is not None
    assert loaded_config.embed_id == "embed_test123"
    assert loaded_config.name == "Test Widget"
    assert loaded_config.flow_id == "embed_flow_fixture"
    assert loaded_config.branch_id == "default"
    assert loaded_config.allowed_origins == ["https://example.com"]
    assert loaded_config.status == EmbedStatus.ACTIVE
    assert loaded_config.show_reasoning is True
    assert loaded_config.show_tool_calls is False
    assert loaded_config.usage_count == 0
    
    # Обновляем
    loaded_config.name = "Updated Widget"
    loaded_config.status = EmbedStatus.DISABLED
    await repo.set(loaded_config)
    
    # Проверяем обновление
    updated_config = await repo.get("embed_test123")
    assert updated_config.name == "Updated Widget"
    assert updated_config.status == EmbedStatus.DISABLED
    
    # Удаляем
    await repo.delete("embed_test123")
    deleted_config = await repo.get("embed_test123")
    assert deleted_config is None


@pytest.mark.asyncio
async def test_embed_config_increment_usage(storage):
    """Тест увеличения счетчика использований"""
    repo = EmbedConfigRepository(storage=storage)
    
    config = EmbedConfig(
        embed_id="embed_usage",
        name="Usage Test",
        flow_id="embed_flow_fixture",
        created_by="test_user",
    )
    
    await repo.set(config)
    
    # Проверяем начальное значение
    loaded = await repo.get("embed_usage")
    assert loaded.usage_count == 0
    assert loaded.last_used_at is None
    
    # Увеличиваем счетчик
    await repo.increment_usage("embed_usage")
    
    # Проверяем обновление
    loaded = await repo.get("embed_usage")
    assert loaded.usage_count == 1
    assert loaded.last_used_at is not None
    assert isinstance(loaded.last_used_at, datetime)
    
    # Еще раз увеличиваем
    await repo.increment_usage("embed_usage")
    
    loaded = await repo.get("embed_usage")
    assert loaded.usage_count == 2
    
    await repo.delete("embed_usage")


@pytest.mark.asyncio
async def test_embed_config_list(storage):
    """Тест получения списка конфигураций"""
    repo = EmbedConfigRepository(storage=storage)
    
    # Создаем несколько конфигураций
    for i in range(3):
        config = EmbedConfig(
            embed_id=f"embed_list_{i}",
            name=f"Widget {i}",
            flow_id=f"agent_{i}",
            created_by="test_user",
        )
        await repo.set(config)
    
    # Получаем список
    configs = await repo.list(limit=100)
    
    # В списке должно быть минимум 3 элемента (могут быть и другие из других тестов)
    assert len(configs) >= 3
    
    # Проверяем что наши конфигурации есть
    embed_ids = [c.embed_id for c in configs]
    assert "embed_list_0" in embed_ids
    assert "embed_list_1" in embed_ids
    assert "embed_list_2" in embed_ids
    
    # Cleanup
    for i in range(3):
        await repo.delete(f"embed_list_{i}")


@pytest.mark.asyncio
async def test_embed_config_is_global_false_isolation(storage, storage_shared):
    """
    Тест изоляции по компаниям (is_global=False).
    
    EmbedConfig должен быть изолирован по компаниям - 
    конфигурации одной компании не видны другой.
    """
    repo = EmbedConfigRepository(storage=storage)
    
    # Контекст компании 1
    context1 = Context(
        active_company=Company(company_id="company_1", name="Company 1"),
        user=User(user_id="user1", name="User 1"),
        channel="test",
        metadata={},
    )
    
    # Контекст компании 2
    context2 = Context(
        active_company=Company(company_id="company_2", name="Company 2"),
        user=User(user_id="user2", name="User 2"),
        channel="test",
        metadata={},
    )
    
    # Создаем конфигурацию в компании 1
    set_context(context1)
    config1 = EmbedConfig(
        embed_id="embed_company1",
        name="Company 1 Widget",
        flow_id="agent_1",
        created_by="user1",
    )
    await repo.set(config1)
    
    # Создаем конфигурацию в компании 2
    set_context(context2)
    config2 = EmbedConfig(
        embed_id="embed_company2",
        name="Company 2 Widget",
        flow_id="agent_2",
        created_by="user2",
    )
    await repo.set(config2)
    
    # Проверяем: компания 1 видит только свою конфигурацию
    set_context(context1)
    loaded1 = await repo.get("embed_company1")
    assert loaded1 is not None
    assert loaded1.name == "Company 1 Widget"
    
    # Компания 1 НЕ видит конфигурацию компании 2
    loaded2_from_1 = await repo.get("embed_company2")
    assert loaded2_from_1 is None
    
    # Проверяем: компания 2 видит только свою конфигурацию
    set_context(context2)
    loaded2 = await repo.get("embed_company2")
    assert loaded2 is not None
    assert loaded2.name == "Company 2 Widget"
    
    # Компания 2 НЕ видит конфигурацию компании 1
    loaded1_from_2 = await repo.get("embed_company1")
    assert loaded1_from_2 is None
    
    # Список конфигураций для компании 1
    set_context(context1)
    list1 = await repo.list(limit=100)
    embed_ids1 = [c.embed_id for c in list1]
    assert "embed_company1" in embed_ids1
    assert "embed_company2" not in embed_ids1
    
    # Список конфигураций для компании 2
    set_context(context2)
    list2 = await repo.list(limit=100)
    embed_ids2 = [c.embed_id for c in list2]
    assert "embed_company2" in embed_ids2
    assert "embed_company1" not in embed_ids2
    
    # Cleanup
    set_context(context1)
    await repo.delete("embed_company1")
    
    set_context(context2)
    await repo.delete("embed_company2")
    
    clear_context()


@pytest.mark.asyncio
async def test_embed_mapping_repository_basic(storage_shared):
    """Тест базовых операций с EmbedMappingRepository"""
    repo = EmbedMappingRepository(storage=storage_shared)
    
    # Создаем маппинг
    mapping = EmbedMapping(
        embed_id="embed_mapping_test",
        company_id="company_abc",
    )
    
    # Сохраняем
    await repo.set(mapping)
    
    # Получаем обратно
    loaded_mapping = await repo.get("embed_mapping_test")
    
    assert loaded_mapping is not None
    assert loaded_mapping.embed_id == "embed_mapping_test"
    assert loaded_mapping.company_id == "company_abc"
    
    # Получаем через get_company_id
    company_id = await repo.get_company_id("embed_mapping_test")
    assert company_id == "company_abc"
    
    # Удаляем
    deleted = await repo.delete_by_embed_id("embed_mapping_test")
    assert deleted is True
    
    # Проверяем что удалился
    loaded_after_delete = await repo.get("embed_mapping_test")
    assert loaded_after_delete is None
    
    # Повторное удаление возвращает False
    deleted_again = await repo.delete_by_embed_id("embed_mapping_test")
    assert deleted_again is False


@pytest.mark.asyncio
async def test_embed_mapping_is_global_true(storage_shared):
    """
    Тест глобального маппинга (is_global=True).
    
    EmbedMapping должен быть доступен глобально,
    независимо от контекста компании.
    """
    repo = EmbedMappingRepository(storage=storage_shared)
    
    # Создаем маппинг в контексте компании 1
    context1 = Context(
        active_company=Company(company_id="company_1", name="Company 1"),
        user=User(user_id="user1", name="User 1"),
        channel="test",
        metadata={},
    )
    
    set_context(context1)
    
    mapping = EmbedMapping(
        embed_id="embed_global_test",
        company_id="company_1",
    )
    await repo.set(mapping)
    
    # Переключаемся на контекст компании 2
    context2 = Context(
        active_company=Company(company_id="company_2", name="Company 2"),
        user=User(user_id="user2", name="User 2"),
        channel="test",
        metadata={},
    )
    
    set_context(context2)
    
    # Маппинг должен быть доступен глобально
    loaded_mapping = await repo.get("embed_global_test")
    assert loaded_mapping is not None
    assert loaded_mapping.company_id == "company_1"
    
    # get_company_id тоже должен работать
    company_id = await repo.get_company_id("embed_global_test")
    assert company_id == "company_1"
    
    # Удаляем
    await repo.delete_by_embed_id("embed_global_test")
    
    clear_context()


@pytest.mark.asyncio
async def test_embed_full_flow(storage, storage_shared):
    """
    Тест полного потока:
    1. Создание EmbedConfig в компании
    2. Создание глобального маппинга
    3. Получение конфигурации через маппинг из другой компании
    """
    config_repo = EmbedConfigRepository(storage=storage)
    mapping_repo = EmbedMappingRepository(storage=storage_shared)
    
    # Шаг 1: Создаем конфигурацию в компании
    company_id = "company_test_flow"
    context = Context(
        active_company=Company(company_id=company_id, name="Test Company"),
        user=User(user_id="user_test", name="Test User"),
        channel="test",
        metadata={},
    )
    
    set_context(context)
    
    embed_id = "embed_flow_test"
    config = EmbedConfig(
        embed_id=embed_id,
        name="Flow Test Widget",
        flow_id="agent_flow",
        created_by="user_test",
    )
    await config_repo.set(config)
    
    # Шаг 2: Создаем глобальный маппинг
    mapping = EmbedMapping(
        embed_id=embed_id,
        company_id=company_id,
    )
    await mapping_repo.set(mapping)
    
    # Шаг 3: Симулируем публичный API (без контекста компании)
    clear_context()
    
    # Находим company_id через маппинг
    found_company_id = await mapping_repo.get_company_id(embed_id)
    assert found_company_id == company_id
    
    # Устанавливаем контекст найденной компании
    set_context(Context(
        user=User(user_id="embed_user", name="Embed User"),
        active_company=Company(company_id=found_company_id, name=""),
        channel="embed",
        metadata={},
    ))
    
    # Получаем конфигурацию
    loaded_config = await config_repo.get(embed_id)
    assert loaded_config is not None
    assert loaded_config.name == "Flow Test Widget"
    
    # Cleanup
    await config_repo.delete(embed_id)
    await mapping_repo.delete_by_embed_id(embed_id)
    
    clear_context()

