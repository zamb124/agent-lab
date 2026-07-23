# Фикстуры платформы

Центральное место для всех pytest фикстур платформы.

## Владение процессами

Все процессы тестового стека (granian HTTP-сервисы 9001-9022 и TaskIQ-воркеры)
стартует **`make test-up`** через супервизор `scripts/test_stack.py` — единственный
владелец процессов. pytest ничего не запускает и не убивает: ни FileLock,
ни pid/ref-count файлов, ни pkill в фикстурах нет.

- `scripts/test_stack.py up` — параллельный старт всех процессов + параллельное
  ожидание readiness; манифест `/tmp/platform_test_stack.json`, логи
  `/tmp/platform_test_stack/<name>.{log,err}`.
- `scripts/test_stack.py down` / `status` — остановка/диагностика по манифесту.
- Миграции применяет `scripts/test_migrate.py` (тоже из `make test-up`).

## Структура

```
tests/fixtures/
├── __init__.py           # Докстринг модулей
├── workers.py            # Readiness-фикстуры TaskIQ-воркеров + taskiq_scheduler
├── services.py           # Readiness-фикстуры HTTP-сервисов стека
├── clients.py            # HTTP клиенты для тестирования API
├── e2e_scope.py          # Статический test scope для -n0 E2E-фаз
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

Session-scoped readiness-проверки HTTP-сервисов стека (`GET /health`):

- `flows_service` (9001), `rag_service` (9002), `crm_service` (9003),
  `frontend_service` (9004), `sync_service` (9005), `office_service` (9008),
  `search_service` (9010), `provider_litserve_service` (9014),
  `voice_service` (9015), `capability_gateway_service` (9016),
  `code_runner_*_service` (9017-9020), `worktracker_http_service` (9021),
  `secrets_service` (9022)
- `sandbox_services` — контур capability_gateway + code-runner-*
- `all_services` — проверка всех сервисов сразу

Если сервис недоступен — `pytest.fail("... выполните make test-up")`.

### HTTP Клиенты (из `clients.py`)

#### ASGI Transport (для unit тестов)

Быстрые, не требуют запуска реального сервера:

- `agents_client` - клиент для Agents API
- `rag_client` - клиент для RAG API (зависит от `rag_worker`)
- `crm_client` - клиент для CRM API (зависит от `rag_service`)
- `frontend_client` - клиент для Frontend API

#### HTTP (для E2E тестов)

Используют реальные HTTP серверы стека:

- `flows_client_http` - клиент к Flows на localhost:9001
- `office_client_http` - клиент к Office на localhost:9008

### Workers (из `workers.py`)

Session-scoped readiness-проверки TaskIQ-воркеров стека (consumer в
Redis Stream группы `taskiq`):

- `taskiq_worker` — flows_worker (stream `flows_worker`)
- `rag_worker` — rag_worker (stream `rag`)
- `search_worker` — search_worker (stream `search`)
- `sync_worker` — sync_worker (stream `sync`)
- `crm_worker` — crm_worker (stream `crm`)
- `taskiq_scheduler` — единственное исключение: subprocess на время сессии
  (scheduler не входит в стек, его тики мешали бы остальным тестам)

**Использование:**
```python
@pytest.mark.real_taskiq  # Маркер для тестов с реальным TaskIQ
async def test_with_worker(rag_worker):
    from apps.rag_worker.tasks.indexing_tasks import index_document_profile_task

    task = await enqueue(RAG_INDEX_DOCUMENT_S3, ...)
    result = await task.wait_result(timeout=10)
    assert result["status"] == "completed"
```

## Изоляция тестов

- Данные — через `unique_id`.
- MockLLM — через test scope: autouse-фикстура `platform_test_scope` генерирует
  `test_<hex>`, он едет по платформе как `X-Test-Scope`/TaskIQ label, MockLLM
  читает строго свою очередь `mock_llm:responses:<scope>`.
- E2E-фазы `-n0` (Playwright/Electron) используют статический scope
  `TEST_SCOPE_STATIC_E2E` (`tests/fixtures/e2e_scope.py` + env
  `TEST_SCOPE_DEFAULT` у сервисов стека).

## Конфигурация окружения

Единая конфигурация стека — `scripts/test_stack.py::COMMON_TEST_ENV`
(база — `tests/fixtures/test_database_env.py::TEST_DATABASE_ENV`).

## Добавление нового сервиса

1. Добавь `GranianService`/`TaskiqWorkerService` в декларативную таблицу
   `scripts/test_stack.py` (порт, app path, env, readiness timeout).
2. Добавь readiness-фикстуру в `services.py`/`workers.py`
   (`require_http_service` / `require_taskiq_worker`).
3. При необходимости добавь клиента в `clients.py`.
4. Добавь порт/команду в `scripts/test_process_preflight_cleanup.py`.

## Best Practices

1. **Unit тесты** - используй ASGI клиенты (`rag_client`, `crm_client`).
2. **Integration тесты** - комбинация ASGI клиентов и HTTP сервисов стека.
3. **E2E тесты** - HTTP клиенты (`flows_client_http`) или Playwright (`tests/ui/e2e`).
4. **Параллельность** - тесты изолируются данными (`unique_id`) и test scope,
   а не последовательностью; никаких lock'ов и `xdist_group`.

## Troubleshooting

### Сервис не запущен

```bash
uv run python -m scripts.test_stack status
tail -f /tmp/platform_test_stack/<name>.err
make test-up
```

### Порт занят посторонним процессом

`make test-up` выполняет preflight-зачистку (`scripts/test_process_preflight_cleanup.py`).
