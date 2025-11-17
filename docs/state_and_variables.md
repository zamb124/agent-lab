# Система State и Переменных

Единая система для работы с сессионными данными и переменными в агентах.

## Архитектура

### State

`State` - единый TypedDict для всех агентов (ReAct и StateGraph), который:
- Автоматически персистится через StateManager
- Доступен в тулах через контекст `get_state()`
- Содержит сессионное хранилище `store`

```python
from app.core.state import State

class State(TypedDict):
    messages: List  # История диалога
    store: Dict[str, Any]  # Сессионное хранилище
    task_id: str
    session_id: str
    user_id: str
```

### Context

`Context` - глобальный контекст запроса, который содержит:
- Данные пользователя и компании
- Переменные flow и компании
- Ссылку на текущий state агента

```python
from app.core.context import get_context

context = get_context()
# context.user - пользователь
# context.active_company - компания
# context.flow_variables - переменные flow
# context.state - текущий state агента
```

## Использование

### 1. Переменные в конфигурации

#### Переменные Flow

```json
{
  "flow_id": "support_flow",
  "name": "Поддержка",
  "variables": {
    "bot_name": "Помощник",
    "support_email": "support@company.com",
    "working_hours": "9:00-18:00",
    "max_wait_time": 30
  }
}
```

#### Переменные Агента

```json
{
  "agent_id": "greeting_agent",
  "name": "Приветствие",
  "prompt": "Привет! Я {bot_name}. Наши часы работы: {working_hours}.",
  "local_variables": {
    "greeting": "Здравствуйте!",
    "max_attempts": 3
  }
}
```

### 2. Использование переменных в промптах

Переменные автоматически подставляются при использовании `{variable}`:

```python
prompt = """
Привет! Я {bot_name} компании {company_name}.

Наши часы работы: {working_hours}
Email: {support_email}

Доступные переменные:
- user_name: {user_name}
- current_date: {current_date}
"""
```

**Доступные системные переменные:**
- `current_date` - текущая дата (YYYY-MM-DD)
- `current_time` - текущее время (HH:MM)
- `current_datetime` - дата и время
- `current_year`, `current_month`, `current_day`
- `company_name` - название компании
- `company_id` - ID компании
- `user_name` - имя пользователя
- `user_id` - ID пользователя

### 3. Сессионное хранилище в тулах

Используйте готовые тулы для работы с сессией:

```python
from app.tools.session.session_tools import (
    session_set,
    session_get,
    session_has,
    session_delete,
    session_keys,
    get_variable
)

# В конфигурации агента
tools = [
    ToolReference(tool_id="app.tools.session.session_tools.session_set"),
    ToolReference(tool_id="app.tools.session.session_tools.session_get"),
]
```

#### Примеры использования в агенте:

```python
# Агент может сохранять данные между запросами
tools = [session_set, session_get, session_has]

prompt = """
Ты агент поддержки.

ВАЖНО: Используй session_set для сохранения важной информации:
- session_set("user_warehouse", "название склада")
- session_get("user_warehouse") - получить склад

Сохраняй все что узнаешь о пользователе.
"""
```

### 4. Доступ к State из кастомных тулов

```python
from langchain_core.tools import tool
from app.core.variables import get_state

@tool
def my_custom_tool(data: str) -> str:
    """Кастомный тул с доступом к state"""
    state = get_state()
    
    if not state:
        return "State недоступен"
    
    # Читаем из store
    previous_data = state.get("store", {}).get("my_key")
    
    # Пишем в store
    if "store" not in state:
        state["store"] = {}
    state["store"]["my_key"] = data
    
    return f"Сохранено: {data}"
```

### 5. Работа с переменными в коде

```python
from app.core.variables import VariableResolver

# Получить все переменные
variables = VariableResolver.resolve_all()

# Получить с локальными переменными
variables = VariableResolver.resolve_all(
    local_vars={"my_var": "value"}
)

# Рендерить шаблон
result = VariableResolver.render_template(
    "Привет, {user_name}! Компания: {company_name}",
    local_vars={"custom": "value"}
)
```

## Примеры сценариев

### Сценарий 1: Сбор данных о пользователе

```python
# Агент последовательно собирает данные
class DataCollectorAgent(BaseAgent):
    prompt = """
    Собери информацию о пользователе:
    1. Имя склада
    2. Номер курьера
    3. Описание проблемы
    
    Используй session_set для сохранения каждого ответа:
    - session_set("warehouse_name", "...")
    - session_set("courier_id", "...")
    - session_set("issue_description", "...")
    
    Проверяй что уже сохранено с помощью session_has.
    """
    
    tools = [session_set, session_get, session_has, ask_user]
```

### Сценарий 2: Передача данных между агентами

```python
# Первый агент сохраняет
class Agent1(BaseAgent):
    prompt = """
    Узнай у пользователя склад и сохрани:
    session_set("warehouse_id", "12345")
    """
    tools = [session_set, ask_user]

# Второй агент использует
class Agent2(BaseAgent):
    prompt = """
    Получи склад из сессии:
    warehouse_id = session_get("warehouse_id")
    
    Используй его для дальнейшей работы.
    """
    tools = [session_get]
```

### Сценарий 3: StateGraph с единым State

```python
from app.core.state import State

def warehouse_node(state: State) -> State:
    """Нода определения склада"""
    warehouse_id = "12345"  # Логика определения
    
    # Сохраняем в store
    state["store"]["warehouse_id"] = warehouse_id
    state["store"]["warehouse_name"] = "Большие Каменщики"
    
    return state

def courier_node(state: State) -> State:
    """Нода работы с курьером"""
    # Читаем из store
    warehouse_id = state["store"].get("warehouse_id")
    
    # Работаем с данными
    courier_id = find_courier(warehouse_id)
    state["store"]["courier_id"] = courier_id
    
    return state
```

## Приоритет переменных

1. **Локальные переменные агента** (наивысший приоритет)
2. **Переменные flow**
3. **Переменные компании**
4. **Системные переменные**

## StateManager

`StateManager` - менеджер состояния для агентов, который обеспечивает персистентность через PostgreSQL.

### Архитектура

StateManager использует две таблицы PostgreSQL:

1. **`stores`** - единое хранилище `store` для всего flow (по `store_id`)
2. **`agent_states`** - состояние агента с `messages` и метаданными (по `session_id`)

#### Разделение данных

**Store (единый для flow):**
- Хранится в таблице `stores` по `store_id`
- Для родительских сессий: `store_id = session_id`
- Для sub-сессий: `store_id` наследуется от родителя
- Все агенты в flow видят один и тот же `store`

**State (индивидуальный для сессии):**
- Хранится в таблице `agent_states` по `session_id`
- Содержит `messages`, `task_id`, `user_id`, `remaining_steps`, `interrupt_context`
- Ссылается на `store` через `store_id`

### Основные методы

#### load_state

Загружает состояние для сессии. Для sub-сессий автоматически определяет политику памяти из формата `session_id`.

```python
from app.core.state_manager import get_state_manager

state_manager = await get_state_manager()

# Обычная сессия
state = await state_manager.load_state("user_session_123")

# Sub-сессия (автоматически применяет политику)
sub_state = await state_manager.load_state("parent:sub:agent:accumulated")
```

#### save_state

Сохраняет состояние для сессии и синхронизирует `store` в контексте.

**ВАЖНО**: `store` всегда берется из контекста (обновлен через `session_set`).

```python
from app.core.state_manager import get_state_manager

state_manager = await get_state_manager()

# Сохранение (store автоматически синхронизируется)
await state_manager.save_state(session_id, state)

# Для sub-сессий автоматически обновляется parent_state["store"] в контексте
```

#### load_state_for_sub_agent

Загружает состояние для субагента с учетом политики памяти.

**ВАЖНО**: `store` всегда берется из родительской сессии (единый для всего flow).

```python
from app.core.state_manager import get_state_manager

state_manager = await get_state_manager()

# Загрузка для субагента (store из родителя)
sub_state = await state_manager.load_state_for_sub_agent(
    sub_session_id="parent:sub:agent:accumulated",
    parent_state=parent_state
)
```

### Политики памяти для субагентов

StateManager поддерживает 4 политики памяти для субагентов:

#### ISOLATED (по умолчанию)

Каждый вызов субагента создает новую сессию с новой памятью.

**Формат session_id:**
```
{parent_session_id}:sub:{agent_id}:{unique_uuid}
```

**Поведение:**
- Новые `messages` для каждого вызова
- `store` единый через ссылку на родителя
- Состояние сохраняется только для interrupt

#### ACCUMULATED

Накопление памяти между вызовами (один `session_id` для всех вызовов).

**Формат session_id:**
```
{parent_session_id}:sub:{agent_id}:accumulated
```

**Поведение:**
- Фиксированный `session_id` для всех вызовов
- `messages` накапливаются между вызовами
- `store` единый через ссылку на родителя
- Состояние сохраняется после каждого вызова

#### SNAPSHOT

Копирует память родителя при вызове, но возвращает только результат.

**Формат session_id:**
```
{parent_session_id}:sub:{agent_id}:snapshot:{unique_uuid}
```

**Поведение:**
- Новый `session_id` для каждого вызова (с маркером `snapshot`)
- `messages` копируются из родителя при первом вызове
- `store` единый через ссылку на родителя
- Состояние сохраняется только для interrupt

#### SHARED

Работает в одной памяти с родителем (один `session_id`).

**Формат session_id:**
```
{parent_session_id}  # Та же сессия!
```

**Поведение:**
- Использует `session_id` родителя напрямую
- Полный доступ к `messages` и `store` родителя
- Изменения видны родителю сразу

### Синхронизация store

**ВАЖНО**: `store` всегда единый для всего flow через `store_id`.

```python
# Родительская сессия
parent_state = {
    "session_id": "parent",
    "store_id": "parent",  # store_id = session_id для родителя
    "store": {"warehouse_id": "12345"}
}

# Sub-сессия наследует store_id
sub_state = {
    "session_id": "parent:sub:agent:abc123",
    "store_id": "parent",  # Наследуется от родителя!
    "store": parent_state["store"]  # Та же ссылка
}

# Изменения в sub_state["store"] видны в parent_state["store"]
sub_state["store"]["courier_id"] = "67890"
# parent_state["store"]["courier_id"] == "67890"  # Видно сразу!
```

После сохранения sub-сессии `store` автоматически синхронизируется в контексте родителя.

### Генерация sub_session_id

Используй `get_sub_session_id` для генерации правильного `sub_session_id`:

```python
from app.core.state_manager import get_state_manager
from app.models.core_models import SubAgentMemoryPolicy

state_manager = await get_state_manager()

# ISOLATED
sub_session_id = await state_manager.get_sub_session_id(
    parent_session_id="parent",
    sub_agent_id="app.agents.weather.agent.WeatherAgent",
    policy=SubAgentMemoryPolicy.ISOLATED
)
# "parent:sub:app.agents.weather.agent.WeatherAgent:abc123"

# ACCUMULATED
sub_session_id = await state_manager.get_sub_session_id(
    parent_session_id="parent",
    sub_agent_id="app.agents.weather.agent.WeatherAgent",
    policy=SubAgentMemoryPolicy.ACCUMULATED
)
# "parent:sub:app.agents.weather.agent.WeatherAgent:accumulated"

# SHARED
sub_session_id = await state_manager.get_sub_session_id(
    parent_session_id="parent",
    sub_agent_id="app.agents.weather.agent.WeatherAgent",
    policy=SubAgentMemoryPolicy.SHARED
)
# "parent" (та же сессия)
```

## Персистентность

### Что персистится автоматически:
- `messages` - история диалога (в `agent_states`)
- `store` - сессионное хранилище (в `stores` по `store_id`)
- Весь `State` через StateManager

### Что НЕ персистится:
- `variables` из Context (заполняются при каждом запросе)
- `flow_variables` из Context (заполняются из FlowConfig)

## Best Practices

1. **Используйте `store` для данных между запросами**
   ```python
   state["store"]["user_data"] = {...}
   ```

2. **Используйте переменные для констант**
   ```json
   {
     "variables": {
       "max_retries": 3,
       "timeout_seconds": 30
     }
   }
   ```

3. **Проверяйте наличие данных**
   ```python
   if session_has("warehouse_id") == "yes":
       warehouse = session_get("warehouse_id")
   ```

4. **Документируйте переменные в промпте**
   ```python
   prompt = """
   Доступные переменные:
   - {bot_name} - название бота
   - {support_email} - email поддержки
   """
   ```

5. **Используйте понятные ключи**
   ```python
   # Хорошо
   session_set("user_warehouse_id", "12345")
   
   # Плохо
   session_set("uw", "12345")
   ```

## Миграция с существующего кода

### Было (SessionConfig.metadata):
```python
session_config.metadata["warehouse_id"] = "12345"
```

### Стало (State.store):
```python
# В агенте
session_set("warehouse_id", "12345")

# В кастомном коде
state["store"]["warehouse_id"] = "12345"
```

### Было (хардкод в промпте):
```python
prompt = "Привет! Я Помощник компании ABC."
```

### Стало (переменные):
```python
# В FlowConfig.variables
{"bot_name": "Помощник", "company_name": "ABC"}

# В промпте
prompt = "Привет! Я {bot_name} компании {company_name}."
```
