"""
Тесты для системы переменных компании.
Проверяет изоляцию per-company, API endpoints и резолюцию @var:key.
"""

import pytest
import pytest_asyncio
from app.services.variables_service import VariablesService, get_variables_service
from app.core.storage import Storage
from app.core.context import set_context, clear_context
from app.models import Context
from app.identity.models import Company, User, AuthProvider, UserStatus
from app.models.i18n_models import Language


@pytest_asyncio.fixture
async def setup_companies():
    """Создает тестовые компании"""
    storage = Storage()
    
    # Компания 1
    company1 = Company(
        company_id="test_company_1",
        subdomain="test1",
        name="Test Company 1",
        status="active"
    )
    await storage.set("company:test_company_1", company1.model_dump_json(), force_global=True)
    await storage.set("subdomain:test1", '"test_company_1"', force_global=True)
    
    # Компания 2
    company2 = Company(
        company_id="test_company_2",
        subdomain="test2",
        name="Test Company 2",
        status="active"
    )
    await storage.set("company:test_company_2", company2.model_dump_json(), force_global=True)
    await storage.set("subdomain:test2", '"test_company_2"', force_global=True)
    
    yield company1, company2
    
    # Cleanup
    await storage.delete("company:test_company_1")
    await storage.delete("subdomain:test1")
    await storage.delete("company:test_company_2")
    await storage.delete("subdomain:test2")
    clear_context()


@pytest_asyncio.fixture
async def setup_context_company1(setup_companies):
    """Устанавливает контекст компании 1"""
    company1, company2 = setup_companies
    
    user = User(
        user_id="test_user_1",
        provider=AuthProvider.YANDEX,
        provider_user_id="test_123",
        email="test@test.com",
        name="Test User",
        status=UserStatus.ACTIVE,
        groups=["user"],
        companies={"test_company_1": ["admin"]},
        active_company_id="test_company_1"
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=company1,
        user_companies=[company1],
        language=Language.RU
    )
    
    set_context(context)
    yield context
    clear_context()


@pytest_asyncio.fixture
async def setup_context_company2(setup_companies):
    """Устанавливает контекст компании 2"""
    company1, company2 = setup_companies
    
    user = User(
        user_id="test_user_2",
        provider=AuthProvider.YANDEX,
        provider_user_id="test_456",
        email="test2@test.com",
        name="Test User 2",
        status=UserStatus.ACTIVE,
        groups=["user"],
        companies={"test_company_2": ["admin"]},
        active_company_id="test_company_2"
    )
    
    context = Context(
        user=user,
        platform="test",
        active_company=company2,
        user_companies=[company2],
        language=Language.RU
    )
    
    set_context(context)
    yield context
    clear_context()


@pytest.mark.asyncio
async def test_variables_service_set_and_get(setup_context_company1):
    """Тест сохранения и получения переменной"""
    variables_service = VariablesService()
    
    # Сохраняем переменную
    success = await variables_service.set_var("test_var", "test_value", is_secret=False)
    assert success is True
    
    # Получаем переменную
    value = await variables_service.get_var("test_var")
    assert value == "test_value"
    
    # Cleanup
    await variables_service.delete_var("test_var")


@pytest.mark.asyncio
async def test_variables_service_secret(setup_context_company1):
    """Тест сохранения секрета"""
    variables_service = VariablesService()
    
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
    
    # Cleanup
    await variables_service.delete_var("secret_key")


@pytest.mark.asyncio
async def test_variables_per_company_isolation(setup_companies):
    """Тест изоляции переменных между компаниями"""
    company1, company2 = setup_companies
    
    # Контекст компании 1
    user1 = User(
        user_id="test_user_1",
        provider=AuthProvider.YANDEX,
        provider_user_id="test_123",
        email="test@test.com",
        name="Test User 1",
        status=UserStatus.ACTIVE,
        groups=["user"],
        companies={"test_company_1": ["admin"]},
        active_company_id="test_company_1"
    )
    context1 = Context(
        user=user1,
        platform="test",
        active_company=company1,
        user_companies=[company1],
        language=Language.RU
    )
    set_context(context1)
    
    variables_service = VariablesService()
    await variables_service.set_var("shared_key", "value_from_company1", is_secret=False)
    
    # Контекст компании 2
    user2 = User(
        user_id="test_user_2",
        provider=AuthProvider.YANDEX,
        provider_user_id="test_456",
        email="test2@test.com",
        name="Test User 2",
        status=UserStatus.ACTIVE,
        groups=["user"],
        companies={"test_company_2": ["admin"]},
        active_company_id="test_company_2"
    )
    context2 = Context(
        user=user2,
        platform="test",
        active_company=company2,
        user_companies=[company2],
        language=Language.RU
    )
    set_context(context2)
    
    # Компания 2 не видит переменную компании 1
    value = await variables_service.get_var("shared_key")
    assert value is None
    
    # Компания 2 сохраняет свою переменную с тем же ключом
    await variables_service.set_var("shared_key", "value_from_company2", is_secret=False)
    value = await variables_service.get_var("shared_key")
    assert value == "value_from_company2"
    
    # Возвращаемся в контекст компании 1
    set_context(context1)
    value = await variables_service.get_var("shared_key")
    assert value == "value_from_company1"
    
    # Cleanup
    set_context(context1)
    await variables_service.delete_var("shared_key")
    set_context(context2)
    await variables_service.delete_var("shared_key")
    clear_context()


@pytest.mark.asyncio
async def test_variables_resolve_reference(setup_context_company1):
    """Тест резолюции @var:key ссылок"""
    variables_service = VariablesService()
    
    # Сохраняем переменную
    await variables_service.set_var("bot_token", "123:ABC...", is_secret=True)
    
    # Резолвим ссылку
    resolved = await variables_service.resolve("@var:bot_token")
    assert resolved == "123:ABC..."
    
    # Обычная строка возвращается как есть
    resolved = await variables_service.resolve("hardcoded_value")
    assert resolved == "hardcoded_value"
    
    # Cleanup
    await variables_service.delete_var("bot_token")


@pytest.mark.asyncio
async def test_variables_resolve_not_found(setup_context_company1):
    """Тест auto-create при резолюции несуществующей переменной"""
    variables_service = VariablesService()
    
    # С auto_create=True (по умолчанию) создается пустая переменная
    result = await variables_service.resolve("@var:nonexistent_var")
    assert result == ""  # Создалась пустая
    
    # Проверяем что создалась
    value = await variables_service.get_var("nonexistent_var")
    assert value == ""
    
    # С auto_create=False должна быть ошибка
    await variables_service.delete_var("nonexistent_var")
    with pytest.raises(ValueError, match="Variable nonexistent_var_2 not found"):
        await variables_service.resolve("@var:nonexistent_var_2", auto_create=False)


@pytest.mark.asyncio
async def test_variables_resolve_dict(setup_context_company1):
    """Тест резолюции в словарях"""
    variables_service = VariablesService()
    
    # Сохраняем переменные
    await variables_service.set_var("bot_name", "Test Bot", is_secret=False)
    await variables_service.set_var("bot_token", "123:ABC...", is_secret=True)
    
    # Резолвим словарь
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
    
    # Cleanup
    await variables_service.delete_var("bot_name")
    await variables_service.delete_var("bot_token")


@pytest.mark.asyncio
async def test_variables_resolve_list(setup_context_company1):
    """Тест резолюции в списках"""
    variables_service = VariablesService()
    
    # Сохраняем переменную
    await variables_service.set_var("api_key", "sk-123", is_secret=True)
    
    # Резолвим список
    items = ["@var:api_key", "hardcoded", 123, {"key": "@var:api_key"}]
    resolved = await variables_service.resolve(items)
    
    assert resolved[0] == "sk-123"
    assert resolved[1] == "hardcoded"
    assert resolved[2] == 123
    assert resolved[3]["key"] == "sk-123"
    
    # Cleanup
    await variables_service.delete_var("api_key")


@pytest.mark.asyncio
async def test_variables_delete(setup_context_company1):
    """Тест удаления переменной"""
    variables_service = VariablesService()
    
    # Создаем переменную
    await variables_service.set_var("temp_var", "temp_value", is_secret=False)
    value = await variables_service.get_var("temp_var")
    assert value == "temp_value"
    
    # Удаляем
    success = await variables_service.delete_var("temp_var")
    assert success is True
    
    # Проверяем что удалена
    value = await variables_service.get_var("temp_var")
    assert value is None


@pytest.mark.asyncio
async def test_variables_list(setup_context_company1):
    """Тест получения списка переменных"""
    variables_service = VariablesService()
    
    # Создаем несколько переменных
    await variables_service.set_var("var1", "value1", is_secret=False)
    await variables_service.set_var("var2", "value2", is_secret=True)
    await variables_service.set_var("var3", "value3", is_secret=False)
    
    # Получаем список
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
    
    # Cleanup
    await variables_service.delete_var("var1")
    await variables_service.delete_var("var2")
    await variables_service.delete_var("var3")


@pytest.mark.asyncio
async def test_variables_storage_keys(setup_context_company1):
    """Тест правильности формата ключей в Storage"""
    variables_service = VariablesService()
    storage = Storage()
    
    # Сохраняем переменную
    await variables_service.set_var("test_key", "test_value", is_secret=False)
    
    # Проверяем ключ в Storage
    # Формат: company:test_company_1:var:test_key
    storage_key = "company:test_company_1:var:test_key"
    data = await storage.get(storage_key, force_global=True)
    
    assert data is not None
    import json
    var_data = json.loads(data)
    assert var_data["value"] == "test_value"
    assert var_data["secret"] is False
    
    # Cleanup
    await variables_service.delete_var("test_key")


@pytest.mark.asyncio
async def test_variables_singleton():
    """Тест глобального экземпляра VariablesService"""
    service1 = get_variables_service()
    service2 = get_variables_service()
    
    assert service1 is service2


@pytest.mark.asyncio
async def test_variables_update(setup_context_company1):
    """Тест обновления существующей переменной"""
    variables_service = VariablesService()
    
    # Создаем переменную
    await variables_service.set_var("update_var", "old_value", is_secret=False)
    value = await variables_service.get_var("update_var")
    assert value == "old_value"
    
    # Обновляем значение
    await variables_service.set_var("update_var", "new_value", is_secret=False)
    value = await variables_service.get_var("update_var")
    assert value == "new_value"
    
    # Обновляем и делаем секретом
    await variables_service.set_var("update_var", "secret_value", is_secret=True)
    value = await variables_service.get_var("update_var")
    assert value == "secret_value"
    
    all_vars = await variables_service.list_vars()
    assert all_vars["update_var"]["secret"] is True
    
    # Cleanup
    await variables_service.delete_var("update_var")


@pytest.mark.asyncio
async def test_variables_complex_resolve(setup_context_company1):
    """Тест сложной резолюции с вложенными структурами"""
    variables_service = VariablesService()
    
    # Сохраняем переменные
    await variables_service.set_var("api_key", "sk-123", is_secret=True)
    await variables_service.set_var("bot_name", "Test Bot", is_secret=False)
    await variables_service.set_var("timeout", "60", is_secret=False)
    
    # Сложная структура
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
    
    # Резолвим
    resolved = await variables_service.resolve(config)
    
    assert resolved["platforms"]["telegram"]["username"] == "Test Bot"
    assert resolved["platforms"]["telegram"]["token"] == "sk-123"
    assert resolved["platforms"]["api"]["key"] == "sk-123"
    assert resolved["settings"]["timeout"] == "60"
    assert resolved["settings"]["retries"] == 3
    assert resolved["settings"]["endpoints"][0] == "sk-123"
    assert resolved["settings"]["endpoints"][1] == "hardcoded_endpoint"
    
    # Cleanup
    await variables_service.delete_var("api_key")
    await variables_service.delete_var("bot_name")
    await variables_service.delete_var("timeout")


@pytest.mark.asyncio
async def test_flow_variables_resolution(setup_context_company1):
    """Тест резолюции переменных в FlowConfig.variables"""
    from app.models import FlowConfig
    from app.core.storage import Storage
    
    variables_service = VariablesService()
    storage = Storage()
    
    # Сохраняем company переменные
    await variables_service.set_var("company_bot_name", "Company Bot", is_secret=False)
    await variables_service.set_var("api_key", "sk-123", is_secret=True)
    
    # Создаем FlowConfig с ссылками на переменные
    flow_config = FlowConfig(
        flow_id="test_variables_flow",
        name="Test Variables Flow",
        entry_point_agent="app.agents.weather.agent.WeatherAgent",
        variables={
            "bot_name": "@var:company_bot_name",  # Ссылка
            "api_key": "@var:api_key",            # Ссылка
            "greeting": "Hello",                  # Хардкод
            "timeout": "60"                       # Хардкод
        }
    )
    
    await storage.set_flow_config(flow_config)
    
    # Резолвим переменные flow
    resolved = await variables_service.resolve(flow_config.variables)
    
    assert resolved["bot_name"] == "Company Bot"
    assert resolved["api_key"] == "sk-123"
    assert resolved["greeting"] == "Hello"
    assert resolved["timeout"] == "60"
    
    # Cleanup
    await storage.delete_flow_config("test_variables_flow")
    await variables_service.delete_var("company_bot_name")
    await variables_service.delete_var("api_key")


@pytest.mark.asyncio
async def test_platform_config_resolution(setup_context_company1):
    """Тест резолюции @var:key в platform config"""
    from app.models import FlowConfig
    from app.core.storage import Storage
    
    variables_service = VariablesService()
    storage = Storage()
    
    # Сохраняем токен как переменную
    await variables_service.set_var("telegram_bot_token", "123:ABC...", is_secret=True)
    await variables_service.set_var("bot_username", "my_test_bot", is_secret=False)
    
    # Создаем FlowConfig с ссылками
    flow_config = FlowConfig(
        flow_id="test_platform_flow",
        name="Test Platform Flow",
        entry_point_agent="app.agents.weather.agent.WeatherAgent",
        platforms={
            "telegram": {
                "username": "@var:bot_username",        # Ссылка
                "token": "@var:telegram_bot_token"      # Ссылка
            },
            "api": {
                "key": "hardcoded_key"                  # Хардкод
            }
        }
    )
    
    await storage.set_flow_config(flow_config)
    
    # Резолвим platforms
    resolved_platforms = await variables_service.resolve(flow_config.platforms)
    
    assert resolved_platforms["telegram"]["username"] == "my_test_bot"
    assert resolved_platforms["telegram"]["token"] == "123:ABC..."
    assert resolved_platforms["api"]["key"] == "hardcoded_key"
    
    # Cleanup
    await storage.delete_flow_config("test_platform_flow")
    await variables_service.delete_var("telegram_bot_token")
    await variables_service.delete_var("bot_username")


@pytest.mark.asyncio
async def test_nested_flow_variables(setup_context_company1):
    """Тест вложенных структур в flow variables"""
    from app.models import FlowConfig
    from app.core.storage import Storage
    
    variables_service = VariablesService()
    storage = Storage()
    
    # Сохраняем переменные
    await variables_service.set_var("db_host", "localhost", is_secret=False)
    await variables_service.set_var("db_password", "secret123", is_secret=True)
    
    # FlowConfig с вложенными переменными
    flow_config = FlowConfig(
        flow_id="test_nested_flow",
        name="Test Nested Flow",
        entry_point_agent="app.agents.weather.agent.WeatherAgent",
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
    
    await storage.set_flow_config(flow_config)
    
    # Резолвим
    resolved = await variables_service.resolve(flow_config.variables)
    
    assert resolved["database"]["host"] == "localhost"
    assert resolved["database"]["port"] == 5432
    assert resolved["database"]["password"] == "secret123"
    assert resolved["database"]["name"] == "mydb"
    assert resolved["api"]["endpoints"][0] == "localhost"
    assert resolved["api"]["endpoints"][1] == "api.example.com"
    
    # Cleanup
    await storage.delete_flow_config("test_nested_flow")
    await variables_service.delete_var("db_host")
    await variables_service.delete_var("db_password")


@pytest.mark.asyncio
async def test_flow_variables_in_runtime(setup_context_company1):
    """
    Полный тест: создание company variable → добавление во flow → доступ из тула
    """
    from app.models import FlowConfig
    from app.core.storage import Storage
    from app.core.variables import VariableResolver
    from app.core.context import get_context
    from app.tools.session_tools import get_variable
    
    variables_service = VariablesService()
    storage = Storage()
    
    # 1. Создаем company variable
    await variables_service.set_var(
        key="test_bot_token",
        value="123:ABC_TEST_TOKEN",
        is_secret=True,
        groups=["telegram", "test"],
        description="Тестовый токен для бота"
    )
    
    # 2. Создаем FlowConfig с ссылкой на переменную
    flow_config = FlowConfig(
        flow_id="test_flow_runtime",
        name="Test Flow Runtime",
        entry_point_agent="app.agents.weather.agent.WeatherAgent",
        variables={
            "bot_token": "@var:test_bot_token",  # Ссылка на company variable
            "bot_name": "Test Bot",              # Хардкод
            "timeout": "60"                      # Хардкод
        }
    )
    
    await storage.set_flow_config(flow_config)
    
    # 3. Резолвим переменные (как в TaskProcessor)
    resolved_variables = await variables_service.resolve(flow_config.variables)
    
    # Проверяем резолюцию
    assert resolved_variables["bot_token"] == "123:ABC_TEST_TOKEN"  # Резолвнуто!
    assert resolved_variables["bot_name"] == "Test Bot"
    assert resolved_variables["timeout"] == "60"
    
    # 4. Устанавливаем в контекст (как делает TaskProcessor)
    context = get_context()
    context.flow_variables = resolved_variables
    
    # 5. Проверяем доступ через VariableResolver (используется в промптах)
    all_vars = VariableResolver.resolve_all()
    
    assert "bot_token" in all_vars
    assert all_vars["bot_token"] == "123:ABC_TEST_TOKEN"
    assert "bot_name" in all_vars
    assert all_vars["bot_name"] == "Test Bot"
    
    # 6. Проверяем доступ через get_variable (используется в тулах)
    bot_token_from_tool = get_variable("bot_token")
    assert bot_token_from_tool == "123:ABC_TEST_TOKEN"
    
    bot_name_from_tool = get_variable("bot_name")
    assert bot_name_from_tool == "Test Bot"
    
    # Cleanup
    await storage.delete_flow_config("test_flow_runtime")
    await variables_service.delete_var("test_bot_token")


@pytest.mark.asyncio
async def test_variables_in_prompts(setup_context_company1):
    """
    Тест подстановки переменных в промпты с поддержкой вложенных структур
    """
    from app.models import FlowConfig
    from app.core.storage import Storage
    from app.core.variables import VariableResolver
    from app.core.context import get_context
    
    variables_service = VariablesService()
    storage = Storage()
    
    # Создаем company variables
    await variables_service.set_var("api_endpoint", "https://api.example.com", is_secret=False)
    await variables_service.set_var("api_key", "sk-test-123", is_secret=True)
    
    # FlowConfig с вложенными переменными
    flow_config = FlowConfig(
        flow_id="test_flow_prompts",
        name="Test Flow Prompts",
        entry_point_agent="app.agents.weather.agent.WeatherAgent",
        variables={
            "bot_name": "Assistant",
            "api": {
                "endpoint": "@var:api_endpoint",
                "key": "@var:api_key"
            },
            "cities": ["Москва", "Питер", "@var:default_city"]
        }
    )
    
    await storage.set_flow_config(flow_config)
    
    # Резолвим и добавляем в контекст
    resolved = await variables_service.resolve(flow_config.variables)
    context = get_context()
    context.flow_variables = resolved
    
    # Тестируем подстановку в промпты
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
    
    # Cleanup
    await storage.delete_flow_config("test_flow_prompts")
    await variables_service.delete_var("api_endpoint")
    await variables_service.delete_var("api_key")

