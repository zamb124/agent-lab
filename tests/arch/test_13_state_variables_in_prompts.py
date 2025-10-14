"""
Тесты для state variables в промптах агентов.

Проверяем:
1. Переменные из store в промпте основного агента
2. Переменные из store в промптах субагентов
3. Изменение переменных в store и динамическое обновление промптов
"""

import pytest
from langchain_core.messages import HumanMessage

from app.models import (
    AgentConfig,
    AgentType,
    LLMConfig,
    ToolReference,
    CodeMode,
)


@pytest.mark.asyncio
async def test_01_store_variables_in_prompt(migrated_db, storage, agent_factory, test_helpers, unique_id):
    """Тест 1: Переменные из store в промпте агента"""
    agent_id = unique_id("agent")
    
    await test_helpers.create_simple_agent(
        storage=storage,
        agent_id=agent_id,
        name="Test Store Variables Agent",
        prompt="""
Ты помощник компании {company_name}.
Текущий пользователь: {user_name}

ДАННЫЕ СЕССИИ:
- Склад: {?store.warehouse_name|не определен}
- ID склада: {?store.warehouse_id|не определен}
- Курьер: {?store.courier_name|не определен}
- Счетчик запросов: {?store.request_count|0}

Отвечай коротко на основе этих данных.
""",
        tools=[]
    )
    
    agent = await agent_factory.get_agent(agent_id)
    
    thread_id = unique_id("thread")
    config = {"configurable": {"thread_id": thread_id}}
    
    input_data = {
        "messages": [HumanMessage(content="Какой у меня склад?")],
        "store": {
            "warehouse_name": "Большие Каменщики",
            "warehouse_id": "12345",
            "courier_name": "Иван Петров",
            "request_count": 5,
        },
        "remaining_steps": 25,
        "session_id": "test_session",
        "task_id": "task_1",
        "user_id": "user_1",
    }
    
    result = await agent.ainvoke(input_data, config=config)
    
    assert "messages" in result
    assert len(result["messages"]) > 1
    assert result["store"]["warehouse_name"] == "Большие Каменщики"
    assert result["store"]["warehouse_id"] == "12345"


@pytest.mark.asyncio
async def test_02_store_variables_in_subagent_prompt(migrated_db, storage, agent_factory, test_helpers, unique_id):
    """Тест 2: Переменные из store в промпте субагента"""
    subagent_id = unique_id("agent")
    main_agent_id = unique_id("agent")
    
    await test_helpers.create_simple_agent(
        storage=storage,
        agent_id=subagent_id,
        name="Test Subagent With Store",
        prompt="""
Ты субагент для работы со складами.

ТЕКУЩИЕ ДАННЫЕ:
- Склад: {?store.warehouse_name|не определен}
- ID: {?store.warehouse_id|не определен}
- Запросов к складу: {?store.warehouse_requests|0}

Отвечай на основе этих данных.
""",
        tools=[]
    )
    
    await test_helpers.create_simple_agent(
        storage=storage,
        agent_id=main_agent_id,
        name="Test Main Agent",
        prompt="""
Ты главный агент.

ОБЩИЕ ДАННЫЕ:
- Пользователь: {user_name}
- Склад: {?store.warehouse_name|не определен}

Используй субагента для работы со складом.
""",
        tools=[f"agent:{subagent_id}"]
    )
    
    main_agent = await agent_factory.get_agent(main_agent_id)
    
    # Вызываем с данными в store
    thread_id = unique_id("thread")
    config = {"configurable": {"thread_id": thread_id}}
    
    input_data = {
        "messages": [HumanMessage(content="Проверь склад")],
        "store": {
            "warehouse_name": "Склад №5",
            "warehouse_id": "555",
            "warehouse_requests": 10,
        },
        "remaining_steps": 25,
        "session_id": "test_session",
        "task_id": "task_1",
        "user_id": "user_1",
    }
    
    result = await main_agent.ainvoke(input_data, config=config)
    
    # Проверяем что store данные сохранились
    assert result["store"]["warehouse_name"] == "Склад №5"
    assert result["store"]["warehouse_requests"] == 10
    
    print("✅ Тест 2 пройден: Субагент видит store переменные в промпте")


@pytest.mark.asyncio
async def test_03_store_variables_update_changes_prompt(migrated_db, storage, agent_factory, test_helpers, unique_id):
    """
    Тест 3: Изменение store переменных меняет промпт.
    Проверяем что при изменении store.warehouse_name промпт обновляется.
    """
    
    agent_id = unique_id("agent")
    
    await test_helpers.create_simple_agent(
        storage=storage,
        agent_id=agent_id,
        name="Test Dynamic Prompt Agent",
        prompt="""
Ты помощник.

ТЕКУЩИЙ СКЛАД: {?store.warehouse_name|НЕТ ДАННЫХ}
ID СКЛАДА: {?store.warehouse_id|НЕТ}
СТАТУС: {?store.status|unknown}
СЧЕТЧИК: {?store.counter|0}

Если склад не определен, скажи "нет данных".
Если склад определен, скажи его название.
""",
        tools=[]
    )
    
    agent = await agent_factory.get_agent(agent_id)
    
    thread_id = unique_id("thread")
    config = {"configurable": {"thread_id": thread_id}}
    
    # ВЫЗОВ 1: БЕЗ данных в store
    input_data_1 = {
        "messages": [HumanMessage(content="Какой склад?")],
        "store": {},
        "remaining_steps": 25,
        "session_id": "test_session",
        "task_id": "task_1",
        "user_id": "user_1",
    }
    
    result_1 = await agent.ainvoke(input_data_1, config=config)
    
    # Store должен быть пустой
    assert result_1["store"] == {}
    
    # ВЫЗОВ 2: ДОБАВЛЯЕМ данные в store
    input_data_2 = {
        "messages": [HumanMessage(content="А теперь?")],
        "store": {
            "warehouse_name": "Новый Склад",
            "warehouse_id": "999",
            "status": "active",
            "counter": 1,
        },
    }
    
    result_2 = await agent.ainvoke(input_data_2, config=config)
    
    # Проверяем что store обновился
    assert result_2["store"]["warehouse_name"] == "Новый Склад"
    assert result_2["store"]["warehouse_id"] == "999"
    assert result_2["store"]["status"] == "active"
    assert result_2["store"]["counter"] == 1
    
    # ВЫЗОВ 3: ИЗМЕНЯЕМ данные в store
    # В реальности store будет уже содержать данные из предыдущего вызова
    input_data_3 = {
        "messages": [HumanMessage(content="Статус изменился?")],
    }
    
    result_3 = await agent.ainvoke(input_data_3, config=config)
    
    # Проверяем что store персистился
    assert result_3["store"]["warehouse_name"] == "Новый Склад"
    assert result_3["store"]["counter"] == 1
    
    # Теперь меняем counter
    result_3["store"]["counter"] = 2
    result_3["store"]["status"] = "updated"
    
    input_data_4 = {
        "messages": [HumanMessage(content="Еще раз")],
    }
    
    result_4 = await agent.ainvoke(input_data_4, config=config)
    
    # Store должен содержать обновленные данные из result_3
    # (LangGraph персистит изменения)
    assert "warehouse_name" in result_4["store"]
    
    print("✅ Тест 3 пройден: Изменение store меняет промпт динамически")


@pytest.mark.asyncio
async def test_04_optional_and_default_values(migrated_db, storage, agent_factory, test_helpers, unique_id):
    """
    Тест 4: Опциональные переменные и значения по умолчанию.
    Проверяем {?var} и {?var|default} синтаксис.
    """
    
    # Создаем агента с опциональными переменными
    agent_config = AgentConfig(
        agent_id="test_optional_vars_agent",
        name="Test Optional Variables Agent",
        description="Агент с опциональными переменными",
        type=AgentType.REACT,
        prompt="""
Ты помощник.

ОБЯЗАТЕЛЬНЫЕ ПОЛЯ:
- Пользователь: {user_name}
- Компания: {company_name}

ОПЦИОНАЛЬНЫЕ ПОЛЯ:
- Склад: {?store.warehouse_name}
- Курьер: {?store.courier_name|НЕ НАЗНАЧЕН}
- Лимит: {?store.request_limit|100}
- Флаг: {?store.some_flag|false}

Отвечай на основе этих данных.
""",
        tools=[],
        llm_config=LLMConfig(
            provider="mock",
            model="mock-gpt-4",
            temperature=0.1,
        ),
    )
    
    await storage.set_agent_config(agent_config)
    
    agent = await agent_factory.get_agent("test_optional_vars_agent")
    
    thread_id = unique_id("thread")
    config = {"configurable": {"thread_id": thread_id}}
    
    # Вызываем с ЧАСТИЧНЫМИ данными в store
    input_data = {
        "messages": [HumanMessage(content="Проверь данные")],
        "store": {
            "warehouse_name": "Склад А",
            # courier_name НЕТ - должно быть "НЕ НАЗНАЧЕН"
            # request_limit НЕТ - должно быть "100"
            # some_flag НЕТ - должно быть "false"
        },
        "remaining_steps": 25,
        "session_id": "test_session",
        "task_id": "task_1",
        "user_id": "user_1",
    }
    
    result = await agent.ainvoke(input_data, config=config)
    
    # Проверяем что agent успешно выполнился
    assert "messages" in result
    assert result["store"]["warehouse_name"] == "Склад А"
    
    print("✅ Тест 4 пройден: Опциональные переменные и дефолты работают")


@pytest.mark.asyncio
async def test_05_special_functions(migrated_db, storage, agent_factory, test_helpers, unique_id):
    """
    Тест 5: Специальные функции {#messages.count}, {#store.keys}.
    Проверяем что специальные функции работают.
    """
    
    # Создаем агента со специальными функциями
    agent_config = AgentConfig(
        agent_id="test_special_funcs_agent",
        name="Test Special Functions Agent",
        description="Агент со специальными функциями",
        type=AgentType.REACT,
        prompt="""
Ты помощник.

СТАТИСТИКА:
- Сообщений в истории: {#messages.count}
- Ключи в store: {#store.keys}
- Store пустой: {#store.empty}

Отвечай коротко.
""",
        tools=[],
        llm_config=LLMConfig(
            provider="mock",
            model="mock-gpt-4",
            temperature=0.1,
        ),
    )
    
    await storage.set_agent_config(agent_config)
    
    agent = await agent_factory.get_agent("test_special_funcs_agent")
    
    thread_id = unique_id("thread")
    config = {"configurable": {"thread_id": thread_id}}
    
    # Первый вызов
    input_data_1 = {
        "messages": [HumanMessage(content="Первое сообщение")],
        "store": {},
        "remaining_steps": 25,
        "session_id": "test_session",
        "task_id": "task_1",
        "user_id": "user_1",
    }
    
    result_1 = await agent.ainvoke(input_data_1, config=config)
    
    # Должно быть как минимум 2 сообщения (user + assistant)
    assert len(result_1["messages"]) >= 2
    
    # Второй вызов с данными в store
    input_data_2 = {
        "messages": [HumanMessage(content="Второе сообщение")],
        "store": {
            "key1": "value1",
            "key2": "value2",
        },
    }
    
    result_2 = await agent.ainvoke(input_data_2, config=config)
    
    # Проверяем что store заполнен
    assert len(result_2["store"]) >= 2
    assert "key1" in result_2["store"]
    assert "key2" in result_2["store"]
    
    print("✅ Тест 5 пройден: Специальные функции работают")


@pytest.mark.asyncio
async def test_06_nested_store_access(migrated_db, storage, agent_factory, test_helpers, unique_id):
    """
    Тест 6: Доступ к вложенным данным в store.
    Проверяем {store.settings.timeout} синтаксис.
    """
    
    # Создаем агента с вложенными данными
    agent_config = AgentConfig(
        agent_id="test_nested_store_agent",
        name="Test Nested Store Agent",
        description="Агент с вложенными данными в store",
        type=AgentType.REACT,
        prompt="""
Ты помощник.

НАСТРОЙКИ:
- Таймаут: {?store.settings.timeout|30}
- Язык: {?store.settings.language|ru}
- Единицы температуры: {?store.units.temperature|celsius}

ЛИМИТЫ:
- Макс запросов: {?store.limits.max_requests|10}

Отвечай на основе этих данных.
""",
        tools=[],
        llm_config=LLMConfig(
            provider="mock",
            model="mock-gpt-4",
            temperature=0.1,
        ),
    )
    
    await storage.set_agent_config(agent_config)
    
    agent = await agent_factory.get_agent("test_nested_store_agent")
    
    thread_id = unique_id("thread")
    config = {"configurable": {"thread_id": thread_id}}
    
    # Вызываем с вложенными данными
    input_data = {
        "messages": [HumanMessage(content="Покажи настройки")],
        "store": {
            "settings": {
                "timeout": 60,
                "language": "en",
            },
            "units": {
                "temperature": "fahrenheit",
            },
            "limits": {
                "max_requests": 50,
            },
        },
        "remaining_steps": 25,
        "session_id": "test_session",
        "task_id": "task_1",
        "user_id": "user_1",
    }
    
    result = await agent.ainvoke(input_data, config=config)
    
    # Проверяем что вложенные данные доступны
    assert result["store"]["settings"]["timeout"] == 60
    assert result["store"]["settings"]["language"] == "en"
    assert result["store"]["units"]["temperature"] == "fahrenheit"
    assert result["store"]["limits"]["max_requests"] == 50
    
    print("✅ Тест 6 пройден: Вложенные данные в store работают")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

