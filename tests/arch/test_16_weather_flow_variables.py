"""
Тесты для проверки переменных в WeatherFlow.

Проверяем:
1. Flow variables подставляются в промпты WeatherAgent и TravelInfoAgent
2. Session Store подставляется в промпты обоих агентов
3. Системные переменные работают
4. Специальные функции (#messages.count) работают
5. Унифицированный синтаксис {?var|default} работает для всех типов
"""

import pytest
from langchain_core.messages import HumanMessage

from app.models import FlowConfig


@pytest.mark.asyncio
async def test_01_weather_flow_has_store_config(migrated_db, storage, test_context, flow_repo):
    """
    Тест 1: WeatherFlow имеет конфигурацию store.
    
    ВАЖНО: Store теперь задается в FlowConfig, а НЕ в агенте!
    """
    from app.flows.weather_flow import weather_flow_config
    
    # Проверяем что у FlowConfig есть store (НЕ у агента!)
    assert hasattr(weather_flow_config, 'store')
    assert weather_flow_config.store is not None
    assert isinstance(weather_flow_config.store, dict)
    
    print(f"✅ WeatherFlow.store определен: {weather_flow_config.store}")
    print(f"   Ключей в store: {len(weather_flow_config.store)}")


@pytest.mark.asyncio
async def test_01b_travel_info_agent_uses_store_in_prompt(migrated_db, storage, test_context):
    """
    Тест 1b: TravelInfoAgent использует store переменные в промпте.
    
    Проверяем что в промпте есть обращения к store.
    """
    from app.agents.weather.agent import TravelInfoAgent
    
    # Проверяем промпт
    assert TravelInfoAgent.prompt is not None
    assert "{?store.travel_destination" in TravelInfoAgent.prompt
    assert "session_set" in TravelInfoAgent.prompt
    
    # Проверяем что в tools есть session_set
    travel_tools_ids = [str(t) for t in TravelInfoAgent.tools]
    assert any("session_set" in str(t) for t in travel_tools_ids)
    
    print(f"✅ TravelInfoAgent использует store переменные в промпте")


@pytest.mark.asyncio
async def test_02_weather_agent_prompt_has_variables(migrated_db, storage, test_context):
    """
    Тест 2: WeatherAgent промпт содержит переменные разных типов.
    
    Проверяем что в промпте используются:
    - Системные переменные
    - Flow variables  
    - Store variables
    - Унифицированный синтаксис
    """
    from app.agents.weather.agent import WeatherAgent
    
    prompt = WeatherAgent.prompt
    
    # Системные переменные
    assert "{current_date}" in prompt
    assert "{current_time}" in prompt
    assert "{?user_name|" in prompt or "{user_name}" in prompt
    assert "{?company_name|" in prompt
    
    # Store переменные с унифицированным синтаксисом
    assert "{?store.last_city|" in prompt
    assert "{?store.last_temperature|" in prompt
    assert "{?store.travel_destination|" in prompt
    assert "{?store.requests_count|" in prompt
    assert "{?store.show_tips|" in prompt
    
    # Специальные функции
    assert "{#messages.count}" in prompt
    
    # Условные блоки
    assert "{?store.last_city:" in prompt  # Начало условного блока
    
    print(f"✅ WeatherAgent.prompt содержит все типы переменных")
    print(f"   Длина промпта: {len(prompt)} символов")


@pytest.mark.asyncio
async def test_03_weather_flow_has_store_config(migrated_db, storage, test_context):
    """
    Тест 3: WeatherFlow имеет конфигурацию store.
    
    Проверяем что у flow есть поле store с начальными значениями.
    """
    from app.flows.weather_flow import weather_flow_config
    
    # Проверяем что у flow_config есть store
    assert hasattr(weather_flow_config, 'store')
    assert weather_flow_config.store is not None
    assert isinstance(weather_flow_config.store, dict)
    
    # Проверяем наличие ключей
    assert "max_requests_per_session" in weather_flow_config.store
    assert "show_welcome" in weather_flow_config.store
    assert "language_preference" in weather_flow_config.store
    
    # Проверяем что есть @var: ссылки
    assert weather_flow_config.store["language_preference"] == "@var:default_language"
    assert weather_flow_config.store["api_key"] == "@var:weather_api_key"
    
    print(f"✅ WeatherFlow.store определен: {weather_flow_config.store}")
    print(f"   Ключей в store: {len(weather_flow_config.store)}")


@pytest.mark.asyncio
async def test_04_weather_flow_has_variables_config(migrated_db, storage, test_context):
    """
    Тест 4: WeatherFlow имеет конфигурацию variables.
    
    Проверяем что у flow есть поле variables с настройками.
    """
    from app.flows.weather_flow import weather_flow_config
    
    # Проверяем что у flow_config есть variables
    assert hasattr(weather_flow_config, 'variables')
    assert weather_flow_config.variables is not None
    assert isinstance(weather_flow_config.variables, dict)
    
    # Проверяем наличие ключей
    assert "bot_name" in weather_flow_config.variables
    assert "greeting" in weather_flow_config.variables
    assert "timeout_minutes" in weather_flow_config.variables
    
    # Проверяем вложенные структуры
    assert "settings" in weather_flow_config.variables
    assert isinstance(weather_flow_config.variables["settings"], dict)
    assert "temperature_unit" in weather_flow_config.variables["settings"]
    
    # Проверяем что есть @var: ссылки
    assert weather_flow_config.variables["support_email"] == "@var:company_support_email"
    assert weather_flow_config.variables["api_key"] == "@var:weather_api_key"
    
    print(f"✅ WeatherFlow.variables определен: {list(weather_flow_config.variables.keys())}")
    print(f"   Вложенная структура settings: {weather_flow_config.variables['settings']}")


@pytest.mark.asyncio
async def test_05_all_variable_types_in_prompt(migrated_db, storage, test_context):
    """
    Тест 5: Все типы переменных работают в одном промпте.
    
    Проверяем что в одном промпте одновременно работают:
    - Системные ({current_date}, {company_name})
    - Flow variables ({bot_name}, {timeout})
    - Store variables ({store.last_city}, {#messages.count})
    - Опциональный синтаксис ({?var|default})
    """
    from app.core.variables import VariableResolver
    from app.core.context import get_context
    
    # Устанавливаем flow variables в глобальный контекст
    context = get_context()
    context.flow_variables = {
        "bot_name": "Weather Bot",
        "timeout": 30,
        "greeting": "Привет от погодного бота!"
    }
    
    # Тестовый промпт со ВСЕМИ типами переменных
    prompt = """
Ты {bot_name} компании {?company_name|Weather Service}.
Дата: {current_date}, Пользователь: {?user_name|Гость}

СТАТИЧЕСКИЕ:
- Приветствие: {greeting}
- Таймаут: {?timeout|60} минут
- Email: {?support_email|support@company.com}

ДИНАМИЧЕСКИЕ (будут после рендеринга state):
- Последний город: {?store.last_city|нет}
- Счетчик: {?store.requests_count|0}
- Сообщений: {#messages.count}
"""
    
    # Рендерим статические переменные
    static_rendered = VariableResolver.render_template(prompt)
    
    # Проверяем что статические переменные подставились
    assert "Weather Bot" in static_rendered
    assert context.active_company.name in static_rendered
    assert context.user.name in static_rendered
    assert "Привет от погодного бота!" in static_rendered
    assert "30 минут" in static_rendered
    assert "support@company.com" in static_rendered
    
    # Проверяем что store переменные тоже попытались зарезолвиться
    # VariableResolver работает со статическими переменными, store в нем нет
    # Поэтому {?store.last_city|нет} → "нет" (дефолт)
    # А {#messages.count} останется как есть (это не переменная, а спец функция)
    assert "Последний город: нет" in static_rendered  # Дефолт подставился
    assert "Счетчик: 0" in static_rendered  # Дефолт подставился
    
    # NOTE: В реальности state_modifier перезапишет эти значения динамически
    # Но VariableResolver корректно обработал опциональный синтаксис
    
    print("✅ Тест 5 пройден: Все типы переменных работают в одном промпте")


@pytest.mark.asyncio
async def test_06_optional_syntax_consistency(test_context):
    """
    Тест 6: Опциональный синтаксис работает единообразно.
    
    Проверяем что {?var|default} работает для:
    - Системных переменных
    - Flow переменных
    - Вложенных переменных
    """
    from app.core.variables import VariableResolver
    
    context = test_context
    context.flow_variables = {
        "existing_var": "значение",
        "nested": {
            "key1": "value1"
        }
    }
    
    # Существующие переменные
    assert VariableResolver.render_template("{?company_name|НЕТ}") == "Test Company"
    assert VariableResolver.render_template("{?existing_var|НЕТ}") == "значение"
    assert VariableResolver.render_template("{?nested.key1|НЕТ}") == "value1"
    
    # Несуществующие переменные
    assert VariableResolver.render_template("{?nonexistent|ДЕФОЛТ}") == "ДЕФОЛТ"
    assert VariableResolver.render_template("{?nested.missing|ДЕФОЛТ}") == "ДЕФОЛТ"
    
    # Без дефолта
    assert VariableResolver.render_template("{?nonexistent}") == ""
    
    print("✅ Тест 6 пройден: Опциональный синтаксис единообразен")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

