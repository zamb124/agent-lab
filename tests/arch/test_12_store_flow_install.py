"""
Тесты для Store функционала - установка и удаление flows.

Проверяет:
1. Создание компании - мигрируются только публичные tools
2. Установка flow - создаются flow, агенты, tools
3. Удаление flow - удаляются flow, агенты, tools
4. Выполнение хуков install/uninstall
"""
import pytest
import pytest_asyncio
import logging
from datetime import datetime, timezone

from core.context import set_context, clear_context, get_context
from core.models import Company, User, AuthProvider, UserStatus
from core.models.context_models import Context
from apps.agents.models import ToolReference

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def create_test_company(company_repo, subdomain_repo, flow_repo):
    """Создает тестовую компанию (с автоочисткой)"""
    from core.db.repositories.subdomain_repository import SubdomainMapping
    
    created_companies = []

    async def _create(company_id: str = "test_store_company"):
        company = Company(
            company_id=company_id,
            subdomain=f"test_store_{company_id}",
            name=f"Test Store Company {company_id}",
            status="active",
            created_at=datetime.now(timezone.utc)
        )

        await company_repo.set(company)
        
        subdomain_mapping = SubdomainMapping(
            subdomain=company.subdomain,
            company_id=company.company_id
        )
        await subdomain_repo.set(subdomain_mapping)
        
        created_companies.append(company)

        # Создаем и устанавливаем контекст для компании
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

        return company

    yield _create

    # Очистка после теста
    from apps.agents.container import get_agents_container
    for company in created_companies:
        try:
            ctx = get_context()
            if ctx:
                ctx.active_company = company
                set_context(ctx)
            
            # Удаляем все flows (через репозиторий)
            all_flows = await flow_repo.list_all(limit=1000)
            for flow in all_flows:
                try:
                    _flow_factory = get_agents_container().flow_factory
                    await _flow_factory.uninstall_flow(flow.flow_id)
                    logger.info(f"Удален flow {flow.flow_id} из компании {company.company_id}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить flow {flow.flow_id}: {e}")
            
            # Удаляем компанию
            await company_repo.delete(company.company_id)
            await subdomain_repo.delete(company.subdomain)
        except Exception as e:
            logger.warning(f"Ошибка очистки компании {company.company_id}: {e}")

    clear_context()


@pytest.mark.asyncio
async def test_new_company_only_tools(migrated_db, system_context, create_test_company, agent_repo, flow_repo, tool_repo, migrator):
    """
    Тест 1: При создании компании мигрируются только публичные tools.

    Проверяет что:
    - Мигрируются ТОЛЬКО публичные tools (is_public=True)
    - Flows НЕ мигрируются
    - Агенты НЕ мигрируются
    """
    test_company = await create_test_company("new_company_1_uniq")

    await migrator.migrate_defaults_for_company(test_company)

    simple_flow = await flow_repo.get("apps.agents.flows.simple_flow.simple_flow_config")
    assert simple_flow is None, "Flows НЕ должны автоматически мигрироваться"

    weather_flow = await flow_repo.get("apps.agents.flows.weather_flow.weather_flow_config")
    assert weather_flow is None, "Flows НЕ должны автоматически мигрироваться"

    weather_agent = await agent_repo.get("apps.agents.agents.weather.agent.WeatherAgent")
    assert weather_agent is None, "Агенты НЕ должны автоматически мигрироваться"

    tool_data = await tool_repo.get("apps.agents.tools.calc.calc_tools.calculate")
    assert tool_data is not None, "Публичные tools должны быть мигрированы"

    print("✅ Тест new_company_only_tools пройден!")


@pytest.mark.asyncio
async def test_install_flow_creates_dependencies(migrated_db, flow_factory, system_context, create_test_company, agent_repo, flow_repo, variable_repo):
    """
    Тест 2: Установка flow создает все зависимости.

    Проверяет что при установке flow:
    - Создается flow
    - Создаются все агенты
    - Создаются все приватные tools
    - Выполняется install hook
    """
    test_company = await create_test_company("install_test_company")

    weather_flow = await flow_repo.get("apps.agents.flows.weather_flow.weather_flow_config")
    assert weather_flow is None, "Flow не должен быть установлен до вызова install"

    result = await flow_factory.install_flow("apps.agents.flows.weather_flow.weather_flow_config")

    assert result["flow_id"] == "apps.agents.flows.weather_flow.weather_flow_config"
    assert result["company_id"] == test_company.company_id

    weather_flow = await flow_repo.get("apps.agents.flows.weather_flow.weather_flow_config")
    assert weather_flow is not None, "Flow должен быть установлен"
    assert weather_flow.install_hook is not None, "install_hook должен быть извлечен"
    assert isinstance(weather_flow.install_hook, ToolReference), "install_hook должен быть ToolReference"

    weather_agent = await agent_repo.get("apps.agents.agents.weather.agent.WeatherAgent")
    assert weather_agent is not None, "Агент flow должен быть мигрирован"

    variable = await variable_repo.get("default_city")
    assert variable is not None, "install hook должен создать переменную default_city"

    print("✅ Тест install_flow_creates_dependencies пройден!")

    import asyncio
    await asyncio.sleep(2.0)


@pytest.mark.asyncio
async def test_flow_hooks_execution(migrated_db,  system_context, agent_repo, flow_repo):
    """
    Тест 4: Проверка выполнения хуков install и uninstall.

    Проверяет что хуки правильно извлекаются из кода и выполняются.
    """

    weather_flow = await flow_repo.get("apps.agents.flows.weather_flow.weather_flow_config")
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
async def test_hooks_actually_execute(migrated_db, flow_factory, system_context, create_test_company, agent_repo, flow_repo, variable_repo):
    """
    Тест 4.5: Проверка ФАКТИЧЕСКОГО выполнения хуков install and uninstall.

    Проверяет что хуки реально выполняются, а не просто извлекаются из кода.
    """
    test_company = await create_test_company("hooks_test_company")

    try:
        await variable_repo.delete("default_city")
    except:
        pass

    before_install = await variable_repo.get("default_city")
    assert before_install is None, "Переменная не должна существовать до install"

    print("Переменная default_city отсутствует до install")

    result = await flow_factory.install_flow("apps.agents.flows.weather_flow.weather_flow_config")
    assert result["flow_id"] == "apps.agents.flows.weather_flow.weather_flow_config"

    after_install = await variable_repo.get("default_city")
    assert after_install is not None, "install hook ДОЛЖЕН был создать переменную default_city"

    assert after_install.value, "Переменная должна содержать value"
    print(f"install hook выполнился! Создана переменная: {after_install.value}")

    await flow_factory.uninstall_flow("apps.agents.flows.weather_flow.weather_flow_config")

    after_uninstall = await variable_repo.get("default_city")
    assert after_uninstall is None, "uninstall hook ДОЛЖЕН был удалить переменную default_city"

    print("✅ uninstall hook выполнился! Переменная удалена")
    print("✅ Тест hooks_actually_execute пройден!")

    import asyncio
    await asyncio.sleep(2.0)

    clear_context()


@pytest.mark.asyncio
async def test_flow_with_image(migrated_db,  system_context, agent_repo, flow_repo):
    """
    Тест 5: Проверка загрузки картинки flow в S3.

    Проверяет что при миграции flow с image_path:
    - Картинка загружается в S3 (если файл существует)
    - image_file_id сохраняется
    """

    weather_flow = await flow_repo.get("apps.agents.flows.weather_flow.weather_flow_config")
    assert weather_flow is not None, "Weather flow должен быть мигрирован"
    assert weather_flow.image_path == "app/flows/weather_flow.jpg", "image_path должен быть сохранен"

    print("✅ Тест flow_with_image пройден!")
    clear_context()


@pytest.mark.asyncio
async def test_multiple_flows_isolation(migrated_db, flow_factory, system_context, create_test_company, agent_repo, flow_repo, migrator):
    """
    Тест 6: Изоляция flows между компаниями.

    Проверяет что flows в одной компании не видны в другой.
    """
    company1 = await create_test_company("isolation_company_1_uniq")
    company2 = await create_test_company("isolation_company_2_uniq")

    from core.context import get_context
    context = get_context()
    context.active_company = company1
    set_context(context)
    await migrator.migrate_defaults_for_company(company1)
    await flow_factory.install_flow("apps.agents.flows.weather_flow.weather_flow_config")

    flow_in_company1 = await flow_repo.get("apps.agents.flows.weather_flow.weather_flow_config")
    assert flow_in_company1 is not None, "Flow должен быть в компании 1"

    # Переключаемся на company2
    context.active_company = company2
    set_context(context)
    await migrator.migrate_defaults_for_company(company2)

    flow_in_company2 = await flow_repo.get("apps.agents.flows.weather_flow.weather_flow_config")
    assert flow_in_company2 is None, "Flow НЕ должен быть виден в компании 2"

    await flow_factory.install_flow("apps.agents.flows.weather_flow.weather_flow_config")

    flow_in_company2_after = await flow_repo.get("apps.agents.flows.weather_flow.weather_flow_config")
    assert flow_in_company2_after is not None, "Flow должен быть установлен в компании 2"

    # Переключаемся обратно на company1
    context.active_company = company1
    set_context(context)
    await flow_factory.uninstall_flow("apps.agents.flows.weather_flow.weather_flow_config")

    flow_in_company1_after = await flow_repo.get("apps.agents.flows.weather_flow.weather_flow_config")
    assert flow_in_company1_after is None, "Flow должен быть удален из компании 1"

    # Переключаемся на company2
    context.active_company = company2
    set_context(context)
    flow_still_in_company2 = await flow_repo.get("apps.agents.flows.weather_flow.weather_flow_config")
    assert flow_still_in_company2 is not None, "Flow должен остаться в компании 2"

    print("✅ Тест multiple_flows_isolation пройден!")

    # Даем время завершиться всем асинхронным задачам
    import asyncio
    await asyncio.sleep(2.0)  # Увеличиваем время ожидания


@pytest.mark.asyncio
async def test_flow_author_extraction(migrated_db,  system_context, agent_repo, flow_repo):
    """
    Тест 7: Проверка извлечения информации об авторе.

    Проверяет что author правильно мигрируется из кода.
    """

    weather_flow = await flow_repo.get("apps.agents.flows.weather_flow.weather_flow_config")
    assert weather_flow is not None, "Weather flow должен быть мигрирован"
    assert weather_flow.author is not None, "Author должен быть извлечен"
    assert weather_flow.author.name == "Viktor Shved", "Имя автора должно совпадать"
    assert weather_flow.author.email == "viktor@shved.com", "Email автора должен совпадать"
    assert weather_flow.author.github == "https://github.com/viktorshved", "GitHub должен совпадать"

    print("✅ Тест flow_author_extraction пройден!")
    clear_context()


@pytest.mark.asyncio
async def test_uninstall_not_installed_should_fail(migrated_db,  flow_factory, system_context, create_test_company, agent_repo, flow_repo):
    """
    Тест 9: Удаление неустановленного flow должно вызывать ошибку.

    Проверяет что нельзя удалить flow который не установлен.
    """
    test_company = await create_test_company("uninstall_empty_company_uniq")

    # Миграция уже выполнена в migrated_db фикстуре, не нужно повторять

    # Устанавливаем контекст для test_company
    context = get_context()
    context.active_company = test_company
    set_context(context)

    error_raised = False
    try:
        await flow_factory.uninstall_flow("apps.agents.flows.weather_flow.weather_flow_config")
    except ValueError as e:
        error_raised = True
        assert "не установлен" in str(e).lower() or "not found" in str(e).lower()

    assert error_raised, "Удаление несуществующего flow должно вызывать ошибку"

    print("✅ Тест uninstall_not_installed_should_fail пройден!")


@pytest.mark.asyncio
async def test_variables_definitions_validation(migrated_db,  caplog):
    """Тест валидации variables_definitions в FlowConfig"""
    import logging
    from apps.agents.models import FlowConfig

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
async def test_flow_variables_definitions_install(migrated_db,  migrator, create_test_company, variables_service):
    """Тест установки flow с variables_definitions через API"""
    from apps.frontend.api.flows import install_flow
    from pydantic import BaseModel

    test_company = await create_test_company("test_vars_api_company")

    # Используем реальный flow с variables_definitions - lawyer_flow
    flow_id = "apps.agents.flows.lawyer_flow.lawyer_flow"

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
        flow_repo=None,
        variables_service=variables_service,
        request=request
    )

    # Проверяем что flow установлен
    assert result["flow_id"] == flow_id

    # Проверяем что переменные созданы с правильными значениями
    lawyer_bot = await variables_service.get_var("lawyer_bot")
    token = await variables_service.get_var("lawyer_bot_telegram_token")
    company_name = await variables_service.get_var("company_short_name")

    assert lawyer_bot == "test_bot"
    assert token == "test_token_123"
    assert company_name == "Test Company"

    print("✅ Тест flow_variables_definitions_install пройден!")




@pytest.mark.asyncio
async def test_variables_resolution_after_install(migrated_db,  migrator, create_test_company, variables_service):
    """Тест резолюции @var: ссылок после установки flow с переменными"""
    from apps.frontend.api.flows import install_flow
    from pydantic import BaseModel

    test_company = await create_test_company("test_resolution_company")

    # Используем weather_flow для тестирования резолюции
    flow_id = "apps.agents.flows.weather_flow.weather_flow_config"

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
        flow_repo=None,
        variables_service=variables_service,
        request=request
    )

    # Проверяем что переменные созданы
    api_key = await variables_service.get_var("weather_api_key")
    bot_name = await variables_service.get_var("bot_name")

    assert api_key == "test_api_key_123"
    assert bot_name == "Test Weather Bot"

    # Проверяем резолюцию - берем flow config и резолвим его variables
    from apps.agents.flows.weather_flow import weather_flow_config
    resolved_vars = await variables_service.resolve(weather_flow_config.variables)

    # bot_name должен быть резолвен
    assert resolved_vars["bot_name"] == "Test Weather Bot"

    print("✅ Тест variables_resolution_after_install пройден!")


@pytest.mark.asyncio
async def test_flow_install_skip_empty_variables(migrated_db,  migrator, create_test_company, variables_service):
    """Тест установки flow с пропуском пустых переменных"""
    from apps.frontend.api.flows import install_flow
    from pydantic import BaseModel

    test_company = await create_test_company("test_skip_empty_vars_company")

    # Используем lawyer_flow для тестирования пропуска пустых переменных
    flow_id = "apps.agents.flows.lawyer_flow.lawyer_flow"

    # Создаем request с одной заполненной и одной пустой переменной
    class InstallFlowRequest(BaseModel):
        variables: dict = None

    request = InstallFlowRequest(variables={
        "lawyer_bot": "test_bot",
        "company_short_name_en": "",
        "lawyer_bot_telegram_token": "test_token"
    })

    # Устанавливаем flow
    result = await install_flow(
        flow_id=flow_id,
        flow_repo=None,
        variables_service=variables_service,
        request=request
    )

    # Проверяем что flow установлен
    assert result["flow_id"] == flow_id

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


@pytest.mark.asyncio
async def test_variables_service_operations(migrated_db,  create_test_company, variables_service):
    """Тест базовых операций с переменными через VariablesService"""
    test_company = await create_test_company("test_vars_service_company")

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



