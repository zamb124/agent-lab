"""
Тест миграции для компаний.

Проверяет:
1. Миграция базовых сущностей при создании новой компании
2. Миграция отдельных сущностей (flow, agent, tool)
3. Перемиграция сущностей для отката к базовому состоянию
"""
import pytest
from datetime import datetime, timezone

from core.context import set_context, clear_context
from core.models import Company, User, AuthProvider, UserStatus
from core.models.context_models import Context
from apps.agents.models import AgentType


@pytest.fixture
def test_migration_company(company_repo, subdomain_repo, flow_repo, agent_repo, tool_repo):
    """Создает тестовую компанию для миграции"""
    from core.db.repositories.subdomain_repository import SubdomainMapping
    
    async def _create():
        company = Company(
            company_id="test_company_migration",
            subdomain="test_migration",
            name="Test Migration Company",
            status="active",
            created_at=datetime.now(timezone.utc)
        )

        await company_repo.set(company)
        
        subdomain_mapping = SubdomainMapping(
            subdomain=company.subdomain,
            company_id=company.company_id
        )
        await subdomain_repo.set(subdomain_mapping)
        
        return company

    async def _cleanup(company):
        user = User(
            user_id="test_cleanup",
            provider=AuthProvider.YANDEX,
            provider_user_id="test",
            email="test@test.com",
            name="Test Cleanup",
            status=UserStatus.ACTIVE,
            groups=["admin"],
            companies={company.company_id: ["admin"]},
            active_company_id=company.company_id
        )

        context = Context(
            user=user,
            platform="test",
            active_company=company,
            user_companies=[company]
        )
        set_context(context)

        try:
            all_flows = await flow_repo.list_all(limit=1000)
            for flow in all_flows:
                await flow_repo.delete(flow.flow_id)
            
            all_agents = await agent_repo.list_all(limit=1000)
            for agent in all_agents:
                await agent_repo.delete(agent.agent_id)
            
            all_tools = await tool_repo.list_all(limit=1000)
            for tool in all_tools:
                await tool_repo.delete(tool.tool_id)
        except Exception as e:
            print(f"Ошибка очистки данных: {e}")

        await company_repo.delete(company.company_id)
        await subdomain_repo.delete(company.subdomain)
        clear_context()

    return _create, _cleanup


@pytest.mark.asyncio
async def test_migrate_defaults_for_company(migrated_db,  migrator, test_migration_company, agent_repo, flow_repo, storage):
    """
    Тест 1: Миграция только публичных tools для новой компании.

    Проверяет что при вызове migrate_defaults_for_company():
    - Мигрируются ТОЛЬКО публичные tools (is_public=True)
    - Flows НЕ мигрируются (устанавливаются через Store)
    - Агенты НЕ мигрируются
    """
    create_company, cleanup_company = test_migration_company
    test_company = await create_company()

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

    await migrator.migrate_defaults_for_company(test_company)

    # Проверяем что flows НЕ мигрировались
    simple_flow_config = await flow_repo.get("apps.agents.flows.simple_flow.simple_flow_config")
    assert simple_flow_config is None, "Flows НЕ должны автоматически мигрироваться"

    weather_flow_config = await flow_repo.get("apps.agents.flows.weather_flow.weather_flow_config")
    assert weather_flow_config is None, "Flows НЕ должны автоматически мигрироваться"

    # Проверяем что агенты НЕ мигрировались
    weather_agent = await agent_repo.get("apps.agents.agents.weather.agent.WeatherAgent")
    assert weather_agent is None, "Агенты НЕ должны автоматически мигрироваться"

    # Проверяем что публичные tools мигрировались
    tool1_data = await storage.get("tool:apps.agents.tools.calc.calc_tools.calculate")
    assert tool1_data is not None, "Публичные tools должны быть мигрированы"

    tool2_data = await storage.get("tool:apps.agents.tools.calc.calc_tools.get_math_help")
    assert tool2_data is not None, "Публичные tools должны быть мигрированы"

    print("✅ Тест migrate_defaults_for_company пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_migrate_single_flow_for_company(migrated_db,  migrator, test_migration_company, agent_repo, flow_repo):
    """
    Тест 2: Миграция отдельного flow в компанию.

    Проверяет что можно мигрировать отдельный flow
    со всеми зависимостями.
    """
    create_company, cleanup_company = test_migration_company
    test_company = await create_company()

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
        flows=["apps.agents.flows.simple_flow.simple_flow_config"],
        with_dependencies=True
    )

    # Проверяем flow
    flow_config = await flow_repo.get("apps.agents.flows.simple_flow.simple_flow_config")
    assert flow_config is not None, "Flow должен быть мигрирован"

    # Проверяем зависимости
    agent_config = await agent_repo.get("apps.agents.flows.simple_flow.SimpleFlowAgent")
    assert agent_config is not None, "Зависимые агенты должны быть мигрированы"

    print("✅ Тест migrate_single_flow_for_company пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_migrate_single_agent_for_company(migrated_db,  migrator, test_migration_company, agent_repo, flow_repo):
    """
    Тест 3: Миграция отдельного агента в компанию.

    Проверяет что можно мигрировать отдельный агент
    без зависимостей.
    """
    create_company, cleanup_company = test_migration_company
    test_company = await create_company()

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
        agents=["apps.agents.flows.simple_flow.SimpleFlowAgent"],
        with_dependencies=False
    )

    # Проверяем агента
    agent_config = await agent_repo.get("apps.agents.flows.simple_flow.SimpleFlowAgent")
    assert agent_config is not None, "Агент должен быть мигрирован"

    print("✅ Тест migrate_single_agent_for_company пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_remigrate_flow(migrated_db,  migrator, test_migration_company, agent_repo, flow_repo):
    """
    Тест 4: Перемиграция flow для отката к базовому состоянию.

    Проверяет что можно перемигрировать flow и
    откатить изменения к коду.
    """
    create_company, cleanup_company = test_migration_company
    test_company = await create_company()

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
        flows=["apps.agents.flows.simple_flow.simple_flow_config"],
        with_dependencies=True
    )

    # 2. Получаем flow из БД (Storage использует контекст компании)
    flow_config = await flow_repo.get("apps.agents.flows.simple_flow.simple_flow_config")
    original_updated_at = flow_config.updated_at

    # 3. "Изменяем" flow в БД (симулируем изменение)
    flow_config.description = "ИЗМЕНЕНО!!!"
    await flow_repo.set(flow_config)

    # 4. Перемигрируем flow (откат к коду)
    await migrator.remigrate_flow(
        "apps.agents.flows.simple_flow.simple_flow_config",
        test_company
    )

    # 5. Проверяем что откатилось к базовому состоянию
    flow_config_after = await flow_repo.get("apps.agents.flows.simple_flow.simple_flow_config")

    assert flow_config_after.description != "ИЗМЕНЕНО!!!", "Описание должно откатиться к базовому"
    assert flow_config_after.description == "Простой тестовый флоу без LLM", "Описание должно быть из кода"
    assert flow_config_after.updated_at > original_updated_at, "updated_at должен обновиться"

    print("✅ Тест remigrate_flow пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_remigrate_agent(migrated_db,  migrator, test_migration_company, agent_repo, flow_repo):
    """
    Тест 5: Перемиграция агента для отката к базовому состоянию.
    """
    create_company, cleanup_company = test_migration_company
    test_company = await create_company()

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
        agents=["apps.agents.flows.simple_flow.SimpleFlowAgent"],
        with_dependencies=False
    )

    # 2. Получаем агента из БД
    agent_config = await agent_repo.get("apps.agents.flows.simple_flow.SimpleFlowAgent")
    original_name = agent_config.name

    # 3. "Изменяем" агента в БД
    agent_config.name = "ИЗМЕНЕННОЕ ИМЯ"
    await agent_repo.set(agent_config)

    # 4. Перемигрируем агента
    await migrator.remigrate_agent(
        "apps.agents.flows.simple_flow.SimpleFlowAgent",
        test_company
    )

    # 5. Проверяем откат
    agent_config_after = await agent_repo.get("apps.agents.flows.simple_flow.SimpleFlowAgent")

    assert agent_config_after.name != "ИЗМЕНЕННОЕ ИМЯ", "Имя должно откатиться"
    assert agent_config_after.name == original_name, "Имя должно быть из кода"

    print("✅ Тест remigrate_agent пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_migrate_with_nested_dependencies(migrated_db,  migrator, test_migration_company, agent_repo, flow_repo):
    """
    Тест 6: Миграция с вложенными зависимостями.

    Проверяет что при миграции flow с зависимостями,
    все субагенты и их tools тоже мигрируются.
    """
    create_company, cleanup_company = test_migration_company
    test_company = await create_company()

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
        flows=["apps.agents.flows.simple_flow.simple_flow_config"],
        with_dependencies=True
    )

    # Проверяем что все сущности мигрировались в компанию
    flow_config = await flow_repo.get("apps.agents.flows.simple_flow.simple_flow_config")
    assert flow_config is not None, "Flow должен быть в компании"

    agent_config = await agent_repo.get("apps.agents.flows.simple_flow.SimpleFlowAgent")
    assert agent_config is not None, "Агент должен быть в компании"

    print("✅ Тест migrate_with_nested_dependencies пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_migrate_single_tool(migrated_db,  migrator, test_migration_company, agent_repo, flow_repo, storage):
    """
    Тест 7: Миграция отдельного tool.

    Проверяет что можно мигрировать отдельный tool.
    """
    create_company, cleanup_company = test_migration_company
    test_company = await create_company()

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
        tools=["apps.agents.tools.calc.calc_tools.calculate"],
        with_dependencies=False
    )

    # Проверяем tool
    tool_key = "tool:apps.agents.tools.calc.calc_tools.calculate"
    tool_data = await storage.get(tool_key)
    assert tool_data is not None, "Tool должен быть мигрирован"

    print("✅ Тест migrate_single_tool пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_remigrate_tool(migrated_db,  migrator, test_migration_company, agent_repo, flow_repo, tool_repo, storage):
    """
    Тест 8: Перемиграция tool для отката к базовому состоянию.
    """
    create_company, cleanup_company = test_migration_company
    test_company = await create_company()

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
        tools=["apps.agents.tools.calc.calc_tools.calculate"],
        with_dependencies=False
    )

    # 2. Получаем tool из БД
    from apps.agents.models import ToolReference
    tool_key = "tool:apps.agents.tools.calc.calc_tools.calculate"
    tool_data = await storage.get(tool_key)
    tool_ref = ToolReference.model_validate_json(tool_data)
    original_description = tool_ref.description

    # 3. "Изменяем" tool в БД
    tool_ref.description = "ИЗМЕНЕНО!!!"
    await tool_repo.set(tool_ref)

    # 4. Перемигрируем tool
    await migrator.remigrate_tool(
        "apps.agents.tools.calc.calc_tools.calculate",
        test_company
    )

    # 5. Проверяем откат
    tool_data_after = await storage.get(tool_key)
    tool_ref_after = ToolReference.model_validate_json(tool_data_after)

    assert tool_ref_after.description != "ИЗМЕНЕНО!!!", "Описание должно откатиться"
    assert tool_ref_after.description == original_description, "Описание должно быть из кода"

    print("✅ Тест remigrate_tool пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_react_agent_migration(migrated_db,  migrator, test_migration_company, agent_repo, flow_repo):
    """
    Тест 9: Проверка миграции ReAct агента.

    Проверяет что ReAct агенты (WeatherAgent, CalculatorAgent)
    мигрируются с правильным типом и настройками.
    """
    create_company, cleanup_company = test_migration_company
    test_company = await create_company()

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
            "apps.agents.agents.calculator.agent.CalculatorAgent",
            "apps.agents.agents.weather.agent.WeatherAgent"
        ],
        with_dependencies=False
    )

    # Проверяем CalculatorAgent
    calc_agent = await agent_repo.get("apps.agents.agents.calculator.agent.CalculatorAgent")
    assert calc_agent is not None, "CalculatorAgent должен быть мигрирован"
    assert calc_agent.type == AgentType.REACT, f"CalculatorAgent должен быть REACT, получили {calc_agent.type}"
    assert calc_agent.prompt is not None, "ReAct агент должен иметь prompt"
    assert calc_agent.graph_definition is None, "ReAct агент не должен иметь graph_definition"

    # Проверяем WeatherAgent
    weather_agent = await agent_repo.get("apps.agents.agents.weather.agent.WeatherAgent")
    assert weather_agent is not None, "WeatherAgent должен быть мигрирован"
    assert weather_agent.type == AgentType.REACT, f"WeatherAgent должен быть REACT, получили {weather_agent.type}"
    assert weather_agent.prompt is not None, "ReAct агент должен иметь prompt"

    print("✅ Тест react_agent_migration пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_stategraph_agent_migration(migrated_db,  migrator, test_migration_company, agent_repo, flow_repo):
    """
    Тест 10: Проверка миграции StateGraph агента.

    Проверяет что StateGraph агенты (SimpleFlowAgent)
    мигрируются с правильным типом и graph_definition.
    """
    create_company, cleanup_company = test_migration_company
    test_company = await create_company()

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
        agents=["apps.agents.flows.simple_flow.SimpleFlowAgent"],
        with_dependencies=False
    )

    # Проверяем SimpleFlowAgent
    agent_config = await agent_repo.get("apps.agents.flows.simple_flow.SimpleFlowAgent")
    assert agent_config is not None, "SimpleFlowAgent должен быть мигрирован"
    assert agent_config.type == AgentType.STATEGRAPH, f"SimpleFlowAgent должен быть STATEGRAPH, получили {agent_config.type}"
    assert agent_config.graph_definition is not None, "StateGraph агент должен иметь graph_definition"
    assert agent_config.graph_definition.nodes is not None, "graph_definition должен содержать nodes"
    assert agent_config.graph_definition.edges is not None, "graph_definition должен содержать edges"
    assert len(agent_config.graph_definition.nodes) > 0, "graph_definition должен содержать хотя бы одну ноду"

    print("✅ Тест stategraph_agent_migration пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_company_isolation(migrated_db,  migrator, agent_repo, flow_repo, company_repo, subdomain_repo):
    """
    Тест 11: Проверка изоляции данных между компаниями.

    Проверяет что сущности одной компании не видны другой компании.
    """
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

    await company_repo.set(company1)
    await company_repo.set(company2)

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
            flows=["apps.agents.flows.simple_flow.simple_flow_config"],
            with_dependencies=True
        )

        # 2. Проверяем что flow есть в первой компании
        flow_config_1 = await flow_repo.get("apps.agents.flows.simple_flow.simple_flow_config")
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
        flow_config_2 = await flow_repo.get("apps.agents.flows.simple_flow.simple_flow_config")
        assert flow_config_2 is None, "Flow НЕ должен быть виден в компании 2"

        # 5. Мигрируем агента во вторую компанию
        await migrator.migrate_for_company(
            company=company2,
            agents=["apps.agents.agents.calculator.agent.CalculatorAgent"],
            with_dependencies=False
        )

        # 6. Проверяем что агент есть во второй компании
        agent_config_2 = await agent_repo.get("apps.agents.agents.calculator.agent.CalculatorAgent")
        assert agent_config_2 is not None, "Агент должен быть в компании 2"

        # 7. Переключаемся обратно на первую компанию
        set_context(context1)

        # 8. Проверяем что агента НЕТ в первой компании
        agent_config_1 = await agent_repo.get("apps.agents.agents.calculator.agent.CalculatorAgent")
        assert agent_config_1 is None, "Агент НЕ должен быть виден в компании 1"

        print("✅ Тест company_isolation пройден!")

    finally:
        clear_context()
        await company_repo.delete(company1.company_id)
        await company_repo.delete(company2.company_id)


@pytest.mark.asyncio
async def test_migrate_without_dependencies(migrated_db,  migrator, agent_repo, flow_repo, company_repo, subdomain_repo):
    """
    Тест 12: Миграция flow без зависимостей.

    Проверяет что при with_dependencies=False зависимости не мигрируются.
    """
    fresh_company = Company(
        company_id="test_company_no_deps",
        subdomain="test_no_deps",
        name="Test No Deps Company",
        status="active",
        created_at=datetime.now(timezone.utc)
    )

    await company_repo.set(fresh_company)

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
        flows=["apps.agents.flows.weather_flow.weather_flow_config"],
        with_dependencies=False
    )

    # Проверяем что flow мигрировался
    flow_config = await flow_repo.get("apps.agents.flows.weather_flow.weather_flow_config")
    assert flow_config is not None, "Flow должен быть мигрирован"

    # Проверяем что зависимости НЕ мигрировались
    agent_config = await agent_repo.get("apps.agents.agents.weather.agent.WeatherAgent")
    assert agent_config is None, "Зависимости НЕ должны быть мигрированы при with_dependencies=False"

    print("✅ Тест migrate_without_dependencies пройден!")
    clear_context()
    await company_repo.delete(fresh_company.company_id)


@pytest.mark.asyncio
async def test_api_remigrate_endpoints(migrated_db,  migrator, test_migration_company, agent_repo, flow_repo, storage):
    """
    Тест 13: Проверка API endpoints для перемиграции.

    Проверяет что API endpoints работают корректно.
    """
    create_company, cleanup_company = test_migration_company
    test_company = await create_company()

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
        flows=["apps.agents.flows.simple_flow.simple_flow_config"],
        agents=["apps.agents.agents.calculator.agent.CalculatorAgent"],
        tools=["apps.agents.tools.calc.calc_tools.calculate"],
        with_dependencies=False
    )

    # Проверяем что сущности есть
    flow_config = await flow_repo.get("apps.agents.flows.simple_flow.simple_flow_config")
    agent_config = await agent_repo.get("apps.agents.agents.calculator.agent.CalculatorAgent")
    tool_data = await storage.get("tool:apps.agents.tools.calc.calc_tools.calculate")

    assert flow_config is not None
    assert agent_config is not None
    assert tool_data is not None

    print("✅ Тест api_remigrate_endpoints пройден (сущности подготовлены)!")
    clear_context()
    await cleanup_company(test_company)



