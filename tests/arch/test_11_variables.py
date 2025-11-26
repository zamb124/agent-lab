"""
Тесты для системы переменных компании.
Проверяет изоляцию per-company, API endpoints и резолюцию @var:key.
"""

import pytest
# get_variables_service доступен через фикстуру variables_service
from core.context import set_context


@pytest.mark.asyncio
async def test_variables_service_set_and_get(variables_service, flow_repo):
    """Тест сохранения и получения переменной"""

    # Сохраняем переменную
    success = await variables_service.set_var("test_var", "test_value", is_secret=False)
    assert success is True

    # Получаем переменную
    value = await variables_service.get_var("test_var")
    assert value == "test_value"


@pytest.mark.asyncio
async def test_variables_service_secret(variables_service, flow_repo):
    """Тест сохранения секрета"""

    # Сохраняем секрет
    await variables_service.set_var("secret_key", "super_secret_value", is_secret=True)

    # Получаем секрет
    value = await variables_service.get_var("secret_key")
    assert value == "super_secret_value"

    # Проверяем что в списке он скрыт
    all_vars = await variables_service.list_vars()
    assert "secret_key" in all_vars
    assert all_vars["secret_key"]["value"] == "***"
    assert all_vars["secret_key"]["secret"] is True


@pytest.mark.asyncio
async def test_variables_per_company_isolation(unique_id, flow_repo, company_repo):
    """Тест изоляции переменных между компаниями"""
    from core.models import Company, User, AuthProvider, UserStatus
    from core.models.context_models import Context

    company1_id = unique_id("company")
    company2_id = unique_id("company")

    company1 = Company(
        company_id=company1_id,
        subdomain=unique_id("subdomain"),
        name="Test Company 1",
        status="active"
    )
    company2 = Company(
        company_id=company2_id,
        subdomain=unique_id("subdomain"),
        name="Test Company 2",
        status="active"
    )

    await company_repo.set(company1)
    await company_repo.set(company2)

    user1 = User(
        user_id=unique_id("user"),
        provider=AuthProvider.YANDEX,
        provider_user_id="test_123",
        email="test1@test.com",
        name="Test User 1",
        status=UserStatus.ACTIVE,
        groups=["user"],
        companies={company1_id: ["admin"]},
        active_company_id=company1_id
    )

    user2 = User(
        user_id=unique_id("user"),
        provider=AuthProvider.YANDEX,
        provider_user_id="test_456",
        email="test2@test.com",
        name="Test User 2",
        status=UserStatus.ACTIVE,
        groups=["user"],
        companies={company2_id: ["admin"]},
        active_company_id=company2_id
    )

    context1 = Context(
        user=user1,
        platform="test",
        active_company=company1,
        user_companies=[company1]
    )

    context2 = Context(
        user=user2,
        platform="test",
        active_company=company2,
        user_companies=[company2]
    )

    from core.variables import VariablesService
    from apps.agents.container import get_agents_container
    variables_service = get_agents_container().variables_service

    set_context(context1)
    await variables_service.set_var("shared_key", "value_from_company1", is_secret=False)

    set_context(context2)
    value = await variables_service.get_var("shared_key")
    assert value is None

    await variables_service.set_var("shared_key", "value_from_company2", is_secret=False)
    value = await variables_service.get_var("shared_key")
    assert value == "value_from_company2"

    set_context(context1)
    value = await variables_service.get_var("shared_key")
    assert value == "value_from_company1"


@pytest.mark.asyncio
async def test_variables_resolve_reference(variables_service, flow_repo):
    """Тест резолюции @var:key ссылок"""

    await variables_service.set_var("bot_token", "123:ABC...", is_secret=True)

    resolved = await variables_service.resolve("@var:bot_token")
    assert resolved == "123:ABC..."

    resolved = await variables_service.resolve("hardcoded_value")
    assert resolved == "hardcoded_value"


@pytest.mark.asyncio
async def test_variables_resolve_not_found(variables_service, flow_repo):
    """Тест auto-create при резолюции несуществующей переменной"""

    result = await variables_service.resolve("@var:nonexistent_var")
    assert result == ""

    value = await variables_service.get_var("nonexistent_var")
    assert value == ""

    with pytest.raises(ValueError, match="Variable nonexistent_var_2 not found"):
        await variables_service.resolve("@var:nonexistent_var_2", auto_create=False)


@pytest.mark.asyncio
async def test_variables_resolve_dict(variables_service, flow_repo):
    """Тест резолюции в словарях"""

    await variables_service.set_var("bot_name", "Test Bot", is_secret=False)
    await variables_service.set_var("bot_token", "123:ABC...", is_secret=True)

    platform_config = {
        "username": "@var:bot_name",
        "token": "@var:bot_token",
        "timeout": 30,
        "nested": {
            "key": "@var:bot_name"
        }
    }

    resolved = await variables_service.resolve(platform_config)

    assert resolved["username"] == "Test Bot"
    assert resolved["token"] == "123:ABC..."
    assert resolved["timeout"] == 30
    assert resolved["nested"]["key"] == "Test Bot"


@pytest.mark.asyncio
async def test_variables_resolve_list(variables_service, flow_repo):
    """Тест резолюции в списках"""

    await variables_service.set_var("api_key", "sk-123", is_secret=True)

    items = ["@var:api_key", "hardcoded", 123, {"key": "@var:api_key"}]
    resolved = await variables_service.resolve(items)

    assert resolved[0] == "sk-123"
    assert resolved[1] == "hardcoded"
    assert resolved[2] == 123
    assert resolved[3]["key"] == "sk-123"


@pytest.mark.asyncio
async def test_variables_delete(variables_service, flow_repo):
    """Тест удаления переменной"""

    await variables_service.set_var("temp_var", "temp_value", is_secret=False)
    value = await variables_service.get_var("temp_var")
    assert value == "temp_value"

    success = await variables_service.delete_var("temp_var")
    assert success is True

    value = await variables_service.get_var("temp_var")
    assert value is None


@pytest.mark.asyncio
async def test_variables_list(variables_service, flow_repo):
    """Тест получения списка переменных"""

    await variables_service.set_var("var1", "value1", is_secret=False)
    await variables_service.set_var("var2", "value2", is_secret=True)
    await variables_service.set_var("var3", "value3", is_secret=False)

    all_vars = await variables_service.list_vars()

    assert "var1" in all_vars
    assert all_vars["var1"]["value"] == "value1"
    assert all_vars["var1"]["secret"] is False

    assert "var2" in all_vars
    assert all_vars["var2"]["value"] == "***"
    assert all_vars["var2"]["secret"] is True

    assert "var3" in all_vars
    assert all_vars["var3"]["value"] == "value3"
    assert all_vars["var3"]["secret"] is False


@pytest.mark.asyncio
async def test_variables_storage_keys(variables_service, variable_repo, test_company, flow_repo):
    """Тест правильности формата ключей в Storage"""
    await variables_service.set_var("test_key", "test_value", is_secret=False)

    variable = await variable_repo.get("test_key")

    assert variable is not None
    assert variable.value == "test_value"
    assert variable.secret is False


@pytest.mark.asyncio
async def test_variables_singleton(flow_repo):
    """Тест глобального экземпляра VariablesService"""
    from apps.agents.container import get_agents_container
    container = get_agents_container()
    service1 = container.variables_service
    service2 = container.variables_service

    assert service1 is service2


@pytest.mark.asyncio
async def test_variables_update(variables_service, flow_repo):
    """Тест обновления существующей переменной"""
    await variables_service.set_var("update_var", "old_value", is_secret=False)
    value = await variables_service.get_var("update_var")
    assert value == "old_value"

    await variables_service.set_var("update_var", "new_value", is_secret=False)
    value = await variables_service.get_var("update_var")
    assert value == "new_value"

    await variables_service.set_var("update_var", "secret_value", is_secret=True)
    value = await variables_service.get_var("update_var")
    assert value == "secret_value"

    all_vars = await variables_service.list_vars()
    assert all_vars["update_var"]["secret"] is True


@pytest.mark.asyncio
async def test_variables_complex_resolve(variables_service, flow_repo):
    """Тест сложной резолюции с вложенными структурами"""
    await variables_service.set_var("api_key", "sk-123", is_secret=True)
    await variables_service.set_var("bot_name", "Test Bot", is_secret=False)
    await variables_service.set_var("timeout", "60", is_secret=False)

    config = {
        "platforms": {
            "telegram": {
                "username": "@var:bot_name",
                "token": "@var:api_key"
            },
            "api": {
                "key": "@var:api_key"
            }
        },
        "settings": {
            "timeout": "@var:timeout",
            "retries": 3,
            "endpoints": [
                "@var:api_key",
                "hardcoded_endpoint"
            ]
        }
    }

    resolved = await variables_service.resolve(config)

    assert resolved["platforms"]["telegram"]["username"] == "Test Bot"
    assert resolved["platforms"]["telegram"]["token"] == "sk-123"
    assert resolved["platforms"]["api"]["key"] == "sk-123"
    assert resolved["settings"]["timeout"] == "60"
    assert resolved["settings"]["retries"] == 3
    assert resolved["settings"]["endpoints"][0] == "sk-123"
    assert resolved["settings"]["endpoints"][1] == "hardcoded_endpoint"


@pytest.mark.asyncio
async def test_flow_variables_resolution(variables_service,  flow_repo):
    """Тест резолюции переменных в FlowConfig.variables"""
    from apps.agents.models import FlowConfig

    # Сохраняем company переменные
    await variables_service.set_var("company_bot_name", "Company Bot", is_secret=False)
    await variables_service.set_var("api_key", "sk-123", is_secret=True)

    # Создаем FlowConfig с ссылками на переменные
    flow_config = FlowConfig(
        flow_id="test_variables_flow",
        name="Test Variables Flow",
        entry_point_agent="apps.agents.agents.weather.agent.WeatherAgent",
        variables={
            "bot_name": "@var:company_bot_name",  # Ссылка
            "api_key": "@var:api_key",            # Ссылка
            "greeting": "Hello",                  # Хардкод
            "timeout": "60"                       # Хардкод
        }
    )

    await flow_repo.set(flow_config)

    # Резолвим переменные flow
    resolved = await variables_service.resolve(flow_config.variables)

    assert resolved["bot_name"] == "Company Bot"
    assert resolved["api_key"] == "sk-123"
    assert resolved["greeting"] == "Hello"
    assert resolved["timeout"] == "60"


@pytest.mark.asyncio
async def test_platform_config_resolution(variables_service,  flow_repo):
    """Тест резолюции @var:key в platform config"""
    from apps.agents.models import FlowConfig

    await variables_service.set_var("telegram_bot_token", "123:ABC...", is_secret=True)
    await variables_service.set_var("bot_username", "my_test_bot", is_secret=False)

    flow_config = FlowConfig(
        flow_id="test_platform_flow",
        name="Test Platform Flow",
        entry_point_agent="apps.agents.agents.weather.agent.WeatherAgent",
        platforms={
            "telegram": {
                "username": "@var:bot_username",
                "token": "@var:telegram_bot_token"
            },
            "api": {
                "key": "hardcoded_key"
            }
        }
    )

    await flow_repo.set(flow_config)

    resolved_platforms = await variables_service.resolve(flow_config.platforms)

    assert resolved_platforms["telegram"]["username"] == "my_test_bot"
    assert resolved_platforms["telegram"]["token"] == "123:ABC..."
    assert resolved_platforms["api"]["key"] == "hardcoded_key"


@pytest.mark.asyncio
async def test_nested_flow_variables(variables_service,  flow_repo):
    """Тест вложенных структур в flow variables"""
    from apps.agents.models import FlowConfig

    await variables_service.set_var("db_host", "localhost", is_secret=False)
    await variables_service.set_var("db_password", "secret123", is_secret=True)

    flow_config = FlowConfig(
        flow_id="test_nested_flow",
        name="Test Nested Flow",
        entry_point_agent="apps.agents.agents.weather.agent.WeatherAgent",
        variables={
            "database": {
                "host": "@var:db_host",
                "port": 5432,
                "password": "@var:db_password",
                "name": "mydb"
            },
            "api": {
                "endpoints": [
                    "@var:db_host",
                    "api.example.com"
                ]
            }
        }
    )

    await flow_repo.set(flow_config)

    resolved = await variables_service.resolve(flow_config.variables)

    assert resolved["database"]["host"] == "localhost"
    assert resolved["database"]["port"] == 5432
    assert resolved["database"]["password"] == "secret123"
    assert resolved["database"]["name"] == "mydb"
    assert resolved["api"]["endpoints"][0] == "localhost"
    assert resolved["api"]["endpoints"][1] == "api.example.com"


@pytest.mark.asyncio
async def test_flow_variables_in_runtime(variables_service,  flow_repo):
    """Полный тест: создание company variable → добавление во flow → доступ из тула"""
    from apps.agents.models import FlowConfig
    from core.variables import VariableResolver
    from core.context import get_context
    from apps.agents.tools.session.session_tools import get_variable

    await variables_service.set_var(
        key="test_bot_token",
        value="123:ABC_TEST_TOKEN",
        is_secret=True,
        groups=["telegram", "test"],
        description="Тестовый токен для бота"
    )

    flow_config = FlowConfig(
        flow_id="test_flow_runtime",
        name="Test Flow Runtime",
        entry_point_agent="apps.agents.agents.weather.agent.WeatherAgent",
        variables={
            "bot_token": "@var:test_bot_token",
            "bot_name": "Test Bot",
            "timeout": "60"
        }
    )

    await flow_repo.set(flow_config)

    resolved_variables = await variables_service.resolve(flow_config.variables)

    assert resolved_variables["bot_token"] == "123:ABC_TEST_TOKEN"
    assert resolved_variables["bot_name"] == "Test Bot"
    assert resolved_variables["timeout"] == "60"

    context = get_context()
    context.flow_variables = resolved_variables

    all_vars = VariableResolver.resolve_all()

    assert "bot_token" in all_vars
    assert all_vars["bot_token"] == "123:ABC_TEST_TOKEN"
    assert "bot_name" in all_vars
    assert all_vars["bot_name"] == "Test Bot"

    bot_token_from_tool = get_variable("bot_token")
    assert bot_token_from_tool == "123:ABC_TEST_TOKEN"

    bot_name_from_tool = get_variable("bot_name")
    assert bot_name_from_tool == "Test Bot"


@pytest.mark.asyncio
async def test_variables_in_prompts(variables_service,  flow_repo):
    """Тест подстановки переменных в промпты с поддержкой вложенных структур"""
    from apps.agents.models import FlowConfig
    from core.variables import VariableResolver
    from core.context import get_context

    await variables_service.set_var("api_endpoint", "https://api.example.com", is_secret=False)
    await variables_service.set_var("api_key", "sk-test-123", is_secret=True)

    flow_config = FlowConfig(
        flow_id="test_flow_prompts",
        name="Test Flow Prompts",
        entry_point_agent="apps.agents.agents.weather.agent.WeatherAgent",
        variables={
            "bot_name": "Assistant",
            "api": {
                "endpoint": "@var:api_endpoint",
                "key": "@var:api_key"
            },
            "cities": ["Москва", "Питер", "@var:default_city"]
        }
    )

    await flow_repo.set(flow_config)

    resolved = await variables_service.resolve(flow_config.variables)
    context = get_context()
    context.flow_variables = resolved

    template = """
    Ты {bot_name}.
    Endpoint: {api.endpoint}
    Первый город: {cities[0]}
    Второй город: {cities[1]}
    """

    rendered = VariableResolver.render_template(template)

    assert "Ты Assistant" in rendered
    assert "Endpoint: https://api.example.com" in rendered
    assert "Первый город: Москва" in rendered
    assert "Второй город: Питер" in rendered

