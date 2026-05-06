Humanitec - Platform

Канал для создания и управления ИИ-агентами.

**Философия**: Database-First — конфигурация в базе данных является единственным источником правды. Код определяет только поведение, но не структуру.

**Документация**: [docs/](docs/) | [Архитектура](docs/architecture.md) | [Конфигурация](docs/configuration.md) | [API](docs/api.md) | [Makefile](docs/makefile.md) | [Биллинг](docs/billing.md) | [Интернационализация](docs/internationalization.md) | [MinIO S3](docs/minio-setup.md) | [Provider LitServe](apps/provider_litserve/README.md)

## Быстрый старт

### Локальная разработка

```bash
# Установка зависимостей
uv sync

# Сервис browser (Playwright + CDP / Lightpanda): зависимость playwright в группе browser
uv sync --group browser

# Поднять инфраструктуру (Postgres :54321, Redis :63791, MinIO :19001/19011)
make dev-up

# Все сервисы и воркеры локально
make app
# или с предварительным освобождением портов 8001-8006/8014:
make app APP_KILL=1
```

### Тесты

```bash
make test        # Полный прогон (frontend-core + unit + retry-failed)
make test-unit   # Только unit/API
make test-rag    # RAG тесты с pgvector + MinIO
```

### Production деплой

Production разворачивается единым **Helm-чартом** в **MicroK8s** кластере (master + GPU worker). Никаких Docker Compose в проде, никаких ручных скриптов на серверах.

```bash
# Локально (требует kubectl с настроенным kubeconfig к кластеру)
make k8s-lint                       # helm lint
make k8s-template                   # рендер всех манифестов в stdout
make k8s-deploy IMAGE_TAG=<sha>     # helm upgrade --install (атомарно, ждёт rollout)
make k8s-status                     # nodes + pods + svc + ingress + pvc
make k8s-logs SVC=frontend          # поток логов конкретного Deployment
make k8s-rollback                   # helm rollback на предыдущую ревизию
```

Из CI: `.github/workflows/deploy.yml` собирает образ → push в GHCR → `helm upgrade --install` через `KUBECONFIG_B64` секрет.

Полная документация по деплою — [deploy/README.md](deploy/README.md), одноразовая настройка кластера — [deploy/cluster-setup.md](deploy/cluster-setup.md).

Подробнее о командах: [docs/makefile.md](docs/makefile.md)
Конфигурация: [docs/configuration.md](docs/configuration.md)

## Актуальная Файловая Структура Проекта

```
/agent-lab/
├── .env                    # Переменные окружения (не в git)
├── .gitignore
├── docker-compose-dev.yaml # Локальная инфраструктура (Postgres, Redis, MinIO)
├── docker-compose-test.yaml # Тестовое окружение
├── Dockerfile             # Docker образ
├── Makefile               # Команды для разработки и k8s-деплоя
├── mk/                    # Модульные Makefile
│   ├── app.mk            # Локальный запуск (make app)
│   ├── test.mk           # Тесты
│   └── migrate.mk        # Alembic миграции
├── pyproject.toml         # Зависимости проекта (UV)
├── pytest.ini            # Настройки тестов
├── uv.lock               # Блокировка зависимостей
├── conf.json             # Рабочая конфигурация
│
├── README.md             # Главная страница проекта
├── scripts/run.py       # Локальный запуск сервисов и воркеров
│
├── deploy/              # Helm-чарт + документация деплоя
│   ├── README.md        # Helm install, KUBECONFIG_B64, GitHub Secrets
│   ├── cluster-setup.md # Одноразовая настройка нод MicroK8s
│   └── helm/agent-lab/  # Единый Helm-чарт всего стека
│       ├── Chart.yaml
│       ├── values.yaml
│       ├── values-prod.yaml
│       ├── templates/   # postgres, redis, apps, workers, gpu, ingress, observability
│       └── files/       # ConfigMap источники (loki, tempo, alloy, dashboards)
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

**deploy/helm/agent-lab/** - Единый Helm-чарт всего стека (БД, приложения, воркеры, GPU litserve, observability, ingress).

**Makefile** - Команды для разработки (dev-up, app, test) и Kubernetes деплоя (k8s-deploy, k8s-status, k8s-logs).

**conf.json** - Основной конфиг (LLM, БД, Telegram, S3). Подробнее: [docs/configuration.md](docs/configuration.md)

### API Layer (app/api/v1/)

**admin.py** - REST API для управления агентами и флоу. CRUD операции через Storage. Используется для административного управления системой.

**auth.py** - API авторизации через внешние провайдеры (Yandex OAuth). Обрабатывает начало авторизации, callback, получение информации о пользователе и выход из системы.

**fashn.py** - API виртуальной примерки одежды и аксессуаров через FASHN сервис. Принимает URL изображений модели и продукта, выполняет примерку с настраиваемыми параметрами размещения и масштабирования.

**files.py** - API работы с файлами. Скачивание файлов через платформу с проверкой доступа, получение информации о файлах. Поддерживает стриминг файлов из S3.

**flows.py** - API выполнения флоу. Создает задачи в БД для TaskProcessor. Поддерживает синхронное и асинхронное выполнение через очередь задач.

**telegram.py** (flows service) — триггеры Telegram Bot API: регистрация `setWebhook`, приём `POST /flows/api/v1/triggers/telegram/{flow_id}/{trigger_id}` с заголовком `X-Telegram-Bot-Api-Secret-Token`.

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
- **apps/flows_worker/worker.py** - Точка входа TaskIQ для задач flows.

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
uv run python scripts/run.py all

# Запуск воркера
uv run python run_worker.py

# Запуск тестов
uv run pytest

# Поднять локальную инфраструктуру (Postgres/Redis/MinIO)
make dev-up
```