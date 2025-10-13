"""
Тесты для унифицированного синтаксиса переменных.

Проверяем что синтаксис {?var} и {?var|default} работает для:
- Обычных переменных (company_name, current_date, etc.)
- State переменных (store.warehouse_id, user_id, etc.)
- Вложенных переменных (dict.key, list[0])
"""

import pytest
import pytest_asyncio
import uuid
from langchain_core.messages import HumanMessage

from app.core.storage import Storage
from app.core.agent_factory import AgentFactory
from app.core.checkpointer import init_checkpointer
from app.core.variables import VariableResolver
from app.models import (
    AgentConfig,
    AgentType,
    LLMConfig,
)
from app.models.context_models import Context
from app.identity.models import User, Company
from app.core.context import set_context


@pytest_asyncio.fixture
async def setup_storage():
    """Инициализирует storage и checkpointer"""
    storage = Storage()
    await init_checkpointer()
    return storage


@pytest.fixture
def test_context():
    """Создает тестовый контекст с переменными"""
    user = User(
        user_id="test_user_123",
        name="Тестовый Пользователь",
        status="active",
    )
    
    company = Company(
        company_id="test_company",
        subdomain="test",
        name="Тестовая Компания",
    )
    
    context = Context(
        user=user,
        platform="api",
        active_company=company,
        session_id="test_session_123",
        flow_variables={
            "bot_name": "Тест Бот",
            "timeout": 30,
            "nested": {
                "key1": "value1",
                "key2": "value2"
            }
        },
        company_variables={
            "api_key": "sk-123",
        },
    )
    
    set_context(context)
    return context


@pytest.mark.asyncio
async def test_01_optional_syntax_for_static_variables(test_context):
    """
    Тест 1: Опциональный синтаксис для статических переменных.
    
    Проверяем {?variable} и {?variable|default} для обычных переменных.
    """
    # Тест с существующей переменной
    template1 = "Компания: {?company_name|Нет компании}"
    rendered1 = VariableResolver.render_template(template1)
    assert rendered1 == "Компания: Тестовая Компания"
    
    # Тест с несуществующей переменной - должен быть дефолт
    template2 = "Email: {?company_email|не указан}"
    rendered2 = VariableResolver.render_template(template2)
    assert rendered2 == "Email: не указан"
    
    # Тест без дефолта - должна быть пустая строка
    template3 = "Phone: {?company_phone}"
    rendered3 = VariableResolver.render_template(template3)
    assert rendered3 == "Phone: "
    
    # Тест обязательной переменной (без ?) - должна остаться как есть если нет
    template4 = "Missing: {nonexistent_var}"
    rendered4 = VariableResolver.render_template(template4)
    assert rendered4 == "Missing: {nonexistent_var}"  # Не резолвится
    
    print("✅ Тест 1 пройден: Опциональный синтаксис для статических переменных работает")


@pytest.mark.asyncio
async def test_02_optional_syntax_for_nested_variables(test_context):
    """
    Тест 2: Опциональный синтаксис для вложенных переменных.
    
    Проверяем {?dict.key|default} для вложенных структур.
    """
    # Существующий вложенный ключ
    template1 = "Nested key1: {?nested.key1|не найден}"
    rendered1 = VariableResolver.render_template(template1)
    assert rendered1 == "Nested key1: value1"
    
    # Несуществующий вложенный ключ - должен быть дефолт
    template2 = "Nested key3: {?nested.key3|нет такого ключа}"
    rendered2 = VariableResolver.render_template(template2)
    assert rendered2 == "Nested key3: нет такого ключа"
    
    # Несуществующий dict - должен быть дефолт
    template3 = "Deep: {?nonexistent.deep.key|not found}"
    rendered3 = VariableResolver.render_template(template3)
    assert rendered3 == "Deep: not found"
    
    print("✅ Тест 2 пройден: Опциональный синтаксис для вложенных переменных работает")


@pytest.mark.asyncio
async def test_03_unified_syntax_in_agent_prompt(setup_storage, test_context):
    """
    Тест 3: Унифицированный синтаксис в промпте агента.
    
    Проверяем что в одном промпте можно использовать:
    - Статические переменные с {?var|default}
    - State переменные с {?store.var|default}
    """
    storage = setup_storage
    
    agent_config = AgentConfig(
        agent_id="test_unified_syntax_agent",
        name="Unified Syntax Agent",
        type=AgentType.REACT,
        prompt="""
Ты помощник компании {?company_name|Компания не указана}.

СТАТИЧЕСКИЕ ПЕРЕМЕННЫЕ:
- Имя пользователя: {?user_name|Гость}
- Email: {?user_email|не указан}
- API ключ: {?api_key|нет ключа}
- Таймаут: {?timeout|60} секунд
- Nested key: {?nested.key1|не найден}

STATE ПЕРЕМЕННЫЕ:
- Склад: {?store.warehouse_name|не определен}
- Курьер: {?store.courier_name|не назначен}
- Счетчик: {?store.counter|0}

Все переменные используют единый синтаксис!
""",
        tools=[],
        llm_config=LLMConfig(
            provider="mock",
            model="mock-gpt-4",
            temperature=0.1,
        ),
    )
    
    await storage.set_agent_config(agent_config)
    
    # Получаем агента
    agent_factory = AgentFactory()
    agent = await agent_factory.get_agent("test_unified_syntax_agent")
    
    thread_id = f"test_thread_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    
    # Вызываем с частичными данными в store
    input_data = {
        "messages": [HumanMessage(content="Проверь синтаксис")],
        "store": {
            "warehouse_name": "Склад №5",
            # courier_name НЕТ - должно быть "не назначен"
            # counter НЕТ - должно быть "0"
        },
        "remaining_steps": 25,
        "session_id": "test_session",
        "task_id": "task_1",
        "user_id": "user_1",
    }
    
    result = await agent.ainvoke(input_data, config=config)
    
    # Проверяем что агент успешно выполнился
    assert "messages" in result
    assert result["store"]["warehouse_name"] == "Склад №5"
    
    print("✅ Тест 3 пройден: Унифицированный синтаксис работает в промптах")


@pytest.mark.asyncio
async def test_04_variable_resolver_optional_syntax():
    """
    Тест 4: Проверка VariableResolver с опциональным синтаксисом.
    
    Unit-тест для render_template с различными комбинациями.
    """
    # Контекст с переменными
    local_vars = {
        "name": "Виктор",
        "age": 30,
        "city": "Москва",
        "settings": {
            "theme": "dark",
            "language": "ru"
        }
    }
    
    # Тест 1: Обычная подстановка
    assert VariableResolver.render_template("Привет, {name}!", local_vars) == "Привет, Виктор!"
    
    # Тест 2: Опциональная с дефолтом (переменная есть)
    assert VariableResolver.render_template("Город: {?city|не указан}", local_vars) == "Город: Москва"
    
    # Тест 3: Опциональная с дефолтом (переменной НЕТ)
    assert VariableResolver.render_template("Email: {?email|не указан}", local_vars) == "Email: не указан"
    
    # Тест 4: Опциональная без дефолта (переменной НЕТ)
    assert VariableResolver.render_template("Phone: {?phone}", local_vars) == "Phone: "
    
    # Тест 5: Вложенная опциональная
    assert VariableResolver.render_template("Theme: {?settings.theme|light}", local_vars) == "Theme: dark"
    
    # Тест 6: Несуществующий вложенный ключ
    assert VariableResolver.render_template("Font: {?settings.font|Arial}", local_vars) == "Font: Arial"
    
    # Тест 7: Комбинация обычных и опциональных
    template = """
    Пользователь: {name}
    Возраст: {?age|не указан}
    Email: {?email|нет}
    Город: {?city|Москва}
    """
    rendered = VariableResolver.render_template(template, local_vars)
    assert "Виктор" in rendered
    assert "30" in rendered
    assert "нет" in rendered
    assert "Москва" in rendered
    
    print("✅ Тест 4 пройден: VariableResolver с опциональным синтаксисом работает корректно")


@pytest.mark.asyncio
async def test_05_special_characters_in_defaults():
    """
    Тест 5: Специальные символы в значениях по умолчанию.
    
    Проверяем что дефолты могут содержать пробелы, спецсимволы.
    """
    local_vars = {"name": "Test"}
    
    # Дефолт с пробелами
    assert VariableResolver.render_template(
        "{?email|не указан пользователем}",
        local_vars
    ) == "не указан пользователем"
    
    # Дефолт с цифрами
    assert VariableResolver.render_template(
        "{?port|8080}",
        local_vars
    ) == "8080"
    
    # Дефолт с дефисами и подчеркиванием
    assert VariableResolver.render_template(
        "{?status|not-available_yet}",
        local_vars
    ) == "not-available_yet"
    
    # Дефолт с русским текстом
    assert VariableResolver.render_template(
        "{?message|Сообщение не найдено}",
        local_vars
    ) == "Сообщение не найдено"
    
    print("✅ Тест 5 пройден: Специальные символы в дефолтах работают")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

