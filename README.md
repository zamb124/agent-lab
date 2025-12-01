Humanitec - LangGraph Platform

Канал для создания и управления ИИ-агентами на базе LangGraph.

**Философия**: Database-First — конфигурация в базе данных является единственным источником правды. Код определяет только поведение, но не структуру.

**Документация**: [docs/](docs/) | [Архитектура](docs/architecture.md) | [Конфигурация](docs/configuration.md) | [API](docs/api.md) | [Makefile](docs/makefile.md) | [Биллинг](docs/billing.md) | [Интернационализация](docs/internationalization.md)

## Быстрый старт

### Docker (рекомендуется)

```bash
# Скопировать конфигурацию
cp conf.example conf.json

# Собрать и запустить все сервисы
make build
make up

# Проверить логи
make logs

# Остановить
make down
```

### Отдельные сервисы

```bash
make db-up       # Запустить только БД
make app-up      # Запустить приложение
make worker-up   # Запустить worker
make sgr-up      # Запустить SGR сервис
```

### Тесты

```bash
make test        # Запуск тестов (без интеграционных)
make test-all    # Все тесты (включая интеграционные)
```

### Локальная разработка

```bash
# Установка зависимостей
uv sync

# Запуск локально
uv run python run.py
```

Подробнее о командах: [docs/makefile.md](docs/makefile.md)
Конфигурация: [docs/configuration.md](docs/configuration.md)

## Актуальная Файловая Структура Проекта

```
/agent-lab/
├── .env                    # Переменные окружения (не в git)
├── .gitignore
├── docker-compose.yml      # Оркестрация сервисов
├── Dockerfile             # Docker образ
├── Makefile               # Команды для разработки
├── mk/                    # Модульные Makefile
│   ├── db.mk             # Команды для БД
│   ├── app.mk            # Команды для приложения
│   ├── worker.mk         # Команды для worker
│   ├── sgr.mk            # Команды для SGR
│   └── test.mk           # Команды для тестов
├── pyproject.toml         # Зависимости проекта (UV)
├── pytest.ini            # Настройки тестов
├── uv.lock               # Блокировка зависимостей
├── conf.example          # Шаблон конфигурации
├── conf.json             # Рабочая конфигурация
│
├── README.md             # Главная страница проекта
├── run.py               # Запуск сервера
├── run_worker.py        # Запуск воркера задач
├── run_tests.py         # Запуск тестов
├── debug_task.py        # Отладка задач
├── cleanup_non_company_data.py  # Очистка данных
├── amocrm_export_data.py # Экспорт данных из AmoCRM
│
├── certs/               # SSL сертификаты
├── deploy/              # Конфигурация деплоя
│   ├── conf.json
│   ├── nginx.conf
│   └── README.md
│
├── docs/                # Документация
│   ├── README.md        # Навигация
│   ├── architecture.md  # Архитектура
│   ├── api.md          # API Reference
│   ├── billing.md      # Биллинг
│   ├── configuration.md # Конфигурация
│   ├── makefile.md     # Команды Makefile
│   ├── frontend.md     # Веб-интерфейс
│   ├── clients.md      # Клиенты
│   ├── deployment.md   # Развертывание
│   └── integrations/
│       ├── amocrm/     # AmoCRM документация
│       └── whatsapp/   # WhatsApp документация
│
├── tests/               # Тесты
│   ├── arch/           # Архитектурные тесты
│   ├── billing/        # Тесты биллинга
│   ├── clients/        # Тесты клиентов
│   ├── conf/           # Тесты конфигурации
│   ├── core/           # Тесты core компонентов
│   ├── frontend/       # Тесты frontend
│   ├── integration/    # Интеграционные тесты
│   └── conftest.py     # Фикстуры pytest
│
└── app/                # Основной Python пакет
    ├── __init__.py
    ├── main.py            # FastAPI точка входа
    ├── exceptions.py      # Кастомные исключения
    ├── fields.py          # Расширения полей Pydantic
    │
    ├── api/               # HTTP API Layer
    │   ├── __init__.py
    │   └── v1/
    │       ├── admin.py   # REST API агентов/флоу
    │       ├── auth.py    # API авторизации
    │       ├── fashn.py   # API виртуальной примерки
    │       ├── files.py   # API файлов
    │       ├── flows.py   # API выполнения флоу
    │       ├── leads.py   # API лидов AmoCRM
    │       ├── telegram.py # Telegram webhooks
    │       ├── tokens.py  # Токены ботов
    │       └── webhooks.py # Универсальные webhooks
    │
    ├── agents/            # Агенты
    │   ├── base.py        # BaseAgent
    │   ├── calculator/
    │   │   └── agent.py   # CalculatorAgent
    │   ├── explainer/
    │   │   └── agent.py   # ExplainerAgent
    │   └── weather/
    │       └── agent.py   # WeatherAgent
    │
    ├── clients/           # Клиенты внешних API
    │   ├── fashn_client.py
    │   └── amo_crm_integration/
    │       ├── client.py
    │       └── chat_client.py
    │
    ├── core/              # Ядро системы
    │   ├── agent_factory.py  # Фабрика агентов
    │   ├── audio_processor.py # Обработка аудио
    │   ├── checkpointer.py   # LangGraph checkpointer
    │   ├── config.py         # Конфигурация
    │   ├── config_utils.py   # Утилиты конфигурации
    │   ├── container.py      # DI контейнер
    │   ├── context.py        # Глобальный контекст
    │   ├── file_processor.py # Обработка файлов
    │   ├── flow_factory.py   # Фабрика flows
    │   ├── graph_builder.py  # Построитель графов
    │   ├── llm_billing_wrapper.py # LLM с биллингом
    │   ├── llm_factory.py    # Фабрика LLM
    │   ├── migrator.py       # Миграция код→БД
    │   ├── storage.py        # Key-Value Storage
    │   ├── tool_decorator.py # Декоратор @tool
    │   ├── tool_factory.py   # Фабрика tools
    │   └── core_clients/
    │       ├── s3_client.py
    │       ├── cloud_voice_client.py
    │       └── nano_banana_client.py
    │
    ├── custom_flows/      # Кастомные flows
    │   └── fashn_buyer/
    │       ├── agent.py
    │       ├── flow.py
    │       ├── tools.py
    │       └── models.py
    │
    ├── db/                # База данных
    │   ├── database.py    # SQLAlchemy настройка
    │   └── models.py      # SQLAlchemy модели
    │
    ├── flows/             # Flow Templates
    │   ├── flow.py        # Flow обертка
    │   ├── smart_flow.py  # SmartFlowAgent
    │   ├── test_flow.py
    │   └── weather_flow.py
    │
    ├── frontend/          # Веб-интерфейс
    │   ├── api/          # Frontend API
    │   ├── core/         # Template loader, WebSocket manager
    │   ├── modules/      # Модули (builder, chat, billing, admin)
    │   ├── pages/        # Страницы
    │   ├── websockets/   # WebSocket endpoints
    │   ├── shared/       # Статика и шаблоны
    │   ├── environment.py
    │   ├── field_extensions.py
    │   ├── model_registry.py
    │   └── wrappers.py
    │
    ├── identity/          # Авторизация
    │   ├── auth_service.py
    │   ├── base_provider.py
    │   ├── models.py
    │   └── providers/
    │       └── yandex.py
    │
    ├── interfaces/        # Platform Adapters
    │   ├── base.py
    │   ├── factory.py
    │   ├── api_interface.py
    │   ├── telegram_interface.py
    │   └── web_interface.py
    │
    ├── llms/             # Кастомные LLM
    │   └── gemini_chat.py
    │
    ├── middleware/        # FastAPI Middleware
    │   └── auth.py
    │
    ├── models/            # Pydantic модели
    │   ├── billing_models.py
    │   ├── context_models.py
    │   ├── core_models.py
    │   └── fashn_models.py
    │
    ├── services/          # Сервисы
    │   ├── billing_service.py
    │   ├── cleanup_service.py
    │   └── telegram_poller.py
    │
    ├── tools/             # Инструменты
    │   ├── standard.py
    │   ├── calc_tools.py
    │   ├── weather_tools.py
    │   ├── fashn_tools.py
    │   ├── file_tools.py
    │   ├── voice_tools.py
    │   ├── amocrm_tools.py
    │   └── nano_banana_tools.py
    │
    └── workers/           # Background Workers
        └── task_processor.py
```


## Ключевые компоненты

### Корневые файлы

**pyproject.toml** - Конфигурация проекта с UV. Зависимости: FastAPI, LangChain/LangGraph, PostgreSQL, Pydantic.

**docker-compose.yml** - Оркестрация PostgreSQL, app и worker сервисов.

**Makefile** - Команды для разработки (up, down, logs, test).

**conf.json** - Основной конфиг (LLM, БД, Telegram, S3). Подробнее: [docs/configuration.md](docs/configuration.md)

### API Layer (app/api/v1/)

**admin.py** - REST API для управления агентами и флоу. CRUD операции через Storage. Используется для административного управления системой.

**auth.py** - API авторизации через внешние провайдеры (Yandex OAuth). Обрабатывает начало авторизации, callback, получение информации о пользователе и выход из системы.

**fashn.py** - API виртуальной примерки одежды и аксессуаров через FASHN сервис. Принимает URL изображений модели и продукта, выполняет примерку с настраиваемыми параметрами размещения и масштабирования.

**files.py** - API работы с файлами. Скачивание файлов через платформу с проверкой доступа, получение информации о файлах. Поддерживает стриминг файлов из S3.

**flows.py** - API выполнения флоу. Создает задачи в БД для TaskProcessor. Поддерживает синхронное и асинхронное выполнение через очередь задач.

**telegram.py** - Telegram webhook endpoints. Создает TelegramInterface на лету для каждого флоу. Поддерживает универсальные webhooks вида `/webhook/telegram/{flow_id}`.

**whatsapp.py** - WhatsApp webhook endpoints. Полная поддержка WhatsApp Business Cloud API с интерактивными кнопками, медиа и командами.

**tokens.py** - Управление токенами ботов.

**webhooks.py** - Универсальные webhook endpoints.

**leads.py** - API работы с лидами AmoCRM.

Подробнее: [docs/api.md](docs/api.md)

### Clients (app/clients/)

**fashn_client.py** - Клиент для FASHN API виртуальной примерки.

**amo_crm_integration/** - Клиент AmoCRM для работы с лидами, контактами, сделками.

Подробнее: [docs/clients.md](docs/clients.md)

### Core System (app/core/)

**storage.py** - Key-Value Storage на PostgreSQL с префиксами ключей.

**migrator.py** - Автоматическая миграция код→БД.

**agent_factory.py** - Фабрика создания агентов из БД.

**flow_factory.py** - Фабрика Flow экземпляров.

**graph_builder.py** - Построитель StateGraph графов из JSON-описания.

**tool_factory.py** - Создание tools из ToolReference.

**llm_factory.py** - Создание LLM (OpenAI, Gemini, Yandex).

**llm_billing_wrapper.py** - Обертка LLM с автоматическим биллингом.

**tool_decorator.py** - Декоратор @tool с биллинг метаданными.

**context.py** - Глобальный контекст (user, company, session).

**container.py** - DI контейнер для фабрик.

Подробнее: [docs/architecture.md](docs/architecture.md)

### Agents (app/agents/)

**base.py** - BaseAgent. Поддерживает ReAct и StateGraph. Загружает tools из БД. Метод as_tool() для вложенности.

**calculator/agent.py** - Агент для математики.

**explainer/agent.py** - Агент для резюме результатов.

**weather/agent.py** - Агент для погоды и путешествий.

### Flows (app/flows/)

**flow.py** - Flow обертка над entry_point_agent.

**smart_flow.py** - StateGraph с роутингом между агентами.

### Models (app/models/)

**core_models.py** - AgentConfig, FlowConfig, TaskConfig, SessionConfig, ToolReference, GraphDefinition.

**context_models.py** - Context модель (без циклических зависимостей).

**billing_models.py** - TariffPlan, UsageRecord, TARIFF_PRICES.

**fashn_models.py** - Модели для FASHN интеграции.

### Identity (app/identity/)

**auth_service.py** - Сервис авторизации и управление сессиями.

**models.py** - User, Company, AuthSession, AuthProvider.

**providers/yandex.py** - Yandex OAuth провайдер.

### Tools (app/tools/)

**standard.py** - ask_user() для запроса данных через GraphInterrupt.

**calc_tools.py** - calculate(), get_math_help().

**weather_tools.py** - suggest_travel(), get_weather().

**fashn_tools.py** - virtual_try_on(), upload_image_for_try_on().

**file_tools.py** - Работа с файлами и S3.

**voice_tools.py** - Обработка голоса.

**amocrm_tools.py** - Инструменты для AmoCRM.

### Interfaces (app/interfaces/)

**base.py** - BaseInterface с унифицированным Message.

**factory.py** - InterfaceFactory для создания адаптеров платформ.

**telegram_interface.py** - Адаптер Telegram (webhook/polling).

**whatsapp_interface.py** - Адаптер WhatsApp Business Cloud API.

**api_interface.py** - Адаптер REST API.

**web_interface.py** - Адаптер веб-интерфейса.

### Workers (app/workers/)

**task_processor.py** - Воркер задач. Обрабатывает задачи из БД, поддерживает GraphInterrupt.

### Services (app/services/)

**billing_service.py** - Биллинг и учет стоимости. Подробнее: [docs/billing.md](docs/billing.md)

**telegram_poller.py** - Long polling для локальной разработки.

**cleanup_service.py** - Очистка истекших данных.

### Database (app/db/)

**database.py** - Асинхронный SQLAlchemy движок и сессии.

**models.py** - SQLAlchemy модели (Storage table).

### Frontend (app/frontend/)

Веб-интерфейс с Builder, Chat, Billing, Admin модулями.

Подробнее: [docs/frontend.md](docs/frontend.md)

### Main Application

**main.py** - FastAPI приложение с lifecycle (инициализация БД, миграции, воркер).

**run.py** - Запуск uvicorn сервера.

**run_worker.py** - Запуск воркера задач.

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