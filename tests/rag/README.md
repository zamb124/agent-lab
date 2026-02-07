# RAG Service Integration Tests

Полноценные интеграционные тесты для RAG Service без моков.

## Принципы

- **Без моков** (кроме LLM)
- **Реальный PostgreSQL + pgvector** на порту 5433
- **Реальный MinIO** на порту 9002
- **Централизованные фикстуры** в `tests/conftest.py`
- **Изоляция данных** через `unique_namespace_name`

## Структура

```
tests/rag/
├── __init__.py
├── test_providers_api.py       # 5 тестов API провайдеров
├── test_namespaces_api.py      # 8 тестов CRUD namespaces
├── test_documents_api.py       # 10 тестов загрузки/удаления документов
├── test_search_api.py          # 8 тестов семантического поиска
└── test_rag_integration.py     # 6 E2E тестов полных сценариев
```

**Итого: 37+ тестов**

## Фикстуры

### rag_app
FastAPI приложение RAG сервиса для тестов.

### rag_client
HTTP клиент для тестирования RAG API.

```python
async def test_providers(rag_client):
    response = await rag_client.get("/rag/api/v1/providers")
    assert response.status_code == 200
```

### rag_provider_pgvector
Реальный pgvector провайдер с автоматическим cleanup.

```python
async def test_provider(rag_provider_pgvector):
    # Проверка подключения к PostgreSQL + pgvector
    assert rag_provider_pgvector is not None
```

### unique_namespace_name
Уникальное имя namespace для изоляции тестов.

```python
def test_namespace(rag_client, unique_namespace_name):
    # unique_namespace_name = "test_namespace_{uuid}"
    pass
```

## Запуск тестов

### Все RAG тесты

```bash
make test-rag
```

Эта команда:
1. Поднимает docker-compose сервисы (postgres, redis, minio)
2. Ждет 5 секунд готовности сервисов
3. Запускает pytest для `tests/rag/`

### Отдельные тестовые файлы

```bash
# Тесты провайдеров
uv run pytest tests/rag/test_providers_api.py -v

# Тесты namespaces
uv run pytest tests/rag/test_namespaces_api.py -v

# Тесты документов
uv run pytest tests/rag/test_documents_api.py -v

# Тесты поиска
uv run pytest tests/rag/test_search_api.py -v

# E2E тесты
uv run pytest tests/rag/test_rag_integration.py -v
```

### Конкретный тест

```bash
uv run pytest tests/rag/test_providers_api.py::test_list_providers -v
```

## Покрытие тестами

### API Endpoints

- ✅ `GET /rag/api/v1/providers` - список провайдеров
- ✅ `POST /rag/api/v1/providers/switch` - переключение провайдера
- ✅ `GET /rag/api/v1/namespaces` - список namespaces
- ✅ `POST /rag/api/v1/namespaces` - создание namespace
- ✅ `DELETE /rag/api/v1/namespaces/{id}` - удаление namespace
- ✅ `GET /rag/api/v1/namespaces/{id}/documents` - список документов
- ✅ `POST /rag/api/v1/namespaces/{id}/documents` - загрузка документа
- ✅ `DELETE /rag/api/v1/namespaces/{id}/documents/{doc_id}` - удаление документа
- ✅ `POST /rag/api/v1/namespaces/{id}/search` - поиск в namespace
- ✅ `POST /rag/api/v1/search` - глобальный поиск

### E2E Сценарии

- ✅ Полный цикл: создание → загрузка → поиск → удаление
- ✅ Переключение провайдеров
- ✅ Изоляция данных между namespaces
- ✅ Обработка больших документов
- ✅ Параллельные операции
- ✅ Восстановление после ошибок

## Конфигурация

### Переменные окружения (tests/conftest.py)

```python
os.environ.setdefault("RAG__ENABLED", "true")
os.environ.setdefault("RAG__DEFAULT_PROVIDER", "pgvector")
os.environ.setdefault("RAG__PROVIDERS__PGVECTOR__ENABLED", "true")
os.environ.setdefault("RAG__PROVIDERS__PGVECTOR__HOST", "localhost")
os.environ.setdefault("RAG__PROVIDERS__PGVECTOR__PORT", "5433")
os.environ.setdefault("RAG__PROVIDERS__PGVECTOR__EMBEDDING_API_KEY", "sk-test-key")
```

### Docker Compose (docker-compose-test.yaml)

PostgreSQL + pgvector уже настроен:

```yaml
postgres-test:
  image: pgvector/pgvector:pg16
  ports:
    - "5433:5432"
  environment:
    - POSTGRES_USER=platform_user
    - POSTGRES_PASSWORD=admin
    - POSTGRES_DB=platform_test
```

## Примеры тестов

### Тест провайдеров

```python
@pytest.mark.asyncio
async def test_list_providers(rag_client):
    response = await rag_client.get("/rag/api/v1/providers")
    assert response.status_code == 200
    
    data = response.json()
    assert "providers" in data
    assert "current_provider" in data
```

### Тест создания namespace

```python
@pytest.mark.asyncio
async def test_create_namespace(rag_client, unique_namespace_name):
    response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name}
    )
    assert response.status_code == 200
    assert response.json()["name"] == unique_namespace_name
```

### Тест загрузки документа

```python
@pytest.mark.asyncio
async def test_upload_document(rag_client, unique_namespace_name):
    # Создаем namespace
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name}
    )
    namespace_id = ns_response.json()["namespace_id"]
    
    # Загружаем файл
    content = b"Test document content"
    files = {"file": ("test.txt", BytesIO(content), "text/plain")}
    
    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files
    )
    assert response.status_code == 200
```

### Тест поиска

```python
@pytest.mark.asyncio
async def test_search_documents(rag_client, unique_namespace_name):
    # Создаем namespace и загружаем документ
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name}
    )
    namespace_id = ns_response.json()["namespace_id"]
    
    content = b"Python is a programming language"
    files = {"file": ("python.txt", BytesIO(content), "text/plain")}
    await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files
    )
    
    # Поиск
    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/search",
        json={"query": "What is Python?", "limit": 5}
    )
    assert response.status_code == 200
    assert len(response.json()["results"]) > 0
```

## Troubleshooting

### PostgreSQL + pgvector не запускается

```bash
# Проверяем статус
docker-compose -f docker-compose-test.yaml ps postgres-test

# Логи
docker-compose -f docker-compose-test.yaml logs postgres-test

# Перезапуск
docker-compose -f docker-compose-test.yaml restart postgres-test
```

### Тесты падают с connection error

Убедитесь что сервисы запущены:

```bash
docker-compose -f docker-compose-test.yaml up -d postgres-test redis-test minio-test
```

Подождите несколько секунд для healthcheck.

### Cleanup не работает

Фикстура `rag_provider_pgvector` автоматически удаляет тестовые данные. Если нужно очистить вручную:

```bash
# Перезапуск PostgreSQL удалит все данные
docker-compose -f docker-compose-test.yaml restart postgres-test
```

## CI/CD

Тесты готовы для CI:

```yaml
# .github/workflows/test.yml (example)
- name: Run RAG tests
  run: make test-rag
```

## Расширение

### Добавление нового теста

1. Выберите подходящий файл (`test_*_api.py` или `test_rag_integration.py`)
2. Создайте функцию с префиксом `test_` и маркером `@pytest.mark.asyncio`
3. Используйте фикстуры `rag_client` и `unique_namespace_name`
4. Запустите тест: `uv run pytest tests/rag/test_your_file.py::test_your_function -v`

### Добавление новой фикстуры

Все фикстуры добавляются **централизованно** в `tests/conftest.py`:

```python
@pytest.fixture
def my_rag_fixture():
    # Setup
    yield value
    # Teardown
```

## Статистика

- **37+ тестов**
- **5 файлов**
- **10 API endpoints покрыты**
- **0 моков** (кроме LLM)
- **100% интеграционные тесты**

## Поддержка

При проблемах проверьте:
1. PostgreSQL запущен: `docker ps | grep postgres-test`
2. Порт 5433 свободен: `lsof -i :5433`
3. Логи сервиса: `docker-compose -f docker-compose-test.yaml logs postgres-test`

