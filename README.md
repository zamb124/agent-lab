Agent Lab - LangGraph Platform

Платформа для создания и управления ИИ-агентами на базе LangGraph.

**Философия**: Database-First — конфигурация в базе данных является единственным источником правды. Код определяет только поведение, но не структуру.

**Документация**: [docs/](docs/) | [Архитектура](docs/architecture.md) | [API](docs/api.md) | [Биллинг](docs/billing.md)

## Быстрый старт

1. **Настройка конфигурации**
   ```bash
   cp conf.example conf.json
   ```
   Отредактируйте `conf.json` под ваши нужды. Подробнее: [docs/configuration.md](docs/configuration.md)

2. **Запуск системы**
   ```bash
   # Установка зависимостей
   uv sync
   
   # Запуск с Docker (рекомендуется)
   docker-compose up -d
   
   # Или локально
   uv run python run.py
   ```

## Актуальная Файловая Структура Проекта

```
/agent-lab/
├── .env                    # Переменные окружения (не включен в git)
├── .gitignore
├── docker-compose.yml      # Оркестрация всех сервисов
├── init.sql               # Начальная инициализация БД
├── Makefile               # Команды для разработки
├── pyproject.toml         # Зависимости проекта (UV)
├── pytest.ini            # Настройки тестов
├── README.md              # Этот файл
├── run_tests.py           # Скрипт запуска тестов
├── test_simple.py         # Простые тесты
├── uv.lock               # Блокировка зависимостей UV
├── conf.json             # Конфигурация деплоя
│
├── certs/                # SSL сертификаты
├── deploy/               # Конфигурация деплоя
│   ├── conf.json
│   ├── nginx.conf
│   └── README.md
│
├── Dockerfile            # Docker образ
├── run.py               # Скрипт запуска сервера
├── run_worker.py        # Скрипт запуска воркера
├── debug_task.py        # Скрипт отладки задач
├── cleanup_non_company_data.py  # Скрипт очистки данных
│
├── docs/                # Документация
│   ├── README.md        # Навигация по документам
│   ├── architecture.md  # Архитектура платформы
│   ├── api.md          # API Reference
│   ├── billing.md      # Система биллинга
│   ├── configuration.md # Настройка конфигурации
│   ├── frontend.md     # Веб-интерфейс
│   ├── clients.md      # Клиенты сервисов
│   ├── deployment.md   # Развертывание
│   └── integrations/   # Документация интеграций
│
├── app/
│       ├── __init__.py
│       │
│       ├── api/                  # HTTP API Layer
│       │   ├── __init__.py
│       │   └── v1/
│       │       ├── __init__.py
│       │       ├── admin.py      # REST API управления агентами/флоу
│       │       ├── auth.py       # API авторизации
│       │       ├── fashn.py      # API виртуальной примерки FASHN
│       │       ├── files.py      # API работы с файлами
│       │       ├── flows.py      # API выполнения флоу
│       │       ├── telegram.py   # Telegram webhook endpoints
│       │       ├── tokens.py     # Управление токенами ботов
│       │       └── webhooks.py   # Универсальные webhook endpoints
│       │
│       ├── agents/               # Agent Templates & Logic
│       │   ├── __init__.py
│       │   ├── base.py           # BaseAgent - единый базовый класс
│       │   ├── calculator/
│       │   │   ├── __init__.py
│       │   │   └── agent.py      # CalculatorAgent
│       │   ├── explainer/
│       │   │   ├── __init__.py
│       │   │   └── agent.py      # ExplainerAgent
│       │   ├── router/           # (пустая папка)
│       │   └── weather/
│       │       ├── __init__.py
│       │       └── agent.py      # WeatherAgent
│       │
│       ├── clients/              # External API Clients
│       │   ├── __init__.py
│       │   ├── fashn_client.py   # Клиент FASHN для виртуальной примерки
│       │   └── README.md
│       │
│       ├── core/                 # Core System Components
│       │   ├── __init__.py
│       │   ├── agent_factory.py  # Фабрика создания агентов из БД
│       │   ├── checkpointer.py   # Чекпоинтер для LangGraph
│       │   ├── config_utils.py   # Утилиты конфигурации
│       │   ├── config.py         # Конфигурация приложения
│       │   ├── context.py        # Контекст выполнения
│       │   ├── file_processor.py # Обработчик файлов (S3)
│       │   ├── flow_factory.py   # Фабрика создания флоу из БД
│       │   ├── graph_builder.py  # Построитель StateGraph графов
│       │   ├── llm_factory.py    # Фабрика LLM экземпляров
│       │   ├── migrator.py       # Миграция из кода в БД
│       │   ├── models.py         # Pydantic модели (AgentConfig, FlowConfig)
│       │   ├── storage.py        # Key-Value Storage (единая таблица)
│       │   ├── tool_factory.py   # Фабрика создания инструментов
│       │   └── core_clients/
│       │       ├── __init__.py
│       │       └── s3_client.py  # S3 клиент для файлов
│       │
│       ├── db/                   # Database Layer
│       │   ├── __init__.py
│       │   ├── database.py       # SQLAlchemy настройка
│       │   ├── models.py         # SQLAlchemy модели таблиц
│       │   └── repositories/     # (пустая папка)
│       │       └── __init__.py
│       │
│       ├── flows/                # Flow Templates
│       │   ├── __init__.py
│       │   ├── flow.py           # Flow класс-обертка
│       │   ├── smart_flow.py     # SmartFlowAgent с StateGraph
│       │   ├── test_flow.py      # TestFlow конфигурация
│       │   └── weather_flow.py   # WeatherFlow конфигурация
│       │
│       ├── frontend/             # Web Frontend
│       │   ├── __init__.py
│       │   ├── environment.py    # Конфигурация окружения
│       │   ├── field_extensions.py # Расширения полей форм
│       │   ├── model_registry.py # Реестр моделей
│       │   ├── wrappers.py       # Обертки для форм
│       │   ├── README.md
│       │   │
│       │   ├── api/              # Frontend API
│       │   │   ├── __init__.py
│       │   │   ├── models.py     # Модели для API
│       │   │   ├── pages.py      # API страниц
│       │   │   └── websocket.py  # WebSocket API
│       │   │
│       │   ├── chat/             # Чат интерфейс
│       │   │   ├── __init__.py
│       │   │   ├── api/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── router.py  # Роутер чата
│       │   │   │   └── websocket.py # WebSocket чата
│       │   │   └── templates/
│       │   │       ├── chat.html
│       │   │       ├── chat_widget.html
│       │   │       └── chat_widget_inline.html
│       │   │
│       │   ├── examples/         # Скриншоты примеров
│       │   │   └── [8 скриншотов]
│       │   │
│       │   ├── static/           # Статические файлы
│       │   │   ├── css/          # CSS стили
│       │   │   │   └── [7 CSS файлов]
│       │   │   └── js/           # JavaScript файлы
│       │   │       └── [6 JS файлов]
│       │   │
│       │   └── templates/        # HTML шаблоны
│       │       └── [28 HTML файлов]
│       │
│       ├── identity/             # Система авторизации
│       │   ├── __init__.py
│       │   ├── auth_service.py   # Сервис авторизации
│       │   ├── base_provider.py  # Базовый провайдер авторизации
│       │   ├── models.py         # Модели авторизации
│       │   └── providers/
│       │       └── yandex.py     # Yandex OAuth провайдер
│       │
│       ├── integrations/         # External API Integrations
│       │   └── __init__.py
│       │
│       ├── interfaces/           # Platform Adapters
│       │   ├── __init__.py
│       │   ├── api_interface.py  # API интерфейс
│       │   ├── base.py           # BaseInterface абстракция
│       │   ├── factory.py        # InterfaceFactory
│       │   ├── telegram_interface.py # TelegramInterface
│       │   └── web_interface.py  # Web интерфейс
│       │
│       ├── main.py               # FastAPI точка входа
│       │
│       ├── middleware/           # FastAPI Middleware
│       │   └── auth.py           # Аутентификация
│       │
│       ├── services/             # Background Services
│       │   ├── __init__.py
│       │   └── telegram_poller.py # Long polling для разработки
│       │
│       ├── tools/                # Tool Functions
│       │   ├── __init__.py
│       │   ├── calc_tools.py     # Математические инструменты
│       │   ├── fashn_tools.py    # Инструменты FASHN
│       │   ├── file_tools.py     # Инструменты работы с файлами
│       │   ├── standard.py       # Стандартные инструменты (ask_user)
│       │   └── weather_tools.py  # Погодные инструменты
│       │
│       └── workers/              # Background Workers
│           ├── __init__.py
│           └── task_processor.py # Основной воркер задач
```


## Описание Каждого Файла и Принципов Работы

### 1. Корневые файлы

**pyproject.toml** - Конфигурация проекта на UV. Определяет зависимости: FastAPI, LangChain/LangGraph, PostgreSQL, Pydantic. Использует современный подход с UV вместо pip/poetry.

**docker-compose.yml** - Оркестрация PostgreSQL и приложения. Настраивает БД с нужными портами и переменными окружения.

**Makefile** - Команды для разработки: запуск сервера, воркера, тестов, очистки БД.

**init.sql** - SQL скрипт инициализации БД. Создает базу agent_platform и пользователя.

### 2. API Layer (app/api/v1/)

**admin.py** - REST API для управления агентами и флоу. CRUD операции через Storage. Используется для административного управления системой.

**auth.py** - API авторизации через внешние провайдеры (Yandex OAuth). Обрабатывает начало авторизации, callback, получение информации о пользователе и выход из системы.

**fashn.py** - API виртуальной примерки одежды и аксессуаров через FASHN сервис. Принимает URL изображений модели и продукта, выполняет примерку с настраиваемыми параметрами размещения и масштабирования.

**files.py** - API работы с файлами. Скачивание файлов через платформу с проверкой доступа, получение информации о файлах. Поддерживает стриминг файлов из S3.

**flows.py** - API выполнения флоу. Создает задачи в БД для TaskProcessor. Поддерживает синхронное и асинхронное выполнение через очередь задач.

**telegram.py** - Telegram webhook endpoints. Создает TelegramInterface на лету для каждого флоу. Поддерживает универсальные webhooks вида `/webhook/telegram/{flow_id}`.

**tokens.py** - Управление токенами ботов. Сохраняет токены в БД в формате `token:platform:username`.

**webhooks.py** - Универсальные webhook endpoints. Базовая заглушка для будущих интеграций.
### 3. External Clients (app/clients/)

**fashn_client.py** - Клиент для FASHN API виртуальной примерки. Обрабатывает загрузку изображений, масштабирование продуктов, композицию с моделями, запуск задач FASHN и polling результатов. Поддерживает различные типы продуктов (сумки, одежда).

### 4. Core System (app/core/)

**models.py** - Pydantic модели всей системы. AgentConfig, FlowConfig, TaskConfig, SessionConfig, FileRecord. Поддерживает два режима: CODE_REFERENCE (импорт из кода) и INLINE_CODE (код в БД). Основа Database-First архитектуры.

**storage.py** - Key-Value Storage на одной таблице PostgreSQL. Все сущности хранятся с префиксами: agent:, flow:, task:, session:. JSONB для эффективного поиска. Принцип: одна таблица, простые операции.

**migrator.py** - Автоматическая миграция из кода в БД. Сканирует папки agents/ и flows/, анализирует классы BaseAgent, извлекает статические атрибуты (name, prompt, tools) и создает конфигурации в БД. Умный анализ инструментов через inspect.

**agent_factory.py** - Фабрика создания агентов из БД. Каждый раз создает новые экземпляры. Поддерживает импорт из кода (function_class) и inline режим. Принудительно загружает tools из БД для единообразия.

**flow_factory.py** - Простая фабрика Flow. Загружает FlowConfig из БД и создает экземпляр Flow-обертки над entry_point_agent.

**graph_builder.py** - Построитель StateGraph графов. Динамически создает LangGraph на основе JSON-описания. Поддерживает различные типы нод: agent_node, tool_node, function_node. Обрабатывает conditional edges через router функции.

**llm_factory.py** - Фабрика LLM экземпляров. Поддерживает OpenAI, Anthropic, Yandex GPT. Создает экземпляры на основе LLMConfig.

**tool_factory.py** - Фабрика инструментов. Создает tools из ToolReference. Поддерживает функции, агенты как инструменты, MCP инструменты. Принцип: любой агент может быть инструментом.

**config.py** - Конфигурация приложения через Pydantic Settings. Настройки БД, LLM, сервера, FASHN, S3. Создает простой PostgresCheckpointer для LangGraph без сложных зависимостей.

**config_utils.py** - Утилиты для работы с конфигурацией. Помощники для загрузки и валидации настроек.

**context.py** - Контекст выполнения запросов. Управляет информацией о текущем пользователе и сессии в рамках обработки запроса.

**checkpointer.py** - Чекпоинтер для LangGraph. Сохраняет состояние графов между вызовами для поддержки прерываний и возобновления выполнения.

**file_processor.py** - Обработчик файлов с интеграцией S3. Загрузка, сохранение, получение файлов. Поддерживает публичные и приватные файлы, метаданные, теги.

**core_clients/s3_client.py** - S3 клиент для работы с объектным хранилищем. Поддерживает различных провайдеров S3 (AWS, VK Cloud).
### 5. Agents (app/agents/)

**base.py** - BaseAgent - единый базовый класс. Поддерживает ReAct и StateGraph агентов. Компилирует граф на основе config.type. Загружает tools ТОЛЬКО из БД для единообразия. Метод as_tool() превращает агента в инструмент.

**calculator/agent.py** - CalculatorAgent для математических вычислений. ReAct агент с промптом и списком tools. Принцип: простое объявление статических атрибутов.

**explainer/agent.py** - ExplainerAgent для финальных резюме. Анализирует результаты других агентов. Без дополнительных инструментов.

**weather/agent.py** - WeatherAgent для погоды и путешествий. ReAct агент с инструментами для работы с погодой.

### 6. Flows (app/flows/)

**flow.py** - Flow класс-обертка. Административная сущность над entry_point_agent. Содержит настройки платформ, таймауты, метаданные. Простой паттерн делегирования.

**smart_flow.py** - SmartFlowAgent с StateGraph. Реальный пример сложного агента с роутингом между калькулятором и погодой. Использует conditional edges и функции условий.

**weather_flow.py** - Простая конфигурация FlowConfig. Пример декларативного описания флоу для миграции.

**test_flow.py** - Тестовая конфигурация флоу.

### 7. Frontend (app/frontend/)

**environment.py** - Конфигурация окружения для фронтенда. Определяет переменные среды и настройки для веб-интерфейса.

**field_extensions.py** - Расширения полей форм. Кастомные поля для работы с агентами и флоу в веб-интерфейсе.

**model_registry.py** - Реестр моделей для фронтенда. Централизованное управление моделями данных в веб-интерфейсе.

**wrappers.py** - Обертки для форм. Упрощают работу с формами создания и редактирования агентов.

**api/models.py** - Модели данных для Frontend API. Pydantic модели для обмена данными между фронтендом и бэкендом.

**api/pages.py** - API страниц фронтенда. Рендеринг HTML страниц dashboard, создания агентов, управления флоу.

**api/websocket.py** - WebSocket API для фронтенда. Реальное время обновления интерфейса.

**chat/api/router.py** - Роутер чат API. Обработка сообщений чата через REST API.

**chat/api/websocket.py** - WebSocket для чата. Реальное время сообщений в чат интерфейсе.

**chat/templates/** - HTML шаблоны чата. Виджеты чата для встраивания и отдельные страницы.

**static/css/** - CSS стили фронтенда. Современный responsive дизайн.

**static/js/** - JavaScript фронтенда. Интерактивность, AJAX, WebSocket клиент.

**templates/** - HTML шаблоны. Полный набор страниц веб-интерфейса.

### 8. Identity System (app/identity/)

**auth_service.py** - Сервис авторизации. Управляет сессиями пользователей, интеграция с внешними провайдерами OAuth.

**base_provider.py** - Базовый провайдер авторизации. Абстрактный класс для реализации различных провайдеров OAuth.

**models.py** - Модели авторизации. User, Session, AuthProvider и другие модели для системы аутентификации.

**providers/yandex.py** - Yandex OAuth провайдер. Реализация авторизации через Yandex ID.

### 9. Tools (app/tools/)

**standard.py** - Стандартные инструменты. ask_user() - базовый инструмент для запроса данных у пользователя через GraphInterrupt.

**calc_tools.py** - Математические инструменты. calculate() и get_math_help() с декораторами @tool. Безопасная оценка выражений.

**fashn_tools.py** - Инструменты FASHN. virtual_try_on() и upload_image_for_try_on() для виртуальной примерки одежды.

**file_tools.py** - Инструменты работы с файлами. Загрузка, сохранение, обработка файлов в S3.

**weather_tools.py** - Погодные инструменты. suggest_travel() и get_weather() с моковыми данными.

### 10. Interfaces (app/interfaces/)

**base.py** - BaseInterface абстракция. Определяет унифицированный Message и методы handle_message(), send_message(). Управляет сессиями и командами платформ.

**factory.py** - InterfaceFactory. Создает интерфейсы на лету для разных платформ. Получает токены из БД.

**api_interface.py** - API интерфейс. Обработка HTTP запросов к агентам через REST API.

**telegram_interface.py** - TelegramInterface адаптер. Парсит Telegram Updates, создает Message, отправляет ответы через Bot API. Поддерживает команды и webhook/polling режимы.

**web_interface.py** - Web интерфейс. Обработка запросов от веб-интерфейса, интеграция с чатом.

### 11. Workers (app/workers/)

**task_processor.py** - Основной воркер системы. Обрабатывает задачи из БД в цикле. Поддерживает GraphInterrupt для пользовательского ввода. Отправляет результаты через InterfaceFactory. Принцип: отдельный процесс для фонового выполнения.

### 12. Services (app/services/)

**telegram_poller.py** - Long polling для разработки. Обнаруживает ботов в БД, запускает polling задачи, эмулирует webhooks через локальные HTTP запросы.

### 13. Database (app/db/)

**database.py** - SQLAlchemy настройка. Асинхронный движок, фабрика сессий, функции создания/удаления таблиц.

**models.py** - SQLAlchemy модели. Одна таблица Storage для key-value хранения. JSONB поля, GIN индексы для быстрого поиска.

### 14. Middleware (app/middleware/)

**auth.py** - Middleware аутентификации. Проверка сессий пользователей, установка контекста авторизации.

### 15. Main Application

**main.py** - FastAPI приложение. Lifespan управление: инициализация БД, checkpointer, миграции, Telegram polling. Подключение всех роутеров.

**run.py** - Простой скрипт запуска сервера через uvicorn.

**run_worker.py** - Скрипт запуска воркера задач.

## Принципы архитектуры:

1. **Database-First**: Вся конфигурация в БД, код только для поведения
2. **Единообразие**: Агенты из кода и UI работают идентично
3. **Фабричный паттерн**: Все создается через фабрики из БД
4. **Модульность**: Каждый компонент независим и заменяем  
5. **LangGraph-native**: Использование современных возможностей LangGraph
6. **Асинхронность**: Полностью асинхронная архитектура
7. **Простота**: Минимум абстракций, максимум ясности


## Технологический стек

Проект использует современный Python стек с UV для управления зависимостями:

### Основные технологии

- **Python 3.12+** - Современная версия Python
- **UV** - Быстрый пакетный менеджер (замена pip/poetry)
- **FastAPI** - Асинхронный веб-фреймворк
- **LangChain/LangGraph** - Фреймворк для ИИ агентов
- **PostgreSQL** - База данных с JSONB поддержкой
- **SQLAlchemy** - Асинхронный ORM
- **Pydantic** - Валидация данных и настройки

### Зависимости (pyproject.toml)

```toml
# Web Framework & Server
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6

# LangChain & LangGraph Core  
langchain>=0.1.0
langgraph>=0.0.40
langchain-core>=0.1.0
langchain-community>=0.0.20

# LLM Integrations
langchain-openai>=0.0.8

# Data Validation & Settings
pydantic>=2.5.0
pydantic-settings>=2.1.0

# Database & ORM
sqlalchemy[asyncpg]>=2.0.23
alembic>=1.13.0
psycopg2-binary>=2.9.9
langgraph-checkpoint-postgres>=1.0.0

# HTTP Client
httpx>=0.25.0

# Templating
jinja2>=3.1.2

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

### Команды разработки

```bash
# Установка зависимостей
uv sync

# Запуск сервера
uv run python run.py

# Запуск воркера
uv run python run_worker.py

# Запуск тестов
uv run pytest

# Запуск с Docker
docker-compose up -d
```