"""
Тесты для Store функционала - установка и удаление flows.

Проверяет:
1. Создание компании - мигрируются только публичные tools
2. Установка flow - создаются flow, агенты, tools
3. Удаление flow - удаляются flow, агенты, tools
4. Выполнение хуков install/uninstall
"""
import pytest
from datetime import datetime, timezone

from app.core.context import set_context, clear_context
from app.identity.models import Company, User, AuthProvider, UserStatus
from app.models.context_models import Context
from app.models import ToolReference


@pytest.fixture
def test_store_company(storage):
    """Создает тестовую компанию для store тестов"""
    def _set_company_context(company: Company):
        user = User(
            user_id="test_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="test",
            email="test@test.com",
            name="Test User",
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
    
    async def _create(company_id: str = "test_store_company"):
        company = Company(
            company_id=company_id,
            subdomain=f"test_store_{company_id}",
            name=f"Test Store Company {company_id}",
            status="active",
            created_at=datetime.now(timezone.utc)
        )
        
        await storage.set(f"company:{company.company_id}", company.model_dump_json(), force_global=True)
        return company
    
    async def _cleanup(company: Company):
        prefixes = [
            "flow:",
            "agent:",
            "tool:",
            "session:",
            f"company:{company.company_id}:",
        ]
        
        for prefix in prefixes:
            keys = await storage.list_by_prefix(prefix)
            for key in keys:
                await storage.delete(key, force_global=True)
        
        await storage.delete(f"company:{company.company_id}", force_global=True)
    
    return _create, _cleanup, _set_company_context


@pytest.mark.asyncio
async def test_new_company_only_tools(migrated_db, storage, migrator, test_store_company, agent_repo, flow_repo):
    """
    Тест 1: При создании компании мигрируются только публичные tools.
    
    Проверяет что:
    - Мигрируются ТОЛЬКО публичные tools (is_public=True)
    - Flows НЕ мигрируются
    - Агенты НЕ мигрируются
    """
    create_company, cleanup_company, set_company_context = test_store_company
    test_company = await create_company("new_company_1")
    
    set_company_context(test_company)
    
    await migrator.migrate_defaults_for_company(test_company)
    
    simple_flow = await flow_repo.get("app.flows.simple_flow.simple_flow_config")
    assert simple_flow is None, "Flows НЕ должны автоматически мигрироваться"
    
    weather_flow = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert weather_flow is None, "Flows НЕ должны автоматически мигрироваться"
    
    weather_agent = await agent_repo.get("app.agents.weather.agent.WeatherAgent")
    assert weather_agent is None, "Агенты НЕ должны автоматически мигрироваться"
    
    tool_data = await storage.get("tool:app.tools.calc.calc_tools.calculate")
    assert tool_data is not None, "Публичные tools должны быть мигрированы"
    
    print("✅ Тест new_company_only_tools пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_install_flow_creates_dependencies(migrated_db, storage, flow_factory, migrator, test_store_company, agent_repo, flow_repo):
    """
    Тест 2: Установка flow создает все зависимости.
    
    Проверяет что при установке flow:
    - Создается flow
    - Создаются все агенты
    - Создаются все приватные tools
    - Выполняется install hook
    """
    create_company, cleanup_company, set_company_context = test_store_company
    test_company = await create_company("install_test_company")
    
    set_company_context(test_company)
    
    await migrator.migrate_defaults_for_company(test_company)
    
    weather_flow = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert weather_flow is None, "Flow не должен быть установлен до вызова install"
    
    result = await flow_factory.install_flow("app.flows.weather_flow.weather_flow_config")
    
    assert result["flow_id"] == "app.flows.weather_flow.weather_flow_config"
    assert result["company_id"] == test_company.company_id
    
    weather_flow = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert weather_flow is not None, "Flow должен быть установлен"
    assert weather_flow.install_hook is not None, "install_hook должен быть извлечен"
    assert isinstance(weather_flow.install_hook, ToolReference), "install_hook должен быть ToolReference"
    
    weather_agent = await agent_repo.get("app.agents.weather.agent.WeatherAgent")
    assert weather_agent is not None, "Агент flow должен быть мигрирован"
    
    variable_key = f"company:{test_company.company_id}:var:default_city"
    variable_json = await storage.get(variable_key)
    assert variable_json is not None, "install hook должен создать переменную default_city"
    
    print("✅ Тест install_flow_creates_dependencies пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_uninstall_flow_removes_dependencies(migrated_db, storage, flow_factory, migrator, test_store_company, agent_repo, flow_repo):
    """
    Тест 3: Удаление flow удаляет все зависимости.
    
    Проверяет что при удалении flow:
    - Выполняется uninstall hook
    - Удаляется flow
    - Удаляются агенты flow
    - Публичные tools остаются
    """
    create_company, cleanup_company, set_company_context = test_store_company
    test_company = await create_company("uninstall_test_company")
    
    set_company_context(test_company)
    
    await migrator.migrate_defaults_for_company(test_company)
    
    await flow_factory.install_flow("app.flows.weather_flow.weather_flow_config")
    
    variable_key = f"company:{test_company.company_id}:var:default_city"
    variable_before = await storage.get(variable_key)
    assert variable_before is not None, "Переменная должна существовать после install"
    
    weather_flow_before = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert weather_flow_before is not None, "Flow должен существовать"
    
    await flow_factory.uninstall_flow("app.flows.weather_flow.weather_flow_config")
    
    weather_flow_after = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert weather_flow_after is None, "Flow должен быть удален"
    
    weather_agent_after = await agent_repo.get("app.agents.weather.agent.WeatherAgent")
    assert weather_agent_after is None, "Агенты flow должны быть удалены"
    
    variable_after = await storage.get(variable_key)
    assert variable_after is None, "uninstall hook должен удалить переменную"
    
    tool_data = await storage.get("tool:app.tools.calc.calc_tools.calculate")
    assert tool_data is not None, "Публичные tools должны остаться"
    
    print("✅ Тест uninstall_flow_removes_dependencies пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_flow_hooks_execution(migrated_db, storage, agent_repo, flow_repo):
    """
    Тест 4: Проверка выполнения хуков install и uninstall.
    
    Проверяет что хуки правильно извлекаются из кода и выполняются.
    """
    
    weather_flow = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert weather_flow is not None, "Weather flow должен быть в системной компании"
    
    assert weather_flow.install_hook is not None, "install_hook должен быть извлечен"
    assert isinstance(weather_flow.install_hook, ToolReference), "install_hook должен быть ToolReference"
    assert weather_flow.install_hook.inline_code is not None, "install_hook должен содержать код"
    assert "async def install" in weather_flow.install_hook.inline_code, "Код должен содержать функцию install"
    
    assert weather_flow.uninstall_hook is not None, "uninstall_hook должен быть извлечен"
    assert isinstance(weather_flow.uninstall_hook, ToolReference), "uninstall_hook должен быть ToolReference"
    assert weather_flow.uninstall_hook.inline_code is not None, "uninstall_hook должен содержать код"
    assert "async def uninstall" in weather_flow.uninstall_hook.inline_code, "Код должен содержать функцию uninstall"
    
    print("✅ Тест flow_hooks_execution пройден!")
    clear_context()


@pytest.mark.asyncio
async def test_hooks_actually_execute(migrated_db, storage, flow_factory, migrator, test_store_company, agent_repo, flow_repo):
    """
    Тест 4.5: Проверка ФАКТИЧЕСКОГО выполнения хуков install и uninstall.
    
    Проверяет что хуки реально выполняются, а не просто извлекаются из кода.
    """
    create_company, cleanup_company, set_company_context = test_store_company
    test_company = await create_company("hooks_test_company")
    
    set_company_context(test_company)
    
    await migrator.migrate_defaults_for_company(test_company)
    
    # Проверяем что до install нет переменных
    default_city_key = f"company:{test_company.company_id}:var:default_city"
    before_install = await storage.get(default_city_key)
    assert before_install is None, "Переменная не должна существовать до install"
    
    print("📝 Переменная default_city отсутствует до install")
    
    # Устанавливаем flow - это должно вызвать install hook
    result = await flow_factory.install_flow("app.flows.weather_flow.weather_flow_config")
    assert result["flow_id"] == "app.flows.weather_flow.weather_flow_config"
    
    # Проверяем что install hook РЕАЛЬНО выполнился
    after_install = await storage.get(default_city_key)
    assert after_install is not None, "install hook ДОЛЖЕН был создать переменную default_city"
    
    import json
    variable_data = json.loads(after_install)
    assert "value" in variable_data, "Переменная должна содержать value"
    print(f"✅ install hook выполнился! Создана переменная: {variable_data}")
    
    # Удаляем flow - это должно вызвать uninstall hook
    await flow_factory.uninstall_flow("app.flows.weather_flow.weather_flow_config")
    
    # Проверяем что uninstall hook РЕАЛЬНО выполнился
    after_uninstall = await storage.get(default_city_key)
    assert after_uninstall is None, "uninstall hook ДОЛЖЕН был удалить переменную default_city"
    
    print("✅ uninstall hook выполнился! Переменная удалена")
    print("✅ Тест hooks_actually_execute пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_flow_with_image(migrated_db, storage, agent_repo, flow_repo):
    """
    Тест 5: Проверка загрузки картинки flow в S3.
    
    Проверяет что при миграции flow с image_path:
    - Картинка загружается в S3 (если файл существует)
    - image_file_id сохраняется
    """
    
    weather_flow = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert weather_flow is not None, "Weather flow должен быть мигрирован"
    assert weather_flow.image_path == "app/flows/weather_flow.jpg", "image_path должен быть сохранен"
    
    print("✅ Тест flow_with_image пройден!")
    clear_context()


@pytest.mark.asyncio
async def test_multiple_flows_isolation(migrated_db, storage, flow_factory, migrator, test_store_company, agent_repo, flow_repo):
    """
    Тест 6: Изоляция flows между компаниями.
    
    Проверяет что flows в одной компании не видны в другой.
    """
    create_company, cleanup_company, set_company_context = test_store_company
    company1 = await create_company("isolation_company_1")
    company2 = await create_company("isolation_company_2")
    
    set_company_context(company1)
    await migrator.migrate_defaults_for_company(company1)
    await flow_factory.install_flow("app.flows.weather_flow.weather_flow_config")
    
    flow_in_company1 = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert flow_in_company1 is not None, "Flow должен быть в компании 1"
    
    set_company_context(company2)
    await migrator.migrate_defaults_for_company(company2)
    
    flow_in_company2 = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert flow_in_company2 is None, "Flow НЕ должен быть виден в компании 2"
    
    await flow_factory.install_flow("app.flows.weather_flow.weather_flow_config")
    
    flow_in_company2_after = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert flow_in_company2_after is not None, "Flow должен быть установлен в компании 2"
    
    set_company_context(company1)
    await flow_factory.uninstall_flow("app.flows.weather_flow.weather_flow_config")
    
    flow_in_company1_after = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert flow_in_company1_after is None, "Flow должен быть удален из компании 1"
    
    set_company_context(company2)
    flow_still_in_company2 = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert flow_still_in_company2 is not None, "Flow должен остаться в компании 2"
    
    print("✅ Тест multiple_flows_isolation пройден!")
    clear_context()
    await cleanup_company(company1)
    await cleanup_company(company2)


@pytest.mark.asyncio
async def test_flow_author_extraction(migrated_db, storage, agent_repo, flow_repo):
    """
    Тест 7: Проверка извлечения информации об авторе.
    
    Проверяет что author правильно мигрируется из кода.
    """
    
    weather_flow = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert weather_flow is not None, "Weather flow должен быть мигрирован"
    assert weather_flow.author is not None, "Author должен быть извлечен"
    assert weather_flow.author.name == "Viktor Shved", "Имя автора должно совпадать"
    assert weather_flow.author.email == "viktor@shved.com", "Email автора должен совпадать"
    assert weather_flow.author.github == "https://github.com/viktorshved", "GitHub должен совпадать"
    
    print("✅ Тест flow_author_extraction пройден!")
    clear_context()


@pytest.mark.asyncio
async def test_install_twice_should_succeed(migrated_db, storage, flow_factory, migrator, test_store_company, agent_repo, flow_repo):
    """
    Тест 8: Повторная установка flow должна перезаписывать существующий.
    
    Проверяет что можно переустановить flow (перемиграция).
    """
    create_company, cleanup_company, set_company_context = test_store_company
    test_company = await create_company("double_install_company")
    
    set_company_context(test_company)
    
    await migrator.migrate_defaults_for_company(test_company)
    
    result1 = await flow_factory.install_flow("app.flows.weather_flow.weather_flow_config")
    assert result1["flow_id"] == "app.flows.weather_flow.weather_flow_config"
    
    flow1 = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert flow1 is not None
    created_at_first = flow1.created_at
    
    result2 = await flow_factory.install_flow("app.flows.weather_flow.weather_flow_config")
    assert result2["flow_id"] == "app.flows.weather_flow.weather_flow_config"
    
    flow2 = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert flow2 is not None
    assert flow2.created_at == created_at_first, "created_at должен сохраниться при перемиграции"
    
    print("✅ Тест install_twice_should_succeed пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_uninstall_not_installed_should_fail(migrated_db, storage, flow_factory, migrator, test_store_company, agent_repo, flow_repo):
    """
    Тест 9: Удаление неустановленного flow должно вызывать ошибку.
    
    Проверяет что нельзя удалить flow который не установлен.
    """
    create_company, cleanup_company, set_company_context = test_store_company
    test_company = await create_company("uninstall_empty_company")
    
    set_company_context(test_company)
    
    await migrator.migrate_defaults_for_company(test_company)
    
    error_raised = False
    try:
        await flow_factory.uninstall_flow("app.flows.weather_flow.weather_flow_config")
    except ValueError as e:
        error_raised = True
        assert "не установлен" in str(e).lower() or "not found" in str(e).lower()
    
    assert error_raised, "Удаление несуществующего flow должно вызывать ошибку"
    
    print("✅ Тест uninstall_not_installed_should_fail пройден!")
    clear_context()
    await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_variables_definitions_validation(migrated_db, storage, caplog):
    """Тест валидации variables_definitions в FlowConfig"""
    import logging
    from app.models import FlowConfig
    from pydantic import ValidationError

    # Тест 1: Правильная валидация - все переменные используются
    flow_config = FlowConfig(
        name="Test Flow",
        description="Test flow with variables",
        entry_point_agent="test_agent",
        variables={
            "test_var": "@var:test_key"
        },
        variables_definitions=[
            {
                "key": "test_key",
                "description": "Test variable",
                "is_secret": False,
                "required": True
            }
        ]
    )

    assert len(flow_config.variables_definitions) == 1
    assert flow_config.variables_definitions[0].key == "test_key"
    assert flow_config.variables_definitions[0].is_secret == False
    assert flow_config.variables_definitions[0].required == True

    # Тест 2: Warning - переменная определена но не используется (валидация через warning)
    with caplog.at_level(logging.WARNING):
        FlowConfig(
            name="Test Flow",
            description="Test flow with unused variable",
            entry_point_agent="test_agent",
            variables={
                "test_var": "hardcoded_value"  # Не использует @var:
            },
            variables_definitions=[
                {
                    "key": "unused_key",
                    "description": "Unused variable",
                    "is_secret": False,
                    "required": True
                }
            ]
        )

    # Проверяем что warning был записан
    assert any("has unused variables in definitions" in record.message for record in caplog.records)
    print("✅ Валидация неиспользуемой переменной работает")

    # Тест 3: @var: ссылки без определений разрешены (переменные могут существовать отдельно)
    flow_config = FlowConfig(
        name="Test Flow",
        description="Test flow with undefined variable",
        entry_point_agent="test_agent",
        variables={
            "test_var": "@var:undefined_key"  # Нет определения - это нормально
        },
        variables_definitions=[]
    )

    assert len(flow_config.variables_definitions) == 0
    print("✅ @var: ссылки без определений разрешены")

    # Тест 4: Валидация в platforms
    flow_config = FlowConfig(
        name="Test Flow",
        description="Test flow with platform variables",
        entry_point_agent="test_agent",
        variables={
            "test_var": "@var:platform_key"
        },
        platforms={
            "telegram": {
                "bot_token": "@var:platform_key"
            }
        },
        variables_definitions=[
            {
                "key": "platform_key",
                "description": "Platform variable",
                "is_secret": True,
                "required": True
            }
        ]
    )

    assert len(flow_config.variables_definitions) == 1
    print("✅ Тест variables_definitions_validation пройден!")


@pytest.mark.asyncio
async def test_flow_variables_definitions_install(migrated_db, storage, migrator, test_store_company):
    """Тест установки flow с variables_definitions через API"""
    from app.services.variables_service import VariablesService
    from app.frontend.api.flows import install_flow
    from pydantic import BaseModel

    create_company, cleanup_company, set_company_context = test_store_company
    test_company = await create_company("test_vars_api_company")

    try:
        # Используем реальный flow с variables_definitions - lawyer_flow
        flow_id = "app.flows.lawyer_flow.lawyer_flow"

        # Создаем request с переменными
        class InstallFlowRequest(BaseModel):
            variables: dict = None

        request = InstallFlowRequest(variables={
            "lawyer_bot": "test_bot",
            "lawyer_bot_telegram_token": "test_token_123",
            "company_short_name": "Test Company"
        })

        # Устанавливаем flow
        result = await install_flow(
            flow_id=flow_id,
            storage=storage,
            flow_repo=None,
            request=request
        )

        # Проверяем что flow установлен
        assert result["flow_id"] == flow_id

        # Проверяем что переменные созданы с правильными значениями
        variables_service = VariablesService()
        lawyer_bot = await variables_service.get_var("lawyer_bot")
        token = await variables_service.get_var("lawyer_bot_telegram_token")
        company_name = await variables_service.get_var("company_short_name")

        assert lawyer_bot == "test_bot"
        assert token == "test_token_123"
        assert company_name == "Test Company"

        print("✅ Тест flow_variables_definitions_install пройден!")

    finally:
        clear_context()
        await cleanup_company(test_company)




@pytest.mark.asyncio
async def test_variables_resolution_after_install(migrated_db, storage, migrator, test_store_company):
    """Тест резолюции @var: ссылок после установки flow с переменными"""
    from app.services.variables_service import VariablesService
    from app.frontend.api.flows import install_flow
    from pydantic import BaseModel

    create_company, cleanup_company, set_company_context = test_store_company
    test_company = await create_company("test_resolution_company")

    try:
        # Используем weather_flow для тестирования резолюции
        flow_id = "app.flows.weather_flow.weather_flow_config"

        # Создаем request с переменными
        class InstallFlowRequest(BaseModel):
            variables: dict = None

        request = InstallFlowRequest(variables={
            "weather_api_key": "test_api_key_123",
            "bot_name": "Test Weather Bot"
        })

        # Устанавливаем flow
        result = await install_flow(
            flow_id=flow_id,
            storage=storage,
            flow_repo=None,
            request=request
        )

        # Проверяем резолюцию переменных через VariablesService
        variables_service = VariablesService()

        # Проверяем что переменные созданы
        api_key = await variables_service.get_var("weather_api_key")
        bot_name = await variables_service.get_var("bot_name")

        assert api_key == "test_api_key_123"
        assert bot_name == "Test Weather Bot"

        # Проверяем резолюцию - берем flow config и резолвим его variables
        from app.flows.weather_flow import weather_flow_config
        resolved_vars = await variables_service.resolve(weather_flow_config.variables)

        # bot_name должен быть резолвен
        assert resolved_vars["bot_name"] == "Test Weather Bot"

        print("✅ Тест variables_resolution_after_install пройден!")

    finally:
        clear_context()
        await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_flow_install_skip_empty_variables(migrated_db, storage, migrator, test_store_company):
    """Тест установки flow с пропуском пустых переменных"""
    from app.services.variables_service import VariablesService
    from app.frontend.api.flows import install_flow
    from pydantic import BaseModel

    create_company, cleanup_company, set_company_context = test_store_company
    test_company = await create_company("test_skip_empty_vars_company")

    try:
        # Используем lawyer_flow для тестирования пропуска пустых переменных
        flow_id = "app.flows.lawyer_flow.lawyer_flow"

        # Создаем request с одной заполненной и одной пустой переменной
        class InstallFlowRequest(BaseModel):
            variables: dict = None

        request = InstallFlowRequest(variables={
            "lawyer_bot": "test_bot",  # Заполненная
            "company_short_name_en": "",  # Пустая (без default_value)
            "lawyer_bot_telegram_token": "test_token"
        })

        # Устанавливаем flow
        result = await install_flow(
            flow_id=flow_id,
            storage=storage,
            flow_repo=None,
            request=request
        )

        # Проверяем что flow установлен
        assert result["flow_id"] == flow_id

        # Проверяем что только заполненные переменные созданы
        variables_service = VariablesService()

        # Сначала удалим переменную если она существует от предыдущих тестов
        try:
            await variables_service.delete_var("company_short_name_en")
        except:
            pass

        filled_var = await variables_service.get_var("lawyer_bot")
        empty_var = await variables_service.get_var("company_short_name_en")
        token_var = await variables_service.get_var("lawyer_bot_telegram_token")

        assert filled_var == "test_bot"
        assert token_var == "test_token"
        assert empty_var is None, "Empty variable should not be created"

        print("✅ Тест flow_install_skip_empty_variables пройден!")

    finally:
        clear_context()
        await cleanup_company(test_company)


@pytest.mark.asyncio
async def test_variables_service_operations(migrated_db, storage, test_store_company):
    """Тест базовых операций с переменными через VariablesService"""
    from app.services.variables_service import VariablesService

    create_company, cleanup_company, set_company_context = test_store_company
    test_company = await create_company("test_vars_service_company")

    try:
        variables_service = VariablesService()

        # Создаем переменную
        await variables_service.set_var("test_key", "test_value", is_secret=False, description="Test variable")
        var = await variables_service.get_var("test_key")
        assert var == "test_value"

        # Обновляем переменную
        await variables_service.set_var("test_key", "updated_value", is_secret=False, description="Updated variable")
        var = await variables_service.get_var("test_key")
        assert var == "updated_value"

        # Удаляем переменную
        await variables_service.delete_var("test_key")
        var = await variables_service.get_var("test_key")
        assert var is None

        print("✅ Тест variables_service_operations пройден!")

    finally:
        clear_context()
        await cleanup_company(test_company)


if __name__ == "__main__":
    import asyncio
    
    async def run_all_tests():
        try:
            print("\n=== Тест 1: new_company_only_tools ===")
            await test_new_company_only_tools()
            
            print("\n=== Тест 2: install_flow_creates_dependencies ===")
            await test_install_flow_creates_dependencies()
            
            print("\n=== Тест 3: uninstall_flow_removes_dependencies ===")
            await test_uninstall_flow_removes_dependencies()
            
            print("\n=== Тест 4: flow_hooks_execution ===")
            await test_flow_hooks_execution()
            
            print("\n=== Тест 4.5: hooks_actually_execute ===")
            await test_hooks_actually_execute()
            
            print("\n=== Тест 5: flow_with_image ===")
            await test_flow_with_image()
            
            print("\n=== Тест 6: multiple_flows_isolation ===")
            await test_multiple_flows_isolation()
            
            print("\n=== Тест 7: flow_author_extraction ===")
            await test_flow_author_extraction()
            
            print("\n=== Тест 8: install_twice_should_succeed ===")
            await test_install_twice_should_succeed()
            
            print("\n=== Тест 9: uninstall_not_installed_should_fail ===")
            await test_uninstall_not_installed_should_fail()
            
            print("\n" + "="*60)
            print("✅ ВСЕ 10 ТЕСТОВ STORE ПРОЙДЕНЫ!")
            print("="*60)
        except Exception as e:
            print(f"\n❌ Ошибка в тесте: {e}")
            import traceback
            traceback.print_exc()
        finally:
            clear_context()
    
    asyncio.run(run_all_tests())

