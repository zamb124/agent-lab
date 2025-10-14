# Архитектура Agent Lab

Agent Lab — платформа для создания и управления ИИ-агентами на базе LangGraph. Использует подход Database-First, где конфигурация в базе данных является единственным источником правды.

## Принципы архитектуры

1. **Database-First** - вся конфигурация в БД, код только для поведения
2. **Единообразие** - агенты из кода и UI работают идентично
3. **Фабричный паттерн** - все создается через фабрики из БД
4. **Модульность** - каждый компонент независим и заменяем
5. **LangGraph-native** - использование современных возможностей LangGraph
6. **Асинхронность** - полностью асинхронная архитектура

## Ключевые компоненты

### Storage (Key-Value БД)

Единая таблица PostgreSQL для хранения всех сущностей с префиксами ключей:

- `agent:{agent_id}` - конфигурации агентов
- `flow:{flow_id}` - конфигурации flows
- `task:{task_id}` - задачи для обработки
- `session:{session_id}` - сессии диалогов
- `user:{user_id}` - пользователи
- `company:{company_id}` - компании
- `subdomain:{subdomain}` - маппинг поддоменов

**Файл**: `app/core/storage.py`

### Agents

Агенты наследуются от `BaseAgent` и поддерживают два типа:

1. **ReAct** - классический агент с промптом и инструментами
2. **StateGraph** - граф состояний для сложной логики

**Ключевые методы**:
- `compile_graph()` - компиляция LangGraph графа
- `get_tools()` - загрузка инструментов из БД
- `as_tool()` - превращение агента в инструмент

**Файлы**:
- `app/agents/base.py` - базовый класс
- `app/agents/calculator/agent.py` - пример ReAct агента
- `app/agents/weather/agent.py` - агент с инструментами

### Flows

Flow — административная обертка над агентом с настройками:
- Какой агент является точкой входа
- На каких платформах работает (Telegram, API, Web)
- Метаданные и описание

**Файл**: `app/flows/flow.py`

### Tools

Инструменты создаются через декоратор `@tool` с поддержкой биллинга:

```python
from app.core.tool_decorator import tool

@tool(cost=0.1, billing_name="weather_api")
def get_weather(city: str) -> str:
    return f"Погода в {city}"
```

**Файлы**: `app/tools/*.py`

### Interfaces

Адаптеры для разных платформ, преобразуют специфичные данные в унифицированный `Message`:

- **TelegramInterface** - Telegram боты
- **WhatsAppInterface** - WhatsApp Business Cloud API
- **APIInterface** - REST API
- **WebInterface** - веб-интерфейс
- **AmoCRMInterface** - AmoCRM чаты

**Файл**: `app/interfaces/base.py`

### Task Processor

Асинхронный воркер для обработки задач из БД:
1. Берет задачи в статусе `pending`
2. Создает агента из БД
3. Выполняет задачу
4. Обрабатывает GraphInterrupt для запроса данных у пользователя
5. Отправляет результат через Interface

**Файл**: `app/workers/task_processor.py`

### Billing Service

Система биллинга на уровне компаний:
- Тарифные планы (free, basic, premium, enterprise)
- Учет стоимости LLM и tools
- Лимиты по использованию
- Бюджеты компаний

**Файл**: `app/services/billing_service.py`

### LLM Factory

Создание LLM через OpenRouter с автоматическим биллингом:
- Единый API для всех провайдеров (OpenAI, Anthropic, Google и др.)
- Автоматический учет токенов и стоимости
- Mock модели для тестов
- Поддержка настройки через конфигурацию

**Файлы**: 
- `app/core/llm_factory.py` - фабрика LLM
- `app/core/llm_billing_wrapper.py` - биллинг обертка

**Подробнее**: [LLM документация](llm.md)

### Identity System

Система авторизации с поддержкой:
- User - пользователи
- Company - компании (мультитенантность)
- AuthProvider - провайдеры OAuth (Yandex)
- AuthSession - сессии авторизации

**Файлы**: `app/identity/*.py`

## Поток данных

### 1. Создание агента/flow

```
Код (agent.py) 
    → Migrator сканирует 
    → Создает AgentConfig 
    → Сохраняет в Storage (БД)
```

### 2. Обработка запроса

```
Платформа (Telegram/API/Web)
    → Interface создает Message
    → Создается Task в БД
    → TaskProcessor берет задачу
    → AgentFactory создает агента из БД
    → Агент выполняется (LangGraph)
    → Результат через Interface на платформу
```

### 3. Запрос данных у пользователя

```
Агент вызывает ask_user(question)
    → GraphInterrupt с вопросом
    → TaskProcessor ловит interrupt
    → Interface отправляет вопрос пользователю
    → Пользователь отвечает
    → TaskProcessor возобновляет граф с ответом
```

## Миграция

Автоматическая миграция при старте приложения:

1. Сканирует `app/agents/` и `app/flows/`
2. Анализирует классы BaseAgent
3. Извлекает атрибуты (name, prompt, tools)
4. Создает/обновляет записи в БД

**Файл**: `app/core/migrator.py`

## Контекст выполнения

Глобальный контекст запроса через `contextvars`:

```python
from app.core.context import get_context, set_context

context = get_context()
user = context.user
company = context.active_company
```

Используется для:
- Изоляции данных по компаниям
- Биллинга (кто и сколько потратил)
- Авторизации

**Файл**: `app/core/context.py`

## Веб-интерфейс

Frontend включает:
- **Builder** - визуальный конструктор агентов/flows
- **Chat** - интерфейс чата с агентами
- **Billing** - мониторинг использования
- **Admin** - управление компаниями

Использует FastAPI для рендеринга HTML через Jinja2.

**Папка**: `app/frontend/`

## База данных

PostgreSQL с двумя основными таблицами:

1. **storage** - key-value хранилище для всех сущностей
2. **checkpoints** - LangGraph checkpoints для возобновления графов

**Файлы**: `app/db/*.py`

## Конфигурация

Конфигурация через JSON файл `conf.json`:

```json
{
  "database": {"url": "..."},
  "llm": {"default_provider": "openai"},
  "server": {"host": "0.0.0.0", "port": 8001}
}
```

Подробнее: [configuration.md](configuration.md)

## Развертывание

Поддерживается Docker и ручная установка:

```bash
# Docker
docker-compose up -d

# Локально
uv run python run.py
```

Подробнее: [deployment.md](deployment.md)

