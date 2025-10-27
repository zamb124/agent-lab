# Система переменных и секретов

Централизованное управление переменными и секретами с изоляцией per-company.

## Архитектура

### Хранение

**Storage (одна таблица `variables`):**
```
company:ssd:var:telegram_bot_token = {"value": "123:ABC...", "secret": true}
company:ssd:var:bot_name = {"value": "My Bot", "secret": false}
company:acme:var:telegram_bot_token = {"value": "456:XYZ...", "secret": true}
```

**Таблица БД:**
- `variables` - единая таблица для всех компаний
- Изоляция через префикс ключа `company:{company_id}:var:{key}`
- Автоматическая изоляция через Storage маршрутизацию между компаниями

### Синтаксис ссылок

**@var:key** - ссылка на переменную компании

```python
# Хардкод
"token": "8395450365:AAHSUMIq84eZpjIRwKljo"

# Ссылка на переменную
"token": "@var:telegram_bot_token"
```

## API

### Сохранение переменной

```bash
POST /api/v1/admin/variables
Content-Type: application/json

{
  "key": "telegram_bot_token",
  "value": "8395450365:AAHSUMIReZpjIRwKljo",
  "secret": true
}
```

### Получение списка переменных

```bash
GET /api/v1/admin/variables

Response:
{
  "telegram_bot_token": {
    "value": "***",  # Скрыто для секретов
    "secret": true
  },
  "bot_name": {
    "value": "My Bot",
    "secret": false
  }
}
```

### Получение переменной

```bash
GET /api/v1/admin/variables/bot_name

Response:
{
  "key": "bot_name",
  "value": "My Bot"
}
```

### Удаление переменной

```bash
DELETE /api/v1/admin/variables/telegram_bot_token
```

## Scope переменных

### 1. Системные переменные (автоматические):
- `{company_name}`, `{company_id}`, `{company_subdomain}` - из активной компании
- `{user_name}`, `{user_id}` - из текущего пользователя
- `{current_date}`, `{current_time}`, `{current_datetime}` - текущая дата/время
- `{current_year}`, `{current_month}`, `{current_day}` - компоненты даты
- Доступны всегда во всех flow
- Резолвятся при компиляции графа (статические)

### 2. Company Variables (хранилище секретов):
- `telegram_bot_token`, `weather_api_key`, `api_endpoint` и т.д.
- Создаются через UI `/variables` или API
- НЕ доступны напрямую в промпте
- Используются через `@var:key` ссылки в flow.variables или flow.store
- Изоляция per-company автоматическая

### 3. Flow переменные (статические):
- Объявляются в `FlowConfig.variables`
- Резолвятся ОДИН РАЗ при компиляции графа
- Доступны всем агентам в flow через `{variable}`
- Можно использовать хардкод или `@var:key` ссылки
- Используй для: конфигурация, константы, настройки

### 4. Session Store (динамические):
- Объявляются в `FlowConfig.store` или `AgentConfig.store` (начальные значения)
- Резолвятся ДИНАМИЧЕСКИ перед каждым вызовом LLM
- Доступны через `{store.key}` или `session_get("key")`
- Автоматически персистятся в БД (PostgreSQL checkpointer)
- Общие для ВСЕХ агентов в цепочке (широкая память)
- Используй для: накопление данных, счетчики, флаги, история диалога

### 5. Local переменные (статические, редкие):
- Объявляются в `AgentConfig.local_variables`
- Доступны только конкретному агенту
- Перекрывают flow.variables
- Редактируются через админку агентов `/frontend/models/agent`

## Использование в конфигурации

### FlowConfig.platforms

**Хардкод токена:**
```python
FlowConfig(
    flow_id="weather_flow",
    platforms={
        "telegram": {
            "username": "weather_bot",
            "token": "8395450365:AAHUJq84eZpjIRwKljo"
        }
    }
)
```

**Ссылка на переменную:**
```python
FlowConfig(
    flow_id="weather_flow",
    platforms={
        "telegram": {
            "username": "weather_bot",
            "token": "@var:telegram_bot_token"  # Резолвится автоматически
        }
    }
)
```

**Смешанное использование:**
```python
FlowConfig(
    flow_id="weather_flow",
    platforms={
        "telegram": {
            "username": "@var:tg_bot_name",      # Ссылка
            "token": "@var:telegram_bot_token"   # Ссылка
        },
        "api": {
            "key": "hardcoded_key_123"           # Хардкод
        }
    }
)
```

### FlowConfig.variables

**Переменные flow доступные в промптах агентов:**
```python
FlowConfig(
    flow_id="support_flow",
    variables={
        "bot_name": "Support Bot",                    # Хардкод
        "support_email": "@var:company_support_email", # Ссылка
        "greeting": "Привет! Я @var:bot_name",        # Смешанное
        "timeout_minutes": "30"
    }
)
```

**Использование в промптах:**
```python
AgentConfig(
    agent_id="support_agent",
    prompt="""
    Ты {bot_name}.
    При необходимости переводи пользователя на {support_email}.
    Таймаут: {timeout_minutes} минут.
    """
)
```

### FlowConfig.store и AgentConfig.store

**Начальные значения для Session Store:**
```python
FlowConfig(
    flow_id="weather_flow",
    store={
        "max_requests_per_session": 10,          # Хардкод
        "show_welcome": True,                    # Хардкод
        "api_key": "@var:weather_api_key",       # Ссылка
        "units": {
            "temperature": "celsius",            # Вложенные данные
            "wind": "ms"
        }
    }
)

AgentConfig(
    agent_id="weather_agent",
    store={
        "requests_count": 0,
        "show_tips": True,
        "preferred_units": "celsius"
    }
)
```

**Работа с Session Store в промптах и тулах:**
```python
# В промпте агента (динамическая подстановка)
prompt = """
Запросов в диалоге: {#messages.count}
Последний город: {?store.last_city|не было}
Счетчик: {?store.requests_count|0}
"""

# В туле (изменение store)
@tool
def save_city(city: str) -> str:
    state = get_state()
    state["store"]["last_city"] = city
    state["store"]["requests_count"] = state["store"].get("requests_count", 0) + 1
    return f"Сохранено: {city}"

# Или через session_tools
session_set("last_city", "Москва")
session_get("last_city")  # → "Москва"
```

### AgentConfig.prompt

**Унифицированный синтаксис переменных:**
```python
AgentConfig(
    prompt="""
    Ты {bot_name} компании {?company_name|Weather Service}.
    
    СТАТИЧЕСКИЕ (резолвятся при компиляции):
    - Email: {?support_email|support@company.com}
    - Таймаут: {?timeout|30} минут
    - Настройка: {settings.language}
    
    ДИНАМИЧЕСКИЕ (резолвятся перед каждым вызовом LLM):
    - Последний запрос: {?store.last_city|нет}
    - Всего запросов: {?store.count|0}
    - Запросов в диалоге: {#messages.count}
    
    {?store.last_city:
      КОНТЕКСТ: Ранее вы интересовались {store.last_city}.
    }
    """
)
```

## Унифицированный синтаксис в промптах

Все переменные (статические и динамические) используют единый синтаксис:

### Базовый синтаксис

```python
{variable}              # Обычная подстановка
{?variable}             # Опциональная (пустая строка если нет)
{?variable|default}     # Опциональная со значением по умолчанию
{dict.nested.key}       # Вложенные данные
{#special.function}     # Специальные функции (только для state)
```

### Примеры

```python
# Обычная подстановка
"Компания: {company_name}"           → "Компания: ООО Доставка"
"Город: {store.last_city}"           → "Город: Москва"

# Опциональная (без дефолта)
"Email: {?user_email}"               → "Email: " (пусто если нет)
"Склад: {?store.warehouse_name}"     → "Склад: " (пусто если нет)

# Опциональная с дефолтом
"Email: {?user_email|не указан}"     → "Email: не указан"
"Таймаут: {?timeout|30} сек"         → "Таймаут: 30 сек"
"Склад: {?store.warehouse|НЕТ}"      → "Склад: НЕТ"

# Вложенные данные
"Язык: {settings.language}"          → "Язык: ru"
"Температура: {store.units.temp}"    → "Температура: celsius"

# Специальные функции (state)
"Сообщений: {#messages.count}"       → "Сообщений: 5"
"Ключи: {#store.keys}"               → "Ключи: warehouse_id, courier_id"
"Пустой: {#store.empty}"             → "Пустой: false"
```

### Условные блоки

```python
prompt = """
{?store.warehouse_id:
  ✅ Склад определен: {store.warehouse_name} (ID: {store.warehouse_id})
  Переходим к следующему этапу.
|
  ⏳ Склад еще не определен.
  Используй warehouse_agent для определения склада.
}
"""
```

### Комбинирование статических и динамических

```python
prompt = """
Ты {bot_name} компании {company_name}.
Дата: {current_date}

СТАТИЧЕСКИЕ НАСТРОЙКИ:
- Email поддержки: {?support_email|support@company.com}
- Таймаут: {?timeout|30} минут

ДИНАМИЧЕСКИЕ ДАННЫЕ СЕССИИ:
- Последний запрос: {?store.last_query|нет}
- Всего запросов: {?store.requests_count|0}
- Сообщений в истории: {#messages.count}

{?store.last_query:
  КОНТЕКСТ: Ранее вы спрашивали: "{store.last_query}"
}
"""
```

## Где применяются переменные

### 1. **Platform tokens (автоматическая резолюция)**

```python
# TelegramInterface.get_bot_token_for_flow()
platform_config = {
    "username": "my_bot",
    "token": "@var:telegram_bot_token"
}

# Автоматически резолвится в:
token = "8395450365:AAHSUMIRKYfq84eZpjIRwKljo"
```

### 2. **Flow variables (доступны в context.flow_variables)**

```python
FlowConfig.variables = {
    "bot_name": "Support Bot",
    "timeout": "@var:default_timeout"
}

# В агенте через context:
context.flow_variables["bot_name"]  # "Support Bot"
context.flow_variables["timeout"]   # Резолвлено из @var:default_timeout
```

### 3. **Agent prompts (подстановка через {key})**

```python
AgentConfig.prompt = "Я {bot_name}, работаю {timeout} минут"

# Автоматически подставляется из context.flow_variables
```

### 4. **Session Store (динамические переменные сессии)**

**Автоматическая персистентность:**
```python
# В туле
@tool
def save_warehouse(warehouse_id: str, warehouse_name: str) -> str:
    state = get_state()
    state["store"]["warehouse_id"] = warehouse_id
    state["store"]["warehouse_name"] = warehouse_name
    # ✅ Автоматически сохранится в БД через checkpointer
    return "Сохранено"

# В следующем вызове (тот же thread_id)
state["store"]["warehouse_id"]  # → "12345" (восстановлено из БД!)
```

**Общий store для всех агентов:**
```python
# Координатор устанавливает
state["store"]["user_context"] = {"name": "Виктор", "city": "Москва"}

# Субагент 1 видит и добавляет
state["store"]["user_context"]  # → {"name": "Виктор", "city": "Москва"}
state["store"]["warehouse_id"] = "12345"

# Субагент 2 видит ВСЕ
state["store"]["user_context"]  # → {"name": "Виктор", "city": "Москва"}
state["store"]["warehouse_id"]  # → "12345"
state["store"]["courier_id"] = "789"

# Координатор видит результаты ВСЕХ субагентов
state["store"]  # → {user_context, warehouse_id, courier_id}
```

**Умное слияние (merge_store):**
```python
# Вызов 1
state["store"] = {
    "settings": {"language": "ru", "units": "celsius"},
    "counter": 1
}

# Вызов 2 (тот же thread_id)
state["store"]["settings"]["theme"] = "dark"  # Добавляем в вложенный dict
state["store"]["counter"] = 2                 # Перезаписываем простое значение

# Результат (merge_store):
{
    "settings": {
        "language": "ru",     # ← Осталось из Вызова 1
        "units": "celsius",   # ← Осталось из Вызова 1
        "theme": "dark"       # ← Добавлено в Вызове 2
    },
    "counter": 2              # ← Перезаписано
}
```

**Доступ в промптах:**
```python
prompt = """
СЕССИОННЫЕ ДАННЫЕ:
- Последний город: {?store.last_city|не было запросов}
- Склад: {?store.warehouse_name|не определен}
- Счетчик запросов: {?store.requests_count|0}
- Сообщений: {#messages.count}

{?store.last_city:
  Ранее вы интересовались {store.last_city}.
}
"""
```

## Приоритет резолюции

Когда используется `{key}` в промпте:

1. **state.store** - переменные сессии (runtime)
2. **flow.variables** - переменные flow
3. **company.variables** - переменные компании (через @var:)

## Примеры сценариев

### Сценарий 1: Один токен для нескольких ботов

```python
# Сохраняем токен один раз
POST /api/v1/admin/variables
{
  "key": "main_telegram_token",
  "value": "123:ABC...",
  "secret": true
}

# Используем в разных flow
FlowConfig(flow_id="support_flow", platforms={
    "telegram": {"username": "support_bot", "token": "@var:main_telegram_token"}
})

FlowConfig(flow_id="sales_flow", platforms={
    "telegram": {"username": "sales_bot", "token": "@var:main_telegram_token"}
})
```

### Сценарий 2: Переиспользование настроек

```python
# Сохраняем общие настройки
POST /api/v1/admin/variables
{
  "key": "company_name",
  "value": "SSD Company",
  "secret": false
}

# Используем во всех flow
FlowConfig.variables = {
    "greeting": "Привет от @var:company_name!",
    "support_email": "@var:support_email"
}
```

### Сценарий 3: Разные токены для разных компаний

```
company:ssd:var:telegram_bot_token = "123:ABC..."
company:acme:var:telegram_bot_token = "456:XYZ..."

# Оба flow используют @var:telegram_bot_token
# Но получают разные значения в зависимости от компании
```

## Текущая реализация

### Что работает:

✅ **VariablesService** - сохранение/получение/резолюция  
✅ **Таблица variables** - единая для всех компаний с изоляцией через префикс  
✅ **API endpoints** - полное CRUD управление (`/api/v1/admin/variables`)  
✅ **Резолюция @var:key в platforms** - автоматически в TelegramInterface  
✅ **Резолюция FlowConfig.variables** - автоматически в TaskProcessor  
✅ **Резолюция FlowConfig.store** - автоматически при миграции  
✅ **Резолюция AgentConfig.store** - автоматически при миграции  
✅ **Вложенные структуры** - dict/list с @var:key внутри  
✅ **Per-company изоляция** - автоматическая через Storage  
✅ **Унифицированный синтаксис** - {?var|default} для всех типов переменных  
✅ **State variables** - динамическая подстановка {store.key} в промптах  
✅ **Специальные функции** - {#messages.count}, {#store.keys}  
✅ **Session Store персистентность** - автоматическое сохранение в PostgreSQL  
✅ **Общий store между агентами** - все агенты в цепочке видят один store  
✅ **UI для Session Store** - категория "Session Store" в Prompt Editor  

### Что можно улучшить:

⏳ Миграция старых `token:telegram:{username}` в company variables  
⏳ Валидация переменных (проверка что @var:key существует)  
⏳ Предпросмотр резолвнутых значений в UI  

## Миграция со старого формата

### Старый формат (токены):

```
token:telegram:my_bot = "123:ABC..."
```

### Новый формат (переменные):

```
company:ssd:var:telegram_bot_token = {"value": "123:ABC...", "secret": true}

FlowConfig.platforms = {
    "telegram": {
        "username": "my_bot",
        "token": "@var:telegram_bot_token"
    }
}
```

### Обратная совместимость:

TelegramInterface.get_bot_token_for_flow() поддерживает оба формата:

1. Сначала проверяет `platform_config.get("token")`
2. Если есть `@var:` - резолвит через VariablesService
3. Если нет - ищет legacy `token:telegram:{username}`

## Безопасность

### Секреты в БД:

- `secret: true` - помечает переменную как секрет
- В API списке показывается как `"***"`
- В UI скрывается паролем `type="password"`

### Per-company изоляция:

- Компания `ssd` видит только `ssd_variables`
- Компания `acme` видит только `acme_variables`
- Автоматическая изоляция через Storage маршрутизацию

