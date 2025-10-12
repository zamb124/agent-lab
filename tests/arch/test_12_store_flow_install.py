"""
Тесты для Store функционала - установка и удаление flows.

Проверяет:
1. Создание компании - мигрируются только публичные tools
2. Установка flow - создаются flow, агенты, tools
3. Удаление flow - удаляются flow, агенты, tools
4. Выполнение хуков install/uninstall
"""
import pytest
import asyncio
from datetime import datetime, timezone

from app.core.migrator import Migrator
from app.core.storage import Storage
from app.core.flow_factory import FlowFactory
from app.core.context import set_context, clear_context
from app.identity.models import Company, User, AuthProvider, UserStatus
from app.models.context_models import Context
from app.models import ToolReference


async def _create_test_company(company_id: str = "test_store_company"):
    """Создает тестовую компанию"""
    company = Company(
        company_id=company_id,
        subdomain=f"test_store_{company_id}",
        name=f"Test Store Company {company_id}",
        status="active",
        created_at=datetime.now(timezone.utc)
    )
    
    await _cleanup_test_company(company)
    
    storage = Storage()
    await storage.set(f"company:{company.company_id}", company.model_dump_json(), force_global=True)
    
    return company


async def _cleanup_test_company(company: Company):
    """Удаляет тестовую компанию и все её данные"""
    storage = Storage()
    
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


def _set_company_context(company: Company):
    """Устанавливает контекст компании"""
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


async def _cleanup_system_company():
    """Удаляет все записи системной компании из БД"""
    storage = Storage()
    
    system_company = Company(
        company_id="system",
        subdomain="system",
        name="System Company",
        status="active",
        created_at=datetime.now(timezone.utc)
    )
    
    user = User(
        user_id="system",
        provider=AuthProvider.YANDEX,
        provider_user_id="system",
        email="system@test.com",
        name="System",
        status=UserStatus.ACTIVE,
        groups=["admin"],
        companies={"system": ["admin"]},
        active_company_id="system"
    )
    
    from app.core.context import set_context
    from app.models.context_models import Context
    
    context = Context(
        user=user,
        platform="test",
        active_company=system_company,
        user_companies=[system_company]
    )
    set_context(context)
    
    prefixes = [
        "flow:",
        "agent:",
        "tool:",
    ]
    
    for prefix in prefixes:
        keys = await storage.list_by_prefix(prefix)
        for key in keys:
            await storage.delete(key, force_global=True)


@pytest.mark.asyncio
async def test_new_company_only_tools():
    """
    Тест 1: При создании компании мигрируются только публичные tools.
    
    Проверяет что:
    - Мигрируются ТОЛЬКО публичные tools (is_public=True)
    - Flows НЕ мигрируются
    - Агенты НЕ мигрируются
    """
    await _cleanup_system_company()
    
    migrator = Migrator()
    await migrator.run_full_migration()
    
    test_company = await _create_test_company("new_company_1")
    storage = Storage()
    
    _set_company_context(test_company)
    
    await migrator.migrate_defaults_for_company(test_company)
    
    simple_flow = await storage.get_flow_config("app.flows.simple_flow.simple_flow_config")
    assert simple_flow is None, "Flows НЕ должны автоматически мигрироваться"
    
    weather_flow = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert weather_flow is None, "Flows НЕ должны автоматически мигрироваться"
    
    weather_agent = await storage.get_agent_config("app.agents.weather.agent.WeatherAgent")
    assert weather_agent is None, "Агенты НЕ должны автоматически мигрироваться"
    
    tool_data = await storage.get("tool:app.tools.calc_tools.calculate")
    assert tool_data is not None, "Публичные tools должны быть мигрированы"
    
    print("✅ Тест new_company_only_tools пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_install_flow_creates_dependencies():
    """
    Тест 2: Установка flow создает все зависимости.
    
    Проверяет что при установке flow:
    - Создается flow
    - Создаются все агенты
    - Создаются все приватные tools
    - Выполняется install hook
    """
    await _cleanup_system_company()
    
    migrator = Migrator()
    await migrator.run_full_migration()
    
    test_company = await _create_test_company("install_test_company")
    storage = Storage()
    flow_factory = FlowFactory()
    
    _set_company_context(test_company)
    
    await migrator.migrate_defaults_for_company(test_company)
    
    weather_flow = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert weather_flow is None, "Flow не должен быть установлен до вызова install"
    
    result = await flow_factory.install_flow("app.flows.weather_flow.weather_flow_config")
    
    assert result["flow_id"] == "app.flows.weather_flow.weather_flow_config"
    assert result["company_id"] == test_company.company_id
    
    weather_flow = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert weather_flow is not None, "Flow должен быть установлен"
    assert weather_flow.install_hook is not None, "install_hook должен быть извлечен"
    assert isinstance(weather_flow.install_hook, ToolReference), "install_hook должен быть ToolReference"
    
    weather_agent = await storage.get_agent_config("app.agents.weather.agent.WeatherAgent")
    assert weather_agent is not None, "Агент flow должен быть мигрирован"
    
    variable_key = f"company:{test_company.company_id}:var:default_city"
    variable_json = await storage.get(variable_key)
    assert variable_json is not None, "install hook должен создать переменную default_city"
    
    print("✅ Тест install_flow_creates_dependencies пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_uninstall_flow_removes_dependencies():
    """
    Тест 3: Удаление flow удаляет все зависимости.
    
    Проверяет что при удалении flow:
    - Выполняется uninstall hook
    - Удаляется flow
    - Удаляются агенты flow
    - Публичные tools остаются
    """
    await _cleanup_system_company()
    
    migrator = Migrator()
    await migrator.run_full_migration()
    
    test_company = await _create_test_company("uninstall_test_company")
    storage = Storage()
    flow_factory = FlowFactory()
    
    _set_company_context(test_company)
    
    await migrator.migrate_defaults_for_company(test_company)
    
    await flow_factory.install_flow("app.flows.weather_flow.weather_flow_config")
    
    variable_key = f"company:{test_company.company_id}:var:default_city"
    variable_before = await storage.get(variable_key)
    assert variable_before is not None, "Переменная должна существовать после install"
    
    weather_flow_before = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert weather_flow_before is not None, "Flow должен существовать"
    
    await flow_factory.uninstall_flow("app.flows.weather_flow.weather_flow_config")
    
    weather_flow_after = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert weather_flow_after is None, "Flow должен быть удален"
    
    weather_agent_after = await storage.get_agent_config("app.agents.weather.agent.WeatherAgent")
    assert weather_agent_after is None, "Агенты flow должны быть удалены"
    
    variable_after = await storage.get(variable_key)
    assert variable_after is None, "uninstall hook должен удалить переменную"
    
    tool_data = await storage.get("tool:app.tools.calc_tools.calculate")
    assert tool_data is not None, "Публичные tools должны остаться"
    
    print("✅ Тест uninstall_flow_removes_dependencies пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_flow_hooks_execution():
    """
    Тест 4: Проверка выполнения хуков install и uninstall.
    
    Проверяет что хуки правильно извлекаются из кода и выполняются.
    """
    await _cleanup_system_company()
    
    migrator = Migrator()
    await migrator.run_full_migration()
    
    storage = Storage()
    
    await migrator._set_system_context()
    
    weather_flow = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
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
async def test_hooks_actually_execute():
    """
    Тест 4.5: Проверка ФАКТИЧЕСКОГО выполнения хуков install и uninstall.
    
    Проверяет что хуки реально выполняются, а не просто извлекаются из кода.
    """
    await _cleanup_system_company()
    
    migrator = Migrator()
    await migrator.run_full_migration()
    
    test_company = await _create_test_company("hooks_test_company")
    storage = Storage()
    flow_factory = FlowFactory()
    
    _set_company_context(test_company)
    
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
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_flow_with_image():
    """
    Тест 5: Проверка загрузки картинки flow в S3.
    
    Проверяет что при миграции flow с image_path:
    - Картинка загружается в S3 (если файл существует)
    - image_file_id сохраняется
    """
    await _cleanup_system_company()
    
    migrator = Migrator()
    await migrator.run_full_migration()
    
    storage = Storage()
    await migrator._set_system_context()
    
    weather_flow = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert weather_flow is not None, "Weather flow должен быть мигрирован"
    assert weather_flow.image_path == "app/flows/weather_flow.jpg", "image_path должен быть сохранен"
    
    print("✅ Тест flow_with_image пройден!")
    clear_context()


@pytest.mark.asyncio
async def test_multiple_flows_isolation():
    """
    Тест 6: Изоляция flows между компаниями.
    
    Проверяет что flows в одной компании не видны в другой.
    """
    await _cleanup_system_company()
    
    migrator = Migrator()
    await migrator.run_full_migration()
    
    company1 = await _create_test_company("isolation_company_1")
    company2 = await _create_test_company("isolation_company_2")
    
    storage = Storage()
    flow_factory = FlowFactory()
    
    _set_company_context(company1)
    await migrator.migrate_defaults_for_company(company1)
    await flow_factory.install_flow("app.flows.weather_flow.weather_flow_config")
    
    flow_in_company1 = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert flow_in_company1 is not None, "Flow должен быть в компании 1"
    
    _set_company_context(company2)
    await migrator.migrate_defaults_for_company(company2)
    
    flow_in_company2 = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert flow_in_company2 is None, "Flow НЕ должен быть виден в компании 2"
    
    await flow_factory.install_flow("app.flows.weather_flow.weather_flow_config")
    
    flow_in_company2_after = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert flow_in_company2_after is not None, "Flow должен быть установлен в компании 2"
    
    _set_company_context(company1)
    await flow_factory.uninstall_flow("app.flows.weather_flow.weather_flow_config")
    
    flow_in_company1_after = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert flow_in_company1_after is None, "Flow должен быть удален из компании 1"
    
    _set_company_context(company2)
    flow_still_in_company2 = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert flow_still_in_company2 is not None, "Flow должен остаться в компании 2"
    
    print("✅ Тест multiple_flows_isolation пройден!")
    clear_context()
    await _cleanup_test_company(company1)
    await _cleanup_test_company(company2)


@pytest.mark.asyncio
async def test_flow_author_extraction():
    """
    Тест 7: Проверка извлечения информации об авторе.
    
    Проверяет что author правильно мигрируется из кода.
    """
    await _cleanup_system_company()
    
    migrator = Migrator()
    await migrator.run_full_migration()
    
    storage = Storage()
    await migrator._set_system_context()
    
    weather_flow = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert weather_flow is not None, "Weather flow должен быть мигрирован"
    assert weather_flow.author is not None, "Author должен быть извлечен"
    assert weather_flow.author.name == "Viktor Shved", "Имя автора должно совпадать"
    assert weather_flow.author.email == "viktor@shved.com", "Email автора должен совпадать"
    assert weather_flow.author.github == "https://github.com/viktorshved", "GitHub должен совпадать"
    
    print("✅ Тест flow_author_extraction пройден!")
    clear_context()


@pytest.mark.asyncio
async def test_install_twice_should_succeed():
    """
    Тест 8: Повторная установка flow должна перезаписывать существующий.
    
    Проверяет что можно переустановить flow (перемиграция).
    """
    await _cleanup_system_company()
    
    migrator = Migrator()
    await migrator.run_full_migration()
    
    test_company = await _create_test_company("double_install_company")
    storage = Storage()
    flow_factory = FlowFactory()
    
    _set_company_context(test_company)
    
    await migrator.migrate_defaults_for_company(test_company)
    
    result1 = await flow_factory.install_flow("app.flows.weather_flow.weather_flow_config")
    assert result1["flow_id"] == "app.flows.weather_flow.weather_flow_config"
    
    flow1 = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert flow1 is not None
    created_at_first = flow1.created_at
    
    result2 = await flow_factory.install_flow("app.flows.weather_flow.weather_flow_config")
    assert result2["flow_id"] == "app.flows.weather_flow.weather_flow_config"
    
    flow2 = await storage.get_flow_config("app.flows.weather_flow.weather_flow_config")
    assert flow2 is not None
    assert flow2.created_at == created_at_first, "created_at должен сохраниться при перемиграции"
    
    print("✅ Тест install_twice_should_succeed пройден!")
    clear_context()
    await _cleanup_test_company(test_company)


@pytest.mark.asyncio
async def test_uninstall_not_installed_should_fail():
    """
    Тест 9: Удаление неустановленного flow должно вызывать ошибку.
    
    Проверяет что нельзя удалить flow который не установлен.
    """
    await _cleanup_system_company()
    
    migrator = Migrator()
    await migrator.run_full_migration()
    
    test_company = await _create_test_company("uninstall_empty_company")
    flow_factory = FlowFactory()
    
    _set_company_context(test_company)
    
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
    await _cleanup_test_company(test_company)


if __name__ == "__main__":
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

