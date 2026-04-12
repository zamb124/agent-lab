Humanitec - Platform

Канал для создания и управления ИИ-агентами.

**Философия**: Database-First — конфигурация в базе данных является единственным источником правды. Код определяет только поведение, но не структуру.

**Документация**: [docs/](docs/) | [Архитектура](docs/architecture.md) | [Конфигурация](docs/configuration.md) | [API](docs/api.md) | [Makefile](docs/makefile.md) | [Биллинг](docs/billing.md) | [Интернационализация](docs/internationalization.md) | [MinIO S3](docs/minio-setup.md) | [Provider LitServe](apps/provider_litserve/README.md)

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

# Запуск воркера локально
uv run taskiq worker apps.broker.worker:broker
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
    ├── core/                 # Ядро системы (Framework-agnostic)
    │   ├── clients/           # Клиенты внешних сервисов (S3, STT)
    │   ├── config/            # Модуль конфигурации
    │   ├── container/         # DI контейнеры
    │   ├── db/                # Работа с БД
    │   ├── files/             # Обработка файлов
    │   ├── tasks/             # Базовые задачи (broker, scheduler)
    │   └── ...
    │
    ├── apps/                 # Приложение (Бизнес-логика)
    │   ├── agents/            # Сервис агентов
    │   │   ├── api/           # API Endpoints
    │   │   ├── agents/        # Реализации агентов
    │   │   ├── services/      # Сервисы (Factory, Builder)
    │   │   └── container.py   # DI контейнер приложения
    │   │
    │   ├── frontend/          # Веб-интерфейс
    │   └── worker.py          # Точка входа Worker (регистрирует все задачи)



## Ключевые компоненты

### Корневые файлы

**pyproject.toml** - Конфигурация проекта с UV. Зависимости: FastAPI, PostgreSQL, Pydantic.

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

### Core System (core/)
Базовые компоненты, не зависящие от бизнес-логики:
- **clients/** - Клиенты внешних сервисов (S3, STT, etc).
- **tasks/** - Брокер и планировщик задач (TaskIQ).
- **db/** - Базовые классы для работы с БД.

### Apps (apps/)
Бизнес-логика приложения:
- **apps/flows/** - Управление агентами, флоу и инструментами.
- **apps/frontend/** - Веб-интерфейс.
- **apps/worker.py** - Точка входа для фоновых задач.

### API Layer (apps/flows/api/v1/)
REST API endpoints для управления системой.

### Services (apps/flows/services/)
Бизнес-логика:
- **flow_factory.py** - Создание агентов.
- **flow_factory.py** - Создание флоу.
- **graph_builder.py** - Построение графов.
- **migrator.py** - Миграция конфигурации.


## Принципы архитектуры:

1. **Database-First**: Вся конфигурация в БД, код только для поведения
2. **Единообразие**: Агенты из кода и UI работают идентично
3. **Фабричный паттерн**: Все создается через фабрики из БД
4. **Модульность**: Каждый компонент независим и заменяем
5. **Асинхронность**: Полностью асинхронная архитектура
6. **Простота**: Минимум абстракций, максимум ясности


## Технологический стек

Проект использует современный Python стек с UV для управления зависимостями:

### Основные технологии

- **Python 3.13+** - Современная версия Python
- **UV** - Быстрый пакетный менеджер (замена pip/poetry)
- **FastAPI** - Асинхронный веб-фреймворк
- **PostgreSQL** - База данных с JSONB поддержкой
- **SQLAlchemy** - Асинхронный ORM
- **Pydantic** - Валидация данных и настройки

### Зависимости (pyproject.toml)

```toml
# Web Framework & Server
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6

# Data Validation & Settings
pydantic>=2.5.0
pydantic-settings>=2.1.0

# Database & ORM
sqlalchemy[asyncpg]>=2.0.23
alembic>=1.13.0
psycopg2-binary>=2.9.9

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