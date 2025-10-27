# Конфигурация Agent Lab

Система конфигурации поддерживает гибкое управление настройками через JSON файлы и переменные окружения.

## Порядок приоритетов

Источники конфигурации применяются в следующем порядке (от высшего к низшему):

1. **Переменные окружения (ENV)** ← Высший приоритет
2. **Файлы конфигурации (JSON)**
3. **Значения по умолчанию в коде**

## Структура конфигурации

### Основной файл: `conf.json`

```json
{
  "server": {
    "env": "local",
    "port": 8001,
    "debug": true
  },
  "database": {
    "url": "postgresql+asyncpg://user:password@localhost:5432/dbname",
    "checkpointer_url": "postgresql://user:password@localhost:5432/dbname"
  },
  "llm": {
    "openrouter": {
      "api_key": "sk-or-v1-...",
      "enabled": true,
      "base_url": "https://openrouter.ai/api/v1",
      "site_url": "https://agents-lab.ru",
      "site_name": "Agent Lab"
    },
    "default_model": "anthropic/claude-sonnet-4.5",
    "models": {
      "anthropic/claude-sonnet-4.5": {
        "temperature": 0.2,
        "max_tokens": 10000,
        "input_cost_per_token": 0.00003,
        "output_cost_per_token": 0.00015
      }
    }
  }
}
```

### Дополнительные файлы

- **`conf.local.json`** - локальные настройки (не коммитится, переопределяет `conf.json`)
  - Создается вручную разработчиком
  - Есть пример: `conf.local.json.example`
  - Удобен для локальных экспериментов
- **`AGENT_CONFIG_PATH`** - env переменная с путем к кастомному конфигу

## Переопределение через ENV переменные

### Формат имени переменной

Для вложенных полей используй двойное подчеркивание `__`:

```
СЕКЦИЯ__ПОЛЕ
database__url
llm__providers__openai__api_key
```

### Примеры

#### Локальная разработка

```bash
# Изменить порт сервера
export SERVER__PORT=8002

# Использовать другую БД
export DATABASE__URL="postgresql+asyncpg://user:pass@localhost:5433/mydb"

# Настроить OpenRouter
export LLM__OPENROUTER__API_KEY="sk-or-v1-..."
export LLM__DEFAULT_MODEL="anthropic/claude-sonnet-4.5"

# Включить debug режим
export SERVER__DEBUG=true

# Запуск
uv run python run.py
```

#### Docker окружение

В `docker-compose.yml`:

```yaml
services:
  app:
    environment:
      # Переопределяем хост БД для Docker
      - DATABASE__URL=postgresql+asyncpg://user:pass@postgres:5432/dbname
      - DATABASE__CHECKPOINTER_URL=postgresql://user:pass@postgres:5432/dbname
      
      # Настройка OpenRouter
      - LLM__OPENROUTER__API_KEY=sk-or-v1-...
      - LLM__DEFAULT_MODEL=anthropic/claude-sonnet-4.5
```

#### Продакшн

```bash
# .env файл
DATABASE__URL=postgresql+asyncpg://prod_user:secure_pass@db.example.com:5432/prod_db
LLM__OPENROUTER__API_KEY=sk-or-v1-prod-key-...
LLM__DEFAULT_MODEL=anthropic/claude-sonnet-4.5
SERVER__DEBUG=false
```

## Как это работает внутри

### 1. Загрузка JSON

Система загружает все JSON файлы и объединяет их:

```python
# app/core/config_utils.py
def load_merged_config():
    # Загружает conf.json
    # Затем conf.local.json (переопределяет значения)
    # Затем файл из AGENT_CONFIG_PATH
    ...
```

### 2. Фильтрация по ENV

Перед передачей в Pydantic удаляются значения, для которых есть ENV переменные:

```python
# app/core/config_utils.py
def remove_env_overridden_values(config):
    # Если есть DATABASE__URL в ENV
    # Удаляем database.url из JSON
    # Чтобы Pydantic прочитал DATABASE__URL
    ...
```

### 3. Применение через Pydantic

Pydantic BaseSettings читает конфигурацию:

```python
# app/core/config.py
class Settings(BaseSettings):
    database: DatabaseConfig
    
    class Config:
        env_nested_delimiter = "__"  # Разделитель для вложенных полей
```

**Результат:** ENV переменная всегда побеждает значение из JSON!

## Примеры использования

### Пример 1: Разработка с локальной БД

**conf.json:**
```json
{
  "database": {
    "url": "postgresql+asyncpg://agent_user:agent_password@localhost:5432/agent_platform"
  }
}
```

**Запуск:** `uv run python run.py`

**Результат:** Используется `localhost:5432` из JSON

### Пример 2: Разработка с тестовой БД

**Установка ENV:**
```bash
export DATABASE__URL="postgresql+asyncpg://test:test@localhost:5433/test_db"
uv run python run.py
```

**Результат:** Используется `localhost:5433` из ENV (переопределяет JSON)

### Пример 3: Docker

**conf.json:**
```json
{
  "database": {
    "url": "postgresql+asyncpg://agent_user:agent_password@localhost:5432/agent_platform"
  }
}
```

**docker-compose.yml:**
```yaml
app:
  environment:
    - DATABASE__URL=postgresql+asyncpg://agent_user:agent_password@postgres:5432/agent_platform
```

**Результат:** 
1. В контейнер копируется `conf.json` с `localhost:5432`
2. Устанавливается ENV `DATABASE__URL` с `postgres:5432`
3. Система обнаруживает ENV и игнорирует значение из JSON
4. Приложение подключается к `postgres:5432` ✅

### Пример 4: Переопределение API ключа

**conf.json:**
```json
{
  "llm": {
    "openrouter": {
      "api_key": "sk-or-v1-dev-key-..."
    },
    "default_model": "anthropic/claude-sonnet-4.5"
  }
}
```

**Продакшн:**
```bash
export LLM__OPENROUTER__API_KEY="sk-or-v1-prod-key-..."
export LLM__DEFAULT_MODEL="anthropic/claude-opus-4"
```

**Результат:** В продакшне используется продакшн ключ и более мощная модель, в разработке - dev ключ и базовая модель

## Проверка конфигурации

```python
from app.core.config import settings

# Посмотреть текущие значения
print(f"Database URL: {settings.database.url}")
print(f"Server Port: {settings.server.port}")
print(f"LLM Default Model: {settings.llm.default_model}")
print(f"OpenRouter Enabled: {settings.llm.openrouter.enabled}")
```

## Рекомендации

### ✅ Хорошие практики

- Храни чувствительные данные (пароли, API ключи) в ENV переменных
- Используй `conf.json` для базовых настроек
- Используй `conf.local.json` для локальных экспериментов (добавь в `.gitignore`)
- В Docker всегда переопределяй хосты через ENV

### ❌ Плохие практики

- Не коммить `conf.json` с продакшн паролями
- Не дублировать настройки в коде
- Не хардкодить пути к БД в коде

## Отладка

### Проверить какое значение используется

```python
import os
from app.core.config import settings

# Проверить ENV
print(f"ENV DATABASE__URL: {os.getenv('DATABASE__URL')}")
print(f"ENV LLM__OPENROUTER__API_KEY: {os.getenv('LLM__OPENROUTER__API_KEY')}")

# Проверить итоговое значение
print(f"Settings database.url: {settings.database.url}")
print(f"Settings llm.default_model: {settings.llm.default_model}")
```

### Логи загрузки конфигурации

При старте приложения ищи в логах:

```
INFO - Конфигурация загружена из /path/to/conf.json
DEBUG - Пропускаем database.url из JSON, используется env переменная DATABASE__URL
```

## Миграция с старой системы

Если у тебя были переменные в другом формате:

**Старый формат:**
```bash
DATABASE_URL=postgres://...
```

**Новый формат:**
```bash
DATABASE__URL=postgresql+asyncpg://...
```

Обрати внимание:
- Двойное подчеркивание `__` вместо одинарного `_`
- Префикс `postgresql+asyncpg` для asyncpg драйвера

## Секции конфигурации

### LLM

Подробная документация: [LLM →](llm.md)

Основные параметры:
- `llm.openrouter.api_key` - API ключ OpenRouter
- `llm.openrouter.enabled` - включить OpenRouter
- `llm.default_model` - модель по умолчанию
- `llm.models.*` - настройки отдельных моделей

### Database

- `database.url` - URL для asyncpg (async операции)
- `database.checkpointer_url` - URL для psycopg (checkpointer)

### Server

- `server.env` - окружение (local, production, staging)
- `server.host` - хост сервера
- `server.port` - порт сервера (по умолчанию 8001)
- `server.debug` - режим отладки

### Auth

- `auth.enabled` - включить авторизацию
- `auth.secret_key` - секретный ключ для сессий
- `auth.providers.*` - провайдеры OAuth
