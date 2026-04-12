# Фикстуры платформы

Центральное место для всех pytest фикстур платформы.

## Структура

```
tests/fixtures/
├── __init__.py           # Экспорты основных классов
├── workers.py            # SessionWorkerManager, SessionServerManager
├── services.py           # Фикстуры для запуска сервисов как HTTP серверов
├── clients.py            # HTTP клиенты для тестирования API
└── README.md             # Этот файл
```

## Использование

### 1. В `tests/conftest.py`

Подключаем фикстуры через `pytest_plugins`:

```python
pytest_plugins = [
    "tests.fixtures.services",
    "tests.fixtures.clients",
]
```

### 2. В тестах

Просто используем фикстуры по имени:

```python
# Unit тесты (ASGI transport, быстрые)
async def test_agents_api(agents_client):
    response = await agents_client.get("/flows/api/v1/flows")
    assert response.status_code == 200

# E2E тесты (реальный HTTP, полная интеграция)
async def test_agents_e2e(agents_client_http):
    response = await agents_client_http.get("/flows/api/v1/flows")
    assert response.status_code == 200
```

## Доступные фикстуры

### Сервисы (из `services.py`)

Session-scoped фикстуры, запускают реальные HTTP серверы:

- `agents_service` - Agents сервис на порту 8000
- `rag_service` - RAG сервис на порту 8004
- `crm_service` - CRM сервис на порту 8003
- `frontend_service` - Frontend сервис на порту 8001
- `all_services` - Запускает все сервисы сразу

**Особенности:**
- Запускаются один раз на всю сессию тестов
- Переиспользуются между параллельными pytest worker'ами (pytest-xdist)
- Автоматически останавливаются после завершения тестов
- Используют тестовую конфигурацию (БД, Redis на тестовых портах)

**Пример:**
```python
def test_with_real_server(rag_service):
    # RAG сервер уже запущен на порту 8004
    import requests
    response = requests.get("http://localhost:8004/rag/api/v1/providers")
    assert response.status_code == 200
```

### HTTP Клиенты (из `clients.py`)

#### ASGI Transport (для unit тестов)

Быстрые, не требуют запуска реального сервера:

- `agents_client` - клиент для Agents API
- `rag_client` - клиент для RAG API (зависит от `rag_worker`)
- `crm_client` - клиент для CRM API (зависит от `rag_service`)
- `frontend_client` - клиент для Frontend API

**Использование:**
```python
async def test_api(rag_client):
    response = await rag_client.get("/rag/api/v1/providers")
    assert response.status_code == 200
```

#### HTTP (для E2E тестов)

Используют реальные HTTP серверы:

- `agents_client_http` - клиент к Agents на localhost:8000
- `rag_client_http` - клиент к RAG на localhost:8004
- `crm_client_http` - клиент к CRM на localhost:8003
- `frontend_client_http` - клиент к Frontend на localhost:8001
- `all_clients_http` - dict со всеми клиентами

**Использование:**
```python
async def test_e2e(all_clients_http):
    # Создаем entity в CRM
    response = await all_clients_http["crm"].post(
        "/crm/api/v1/entities/",
        json={"entity_type": "note", "text": "Test"}
    )
    entity_id = response.json()["entity_id"]
    
    # Добавляем attachment через RAG
    with open("test.txt", "rb") as f:
        response = await all_clients_http["crm"].post(
            f"/crm/api/v1/entities/{entity_id}/attachments",
            files={"file": f}
        )
    
    assert response.status_code == 200
```

### Workers (из `workers.py`)

Session-scoped фикстуры для worker процессов:

- `taskiq_worker` - TaskIQ worker для async задач
- `rag_worker` - RAG Worker для обработки документов

**Использование:**
```python
@pytest.mark.real_taskiq  # Маркер для тестов с реальным TaskIQ
async def test_with_worker(rag_worker):
    # Worker уже запущен и готов обрабатывать задачи
    from apps.rag_worker.tasks.indexing_tasks import index_document_profile_task

    task = await index_document_profile_task.kiq(
        company_id="system",
        namespace_id="test",
        s3_key="test.txt",
        document_name="test.txt",
        metadata={"document_id": "doc-1"},
        index_profile_id="<uuid профиля компании>",
    )

    result = await task.wait_result(timeout=10)
    assert result["status"] == "completed"
```

## Конфигурация окружения

Все сервисы используют **единую тестовую конфигурацию** из `services.py`:

```python
from tests.fixtures.test_database_env import TEST_DATABASE_ENV

_COMMON_TEST_ENV = {
    **TEST_DATABASE_ENV,
    "TESTING": "true",
    "DATABASE__REDIS_URL": "redis://localhost:63792/0",
    "TASKS__BROKER_URL": "redis://localhost:63792/1",
    "AUTH__PERMISSIONS_ENABLED": "false",
    "SERVER__DEFAULT_TENANT_ID": "test_tenant",
    "S3__DEFAULT_BUCKET": "test-bucket",
    "RAG__ENABLED": "true",
    "RAG__DEFAULT_PROVIDER": "pgvector",
    "RAG__PROVIDERS__PGVECTOR__ENABLED": "true",
    "RAG__PROVIDERS__PGVECTOR__HOST": "localhost",
    "RAG__PROVIDERS__PGVECTOR__PORT": "5433",
    "LLM__OPENROUTER__API_KEY": "sk-test-key",
}
```

## Архитектура

### SessionServerManager

Универсальный менеджер для запуска HTTP серверов в тестах:

```python
from tests.fixtures.workers import SessionServerManager

manager = SessionServerManager(
    name="MyService",
    lock_file="/tmp/my_service.lock",
    pid_file="/tmp/my_service.pid",
    app_path="apps.myservice.main:app",
    port=8005,
    startup_wait=2.0,
    env={"TESTING": "true"}
)

with manager.start():
    # Сервер запущен на порту 8005
    yield
# Сервер автоматически остановлен
```

**Особенности:**
- Reference counting для корректной работы с pytest-xdist
- File lock для синхронизации между параллельными worker'ами
- Автоматическая очистка старых процессов
- Логи в `/tmp/{service}_server_test.log`

### SessionWorkerManager

Универсальный менеджер для запуска worker процессов:

```python
from tests.fixtures.workers import SessionWorkerManager

manager = SessionWorkerManager(
    name="MyWorker",
    lock_file="/tmp/my_worker.lock",
    pid_file="/tmp/my_worker.pid",
    command=[sys.executable, "-m", "my_worker"],
    env={"TESTING": "true"},
    cleanup_patterns=["my_worker.*"],
    startup_wait=3.0
)

with manager.start() as process:
    # Worker запущен
    yield process
# Worker автоматически остановлен
```

## Зависимости фикстур

```
all_services
├── agents_service (8000)
├── rag_service (8004)
├── crm_service (8003)
└── frontend_service (8001)

crm_client (ASGI)
├── app (agents service)
├── rag_app (RAG ASGI app)
└── rag_service (RAG HTTP server для inter-service communication)

rag_client (ASGI)
├── rag_app (RAG ASGI app)
└── rag_worker (для обработки документов)

crm_client_http
├── crm_service
└── rag_service

all_clients_http
├── agents_client_http → agents_service
├── rag_client_http → rag_service
├── crm_client_http → crm_service + rag_service
└── frontend_client_http → frontend_service
```

## Добавление нового сервиса

### 1. Добавь фикстуру в `services.py`:

```python
_MY_SERVICE_LOCK = "/tmp/platform_test_my_service.lock"
_MY_SERVICE_PID = "/tmp/platform_test_my_service.pid"

@pytest.fixture(scope="session")
def my_service():
    """My Service как реальный HTTP сервер на порту 8010."""
    manager = SessionServerManager(
        name="MyService",
        lock_file=_MY_SERVICE_LOCK,
        pid_file=_MY_SERVICE_PID,
        app_path="apps.myservice.main:app",
        port=8010,
        startup_wait=2.0,
        env=_COMMON_TEST_ENV
    )
    
    with manager.start():
        yield
```

### 2. Добавь клиенты в `clients.py`:

```python
# ASGI client
@pytest_asyncio.fixture
async def my_service_client():
    """HTTP клиент для My Service API (ASGI transport)."""
    from apps.myservice.main import app
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

# HTTP client
@pytest_asyncio.fixture
async def my_service_client_http(my_service):
    """HTTP клиент для My Service API (реальный HTTP)."""
    async with AsyncClient(base_url="http://localhost:8010") as client:
        yield client
```

### 3. Используй в тестах:

```python
async def test_my_service(my_service_client):
    response = await my_service_client.get("/api/v1/health")
    assert response.status_code == 200
```

## Best Practices

1. **Unit тесты** - используй ASGI клиенты (`rag_client`, `crm_client`)
   - Быстрые, не требуют реальных серверов
   - Изолированные, тестируют конкретный сервис

2. **Integration тесты** - используй комбинацию ASGI клиентов и HTTP сервисов
   - Например, `crm_client` (ASGI) + `rag_service` (HTTP)
   - Тестируют взаимодействие между сервисами

3. **E2E тесты** - используй HTTP клиенты (`all_clients_http`)
   - Полная интеграция всей платформы
   - Тестируют реальные пользовательские сценарии

4. **Параллельное выполнение** - все фикстуры поддерживают pytest-xdist
   - Используй `-n auto` для параллельного запуска
   - Сервисы и worker'ы переиспользуются между pytest worker'ами

5. **Cleanup** - фикстуры автоматически очищают ресурсы
   - Не нужно вручную останавливать сервисы
   - PID файлы и lock файлы удаляются автоматически

## Troubleshooting

### Сервис не запускается

Проверь логи:
```bash
tail -f /tmp/rag_server_test.log
tail -f /tmp/rag_server_test_err.log
```

### Порт уже занят

Убей старые процессы:
```bash
pkill -9 -f "uvicorn.*apps.rag.main:app"
rm /tmp/platform_test_rag_server.*
```

### Worker не обрабатывает задачи

Проверь что используется маркер `@pytest.mark.real_taskiq`:
```python
@pytest.mark.real_taskiq
async def test_with_worker(rag_worker):
    # Этот тест будет использовать реальный worker
    pass
```

### Фикстура не найдена

Убедись что pytest_plugins настроен в `tests/conftest.py`:
```python
pytest_plugins = [
    "tests.fixtures.services",
    "tests.fixtures.clients",
]
```

