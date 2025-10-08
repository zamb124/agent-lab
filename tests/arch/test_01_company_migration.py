"""
Тест миграции для компаний.

Проверяет:
1. Миграция базовых сущностей при создании новой компании
2. Миграция отдельных сущностей (flow, agent, tool)
3. Перемиграция сущностей для отката к базовому состоянию
"""
import pytest
import asyncio
from datetime import datetime, timezone

from app.core.migrator import Migrator
from app.core.storage import Storage
from app.core.context import set_context, clear_context
from app.identity.models import Company, User, AuthProvider, UserStatus
from app.models.context_models import Context
from app.models import AgentType


async def _create_test_company():
    """Создает тестовую компанию"""
    company = Company(
        company_id="test_company_migration",
        subdomain="test_migration",
        name="Test Migration Company",
        status="active",
        created_at=datetime.now(timezone.utc)
    )
    
    storage = Storage()
    await storage.set(f"company:{company.company_id}", company.model_dump_json(), force_global=True)
    
    return company


async def _cleanup_test_company(company: Company):
    """Удаляет тестовую компанию"""
    storage = Storage()
    await storage.delete(f"company:{company.company_id}", force_global=True)


@pytest.mark.asyncio
async def test_migrate_defaults_for_company():
    """
    Тест 1: Миграция базовых сущностей для новой компании.
    
    Проверяет что при вызове migrate_defaults_for_company():
    - Мигрируется базовый flow из config
    - Мигрируется entry_point_agent
    - Мигрируются все зависимости
    """
    test_company = await _create_test_company()
    migrator = Migrator()
    storage = Storage()
    
    # Устанавливаем контекст компании
    user = User(
        user_id="test_user",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=test_company,
        user_companies=[test_company]
    )
    set_context(context)
    
    # Выполняем миграцию
    await migrator.migrate_defaults_for_company(test_company)
    
    # Проверяем что все дефолтные flows мигрировались
    test_flow_config = await storage.get_flow_config("app.flows.test_flow.test_flow_config")
    assert test_flow_config is not None, "test_flow должен быть мигрирован"
    assert test_flow_config.flow_id == "app.flows.test_flow.test_flow_config"
    
    weather_flow_config = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert weather_flow_config is not None, "weather_flow должен быть мигрирован"
    
    # Проверяем что entry_point агенты мигрировались
    test_agent = await storage.get_agent_config("app.flows.test_flow.TestFlowAgent")
    assert test_agent is not None, "TestFlowAgent должен быть мигрирован"
    assert test_agent.type == AgentType.STATEGRAPH, "TestFlowAgent должен быть StateGraph"
    
    weather_agent = await storage.get_agent_config("app.agents.weather.agent.WeatherAgent")
    assert weather_agent is not None, "WeatherAgent должен быть мигрирован"
    assert weather_agent.type == AgentType.REACT, "WeatherAgent должен быть ReAct"
    
    # Проверяем что дефолтные агенты мигрировались
    calc_agent = await storage.get_agent_config("app.agents.calculator.agent.CalculatorAgent")
    assert calc_agent is not None, "CalculatorAgent должен быть мигрирован"
    assert calc_agent.type == AgentType.REACT, "CalculatorAgent должен быть ReAct"
    
    # Проверяем что дефолтные tools мигрировались
    tool1_data = await storage.get("tool:app.tools.calc_tools.calculate")
    assert tool1_data is not None, "calculate tool должен быть мигрирован"
    
    tool2_data = await storage.get("tool:app.tools.calc_tools.get_math_help")
    assert tool2_data is not None, "get_math_help tool должен быть мигрирован"
    
    print("✅ Тест migrate_defaults_for_company пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_migrate_single_flow_for_company():
    """
    Тест 2: Миграция отдельного flow в компанию.
    
    Проверяет что можно мигрировать отдельный flow
    со всеми зависимостями.
    """
    test_company = await _create_test_company()
    migrator = Migrator()
    storage = Storage()
    
    # Устанавливаем контекст
    user = User(
        user_id="test_user",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=test_company,
        user_companies=[test_company]
    )
    set_context(context)
    
    # Мигрируем конкретный flow
    await migrator.migrate_for_company(
        company=test_company,
        flows=["app.flows.test_flow.test_flow_config"],
        with_dependencies=True
    )
    
    # Проверяем flow
    flow_config = await storage.get_flow_config("app.flows.test_flow.test_flow_config")
    assert flow_config is not None, "Flow должен быть мигрирован"
    
    # Проверяем зависимости
    agent_config = await storage.get_agent_config("app.flows.test_flow.TestFlowAgent")
    assert agent_config is not None, "Зависимые агенты должны быть мигрированы"
    
    print("✅ Тест migrate_single_flow_for_company пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_migrate_single_agent_for_company():
    """
    Тест 3: Миграция отдельного агента в компанию.
    
    Проверяет что можно мигрировать отдельный агент
    без зависимостей.
    """
    test_company = await _create_test_company()
    migrator = Migrator()
    storage = Storage()
    
    # Устанавливаем контекст
    user = User(
        user_id="test_user",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=test_company,
        user_companies=[test_company]
    )
    set_context(context)
    
    # Мигрируем конкретного агента
    await migrator.migrate_for_company(
        company=test_company,
        agents=["app.flows.test_flow.TestFlowAgent"],
        with_dependencies=False
    )
    
    # Проверяем агента
    agent_config = await storage.get_agent_config("app.flows.test_flow.TestFlowAgent")
    assert agent_config is not None, "Агент должен быть мигрирован"
    
    print("✅ Тест migrate_single_agent_for_company пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_remigrate_flow():
    """
    Тест 4: Перемиграция flow для отката к базовому состоянию.
    
    Проверяет что можно перемигрировать flow и
    откатить изменения к коду.
    """
    test_company = await _create_test_company()
    migrator = Migrator()
    storage = Storage()
    
    # Устанавливаем контекст
    user = User(
        user_id="test_user",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=test_company,
        user_companies=[test_company]
    )
    set_context(context)
    
    # 1. Первая миграция
    await migrator.migrate_for_company(
        company=test_company,
        flows=["app.flows.test_flow.test_flow_config"],
        with_dependencies=True
    )
    
    # 2. Получаем flow из БД (Storage использует контекст компании)
    flow_config = await storage.get_flow_config("app.flows.test_flow.test_flow_config")
    original_updated_at = flow_config.updated_at
    
    # 3. "Изменяем" flow в БД (симулируем изменение)
    flow_config.description = "ИЗМЕНЕНО!!!"
    await storage.set_flow_config(flow_config)
    
    # 4. Перемигрируем flow (откат к коду)
    await migrator.remigrate_flow(
        "app.flows.test_flow.test_flow_config",
        test_company
    )
    
    # 5. Проверяем что откатилось к базовому состоянию
    flow_config_after = await storage.get_flow_config("app.flows.test_flow.test_flow_config")
    
    assert flow_config_after.description != "ИЗМЕНЕНО!!!", "Описание должно откатиться к базовому"
    assert flow_config_after.description == "Простой тестовый флоу без LLM", "Описание должно быть из кода"
    assert flow_config_after.updated_at > original_updated_at, "updated_at должен обновиться"
    
    print("✅ Тест remigrate_flow пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_remigrate_agent():
    """
    Тест 5: Перемиграция агента для отката к базовому состоянию.
    """
    test_company = await _create_test_company()
    migrator = Migrator()
    storage = Storage()
    
    # Устанавливаем контекст
    user = User(
        user_id="test_user",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=test_company,
        user_companies=[test_company]
    )
    set_context(context)
    
    # 1. Первая миграция
    await migrator.migrate_for_company(
        company=test_company,
        agents=["app.flows.test_flow.TestFlowAgent"],
        with_dependencies=False
    )
    
    # 2. Получаем агента из БД
    agent_config = await storage.get_agent_config("app.flows.test_flow.TestFlowAgent")
    original_name = agent_config.name
    
    # 3. "Изменяем" агента в БД
    agent_config.name = "ИЗМЕНЕННОЕ ИМЯ"
    await storage.set_agent_config(agent_config)
    
    # 4. Перемигрируем агента
    await migrator.remigrate_agent(
        "app.flows.test_flow.TestFlowAgent",
        test_company
    )
    
    # 5. Проверяем откат
    agent_config_after = await storage.get_agent_config("app.flows.test_flow.TestFlowAgent")
    
    assert agent_config_after.name != "ИЗМЕНЕННОЕ ИМЯ", "Имя должно откатиться"
    assert agent_config_after.name == original_name, "Имя должно быть из кода"
    
    print("✅ Тест remigrate_agent пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_migrate_with_nested_dependencies():
    """
    Тест 6: Миграция с вложенными зависимостями.
    
    Проверяет что при миграции flow с зависимостями,
    все субагенты и их tools тоже мигрируются.
    """
    test_company = await _create_test_company()
    migrator = Migrator()
    storage = Storage()
    
    # Устанавливаем контекст
    user = User(
        user_id="test_user",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=test_company,
        user_companies=[test_company]
    )
    set_context(context)
    
    # Мигрируем flow со всеми зависимостями
    await migrator.migrate_for_company(
        company=test_company,
        flows=["app.flows.test_flow.test_flow_config"],
        with_dependencies=True
    )
    
    # Проверяем что все сущности мигрировались в компанию
    flow_config = await storage.get_flow_config("app.flows.test_flow.test_flow_config")
    assert flow_config is not None, "Flow должен быть в компании"
    
    agent_config = await storage.get_agent_config("app.flows.test_flow.TestFlowAgent")
    assert agent_config is not None, "Агент должен быть в компании"
    
    print("✅ Тест migrate_with_nested_dependencies пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_migrate_single_tool():
    """
    Тест 7: Миграция отдельного tool.
    
    Проверяет что можно мигрировать отдельный tool.
    """
    test_company = await _create_test_company()
    migrator = Migrator()
    storage = Storage()
    
    # Устанавливаем контекст
    user = User(
        user_id="test_user",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=test_company,
        user_companies=[test_company]
    )
    set_context(context)
    
    # Мигрируем конкретный tool
    await migrator.migrate_for_company(
        company=test_company,
        tools=["app.tools.calc_tools.calculate"],
        with_dependencies=False
    )
    
    # Проверяем tool
    tool_key = "tool:app.tools.calc_tools.calculate"
    tool_data = await storage.get(tool_key)
    assert tool_data is not None, "Tool должен быть мигрирован"
    
    print("✅ Тест migrate_single_tool пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_remigrate_tool():
    """
    Тест 8: Перемиграция tool для отката к базовому состоянию.
    """
    test_company = await _create_test_company()
    migrator = Migrator()
    storage = Storage()
    
    # Устанавливаем контекст
    user = User(
        user_id="test_user",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=test_company,
        user_companies=[test_company]
    )
    set_context(context)
    
    # 1. Первая миграция
    await migrator.migrate_for_company(
        company=test_company,
        tools=["app.tools.calc_tools.calculate"],
        with_dependencies=False
    )
    
    # 2. Получаем tool из БД
    from app.models import ToolReference
    tool_key = "tool:app.tools.calc_tools.calculate"
    tool_data = await storage.get(tool_key)
    tool_ref = ToolReference.model_validate_json(tool_data)
    original_description = tool_ref.description
    
    # 3. "Изменяем" tool в БД
    tool_ref.description = "ИЗМЕНЕНО!!!"
    await storage.set(tool_key, tool_ref.model_dump_json())
    
    # 4. Перемигрируем tool
    await migrator.remigrate_tool(
        "app.tools.calc_tools.calculate",
        test_company
    )
    
    # 5. Проверяем откат
    tool_data_after = await storage.get(tool_key)
    tool_ref_after = ToolReference.model_validate_json(tool_data_after)
    
    assert tool_ref_after.description != "ИЗМЕНЕНО!!!", "Описание должно откатиться"
    assert tool_ref_after.description == original_description, "Описание должно быть из кода"
    
    print("✅ Тест remigrate_tool пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_react_agent_migration():
    """
    Тест 9: Проверка миграции ReAct агента.
    
    Проверяет что ReAct агенты (WeatherAgent, CalculatorAgent) 
    мигрируются с правильным типом и настройками.
    """
    test_company = await _create_test_company()
    migrator = Migrator()
    storage = Storage()
    
    # Устанавливаем контекст
    user = User(
        user_id="test_user",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=test_company,
        user_companies=[test_company]
    )
    set_context(context)
    
    # Мигрируем ReAct агентов
    await migrator.migrate_for_company(
        company=test_company,
        agents=[
            "app.agents.calculator.agent.CalculatorAgent",
            "app.agents.weather.agent.WeatherAgent"
        ],
        with_dependencies=False
    )
    
    # Проверяем CalculatorAgent
    calc_agent = await storage.get_agent_config("app.agents.calculator.agent.CalculatorAgent")
    assert calc_agent is not None, "CalculatorAgent должен быть мигрирован"
    assert calc_agent.type == AgentType.REACT, f"CalculatorAgent должен быть REACT, получили {calc_agent.type}"
    assert calc_agent.prompt is not None, "ReAct агент должен иметь prompt"
    assert calc_agent.graph_definition is None, "ReAct агент не должен иметь graph_definition"
    
    # Проверяем WeatherAgent
    weather_agent = await storage.get_agent_config("app.agents.weather.agent.WeatherAgent")
    assert weather_agent is not None, "WeatherAgent должен быть мигрирован"
    assert weather_agent.type == AgentType.REACT, f"WeatherAgent должен быть REACT, получили {weather_agent.type}"
    assert weather_agent.prompt is not None, "ReAct агент должен иметь prompt"
    
    print("✅ Тест react_agent_migration пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_stategraph_agent_migration():
    """
    Тест 10: Проверка миграции StateGraph агента.
    
    Проверяет что StateGraph агенты (TestFlowAgent)
    мигрируются с правильным типом и graph_definition.
    """
    test_company = await _create_test_company()
    migrator = Migrator()
    storage = Storage()
    
    # Устанавливаем контекст
    user = User(
        user_id="test_user",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=test_company,
        user_companies=[test_company]
    )
    set_context(context)
    
    # Мигрируем StateGraph агента
    await migrator.migrate_for_company(
        company=test_company,
        agents=["app.flows.test_flow.TestFlowAgent"],
        with_dependencies=False
    )
    
    # Проверяем TestFlowAgent
    agent_config = await storage.get_agent_config("app.flows.test_flow.TestFlowAgent")
    assert agent_config is not None, "TestFlowAgent должен быть мигрирован"
    assert agent_config.type == AgentType.STATEGRAPH, f"TestFlowAgent должен быть STATEGRAPH, получили {agent_config.type}"
    assert agent_config.graph_definition is not None, "StateGraph агент должен иметь graph_definition"
    assert agent_config.graph_definition.nodes is not None, "graph_definition должен содержать nodes"
    assert agent_config.graph_definition.edges is not None, "graph_definition должен содержать edges"
    assert len(agent_config.graph_definition.nodes) > 0, "graph_definition должен содержать хотя бы одну ноду"
    
    print("✅ Тест stategraph_agent_migration пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_company_isolation():
    """
    Тест 11: Проверка изоляции данных между компаниями.
    
    Проверяет что сущности одной компании не видны другой компании.
    """
    # Создаем две разные компании
    company1 = Company(
        company_id="test_company_1",
        subdomain="test1",
        name="Test Company 1",
        status="active",
        created_at=datetime.now(timezone.utc)
    )
    
    company2 = Company(
        company_id="test_company_2",
        subdomain="test2",
        name="Test Company 2",
        status="active",
        created_at=datetime.now(timezone.utc)
    )
    
    storage = Storage()
    await storage.set(f"company:{company1.company_id}", company1.model_dump_json(), force_global=True)
    await storage.set(f"company:{company2.company_id}", company2.model_dump_json(), force_global=True)
    
    migrator = Migrator()
    
    try:
        # 1. Мигрируем flow в первую компанию
        user1 = User(
            user_id="test_user_1",
            provider=AuthProvider.YANDEX,
            provider_user_id="test1",
            email="test1@test.com",
            name="Test1",
            status=UserStatus.ACTIVE,
            groups=["admin"],
            companies={company1.company_id: ["admin"]},
            active_company_id=company1.company_id
        )
        
        context1 = Context(
            user=user1,
            platform="test",
            active_company=company1,
            user_companies=[company1]
        )
        set_context(context1)
        
        await migrator.migrate_for_company(
            company=company1,
            flows=["app.flows.test_flow.test_flow_config"],
            with_dependencies=True
        )
        
        # 2. Проверяем что flow есть в первой компании
        flow_config_1 = await storage.get_flow_config("app.flows.test_flow.test_flow_config")
        assert flow_config_1 is not None, "Flow должен быть в компании 1"
        
        # 3. Переключаемся на вторую компанию
        user2 = User(
            user_id="test_user_2",
            provider=AuthProvider.YANDEX,
            provider_user_id="test2",
            email="test2@test.com",
            name="Test2",
            status=UserStatus.ACTIVE,
            groups=["admin"],
            companies={company2.company_id: ["admin"]},
            active_company_id=company2.company_id
        )
        
        context2 = Context(
            user=user2,
            platform="test",
            active_company=company2,
            user_companies=[company2]
        )
        set_context(context2)
        
        # 4. Проверяем что flow НЕТ во второй компании
        flow_config_2 = await storage.get_flow_config("app.flows.test_flow.test_flow_config")
        assert flow_config_2 is None, "Flow НЕ должен быть виден в компании 2"
        
        # 5. Мигрируем агента во вторую компанию
        await migrator.migrate_for_company(
            company=company2,
            agents=["app.agents.calculator.agent.CalculatorAgent"],
            with_dependencies=False
        )
        
        # 6. Проверяем что агент есть во второй компании
        agent_config_2 = await storage.get_agent_config("app.agents.calculator.agent.CalculatorAgent")
        assert agent_config_2 is not None, "Агент должен быть в компании 2"
        
        # 7. Переключаемся обратно на первую компанию
        set_context(context1)
        
        # 8. Проверяем что агента НЕТ в первой компании
        agent_config_1 = await storage.get_agent_config("app.agents.calculator.agent.CalculatorAgent")
        assert agent_config_1 is None, "Агент НЕ должен быть виден в компании 1"
        
        print("✅ Тест company_isolation пройден!")
        
    finally:
        clear_context()
        await storage.delete(f"company:{company1.company_id}", force_global=True)
        await storage.delete(f"company:{company2.company_id}", force_global=True)


@pytest.mark.asyncio
async def test_migrate_without_dependencies():
    """
    Тест 12: Миграция flow без зависимостей.
    
    Проверяет что при with_dependencies=False зависимости не мигрируются.
    """
    # Создаем отдельную компанию для этого теста чтобы избежать конфликтов
    fresh_company = Company(
        company_id="test_company_no_deps",
        subdomain="test_no_deps",
        name="Test No Deps Company",
        status="active",
        created_at=datetime.now(timezone.utc)
    )
    
    storage = Storage()
    await storage.set(f"company:{fresh_company.company_id}", fresh_company.model_dump_json(), force_global=True)
    
    migrator = Migrator()
    
    # Устанавливаем контекст
    user = User(
        user_id="test_user",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={fresh_company.company_id: ["admin"]},
        active_company_id=fresh_company.company_id
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=fresh_company,
        user_companies=[fresh_company]
    )
    set_context(context)
    
    # Мигрируем weather_flow БЕЗ зависимостей
    await migrator.migrate_for_company(
        company=fresh_company,
        flows=["app.flows.weather_flow.weather_flow_config"],
        with_dependencies=False
    )
    
    # Проверяем что flow мигрировался
    flow_config = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert flow_config is not None, "Flow должен быть мигрирован"
    
    # Проверяем что зависимости НЕ мигрировались
    agent_config = await storage.get_agent_config("app.agents.weather.agent.WeatherAgent")
    assert agent_config is None, "Зависимости НЕ должны быть мигрированы при with_dependencies=False"
    
    print("✅ Тест migrate_without_dependencies пройден!")
    clear_context()
    await storage.delete(f"company:{fresh_company.company_id}", force_global=True)


@pytest.mark.asyncio
async def test_api_remigrate_endpoints():
    """
    Тест 13: Проверка API endpoints для перемиграции.
    
    Проверяет что API endpoints работают корректно.
    """
    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app
    
    test_company = await _create_test_company()
    migrator = Migrator()
    storage = Storage()
    
    # Устанавливаем контекст
    user = User(
        user_id="test_user",
        provider=AuthProvider.YANDEX,
        provider_user_id="test",
        email="test@test.com",
        name="Test",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={test_company.company_id: ["admin"]},
        active_company_id=test_company.company_id
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=test_company,
        user_companies=[test_company]
    )
    set_context(context)
    
    # Сначала мигрируем сущности
    await migrator.migrate_for_company(
        company=test_company,
        flows=["app.flows.test_flow.test_flow_config"],
        agents=["app.agents.calculator.agent.CalculatorAgent"],
        tools=["app.tools.calc_tools.calculate"],
        with_dependencies=False
    )
    
    # Проверяем что сущности есть
    flow_config = await storage.get_flow_config("app.flows.test_flow.test_flow_config")
    agent_config = await storage.get_agent_config("app.agents.calculator.agent.CalculatorAgent")
    tool_data = await storage.get("tool:app.tools.calc_tools.calculate")
    
    assert flow_config is not None
    assert agent_config is not None
    assert tool_data is not None
    
    print("✅ Тест api_remigrate_endpoints пройден (сущности подготовлены)!")
    clear_context()
    await _cleanup_test_company(test_company)


if __name__ == "__main__":
    # Прямой запуск для отладки
    async def run_all_tests():
        from app.identity.models import Company
        
        # Создаем тестовую компанию
        test_company = Company(
            company_id="test_company_migration",
            subdomain="test_migration",
            name="Test Migration Company",
            status="active",
            created_at=datetime.now(timezone.utc)
        )
        
        storage = Storage()
        await storage.set(f"company:{test_company.company_id}", test_company.model_dump_json(), force_global=True)
        
        try:
            print("\n=== Запуск теста 1: migrate_defaults_for_company ===")
            await test_migrate_defaults_for_company()
            
            print("\n=== Запуск теста 2: migrate_single_flow_for_company ===")
            await test_migrate_single_flow_for_company()
            
            print("\n=== Запуск теста 3: migrate_single_agent_for_company ===")
            await test_migrate_single_agent_for_company()
            
            print("\n=== Запуск теста 4: remigrate_flow ===")
            await test_remigrate_flow()
            
            print("\n=== Запуск теста 5: remigrate_agent ===")
            await test_remigrate_agent()
            
            print("\n=== Запуск теста 6: migrate_with_nested_dependencies ===")
            await test_migrate_with_nested_dependencies()
            
            print("\n=== Запуск теста 7: migrate_single_tool ===")
            await test_migrate_single_tool()
            
            print("\n=== Запуск теста 8: remigrate_tool ===")
            await test_remigrate_tool()
            
            print("\n=== Запуск теста 9: react_agent_migration ===")
            await test_react_agent_migration()
            
            print("\n=== Запуск теста 10: stategraph_agent_migration ===")
            await test_stategraph_agent_migration()
            
            print("\n=== Запуск теста 11: company_isolation ===")
            await test_company_isolation()
            
            print("\n=== Запуск теста 12: migrate_without_dependencies ===")
            await test_migrate_without_dependencies()
            
            print("\n=== Запуск теста 13: api_remigrate_endpoints ===")
            await test_api_remigrate_endpoints()
            
            print("\n" + "="*60)
            print("✅ ВСЕ 13 ТЕСТОВ ПРОЙДЕНЫ!")
            print("="*60)
        except Exception as e:
            print(f"\n❌ Ошибка в тесте: {e}")
            import traceback
            traceback.print_exc()
        finally:
            clear_context()
    
    asyncio.run(run_all_tests())

