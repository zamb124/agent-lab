---
trigger: manual
description:
globs:
---

# Правила работы с переменными и Session Store

## Унифицированный синтаксис переменных

Используй ЕДИНЫЙ синтаксис для ВСЕХ типов переменных (статических и динамических):

```python
{variable}              # Обычная подстановка
{?variable}             # Опциональная (пустая строка если нет)
{?variable|default}     # С дефолтом
{dict.key}              # Вложенные данные
{#messages.count}       # Специальные функции (state)
```

<good_example>
prompt = """
Ты {bot_name} компании {?company_name|Weather Service}.

СТАТИЧЕСКИЕ:
- Email: {?support_email|support@company.com}
- Таймаут: {?timeout|30} минут

ДИНАМИЧЕСКИЕ:
- Последний город: {?store.last_city|нет}
- Запросов: {?store.count|0}
- Сообщений: {#messages.count}
"""
</good_example>

<bad_example>
# Не используй разный синтаксис
prompt = """
Email: {support_email}           # Не опциональный
Город: {store.last_city}         # Упадет если нет
"""
</bad_example>

## Типы переменных

### Статические переменные (variables)

Резолвятся ОДИН РАЗ при компиляции графа:
- Системные: `{company_name}`, `{current_date}`, `{user_name}`
- Flow: из `FlowConfig.variables`
- Local: из `AgentConfig.local_variables`

<good_example>
FlowConfig(
    variables={
        "bot_name": "Support Bot",
        "timeout": 30,
        "email": "@var:support_email"  # Ссылка на company variable
    }
)
</good_example>

### Динамические переменные (store)

Резолвятся ДИНАМИЧЕСКИ перед каждым вызовом LLM:
- Из `FlowConfig.store` или `AgentConfig.store` (начальные значения)
- Из `state["store"]` (runtime изменения)
- Персистятся автоматически в PostgreSQL

<good_example>
FlowConfig(
    store={
        "max_requests": 10,
        "show_welcome": True,
        "api_key": "@var:weather_api_key"  # Ссылка работает и здесь
    }
)

AgentConfig(
    store={
        "requests_count": 0,
        "preferred_units": "celsius"
    }
)
</good_example>

## Работа с Session Store

### Инициализация

Flow и Agent могут задавать начальные значения:

<good_example>
# Во Flow
FlowConfig(
    store={
        "max_requests_per_session": 10,
        "language": "@var:default_language"
    }
)

# В Agent
AgentConfig(
    store={
        "requests_count": 0,
        "show_tips": True
    }
)

# При первом вызове store = {max_requests_per_session: 10, language: "ru", requests_count: 0, show_tips: true}
</good_example>

### Изменение в тулах

<good_example>
from app.core.variables import get_state

@tool
def save_warehouse(warehouse_id: str, warehouse_name: str) -> str:
    state = get_state()
    state["store"]["warehouse_id"] = warehouse_id
    state["store"]["warehouse_name"] = warehouse_name
    # ✅ Автоматически сохранится в БД
    return "Сохранено"
</good_example>

<bad_example>
@tool
def save_warehouse(warehouse_id: str) -> str:
    # Не используй глобальные переменные!
    global saved_warehouse_id
    saved_warehouse_id = warehouse_id
    return "Сохранено"
</bad_example>

### Изменение через session_tools

<good_example>
from app.tools.session_tools import session_set, session_get

class MyAgent(BaseAgent):
    prompt = """
    Сохрани результат через session_set("last_result", "значение")
    Получи через session_get("last_result")
    """
    tools = [session_set, session_get]
</good_example>

## Общий store между агентами

**ВАЖНО:** Store общий для ВСЕХ агентов в цепочке:

<good_example>
# Координатор
state["store"]["user_id"] = "123"

# Субагент видит изменения координатора
user_id = state["store"]["user_id"]  # "123"

# Субагент добавляет свои данные
state["store"]["warehouse_id"] = "456"

# Координатор видит изменения субагента
warehouse_id = state["store"]["warehouse_id"]  # "456"
</good_example>

## Использование в промптах

### Базовый паттерн

<good_example>
prompt = """
Ты {bot_name}.

КОНТЕКСТ:
- Пользователь: {?user_name|Гость}
- Сообщений: {#messages.count}

ИСТОРИЯ:
- Последний запрос: {?store.last_query|нет}
- Всего запросов: {?store.total_count|0}

{?store.last_query:
  ПРИМЕЧАНИЕ: Ранее вы спрашивали: "{store.last_query}"
}

После выполнения ОБЯЗАТЕЛЬНО сохрани:
- session_set("last_query", "текст запроса")
- session_set("total_count", "{store.total_count|0} + 1")
"""
</good_example>

### Условная логика

<good_example>
prompt = """
{?store.warehouse_id:
  ✅ СКЛАД ОПРЕДЕЛЕН: {store.warehouse_name} (ID: {store.warehouse_id})
  Переходи к следующему этапу - определению курьера.
|
  ⏳ СКЛАД НЕ ОПРЕДЕЛЕН
  Сначала используй warehouse_agent для определения склада.
}
"""
</good_example>

<bad_example>
prompt = """
# Не проверяй наличие переменной в коде промпта
Склад: {store.warehouse_name}  # Упадет если нет

# Используй опциональный синтаксис
Склад: {?store.warehouse_name|не определен}
"""
</bad_example>

## Специальные функции

Только для state переменных:

<good_example>
prompt = """
Сообщений в диалоге: {#messages.count}
Ключи в store: {#store.keys}
Store пустой: {#store.empty}
"""
</good_example>

## Когда использовать variables vs store

### Используй variables (статические) для:
- Конфигурация (bot_name, timeout, api_endpoint)
- Константы (max_retries, default_language)
- Секреты (api_key, bot_token)
- Настройки которые НЕ меняются во время диалога

### Используй store (динамические) для:
- Накопление данных (warehouse_id, courier_id, issue_id)
- Счетчики (requests_count, attempts)
- Флаги состояния (welcome_shown, stage_completed)
- История диалога (last_query, last_result)
- Контекст пользователя (temporary_data)

<good_example>
FlowConfig(
    # Статические настройки
    variables={
        "bot_name": "Support Bot",
        "max_retries": 3,
        "api_key": "@var:support_api_key"
    },
    
    # Динамические данные сессии
    store={
        "welcome_shown": False,
        "current_stage": "init",
        "collected_data": {}
    }
)
</good_example>

## Настройка переменных при установке Flow

### Variables Definitions

Для публичных flows (is_public=True) можно определить переменные, которые нужно заполнить при установке из Store:

<good_example>
FlowConfig(
    name="Weather Flow",
    variables_definitions=[
        {
            "key": "weather_api_key",
            "description": "API ключ сервиса погоды (OpenWeatherMap)",
            "is_secret": True,
            "required": True
        },
        {
            "key": "default_city",
            "description": "Город по умолчанию для прогноза погоды",
            "default_value": "Москва",
            "is_secret": False,
            "required": True
        },
        {
            "key": "company_city",
            "description": "Город компании для демонстрации",
            "default_value": "Санкт-Петербург",
            "is_secret": False,
            "required": False
        }
    ]
)
</good_example>

### Поля VariableDefinition

- **key**: имя переменной (используется как @var:key в коде)
- **description**: описание для пользователя в UI
- **default_value**: значение по умолчанию (опционально)
- **is_secret**: скрытый ввод (пароль) + шифрование в БД
- **required**: обязательно ли заполнить при установке

### Автоматическая валидация

Пудантические модели автоматически валидируют и конвертируют словари в VariableDefinition объекты:

<good_example>
# Можно писать как словари
variables_definitions=[
    {"key": "api_key", "description": "API ключ", "is_secret": True}
]

# Автоматически становится VariableDefinition объектами
# С валидацией типов и обязательных полей
</good_example>

### Создание переменных при установке

При установке flow из Store переменные автоматически создаются в VariablesService:

- Обязательные поля проверяются перед установкой
- Секретные переменные шифруются
- Переменные доступны через @var:key в platforms, variables, store

<good_example>
# В flow после установки
platforms={
    "telegram": {
        "token": "@var:weather_bot_token"  # Создана при установке
    }
}

variables={
    "api_key": "@var:weather_api_key"  # Создана при установке
}
</good_example>

## Работа с VariablesService через контейнер

VariablesService доступен через контейнер для программной работы с переменными:

<good_example>
from app.core.container import get_container
from app.frontend.dependencies import VariablesServiceDep

# В коде (сервисы, фабрики)
container = get_container()
variables_service = container.variables_service

# Установка переменной
await variables_service.set_var("api_key", "secret_value", is_secret=True)

# Получение переменной
api_key = await variables_service.get_var("api_key")

# Список всех переменных
all_vars = await variables_service.list_vars()

# В FastAPI endpoints
@router.post("/variables/{key}")
async def set_variable(
    key: str,
    value: str,
    variables_service: VariablesServiceDep
):
    await variables_service.set_var(key, value)
    return {"success": True}

@router.get("/variables")
async def list_variables(variables_service: VariablesServiceDep):
    return await variables_service.list_vars()
</good_example>

<bad_example>
# ❌ НЕ импортируй VariablesService напрямую
from app.services.variables_service import VariablesService

# ❌ НЕ создавай экземпляр вручную
variables_service = VariablesService()

# ✅ Используй через контейнер
container = get_container()
variables_service = container.variables_service
</bad_example>

