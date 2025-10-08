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

### Company Variables (системные, статичные):
- `{company_name}`, `{company_id}`, `{company_subdomain}`
- `{user_name}`, `{user_id}`  
- `{current_date}`, `{current_time}`
- Доступны всегда во всех flow

### Variables (хранилище секретов):
- `telegram_bot_token`, `weather_api_key`
- НЕ доступны напрямую в промпте
- Используются через Flow переменные с `@var:key`

### Flow переменные:
- Объявляются в `FlowConfig.variables`
- Доступны всем агентам в flow
- Можно использовать хардкод или `@var:key` ссылки

### Local переменные (только в админке агентов):
- Объявляются в `AgentConfig.local_variables`
- Доступны только конкретному агенту
- Редактируются через `/frontend/models/agent`

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

### AgentConfig.prompt

**Подстановка переменных flow:**
```python
AgentConfig(
    prompt="Привет! Я {bot_name}, помогу с {service_type}"
)

# В runtime:
# bot_name = "Weather Bot" (из flow.variables)
# service_type = "погодой" (из flow.variables)
# Результат: "Привет! Я Weather Bot, помогу с погодой"
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

### 4. **Runtime state.store (сессионные переменные)**

```python
# В агенте или туле
state.store["user_name"] = "Виктор"
state.store["current_city"] = "Москва"

# Доступны в промптах
prompt = "Привет {user_name} из {current_city}"
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
✅ **Вложенные структуры** - dict/list с @var:key внутри  
✅ **Per-company изоляция** - автоматическая через Storage  

### Что можно улучшить:

⏳ Подстановка {key} в промптах AgentConfig (сейчас через VariableResolver)  
⏳ UI для управления переменными  
⏳ Миграция старых `token:telegram:{username}` в company variables  

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

